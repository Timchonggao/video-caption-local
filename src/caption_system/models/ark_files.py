"""Ark file upload, durable identity and bounded status polling; no retries."""
import hashlib
import io
import json
import math
import re
import time
import uuid
from pathlib import Path
from urllib.parse import quote

import requests

from caption_system.models.api import RequestFailure
from caption_system.results.atomic import atomic_json

BASE_URL = 'https://ark.cn-beijing.volces.com/api/v3'
MAX_FILE_BYTES = 512_000_000


def video_preprocess(fps, min_frame_tokens=None, max_frame_tokens=None, max_video_tokens=None):
    if not math.isfinite(fps) or not 0.2 <= fps <= 5:
        raise ValueError('Ark video FPS must be within 0.2–5')
    values = {'min_frame_tokens': min_frame_tokens, 'max_frame_tokens': max_frame_tokens,
              'max_video_tokens': max_video_tokens}
    for name, value in values.items():
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1):
            raise ValueError(name + ' must be a positive integer or omitted')
    # Verified on the current Files upload route, 2026-10-07. These are file
    # preprocessing limits, not the native video's per-frame strategy table.
    if min_frame_tokens is not None and not 16 <= min_frame_tokens <= 128:
        raise ValueError('Files API min_frame_tokens must be within 16–128')
    if max_frame_tokens is not None and not 128 <= max_frame_tokens <= 640:
        raise ValueError('Files API max_frame_tokens must be within 128–640')
    if min_frame_tokens is not None and max_frame_tokens is not None and min_frame_tokens > max_frame_tokens:
        raise ValueError('min_frame_tokens exceeds max_frame_tokens')
    if max_frame_tokens is not None and max_video_tokens is not None and max_frame_tokens > max_video_tokens:
        raise ValueError('max_frame_tokens exceeds max_video_tokens')
    # The complete total-video budget range has not been probed; Ark validates it.
    return {'video': {'fps': fps, **{k: v for k, v in values.items() if v is not None}}}


class MultipartFile:
    """Stream multipart fields and one MP4 without buffering the whole video."""
    def __init__(self, handle, size, fields):
        self.boundary = 'caption-' + uuid.uuid4().hex
        prefix = b''
        for name, value in fields.items():
            prefix += (f'--{self.boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
                       f'{value}\r\n').encode()
        prefix += (f'--{self.boundary}\r\nContent-Disposition: form-data; name="file"; filename="source_clip.mp4"'
                   '\r\nContent-Type: video/mp4\r\n\r\n').encode()
        suffix = f'\r\n--{self.boundary}--\r\n'.encode()
        self.parts = [io.BytesIO(prefix), handle, io.BytesIO(suffix)]
        self.index = 0
        self.size = len(prefix) + size + len(suffix)

    def __len__(self):
        return self.size

    def read(self, size=-1):
        result = []
        remaining = size
        while self.index < len(self.parts) and (size < 0 or remaining > 0):
            chunk = self.parts[self.index].read(-1 if size < 0 else remaining)
            if not chunk:
                self.index += 1
                continue
            result.append(chunk)
            if size >= 0:
                remaining -= len(chunk)
        return b''.join(result)


class FileFailure(RequestFailure):
    def __init__(self, message, state, metadata):
        super().__init__(message, state)
        # finally blocks fill timings before the runner records this failure.
        self.result_metadata = metadata


