import type { Run, Result } from "../types";
import { ResourceMetrics } from "./ResourceMetrics";
export function CDComparison({entries,camera,review}: {entries:{run:Run;value?:Result}[];camera:string;review:(camera:string,run:string)=>void}) {
  return <section className="cd-comparison" aria-label="C 与 D 三维对照">
    <p>共用六部分 Prompt：C 为独立图片，D 为视频序列。分别检查描述质量、事实准确性和资源效率，不合成总分。</p>
    <div className="cd-cards">{["C","D"].map(group=> {
      const entry=entries.find(e=>e.run.comparison_group===group);
      if(!entry)return null;
      return <article className="cd-card" key={entry.run.id}>
        <h3>{group} · {group==="C"?"独立图片":"视频序列"}</h3>
        <p className="comparison-caption">{entry.value?.generated_caption || "此视角或片段暂无本轮结果"}</p>
        <details><summary>描述质量与事实检查</summary>
          <p>描述质量：是否清楚规范，是否覆盖关键操作；详细不等于准确。</p>
          <p>事实准确性：对象、动作方向、最终状态是否有画面证据；遗漏和补写分别记录。</p>
        </details>
        <h4>资源效率</h4><ResourceMetrics value={entry.value}/>
        {entry.value?.caption_status==="success"&&<button onClick={()=>review(camera,entry.run.id)}>评价 {group} 结果</button>}
      </article>;
    })}</div>
    <small>这里只展示生成阶段耗时；不把它当作完整流水线耗时，也不自动判定准确性。</small>
  </section>;
}
