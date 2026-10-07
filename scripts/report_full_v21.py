"""Read the v2.1 six-run release and produce reproducible counts/resource reports."""
import argparse,collections,csv,json,statistics,sys
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'scripts'))
from run_full_v21 import manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--require-complete',action='store_true');args=parser.parse_args()
    config=json.loads((PROJECT/'configs/full_v21.json').read_text());tasks,first=manifest();stats=[];records=[];gap=[]
    for provider,runs in config['runs'].items():
        for mode,rid in runs.items():
            folder=PROJECT/'runs'/rid;expected=[t['task_id'] for t in tasks] if mode=='off' else first
            index=json.loads((folder/'active.json').read_text())['selection'] if (folder/'active.json').is_file() else {}
            rows=[json.loads((folder/'versions'/(index[tid]+'.json')).read_text()) for tid in expected if tid in index]
            for tid in expected:
                value=next((r for r in rows if r['task_id']==tid),{})
                if value.get('caption_status')!='success':gap.append({'run_id':rid,'task_id':tid,'status':value.get('caption_status','pending'),'error':value.get('error')})
            for r in rows:records.append({**r,'provider':provider,'profile':mode})
            attempts=[json.loads(p.read_text()) for p in (folder/'versions').glob('*.json')]
            peak={};reserved={}
            for r in rows:
                for gpu,value in (r.get('peak_gpu_allocated_bytes') or {}).items():peak[gpu]=max(peak.get(gpu,0),value)
                for gpu,value in (r.get('peak_gpu_reserved_bytes') or {}).items():reserved[gpu]=max(reserved.get(gpu,0),value)
            stats.append({'run_id':rid,'provider':provider,'profile':mode,'expected':len(expected),'success':sum(r['caption_status']=='success' for r in rows),
                'failed':sum(r['caption_status']=='failed' for r in rows),'pending':len(expected)-len(rows),
                'actual_attempts':len(list((folder/'attempts').glob('*.json'))),
                'generation_seconds':sum(r.get('generation_seconds',0) for r in rows),'total_task_seconds':sum(r.get('elapsed_seconds',0) for r in rows),
                'input_tokens':sum(r.get('input_tokens') or 0 for r in rows),'output_tokens':sum(r.get('generated_tokens') or 0 for r in rows),
                'reasoning_tokens':sum(r.get('thinking_tokens') or 0 for r in rows),'estimated_cost_cny':sum(r.get('estimated_cost_cny') or 0 for r in attempts),
                'all_attempt_output_tokens':sum(r.get('generated_tokens') or 0 for r in attempts),
                'unknown_remote_outcomes':sum(r.get('execution_status')=='unknown_remote_outcome' for r in attempts),
                'transports':dict(collections.Counter(r.get('provider_transport') for r in rows if r.get('provider_transport'))),'peak_gpu_allocated_bytes':peak,'peak_gpu_reserved_bytes':reserved,
                'median_generation_seconds':statistics.median([r.get('generation_seconds',0) for r in rows]) if rows else None,
                'thinking_seconds':sum(r['thinking_seconds'] for r in rows if r.get('thinking_seconds') is not None) if any(r.get('thinking_seconds') is not None for r in rows) else None,
                'caption_seconds':sum(r['caption_seconds'] for r in rows if r.get('caption_seconds') is not None) if any(r.get('caption_seconds') is not None for r in rows) else None})
    report={'prompt_id':config['prompt_id'],'sampling_fps':2,'camera':'camera2','first_task_ids':first,'planned_results':316,'runs':stats,'gaps':gap,
            'complete':not gap,'quality_status':'requires_human_review','estimated_api_cost_cny':sum(r['estimated_cost_cny'] for r in stats),
            'comparison_note':'Qwen uses locally observed PTS; Ark uses requested FPS and provider processing. Inputs are not guaranteed identical.'}
    out=PROJECT/'reports/experiments/v2_1';out.mkdir(parents=True,exist_ok=True)
    (out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    lines=['# v2.1 全量结果与资源报告','',f'目标 316 条；已成功 {sum(r["success"] for r in stats)}；失败 {sum(r["failed"] for r in stats)}；缺口 {len(gap)}。','',
           '整段视频＋r3，camera2，2 fps；不使用标注、历史或窗口。生成完成不等于事实准确。',
           '', '|模型|模式|成功/目标|失败|生成秒|输入/输出 token|估算费用 CNY|','|---|---|---:|---:|---:|---:|---:|']
    for row in stats:lines.append(f'|{row["provider"]}|{row["profile"]}|{row["success"]}/{row["expected"]}|{row["failed"]}|{row["generation_seconds"]:.1f}|{row["input_tokens"]}/{row["output_tokens"]}|{row["estimated_cost_cny"]:.4f}|')
    lines+=['','费用按 2026-10-07 常规公开单价估算，不计缓存折扣，账单为准；没有累计费用停止阈值。','Qwen 的 token 与显存来自本地；豆包服务端实际抽帧、处理尺寸及分阶段耗时未返回时标为未知。','']
    if gap:lines+=['## 待处理缺口','',*[f'- {g["run_id"]} / {g["task_id"]}：{g["status"]}；{g.get("error") or "未生成"}' for g in gap],'']
    (out/'summary.md').write_text('\n'.join(lines)+'\n')
    cols=['sample_id','clip_id','task_id','provider','profile','run_id','result_id','caption_status','generated_caption','generation_seconds','elapsed_seconds','input_tokens','thinking_tokens','caption_tokens','generated_tokens','provider_transport','estimated_cost_cny']
    with (out/'comparisons.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore');writer.writeheader();writer.writerows(sorted(records,key=lambda r:(r['task_id'],r['provider'],r['profile'])))
    print(json.dumps({'success':sum(r['success'] for r in stats),'gaps':len(gap),'estimated_api_cost_cny':report['estimated_api_cost_cny']},ensure_ascii=False))
    if args.require_complete and gap:raise SystemExit('Incomplete v2.1 release; do not activate cloud presentation')

if __name__=='__main__':main()
