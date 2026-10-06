import type { Clip } from "../types";
import { domainLabels } from "../types";
export function SampleSidebar({
  clips,
  current,
  collapsed,
  toggle,
  select,
}: {
  clips: Clip[];
  current?: string;
  collapsed: boolean;
  toggle: () => void;
  select: (id: string) => void;
}) {
  const ids = [...new Set(clips.map((c) => c.sample_id))];
  return (
    <aside className="library">
      <div className="panel-title">
        <h2>样本</h2>
        <span>{ids.length} 个</span>
        <button
          className="sidebar-toggle"
          aria-label={collapsed ? "展开样本栏" : "收起样本栏"}
          aria-expanded={!collapsed}
          onClick={toggle}
        >
          {collapsed ? "→" : "←"}
        </button>
      </div>
      {collapsed && <nav className="compact-samples" aria-label="快速选择样本">
        {ids.map(id => {
          const c = clips.find(c => c.sample_id === id)!;
          return <button key={id}
            className={`compact-sample ${current === id ? "active" : ""}`}
            aria-label={`选择 ${id}`} aria-pressed={current === id}
            title={`${id} · ${domainLabels[c.domain] || c.domain} · ${c.scenario}`}
            onClick={() => select(c.clip_id)}>
            {id.replace(/^sample_/, "")}
          </button>;
        })}
        {!ids.length && <span className="compact-empty" title="没有匹配样本">—</span>}
      </nav>}
      <div className="clip-list" hidden={collapsed}>
        {ids.map((id) => {
          const c = clips.find((c) => c.sample_id === id)!;
          return (
            <button
              key={id}
              className={`clip-card ${current === id ? "active" : ""}`}
              onClick={() => select(c.clip_id)}
            >
              <strong>{id}</strong>
              <span className="clip-meta">
                {domainLabels[c.domain] || c.domain} · {c.scenario}
              </span>
              <small>
                {clips.filter((c) => c.sample_id === id).length} 个片段
              </small>
            </button>
          );
        })}
        {!ids.length && <p className="empty">没有匹配样本</p>}
      </div>
    </aside>
  );
}