class ArkFiles:
    def __init__(self, key, processing_timeout=300, poll_interval=2, expire_days=7,
                 retry_unknown=False, clock=time.monotonic, sleep=time.sleep):
        if not math.isfinite(processing_timeout) or processing_timeout <= 0:
            raise ValueError('File processing timeout must be positive')
        if not math.isfinite(poll_interval) or poll_interval <= 0:
            raise ValueError('File polling interval must be positive')
        if isinstance(expire_days, bool) or not isinstance(expire_days, int) or not 1 <= expire_days <= 30:
            raise ValueError('Ark file expiry must be 1–30 days')
        self.key = key
        self.processing_timeout = processing_timeout
        self.poll_interval = poll_interval
        self.expire_days = expire_days
        self.retry_unknown = retry_unknown
        self.clock = clock
        self.sleep = sleep

    def _json(self, response, action):
        try:
            value = response.json()
        except (ValueError, TypeError):
            raise RequestFailure(f'Ark {action} returned invalid JSON') from None
        if not response.ok:
            error = (value.get('error') or {}) if isinstance(value, dict) else {}
            if not isinstance(error, dict):
                error = {}
            detail = str(error.get('code', '')) + ': ' + str(error.get('message', ''))
            if self.key:
                detail = detail.replace(self.key, '[REDACTED]')
            raise RequestFailure(f'Ark {action} HTTP {response.status_code}; {detail[:1000]}')
        if not isinstance(value, dict):
            raise RequestFailure(f'Ark {action} returned invalid file metadata')
        return value

    def ensure_ready(self, video, digest, preprocess, cache):
        video, cache = Path(video), Path(cache)
        metadata = {'provider_transport': 'files', 'model_call_attempted': False,
                    'file_upload_seconds': 0.0, 'file_processing_seconds': 0.0,
                    'requested_preprocessing': preprocess}
        if not self.key:
            raise FileFailure('Configure API credentials on server', 'file_upload_failed', metadata)
        if video.stat().st_size > MAX_FILE_BYTES:
            raise FileFailure('Video exceeds the Files API 512 MB project limit', 'file_upload_failed', metadata)
        identity = hashlib.sha256(json.dumps({'video_sha256': digest, 'preprocess': preprocess,
                    'endpoint': BASE_URL}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        state = json.loads(cache.read_text()) if cache.exists() else {}
        if state and state.get('identity') != identity:
            raise FileFailure('Cached file input/preprocessing differs; choose a new run', 'file_identity_failed', metadata)

        def save(phase, value=None):
            state.update(identity=identity, phase=phase, requested_preprocessing=preprocess,
                         video_sha256=digest, updated_at=int(time.time()))
            if value is not None:
                state['file'] = {**state.get('file', {}), **{k: value[k] for k in
                    ('id', 'status', 'created_at', 'expire_at', 'bytes', 'mime_type', 'preprocess_configs') if k in value}}
            atomic_json(cache, state)

        def record_file(value, phase):
            file_id = value.get('id')
            if not isinstance(file_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', file_id):
                raise RequestFailure('Ark returned invalid file identity')
            if state.get('file', {}).get('id') and state['file']['id'] != file_id:
                raise RequestFailure('Ark retrieval returned another file identity')
            save(phase, value)
            if value.get('status') == 'failed':
                error = value.get('error') or {}
                detail = json.dumps(error, ensure_ascii=False).replace(self.key, '[REDACTED]')[:1000]
                state['file']['error'] = detail
                atomic_json(cache, state)
            metadata['remote_file'] = dict(state['file'])

        headers = {'Authorization': 'Bearer ' + self.key}
        cached = state.get('file', {})
        metadata['file_reused'] = bool(cached.get('id'))
        if cached.get('id'):
            metadata['remote_file'] = dict(cached)
        if not cached.get('id'):
            if state.get('phase') in ('uploading', 'unknown_upload_outcome') and not self.retry_unknown:
                raise FileFailure('Previous upload outcome unknown; acknowledge with --retry-unknown before resubmitting',
                                  'unknown_remote_outcome', metadata)
            fields = {'purpose': 'user_data', 'expire_at': int(time.time()) + self.expire_days * 86400,
                      **{f'preprocess_configs[video][{k}]': v for k, v in preprocess['video'].items()}}
            save('uploading')
            started = self.clock()
            try:
                with video.open('rb') as handle:
                    body = MultipartFile(handle, video.stat().st_size, fields)
                    response = requests.post(BASE_URL + '/files', data=body,
                        headers={**headers, 'Content-Type': 'multipart/form-data; boundary=' + body.boundary,
                                 'Content-Length': str(len(body))}, timeout=(30, 300))
                value = self._json(response, 'file upload')
                record_file(value, 'uploaded')
            except requests.RequestException:
                save('unknown_upload_outcome')
                raise FileFailure('File upload outcome unknown; no automatic retry', 'unknown_remote_outcome', metadata) from None
            except RequestFailure as error:
                # Missing/invalid success metadata can hide an accepted upload.
                phase = 'upload_failed' if ' HTTP ' in str(error) else 'unknown_upload_outcome'
                save(phase)
                raise FileFailure(str(error), 'file_upload_failed' if phase == 'upload_failed' else 'unknown_remote_outcome', metadata) from None
            finally:
                metadata['file_upload_seconds'] = self.clock() - started
        else:
            expiry = cached.get('expire_at')
            if isinstance(expiry, (int, float)) and expiry <= time.time():
                save('expired')
                raise FileFailure('Cached Ark file expired; choose a new run to upload again', 'file_unavailable', metadata)
            # Retrieve even an active cached file; it could have expired or been deleted.
            state['file']['status'] = 'processing'

        started = self.clock()
        deadline = started + self.processing_timeout
        try:
            while True:
                value = state['file']
                status = value.get('status')
                if status == 'active':
                    expiry = value.get('expire_at')
                    if isinstance(expiry, (int, float)) and expiry <= time.time():
                        save('expired')
                        raise FileFailure('Ark file expired before caption submission', 'file_unavailable', metadata)
                    returned = (value.get('preprocess_configs') or {}).get('video') or {}
                    mismatched = [k for k, v in preprocess['video'].items() if k in returned and returned[k] != v]
                    if mismatched:
                        raise FileFailure('Ark preprocessing echo differs: ' + ','.join(mismatched), 'file_preprocessing_mismatch', metadata)
                    metadata['preprocessing_echo_verified'] = all(k in returned for k in preprocess['video'])
                    save('active')
                    metadata['remote_file'] = dict(state['file'])
                    return value['id'], metadata
                if status == 'failed':
                    save('failed')
                    detail = value.get('error', '')
                    raise FileFailure('Ark file preprocessing failed; caption was not requested: ' + str(detail), 'file_preprocessing_failed', metadata)
                if status != 'processing':
                    raise FileFailure('Unknown Ark file status: ' + str(status), 'file_status_failed', metadata)
                remaining = deadline - self.clock()
                if remaining <= 0:
                    save('processing')
                    raise FileFailure('File preprocessing wait timed out; retained file_id can resume without reupload',
                                      'file_processing_timeout', metadata)
                try:
                    response = requests.get(BASE_URL + '/files/' + quote(value['id'], safe=''),
                                            headers=headers, timeout=(min(15, remaining), min(30, remaining)))
                    if response.status_code == 404:
                        save('unavailable')
                        raise FileFailure('Ark file was deleted or expired; choose a new run to upload again', 'file_unavailable', metadata)
                    value = self._json(response, 'file retrieval')
                    record_file(value, value.get('status', 'unknown'))
                except requests.RequestException:
                    raise FileFailure('Ark file status request failed; retained file_id can resume', 'file_status_failed', metadata) from None
                except FileFailure:
                    raise
                except RequestFailure as error:
                    raise FileFailure(str(error), 'file_status_failed', metadata) from None
                if value.get('status') == 'processing':
                    self.sleep(min(self.poll_interval, max(0, deadline - self.clock())))
        finally:
            metadata['file_processing_seconds'] = self.clock() - started
