"""One MCAP per sample: original subsegments, all cameras and all non-video messages."""
import argparse, av, hashlib, json, re, subprocess
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
from mcap.reader import make_reader
from mcap_protobuf.decoder import DecoderFactory
from google.protobuf.json_format import MessageToDict
from caption_system.config import PROJECT, PATHS
ROOT = PROJECT / 'metadata'

def compact(value):
    if isinstance(value, dict):
        return {k: compact(v) for k, v in value.items() if k not in ['audio_data', 'data']}
    if isinstance(value, list):
        return [compact(x) for x in value[:8]] + ([{'preview_omitted_items': len(value) - 8}] if len(value) > 8 else [])
    if isinstance(value, str) and len(value) > 1000:
        return value[:1000] + ' [preview truncated]'
    return value

def export_sample(sid, source, out):
    directory = out / sid
    directory.mkdir(parents=True, exist_ok=True)
    reportpath = directory / 'inventory.json'
    signature = {'source_size': source.stat().st_size, 'source_mtime_ns': source.stat().st_mtime_ns, 'exporter_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    if reportpath.exists():
        existing = json.loads(reportpath.read_text())
        if existing.get('signature') == signature and all(((directory / m['file']).is_file() for m in existing['media'])):
            return existing
    with source.open('rb') as f:
        reader = make_reader(f, decoder_factories=[DecoderFactory()])
        summary = reader.get_summary()
        annotations = []
        for _, ch, msg, proto in reader.iter_decoded_messages(topics=['/robot0/annotation_v2']):
            annotations.append(MessageToDict(proto, preserving_proto_field_name=True))
    if len(annotations) != 1:
        raise ValueError('Expected exactly one video annotation record per MCAP')
    annotation = annotations[0]
    origin = int(annotation['header']['timestamp'])
    cameras = {}
    stats = {}
    media = []
    validity = []
    invalid_frames = []
    framecounts = {'valid': 0, 'invalid': 0}
    for ch in summary.channels.values():
        schema = summary.schemas[ch.schema_id]
        stats[ch.topic] = {'topic': ch.topic, 'schema': schema.name, 'message_count': summary.statistics.channel_message_counts.get(ch.id, 0), 'first_time_s': None, 'last_time_s': None}
        if schema.name == 'foxglove.CompressedImage':
            name = re.search('camera\\d+', ch.topic).group()
            path = directory / (name + '.mp4')
            cameras[ch.topic] = {'name': name, 'path': path, 'container': None, 'stream': None, 'packets': 0, 'written': 0, 'skipped': [], 'decoder_errors': [], 'started': False, 'decoder': av.CodecContext.create('h264', 'r'), 'first_s': None, 'last_s': None}
    try:
        with source.open('rb') as f:
            reader = make_reader(f, decoder_factories=[DecoderFactory()])
            for schema, ch, msg, proto in reader.iter_decoded_messages():
                timestamp = int(proto.header.timestamp) if hasattr(proto, 'header') and proto.header.timestamp else msg.log_time
                t = (timestamp - origin) / 1000000000.0
                st = stats[ch.topic]
                if st['first_time_s'] is None:
                    st['first_time_s'] = t
                st['last_time_s'] = t
                if ch.topic in cameras:
                    cam = cameras[ch.topic]
                    cam['packets'] += 1
                    if proto.format.lower() != 'h264':
                        raise ValueError('Unsupported video format ' + proto.format)
                    types = [b[0] & 31 for b in re.split(b'\x00\x00\x01', proto.data) if b]
                    if not cam['started']:
                        try:
                            frames = cam['decoder'].decode(av.Packet(proto.data))
                        except av.error.InvalidDataError:
                            cam['decoder_errors'].append({'time_s': t, 'packet_index': cam['packets'] - 1})
                            frames = []
                        if 5 not in types:
                            cam['skipped'].append({'time_s': t, 'reason': 'before_first_IDR'})
                            continue
                        if not frames:
                            width, height = (cam['decoder'].width, cam['decoder'].height)
                        else:
                            width, height = (frames[0].width, frames[0].height)
                        if not width or not height:
                            raise ValueError('Cannot determine camera dimensions at first IDR')
                        cam['container'] = av.open(str(cam['path']), 'w', options={'movflags': '+faststart', 'video_track_timescale': '1000000'})
                        stream = cam['container'].add_stream('h264', rate=30)
                        stream.width = width
                        stream.height = height
                        stream.time_base = Fraction(1, 1000000)
                        cam.update(stream=stream, started=True, width=width, height=height, first_s=t)
                    packet = av.Packet(proto.data)
                    packet.pts = packet.dts = round(t * 1000000)
                    packet.time_base = Fraction(1, 1000000)
                    packet.stream = cam['stream']
                    packet.is_keyframe = 5 in types
                    cam['container'].mux(packet)
                    cam['written'] += 1
                    cam['last_s'] = t
                    continue
                value = MessageToDict(proto, preserving_proto_field_name=True)
                preview = compact(value)
                if 'first_message_preview' not in st:
                    st['first_message_preview'] = preview
                st['last_message_preview'] = preview
                if schema.name == 'foxglove.TimeRangeValidity':
                    validity.append(value)
                if schema.name == 'foxglove.FrameValidity':
                    framecounts['valid' if proto.is_valid else 'invalid'] += 1
                    if not proto.is_valid:
                        invalid_frames.append(value)
    finally:
        for cam in cameras.values():
            if cam['container']:
                cam['container'].close()
    for cam in cameras.values():
        if not cam['started']:
            raise ValueError('No playable IDR for ' + cam['name'])
        probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'stream=width,height,start_time,duration,nb_frames', '-of', 'json', str(cam['path'])]))['streams'][0]
        if abs(float(probe['start_time']) - cam['first_s']) > 0.002:
            raise ValueError('MP4 time origin changed')
        decode = subprocess.run(['ffmpeg', '-v', 'error', '-threads', '2', '-i', str(cam['path']), '-t', '3', '-f', 'null', '-'], capture_output=True, text=True)
        media.append({'id': sid + '_' + cam['name'], 'kind': 'video', 'camera': cam['name'], 'topic': next((t for t, v in cameras.items() if v is cam)), 'file': cam['path'].name, 'width': cam['width'], 'height': cam['height'], 'source_to_video_offset_s': cam['first_s'] - float(probe['start_time']), 'first_available_time_s': cam['first_s'], 'last_available_time_s': cam['last_s'], 'original_packets': cam['packets'], 'published_packets': cam['written'], 'skipped_head_packets': cam['skipped'], 'initial_decoder_errors': cam['decoder_errors'], 'probe': probe, 'first_3s_decode_ok': decode.returncode == 0 and (not decode.stderr), 'first_3s_decode_errors': decode.stderr[:1000]})
    report = {'sample_id': sid, 'signature': signature, 'source_annotation': annotations, 'timeline_origin': 'original annotation header.timestamp', 'origin_ns': str(origin), 'channels': list(stats.values()), 'time_range_validity': validity, 'frame_validity': {'counts': framecounts, 'invalid_records': invalid_frames}, 'media': media, 'policy': {'is_success': 'original annotation boolean; default false when absent in JSON', 'selection': 'all original sub_segments_info, including false; no extra split', 'H264': 'retain original bitstream from first IDR; report undecodable head and continue; no fake frames', 'validity': 'shown, not silently filtered'}}
    reportpath.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(sid, 'cameras', len(cameras), 'MiB', round(sum(((directory / m['file']).stat().st_size for m in media)) / 1024 ** 2, 1), flush=True)
    return report

