"""Offline request preview; no network resources or provider calls."""
import html
import json
from caption_system.results.atomic import atomic_text

def write_preview(root, rows):
    parts = ['<!doctype html><meta charset="utf-8"><title>Caption input preview</title>',
             '<style>body{font-family:system-ui;margin:24px}article{border:1px solid #ccc;padding:16px;margin:16px 0}pre{white-space:pre-wrap}img{max-width:280px}figure{display:inline-block;vertical-align:top}</style>',
             '<h1>Caption 输入预览</h1><p>缺失历史上下文的输入为暂定；正式运行会按确切前驱版本准备。用量未知不代表零费用。</p>']
    for row in rows:
        parts.append('<article><h2>' + html.escape(row['task_id']) + '</h2>')
        if 'path' not in row:
            parts.append('<pre>' + html.escape(row.get('error','Preparation failed')) + '</pre></article>')
            continue
        bundle = json.loads((root / row['path']).read_text())
        parts.append('<p>Ready: ' + str(bundle['ready']) + '; context final: ' + str(bundle['context_final']) + '</p>')
        parts.append('<pre>' + html.escape(json.dumps(bundle['context'],ensure_ascii=False,indent=2)) + '</pre>')
        for frame in bundle['frames']:
            parts.append('<figure><img src="' + html.escape(frame['path'],quote=True) + '"><figcaption>' + html.escape(f"source={frame['source_time_s']:.6f}s; relative={frame['relative_time_s']:.6f}s; PTS={frame['pts']}; deviation={frame['deviation_s']:.6f}s") + '</figcaption></figure>')
        parts.append('<details><summary>最终 Prompt</summary><pre>' + html.escape(bundle['prompt']) + '</pre></details>')
        parts.append('<pre>' + html.escape(json.dumps(bundle.get('request'),indent=2)) + '</pre></article>')
    atomic_text(root/'preview.html','\n'.join(parts))
