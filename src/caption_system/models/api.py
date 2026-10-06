import base64, io, math, json
from pathlib import Path
from caption_system.results.store import sha
from caption_system.results.atomic import atomic_json

class RequestFailure(RuntimeError):
    def __init__(self, message, state='request_failed'):
        super().__init__(message)
        self.execution_status = state

def image_bytes(image, max_pixels):
    if image.width * image.height > max_pixels:
        scale = math.sqrt(max_pixels / (image.width * image.height))
        image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))))
    out = io.BytesIO()
    image.save(out, format='JPEG', quality=95)
    return (base64.b64encode(out.getvalue()).decode(), [image.width, image.height])

def payload(provider, model, prompt, frames, times, max_pixels, max_tokens):
    parts = [{'text': prompt}]
    content = [{'type': 'text', 'text': prompt}]
    sizes = []
    for image, t in zip(frames, times):
        data, size = image_bytes(image, max_pixels)
        sizes.append(size)
        parts.extend([{'text': f'Frame at {t:.6f} seconds:'}, {'inline_data': {'mime_type': 'image/jpeg', 'data': data}}])
        content.extend([{'type': 'text', 'text': f'Frame at {t:.6f} seconds:'}, {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + data}}])
    if provider == 'gemini':
        return ({'contents': [{'role': 'user', 'parts': parts}], 'generationConfig': {'temperature': 0, 'maxOutputTokens': max_tokens, 'responseMimeType': 'application/json'}}, sizes)
    return ({'model': model, 'messages': [{'role': 'user', 'content': content}], 'max_tokens': max_tokens, 'stream': False}, sizes)

def parse(provider, value):
    if provider == 'gemini':
        text = ''.join((p.get('text', '') for p in value['candidates'][0]['content']['parts'] if not p.get('thought')))
        return (text, value.get('usageMetadata', {}))
    return (value['choices'][0]['message']['content'], value.get('usage', {}))

class Api:

    def __init__(self, provider, model, max_pixels, max_tokens):
        import os
        self.provider = provider
        self.model = model
        self.max_pixels = max_pixels
        self.max_tokens = max_tokens
        self.key = os.environ.get('GEMINI_API_KEY' if provider == 'gemini' else 'ARK_API_KEY')
        self.runtime = {'provider': provider, 'model': model, 'live_endpoint_verified': False}

    def prepare(self, prompt, frames, times, folder):
        body, sizes = payload(self.provider, self.model, prompt, frames, times, self.max_pixels, self.max_tokens)
        path = Path(folder) / 'request.json'
        size = len(json.dumps(body).encode())
        if size > self.max_request_bytes:
            raise ValueError('Request exceeds configured byte limit')
        atomic_json(path, body)
        return {'path': str(path), 'sha256': sha(path), 'image_count': len(frames),
                'image_sizes': sizes, 'request_bytes': size,
                'estimated_usage': None, 'estimate_note': 'Provider token/cost estimate unavailable; not zero'}

    max_request_bytes = 32 * 1024 * 1024

    def artifacts_valid(self, bundle):
        paths = [(bundle.get('request') or {}).get('path')]
        request = bundle.get('request')
        return bool(request and paths[0] and Path(paths[0]).is_file() and sha(paths[0]) == request['sha256'])

    def generate_prepared(self, request):
        if sha(request['path']) != request['sha256']:
            raise ValueError('Prepared request changed')
        return self._send(json.loads(Path(request['path']).read_text()), request['image_sizes'])

    def generate(self, prompt, frames, times):
        body, sizes = payload(self.provider, self.model, prompt, frames, times, self.max_pixels, self.max_tokens)
        return self._send(body, sizes)

    def _send(self, body, sizes):
        import requests, time
        from urllib.parse import quote
        if not self.key:
            raise RequestFailure('Configure API credentials on server')
        if self.provider == 'gemini':
            url = 'https://generativelanguage.googleapis.com/v1beta/models/' + quote(self.model, safe='') + ':generateContent'
            headers = {'x-goog-api-key': self.key}
        else:
            url = 'https://ark.cn-beijing.volces.com/api/v3/chat/completions'
            headers = {'Authorization': 'Bearer ' + self.key}
        start = time.perf_counter()
        try:
            response = requests.post(url, headers=headers, json=body, timeout=(30, 240))
        except requests.RequestException:
            raise RequestFailure('Provider request outcome unknown; no automatic retry', 'unknown_remote_outcome') from None
        if not response.ok:
            try:
                error=response.json().get('error',{})
                code=str(error.get('code',''))[:100]
                message=str(error.get('message',''))[:1000].replace(self.key,'[REDACTED]')
            except (ValueError,AttributeError):
                code=message=''
            raise RequestFailure(f'Provider HTTP {response.status_code}; {code}: {message}')
        value = response.json()
        self.runtime['live_endpoint_verified'] = True
        atomic_raw = value  # Responses are persisted by runner; request headers are never saved.
        try:
            raw, usage = parse(self.provider, value)
        except (KeyError, IndexError, TypeError):
            raw, usage = '', value.get('usageMetadata', value.get('usage'))
        finish = (value.get('candidates') or [{}])[0].get('finishReason') if self.provider == 'gemini' else (value.get('choices') or [{}])[0].get('finish_reason')
        return (raw, {'input_tokens': (usage or {}).get('prompt_tokens', (usage or {}).get('promptTokenCount')), 'generated_tokens': (usage or {}).get('completion_tokens', (usage or {}).get('candidatesTokenCount')), 'usage': usage, 'raw_response': atomic_raw, 'finish_reason': finish,
                      'generation_seconds': time.perf_counter() - start, 'sent_image_sizes': sizes, 'reported_model': value.get('modelVersion') or value.get('model'), 'request_id': response.headers.get('x-request-id')})
