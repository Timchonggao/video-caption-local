import { useEffect, useRef, useState } from "react";
import type { Clip, Inventory } from "../types";

export function VideoGrid({clip, inventory, expanded, setExpanded}: {
  clip: Clip;
  inventory: Inventory | null;
  expanded: boolean;
  setExpanded: (expanded: boolean) => void;
}) {
  const grid = useRef<HTMLDivElement>(null);
  const master = useRef<HTMLVideoElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState("");
  const cameras = (inventory?.media || [])
    .filter(m => m.kind === "video")
    .sort((a,b) => Number(a.camera.slice(6)) - Number(b.camera.slice(6)));
  const visible = expanded ? cameras : cameras.filter(m => m.camera === "camera2");
  const masterMedia = cameras.find(m => m.camera === "camera2");
  const sourceTime = () => master.current
    ? master.current.currentTime + (masterMedia?.source_to_video_offset_s || 0)
    : clip.clip_start_time_s;

  useEffect(() => {setPlaying(false); setError("");}, [clip.clip_id]);
  useEffect(() => {
    const videos = Array.from(grid.current?.querySelectorAll("video") || []);
    const sync = () => setPlaying(videos.some(v => !v.paused && !v.ended));
    sync();
    videos.forEach(v => {
      v.addEventListener("play",sync); v.addEventListener("pause",sync); v.addEventListener("ended",sync);
    });
    return () => videos.forEach(v => {
      v.removeEventListener("play",sync); v.removeEventListener("pause",sync); v.removeEventListener("ended",sync);
      // Removed views must release media connections and decoders. The retained
      // camera2 element stays connected when toggling layouts, so keep its time.
      if (!v.isConnected) {
        v.pause();
        v.removeAttribute("src");
        v.load();
      }
    });
  }, [clip.clip_id, inventory, expanded]);

  function changeMode() {
    // camera2 keeps its keyed DOM node and currentTime in both layouts.
    if (expanded) grid.current?.querySelectorAll<HTMLVideoElement>('video[data-camera]:not([data-camera="camera2"])').forEach(v => v.pause());
    setExpanded(!expanded);
    setError("");
  }
  async function toggle() {
    const videos = Array.from(grid.current?.querySelectorAll("video") || []);
    if(videos.some(v => !v.paused && !v.ended)) {videos.forEach(v => v.pause()); return;}
    const outcomes = await Promise.allSettled(videos.map(v => v.play()));
    if(outcomes.some(r=>r.status==="rejected")) {
      videos.forEach(v=>v.pause());setError("部分视频无法播放，请重试。");
    } else setError("");
  }
  return <>
    <div className="video-toolbar">
      <span>{expanded ? "六路相机 · camera2 为主视角" : "camera2"}</span>
      <button aria-expanded={expanded} aria-controls="camera-videos" onClick={changeMode} disabled={!cameras.length}>
        {expanded ? "收起其他相机" : "展开全部相机"}
      </button>
    </div>
    <div ref={grid} id="camera-videos" className={`video-shell ${expanded ? "six-camera-grid" : "single-camera-grid"}`}>
      {visible.map(m => {
        const offset=m.source_to_video_offset_s || 0;
        const from=Math.max(clip.clip_start_time_s,m.first_available_time_s)-offset;
        const to=Math.min(clip.clip_end_time_s,m.last_available_time_s+1/30)-offset;
        return <article className={`camera-tile${m.camera==="camera2" ? " selected-camera" : ""}`} key={m.id}>
          <h2 className="camera-title">{m.camera}</h2>
          <video key={`${clip.clip_id}/${m.id}`} controls playsInline preload="metadata"
            data-camera={m.camera} ref={m.camera==="camera2" ? master : undefined}
            src={`/api/media/${m.id}#t=${from},${to}`}
            onLoadedMetadata={e=>{
              const video=e.currentTarget;
              // Newly mounted auxiliary views follow the current source time,
              // including camera-specific offsets and available-time bounds.
              video.currentTime=m.camera==="camera2" ? from : Math.min(to,Math.max(from,sourceTime()-offset));
              if(m.camera!=="camera2" && master.current && !master.current.paused && !master.current.ended && video.currentTime<to) {
                void video.play().catch(()=>setError(`${m.camera} 无法同步播放，请重试。`));
              }
            }}
            onSeeking={e=>{
              if(e.currentTarget.currentTime<from)e.currentTarget.currentTime=from;
              if(e.currentTarget.currentTime>to)e.currentTarget.currentTime=to;
            }}
            onPlay={e=>{
              if(e.currentTarget.currentTime<from || e.currentTarget.currentTime>=to)e.currentTarget.currentTime=from;
            }}
            onTimeUpdate={e=>{if(e.currentTarget.currentTime>=to)e.currentTarget.pause();}}
            onError={()=>setError(`${m.camera} 视频读取失败`)}
          />
        </article>;
      })}
    </div>
    {!visible.length && inventory && <p className="video-error">此样本暂无 camera2 视频。</p>}
    {error && <p className="video-error" role="alert">{error}</p>}
    <button className="all-playback" id="all-playback" aria-label={expanded ? (playing ? "暂停全部视频" : "播放全部视频") : (playing ? "暂停视频" : "播放视频")}
      onClick={toggle} disabled={!visible.length}>{playing ? "Ⅱ 暂停" : "▶ 播放"}</button>
  </>;
}
