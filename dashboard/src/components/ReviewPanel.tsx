import { useEffect, useState } from "react";
import type { Data, Clip } from "../types";
import { saveReview } from "../api";
export function ReviewPanel({
  data,
  clip,
  camera,
  setCamera,
  run,
  setRun,
  target,
  setTarget,
  reload,
}: {
  data: Data;
  clip: Clip;
  camera: string;
  setCamera: (v: string) => void;
  run: string;
  setRun: (v: string) => void;
  target: string;
  setTarget: (v: string) => void;
  reload: () => Promise<void>;
}) {
  const [reviewer, setReviewer] = useState(
      localStorage.getItem("reviewer") || "",
    ),
    [clarity, setClarity] = useState(""),
    [objectAccuracy, setObjectAccuracy] = useState(""),
    [directionAccuracy, setDirectionAccuracy] = useState(""),
    [outcomeAccuracy, setOutcomeAccuracy] = useState(""),
    [accuracy, setAccuracy] = useState(""),
    [omission, setOmission] = useState(""),
    [notes, setNotes] = useState(""),
    [message, setMessage] = useState(""),
    [saving, setSaving] = useState(false);
  const detailed = target === "model" && data.review_features?.includes("quality_dimensions");
  const task_id = `${clip.clip_id}__${camera}`,
    successful = data.runs.filter((r) =>
      data.results.some(
        (x) =>
          x.task_id === task_id &&
          x.run_id === r.id &&
          x.caption_status === "success",
      ),
    );
  useEffect(() => {
    setClarity("");
    setObjectAccuracy("");
    setDirectionAccuracy("");
    setOutcomeAccuracy("");
    setAccuracy("");
    setOmission("");
    setNotes("");
    setMessage("");
  }, [task_id, run, target]);
  const count = data.reviews
    .filter(
      (r) =>
        r.task_id === task_id &&
        r.target === target &&
        (target === "original" || (r.run_id === run && (r.result_id || "") === (data.results.find(x => x.task_id === task_id && x.run_id === run)?.result_id || ""))),
    )
    .reduce((n, r) => n + r.count, 0);
  return (
    <details className="review-collapse">
      <summary>评价与备注</summary>
      <article className="review">
        <div className="panel-title">
          <h2>人工评价</h2>
          <span>{count} 条</span>
        </div>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setSaving(true);
            try {
              await saveReview({
                version: data.version,
                task_id,
                clip_id: clip.clip_id,
                camera_id: camera,
                target,
                run_id: target === "model" ? run : "",
                result_id: target === "model" ? data.results.find(x => x.task_id === task_id && x.run_id === run)?.result_id : "",
                reviewer,
                accuracy,
                omission,
                notes,
                ...(detailed ? {clarity,object_accuracy:objectAccuracy,direction_accuracy:directionAccuracy,outcome_accuracy:outcomeAccuracy} : {}),
              });
              localStorage.setItem("reviewer", reviewer);
              setMessage("评价已保存");
              await reload();
            } catch (e) {
              setMessage(
                `保存失败：${e instanceof Error ? e.message : String(e)}`,
              );
            } finally {
              setSaving(false);
            }
          }}
        >
          <label>
            相机
            <select
              aria-label="评价相机"
              value={camera}
              onChange={(e) => setCamera(e.target.value)}
            >
              {Array.from({ length: 6 }, (_, i) => (
                <option key={i}>camera{i}</option>
              ))}
            </select>
          </label>
          <label>
            评价对象
            <select value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="original">原始标注与当前视角</option>
              <option value="model">模型结果</option>
            </select>
          </label>
          {target === "model" && (
            <label>
              模型运行
              <select value={run} onChange={(e) => setRun(e.target.value)}>
                <option value="">请选择成功结果</option>
                {successful.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.model_label} · {r.id}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            姓名
            <input
              required
              maxLength={80}
              value={reviewer}
              onChange={(e) => setReviewer(e.target.value)}
            />
          </label>
          {!detailed && <>
          <label>
            {target === "model" ? "事实准确性（整体）" : "准确性"}
            <select
              required
              value={accuracy}
              onChange={(e) => setAccuracy(e.target.value)}
            >
              <option value="">请选择</option>
              {[
                ["accurate", "准确"],
                ["partial", "部分准确"],
                ["incorrect", "不准确"],
                ["unknown", "无法判断"],
              ].map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          <label>
            {target === "model" ? "关键操作覆盖（动作遗漏）" : "动作遗漏"}
            <select
              required
              value={omission}
              onChange={(e) => setOmission(e.target.value)}
            >
              <option value="">请选择</option>
              <option value="none">无</option>
              <option value="yes">有</option>
              <option value="unknown">无法判断</option>
            </select>
          </label>
          </>}
          {detailed && <>
            <fieldset><legend>描述质量</legend>
              <label>清楚与规范
                <select required value={clarity} onChange={e=>setClarity(e.target.value)}>
                  <option value="">请选择</option><option value="clear">清楚规范</option><option value="partial">部分清楚</option><option value="unclear">不清楚</option><option value="unknown">无法判断</option>
                </select>
              </label>
          <label>
            {target === "model" ? "关键操作覆盖（动作遗漏）" : "动作遗漏"}
            <select
              required
              value={omission}
              onChange={(e) => setOmission(e.target.value)}
            >
              <option value="">请选择</option>
              <option value="none">无</option>
              <option value="yes">有</option>
              <option value="unknown">无法判断</option>
            </select>
          </label>
              <small>描述详细与事实正确分别判断。</small>
            </fieldset>
            <fieldset><legend>事实准确性</legend>
          <label>
            {target === "model" ? "事实准确性（整体）" : "准确性"}
            <select
              required
              value={accuracy}
              onChange={(e) => setAccuracy(e.target.value)}
            >
              <option value="">请选择</option>
              {[
                ["accurate", "准确"],
                ["partial", "部分准确"],
                ["incorrect", "不准确"],
                ["unknown", "无法判断"],
              ].map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>

              {[
                {label:"对象是否准确",value:objectAccuracy,set:setObjectAccuracy},
                {label:"动作方向是否准确",value:directionAccuracy,set:setDirectionAccuracy},
                {label:"最终状态是否准确",value:outcomeAccuracy,set:setOutcomeAccuracy},
              ].map(item=><label key={item.label}>{item.label}<select required value={item.value} onChange={e=>item.set(e.target.value)}>
                <option value="">请选择</option><option value="accurate">准确</option><option value="partial">部分准确</option><option value="incorrect">不准确</option><option value="unknown">无法判断</option>
              </select></label>)}
            </fieldset>
            <p>资源效率从结果旁的实测数据查看，不作为人工准确性分数。</p>
          </>}
          <label>
            备注
            <textarea
              maxLength={2000}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </label>
          <button
            className="primary"
            disabled={
              saving ||
              (target === "model" && !successful.some((r) => r.id === run))
            }
          >
            保存评价 →
          </button>
          <a className="button" href="/api/reviews/export">
            导出评价
          </a>
          <p role="status">{message}</p>
          <small>每次评价保留为独立记录</small>
        </form>
      </article>
    </details>
  );
}
