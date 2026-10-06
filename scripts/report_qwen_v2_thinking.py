"""Audit measured thinking on/off without exposing reasoning in the report."""
import argparse,json,statistics
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('--allow-incomplete',action='store_true');a=p.parse_args()
    c=json.loads((PROJECT/'configs/qwen_v2_thinking.json').read_text())
    if c.get('retired'):
        raise SystemExit('旧贪心对照结果已清理；请使用 report_qwen_official_retest.py 查看当前官方四档结果。')
    groups={};tasks={}
    for role,spec in c['groups'].items():
        folder=PROJECT/'runs'/spec['run_id'];active=json.loads((folder/'active.json').read_text())['selection'];rows=[]
        for task in c['task_ids']:
            if task not in active:
                if not a.allow_incomplete:raise ValueError(f'Missing result: {role}/{task}')
                tasks.setdefault(task,{})[role]={'caption_status':'pending'};continue
            r=json.loads((folder/'versions'/(active[task]+'.json')).read_text())
            row={k:r.get(k) for k in ['task_id','result_id','caption_status','output_status','error','generated_caption','generation_seconds',
                    'input_tokens','generated_tokens','thinking_tokens','caption_tokens','delimiter_tokens','terminal_tokens',
                    'first_token_seconds','thinking_seconds','thinking_decode_seconds','caption_seconds','thinking_complete','caption_complete',
                    'finish_reason','peak_gpu_allocated_bytes','timing_note']}
            if r.get('generated_tokens')!=sum(r.get(k,0) for k in ['thinking_tokens','caption_tokens','delimiter_tokens','terminal_tokens']):
                raise ValueError('Token accounting mismatch')
            b=json.loads((folder/'inputs'/(r['input_id']+'.json')).read_text());row['frames']=len(b['frames']);row['processed_sizes']=b['request']['image_sizes']
            tasks.setdefault(task,{})[role]=row;rows.append(row)
        successful=[r for r in rows if r['caption_status']=='success']
        groups[role]={'run_id':spec['run_id'],'completed':len(rows),'success':len(successful),'failed':len(rows)-len(successful),
                     'calls':len(list((folder/'attempts').glob('*.json'))),
                     'generation_total_s':sum(r['generation_seconds'] for r in rows),'thinking_total_tokens':sum(r['thinking_tokens'] for r in rows),'caption_total_tokens':sum(r['caption_tokens'] for r in rows)}
    data={'groups':groups,'tasks':tasks,'config':c,'quality_status':'unreviewed','doubao_calls':0,'cloud_modified':False,
          'timing_semantics':'Host token-boundary timing: thought phase includes prefill; first-token delay shown separately; off caption phase includes prefill. Compare equally traced runs, not legacy baseline timing.',
          'completeness_semantics':'End markers and EOS/text completeness only; does not establish factual accuracy or action coverage.'}
    out=PROJECT/'reports/experiments'
    prior=out/'qwen-v2-thinking.json'
    if prior.exists():
        previous=json.loads(prior.read_text())
        data.update({k:previous[k] for k in ['assistant_initial_review','verification','totals','official_qwen38_audit'] if k in previous})
    (out/'qwen-v2-thinking.json').write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
    lines=['# Qwen v2 视频＋r3：thinking 开／关','', '同一五段、6 fps、同一真实 PTS 与原图片、相同视频像素和 r3。两组总预算 4096 token，最终 caption 独立上限 512 token，确定性解码；唯一语义设置差异是 thinking 模板开关。旧基线只读，不调用豆包，不扩大其他任务，不发布云端。','',data['timing_semantics'],'',data['completeness_semantics'],'', '|组|成功/完成|思考 token|caption token|生成总耗时|','|---|---:|---:|---:|---:|']
    for role,g in groups.items():lines.append(f'|{role}|{g["success"]}/{g["completed"]}|{g["thinking_total_tokens"]}|{g["caption_total_tokens"]}|{g["generation_total_s"]:.2f} 秒|')
    lines+=['','## 分段统计','', '|任务|组|思考/caption token|首 token 延迟|思考阶段（含预填充）|caption阶段|状态|','|---|---|---:|---:|---:|---:|---|']
    for task,variants in tasks.items():
        for role,r in variants.items():
            if r['caption_status']=='pending':continue
            lines.append(f'|{task}|{role}|{r["thinking_tokens"]}/{r["caption_tokens"]}|{r["first_token_seconds"]:.2f} 秒|{r["thinking_seconds"]:.2f} 秒|{r["caption_seconds"]:.2f} 秒|{r["caption_status"]}|')
    for task,variants in tasks.items():
        lines+=['','## '+task]
        for role,r in variants.items():
            lines+=['','### thinking '+role,'',r.get('generated_caption') or ('尚未运行' if r['caption_status']=='pending' else '输出未完成，不作为有效 caption。')]
    if data.get('assistant_initial_review'):
        review=data['assistant_initial_review']
        lines += ['', '## 初查与当前建议', '', review['method'], '', review['recommendation']]
        for task,text in review['tasks'].items():lines.append('- '+task+'：'+text)
    if data.get('official_qwen38_audit'):
        lines += ['', '## 官方设置核对', '', '当前两组使用贪心解码；开启组使用本地模板默认 reasoning_effort=xhigh 并追加系统说明。此结果不是官方推荐采样或 low/medium effort 的表现。旧运行不修改；完整核对见同名 JSON 的 official_qwen38_audit。']
    (out/'qwen-v2-thinking.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(groups,indent=2))
if __name__=='__main__':main()
