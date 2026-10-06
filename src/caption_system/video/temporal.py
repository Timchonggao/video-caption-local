"""Exact PTS grouping for the native video processor; no synthetic timing."""
import math


def temporal_evidence(times, group_size=2):
    if group_size < 1 or not times or any(not math.isfinite(t) or t < 0 for t in times):
        raise ValueError('Invalid video timestamps')
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError('Video timestamps must increase')
    padded = list(times)
    padding = -len(times) % group_size
    padded.extend([times[-1]] * padding)
    groups = []
    for start in range(0, len(padded), group_size):
        values = padded[start:start + group_size]
        # Match the processor's first/last-frame midpoint convention.
        midpoint = (values[0] + values[-1]) / 2
        groups.append({'frame_indices': [min(i, len(times)-1) for i in range(start, start+group_size)],
                       'relative_times_s': values, 'timestamp_s': midpoint,
                       'display_timestamp_s': float(f'{midpoint:.1f}')})
    return {'real_frame_count': len(times), 'encoded_frame_count': len(padded),
            'temporal_patch_size': group_size, 'padding_count': padding,
            'padding_source_index': len(times)-1 if padding else None,
            'groups': groups}
