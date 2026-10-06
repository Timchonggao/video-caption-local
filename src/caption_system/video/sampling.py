import av, numpy as np

def sample_evidence(task, n, max_deviation_s=None, fps=None):
    """Nearest decoded legal frame per request; retain actual PTS and mapping.

    Forward decoding uses bounded memory (previous frame and selected frames).
    Half-open source bounds apply even when the first frame is missing.
    """
    if n < 1:
        raise ValueError('Frame count must be positive')
    start, end = float(task['clip_start_time_s']), float(task['clip_end_time_s'])
    offset = float(task.get('video_timestamp_offset_s', 0))
    if end <= start:
        raise ValueError('Invalid original interval')
    if fps is not None and fps <= 0:
        raise ValueError('FPS must be positive')
    targets = ([start + i / fps for i in range(int(np.ceil((end-start)*fps))) if start+i/fps < end]
               if fps is not None else np.linspace(start, end, n, endpoint=False).tolist())
    n = len(targets)
    selected, metadata = [], []
    index, previous = 0, None

    def keep(frame, source_time, requested):
        deviation = source_time - requested
        if max_deviation_s is not None and abs(deviation) > max_deviation_s:
            raise ValueError('No legal frame within configured sampling deviation')
        selected.append(frame.to_image())
        metadata.append({'requested_source_time_s': requested,
                         'requested_relative_time_s': requested - start,
                         'pts': frame.pts, 'time_base': str(frame.time_base),
                         'media_time_s': float(frame.pts * frame.time_base),
                         'source_time_s': source_time, 'relative_time_s': source_time - start,
                         'deviation_s': deviation, 'size': [frame.width, frame.height],
                         'duplicate_of': next((i for i, m in enumerate(metadata) if m['pts'] == frame.pts), None)})
    with av.open(str(task['media_path'])) as container:
        stream = container.streams.video[0]
        stream.codec_context.thread_count = 1
        # Seek backward in this stream's units, then decode forward.
        container.seek(int((start - offset) / float(stream.time_base)), stream=stream,
                       backward=True, any_frame=False)
        for frame in container.decode(stream):
            if frame.pts is None:
                continue
            source_time = float(frame.pts * frame.time_base) + offset
            if source_time < start:
                continue
            if source_time >= end:
                break
            while index < n and targets[index] <= source_time:
                chosen = (frame, source_time)
                if previous and abs(previous[1] - targets[index]) <= abs(source_time - targets[index]):
                    chosen = previous
                keep(*chosen, targets[index])
                index += 1
            previous = (frame, source_time)
            if index == n:
                break
        if previous:
            while index < n:
                keep(*previous, targets[index])
                index += 1
    if not selected:
        raise ValueError('No decoded frames inside original subsegment')
    if fps is not None:
        unique = [(f, m) for f, m in zip(selected, metadata) if m['duplicate_of'] is None]
        selected, metadata = [x[0] for x in unique], [x[1] for x in unique]
    return selected, metadata

def sample(path, n, start=0.0, end=None):
    with av.open(str(path)) as c:
        stream = c.streams.video[0]
        total = (float(stream.start_time or 0) + float(stream.duration or 0)) * float(stream.time_base) if stream.duration else float(c.duration / 1000000)
        stop = total if end is None else float(end)
        duration = stop - start
        if duration <= 0:
            raise ValueError('Invalid sample interval')
        targets = np.linspace(start, max(start, stop - 0.001), n)
        frames = []
        times = []
        sizes = []
        next_index = 0
        last = None
        if start > 0:
            c.seek(int(max(0, start - 1) * 1000000), backward=True, any_frame=False)
        for f in c.decode(stream):
            t = float(f.pts * f.time_base)
            if t < start:
                continue
            if t >= stop:
                break
            last = (f, t)
            if next_index < len(targets) and t >= targets[next_index]:
                frames.append(f.to_image())
                times.append(t - start)
                sizes.append([f.width, f.height])
                while next_index < len(targets) and targets[next_index] <= t:
                    next_index += 1
        if last and (not times or abs(times[-1] - (last[1] - start)) > 1e-06) and (len(frames) < n):
            f, t = last
            frames.append(f.to_image())
            times.append(t - start)
            sizes.append([f.width, f.height])
        if not frames:
            raise ValueError('No decoded frames inside original subsegment')
    return (frames, times, sizes, duration)

def sample_task(task, n):
    offset = float(task.get('video_timestamp_offset_s', 0))
    start = float(task['clip_start_time_s'])
    end = float(task['clip_end_time_s'])
    return sample(task['media_path'], n, start - offset, end - offset)
