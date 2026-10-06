import { useEffect, useState } from "react";
import { useDashboard } from "./hooks/useDashboard";
import { useAlignment } from "./hooks/useAlignment";
import { SampleSidebar } from "./components/SampleSidebar";
import { SourceAnnotation } from "./components/SourceAnnotation";
import { VideoGrid } from "./components/VideoGrid";
import { ClipStrip } from "./components/ClipStrip";
import {
  ModelComparison,
  normalizeSelection,
} from "./components/ModelComparison";
import { ReviewPanel } from "./components/ReviewPanel";
import { domainLabels } from "./types";
import { availableClipIds } from "./resultAvailability";
export function App() {
  const [selected, setSelectedState] = useState(
      new URLSearchParams(location.search).get("clip") || "",
    ),
    [prompt, setPrompt] = useState(
      normalizeSelection(new URLSearchParams(location.search).get("prompt")),
    );
  const [expandedVideos, setExpandedVideos] = useState(false);
  const [modelKey, setModelKey] = useState("qwen"),
    [selectedRun, setSelectedRun] = useState(""),
    [onlyResults, setOnlyResults] = useState(false);
  const setSelected = (id: string) => { setExpandedVideos(false); setSelectedState(id); };
  const [domain, setDomain] = useState(""),
    [scenario, setScenario] = useState(""),
    [search, setSearch] = useState(""),
    [collapsed, setCollapsed] = useState(
      localStorage.getItem("sidebarCollapsed") !== "false",
    ),
    [reviewCamera, setReviewCamera] = useState("camera0"),
    [reviewRun, setReviewRun] = useState(""),
    [target, setTarget] = useState("original");
  const { data, inventory, error, reload } = useDashboard(
    selected.split("_seg")[0] || undefined,
  );
  const clips = data?.clips || [],
    promptKey = prompt.split(".")[0],
    camera = prompt.split(".")[1],
    promptId = data?.presentation?.fixed_prompt_id || (promptKey === "v1" ? "baseline-v1" : promptKey === "v2" ? "baseline-v2" : promptKey),
    available = data ? availableClipIds(data, modelKey, promptId, camera, selectedRun) : new Set<string>(),
    filtered = clips.filter(
      (c) =>
        (!domain || c.domain === domain) &&
        (!scenario || c.scenario === scenario) &&
        (!search ||
          `${c.clip_id} ${c.bold_mark} ${c.subtask_label}`
            .toLowerCase()
            .includes(search.toLowerCase())),
    ),
    clip = filtered.find((c) => c.clip_id === selected);
  useEffect(() => {
    if (filtered.length && !clip) {
      setSelected(filtered[0].clip_id);
    } else if (onlyResults && clip && !available.has(selected)) {
      const first = filtered.find(c => c.sample_id === clip.sample_id && available.has(c.clip_id));
      if (first) setSelected(first.clip_id);
    }
  }, [data, domain, scenario, search, onlyResults, modelKey, selectedRun, prompt, selected]);
  useEffect(() => {
    const u = new URL(location.href);
    u.searchParams.set("clip", selected);
    u.searchParams.set("prompt", prompt);
    u.searchParams.set("version", "mcap-v2");
    history.replaceState(null, "", u);
  }, [selected, prompt]);
  useEffect(() => {
    const pop = () => {
      const q = new URLSearchParams(location.search);
      setSelected(q.get("clip") || "");
      setPrompt(normalizeSelection(q.get("prompt")));
    };
    addEventListener("popstate", pop);
    return () => removeEventListener("popstate", pop);
  }, []);
  useEffect(() => {
    setReviewCamera(prompt.split(".")[1]);
    setReviewRun("");
    setTarget("original");
  }, [prompt, selected]);
  useAlignment([data, selected, inventory, collapsed, prompt, expandedVideos]);
  const domains = [...new Set(clips.map((c) => c.domain))],
    scenarios = [
      ...new Set(
        clips
          .filter((c) => !domain || c.domain === domain)
          .map((c) => c.scenario),
      ),
    ];
  return (
    <>
      {error && (
        <p role="alert">
          {error}
          <button onClick={reload}>重试</button>
        </p>
      )}
      <section className="toolbar">
        <label>
          领域
          <select
            value={domain}
            onChange={(e) => {
              setDomain(e.target.value);
              setScenario("");
            }}
          >
            <option value="">全部领域</option>
            {domains.map((d) => (
              <option key={d} value={d}>
                {domainLabels[d] || d}
              </option>
            ))}
          </select>
        </label>
        <label>
          场景
          <select
            value={scenario}
            onChange={(e) => setScenario(e.target.value)}
          >
            <option value="">全部场景</option>
            {scenarios.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
        <label className="search">
          搜索
          <input
            placeholder="搜索样本描述或片段编号…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
      </section>
      <main className={[collapsed ? "sidebar-collapsed" : "", !expandedVideos ? "single-camera" : ""].filter(Boolean).join(" ")}>
        <SampleSidebar
          clips={filtered}
          current={clip?.sample_id}
          collapsed={collapsed}
          toggle={() =>
            setCollapsed((v) => {
              localStorage.setItem("sidebarCollapsed", String(!v));
              return !v;
            })
          }
          select={setSelected}
        />
        <section className="viewer">
          {clip ? (
            <>
              <div className="video-and-strip">
                <VideoGrid clip={clip} inventory={inventory}
                  expanded={expandedVideos} setExpanded={setExpandedVideos} />
                <ClipStrip
                  clips={filtered.filter((c) => c.sample_id === clip.sample_id)}
                  selected={selected}
                  select={setSelected}
                  available={available}
                  onlyResults={onlyResults}
                  setOnlyResults={setOnlyResults}
                />
              </div>
              <SourceAnnotation key={clip.sample_id} sample={clip.sample_id} />
            </>
          ) : (
            <p>{data ? "没有匹配片段，请调整筛选。" : "正在加载数据…"}</p>
          )}
        </section>
        <section className="comparison">
          {data && clip && (
            <>
              <details className="annotation sample-reference">
                <summary>raw caption</summary>
                <h2>整体 caption</h2>
                <p>{clip.bold_mark}</p>
                <h2>片段caption</h2>
                <p>{clip.subtask_label}</p>
              </details>
              <ModelComparison
                data={data}
                clip={clip}
                prompt={prompt}
                change={setPrompt}
                review={(camera, run) => {
                  setReviewCamera(camera);
                  setReviewRun(run);
                  setTarget("model");
                  const panel =
                    document.querySelector<HTMLDetailsElement>(
                      ".review-collapse",
                    );
                  if (panel) panel.open = true;
                }}
                modelKey={modelKey}
                selectModel={setModelKey}
                selectedRun={selectedRun}
                selectRun={setSelectedRun}
              />
              <ReviewPanel
                data={data}
                clip={clip}
                camera={reviewCamera}
                setCamera={setReviewCamera}
                run={reviewRun}
                setRun={setReviewRun}
                target={target}
                setTarget={setTarget}
                reload={reload}
              />
            </>
          )}
        </section>
      </main>
    </>
  );
}
