"""Export only decoded frames inside an original interval, retaining source PTS."""
from fractions import Fraction
from pathlib import Path
import av
from caption_system.results.store import sha


def export_subsegment(task, path):
    start, end = float(task['clip_start_time_s']), float(task['clip_end_time_s'])
    offset = float(task.get('video_timestamp_offset_s', 0))
    if end <= start:
        raise ValueError('Invalid video interval')
    path = Path(path)
    points=[]
    with av.open(task['media_path']) as source, av.open(str(path),'w',options={'movie_timescale':'1000000'}) as output:
        source_stream=source.streams.video[0]
        source_stream.codec_context.thread_count=1
        source.seek(int((start-offset)/float(source_stream.time_base)),stream=source_stream,backward=True,any_frame=False)
        stream=output.add_stream('libx264',rate=source_stream.average_rate or 30)
        stream.width=source_stream.width;stream.height=source_stream.height
        stream.pix_fmt='yuv420p'
        stream.codec_context.time_base=Fraction(1,1000000)
        stream.options={'crf':'18','preset':'veryfast'}
        for frame in source.decode(source_stream):
            if frame.pts is None:continue
            source_time=float(frame.pts*frame.time_base)+offset
            if source_time<start:continue
            if source_time>=end:break
            pts=frame.pts;time_base=str(frame.time_base)
            frame.pts=round((source_time-start)*1000000);frame.time_base=Fraction(1,1000000)
            for packet in stream.encode(frame):output.mux(packet)
            points.append({'source_pts':pts,'source_time_base':time_base,'source_time_s':source_time,'export_time_s':source_time-start})
        for packet in stream.encode():output.mux(packet)
    if not points:
        raise ValueError('No decoded frames in original video interval')
    with av.open(str(path)) as video:
        if len(video.streams.audio):raise ValueError('Export unexpectedly contains audio')
        encoded=[float(f.pts*f.time_base) for f in video.decode(video.streams.video[0]) if f.pts is not None]
    if len(encoded)!=len(points) or any(abs(t-p['export_time_s'])>0.0001 for t,p in zip(encoded,points)):
        raise ValueError('Export changed source frame timing')
    return {'sha256':sha(path),'bytes':path.stat().st_size,'source_interval_s':[start,end],
        'source_dimensions':[stream.width,stream.height],'source_frame_count':len(points),'audio':False,
        'encoding':{'codec':'h264','crf':18,'preset':'veryfast','movie_timescale':1000000},'frames':points,'encoded_times_s':encoded}