def main():
    p = argparse.ArgumentParser()
    a = p.parse_args()
    out = Path(PATHS['media_root'])
    out.mkdir(parents=True, exist_ok=True)
    sources = {sid: Path(path) for sid, path in json.loads((ROOT / 'sources.json').read_text()).items()}
    reports = []
    manifest = []
    for sid, source in sorted(sources.items()):
        report = export_sample(sid, source, out)
        reports.append(report)
        (ROOT / 'annotations').mkdir(exist_ok=True)
        (ROOT / 'annotations' / (sid + '.json')).write_text(json.dumps(report['source_annotation'], ensure_ascii=False, indent=2) + '\n')
        annotation = report['source_annotation'][0]
        camera = next((m for m in report['media'] if m.get('camera') == 'camera0'))
        for segment_index, seg in enumerate(annotation['segments_info'], 1):
            for subtask_index, sub in enumerate(seg['sub_segments_info'], 1):
                start = sub.get('start_time_s', 0)
                end = sub.get('end_time_s', 0)
                cid = f'{sid}_seg{segment_index:02d}_sub{subtask_index:02d}'
                manifest.append({'clip_id': cid, 'sample_id': sid, 'source_subtask_id': cid, 'video_id': annotation['video_id'], 'bold_mark': annotation['bold_mark'], 'segment_label': seg.get('fine_label', ''), 'subtask_label': sub.get('fine_label', ''), 'fine_label_detail': sub.get('fine_label_detail', ''), 'segment_index': segment_index, 'subtask_index': subtask_index, 'original_segment_id': seg.get('segment_id', ''), 'original_subsegment_id': sub.get('segment_id', ''), 'clip_start_time_s': start, 'clip_end_time_s': end, 'clip_duration_s': end - start, 'part_index': 1, 'part_count': 1, 'original_is_success': sub.get('is_success', False), 'domain': source.resolve().relative_to(Path(PATHS['dataset_root']).resolve()).parts[0], 'scenario': source.resolve().relative_to(Path(PATHS['dataset_root']).resolve()).parts[1], 'default_media_id': camera['id'], 'mcap_path': str(source), 'video_timestamp_offset_s': camera.get('source_to_video_offset_s', 0), 'media_path': str(out / sid / camera['file'])})
    for row in manifest:
        for key in ['part_index', 'part_count', 'default_media_id', 'media_path', 'video_timestamp_offset_s']:
            row.pop(key, None)
    (ROOT / 'clips.jsonl').write_text(''.join((json.dumps(r, ensure_ascii=False) + '\n' for r in manifest)))
    (ROOT / 'samples.json').write_text(json.dumps(reports, ensure_ascii=False) + '\n')
    print('Complete samples', len(reports), 'original subsegments', len(manifest), flush=True)
if __name__ == '__main__':
    main()
