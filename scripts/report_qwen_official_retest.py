"""Audit the currently retained official runs; preserve matching human notes."""
import argparse,csv,json,statistics
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('--allow-incomplete',action='store_true');a=p.parse_args()
    c=json.loads((PROJECT/'configs/qwen38_official_retest.json').read_text());groups={};tasks={};review=[]
    expected=len(c['task_ids'])*len(c['profiles'])*len(c['seeds'])
    for index,base_seed in enumerate(c['seeds'],1):
        for profile,params in c['profiles'].items():
            name=f'qwen-sample01-v2-official-{profile}-s{index}';folder=PROJECT/'runs'/name
            active=json.loads((folder/'active.json').read_text())['selection'] if (folder/'active.json').exists() else {}
            rows=[]
            for task in c['task_ids']:
                if task not in active:
                    if not a.allow_incomplete:raise ValueError('Missing result '+name+'/'+task)
                    tasks.setdefault(task,{})[f'{profile}-s{index}']={'caption_status':'pending'};continue
                r=json.loads((folder/'versions'/(active[task]+'.json')).read_text())
                if r.get('effective_sampling') and r['effective_sampling'].get('base_seed')!=base_seed:raise ValueError('Seed metadata mismatch')
                if r.get('effective_sampling') and r.get('reasoning_effort')!=(profile if params['thinking'] else None):raise ValueError('Effort metadata mismatch')
                if r.get('generated_tokens') is not None and r['generated_tokens']!=sum(r.get(k,0) for k in ['thinking_tokens','caption_tokens','delimiter_tokens','terminal_tokens']):raise ValueError('Token accounting mismatch')
                fields=['task_id','result_id','input_id','caption_status','output_status','error','generated_caption','generation_seconds','elapsed_seconds','input_tokens','generated_tokens','thinking_tokens','caption_tokens','delimiter_tokens','terminal_tokens','first_token_seconds','thinking_seconds','thinking_decode_seconds','caption_seconds','thinking_complete','caption_complete','finish_reason','peak_gpu_allocated_bytes','peak_gpu_reserved_bytes','effective_sampling','task_seed','reasoning_effort','input_mode','processed_sizes','source_interval_s','sampled_times_s']
                item={k:r.get(k) for k in fields};item.update(run_id=name,profile=profile,seed_index=index,base_seed=base_seed);rows.append(item)
                if r.get('input_id'):
                    bundle=json.loads((folder/'inputs'/(r['input_id']+'.json')).read_text())
                    item['template_summary']=bundle['request'].get('template_summary')
                tasks.setdefault(task,{})[f'{profile}-s{index}']=item
                review.append({'run_id':name,'task_id':task,'result_id':r['result_id'],'profile':profile,'seed_index':index,'caption_status':r['caption_status'],'clarity':'','operation_coverage':'','object_accuracy':'','direction_accuracy':'','outcome_accuracy':'','notes':''})
            success=[r for r in rows if r['caption_status']=='success'];g={'run_id':name,'expected':5,'completed':len(rows),'success':len(success),'failed':len(rows)-len(success),'calls':len(list((folder/'attempts').glob('*.json'))) if folder.exists() else 0,'generation_total_s':sum(r.get('generation_seconds') or 0 for r in rows),'thought_tokens_total':sum(r.get('thinking_tokens') or 0 for r in rows),'caption_tokens_total':sum(r.get('caption_tokens') or 0 for r in rows)}
            timed=[r for r in rows if r.get('generation_seconds') is not None]
            g['unmeasured_generation_count']=len(rows)-len(timed)
            if timed:
                g['generation_mean_s']=statistics.mean(r['generation_seconds'] for r in timed)
                g['peak_allocated_gib']={str(i):max(r['peak_gpu_allocated_bytes'][str(i)] for r in timed)/2**30 for i in [0,1]}
                g['peak_reserved_gib']={str(i):max(r['peak_gpu_reserved_bytes'][str(i)] for r in timed)/2**30 for i in [0,1]}
                g['elapsed_total_s']=sum(r.get('elapsed_seconds') or 0 for r in rows)
                g['first_token_mean_s']=statistics.mean(r['first_token_seconds'] for r in timed)
                g['thinking_phase_total_s']=sum(r.get('thinking_seconds') or 0 for r in rows)
                g['caption_phase_total_s']=sum(r.get('caption_seconds') or 0 for r in rows)
            groups[f'{profile}-s{index}']=g
    total=sum(g['completed'] for g in groups.values());calls=sum(g['calls'] for g in groups.values())
    if calls>expected:raise ValueError('Unexpected excess model attempts')
    result={'groups':groups,'tasks':tasks,'config':c,'completed':total,'expected':expected,'calls':calls,'quality_status':'awaiting_user_review','cloud_published':False,'doubao_calls':0,'scope_note':'用户已选择仅保留官方基础种子 20261006；旧贪心对照与另一种子已清理。此报告不再进行多种子稳定性或旧贪心比较。'}
    profiles={}
    for profile in c['profiles']:
        pair=[groups[f'{profile}-s{i}'] for i in range(1,len(c['seeds'])+1)]
        n=sum(g['completed'] for g in pair)
        profiles[profile]={'completed':n,'expected':len(c['task_ids'])*len(c['seeds']),'success':sum(g['success'] for g in pair),'failed':sum(g['failed'] for g in pair),
            'generation_total_s':sum(g['generation_total_s'] for g in pair),
            'generation_mean_s':sum(g['generation_total_s'] for g in pair)/n if n else None,
            'generation_per_seed_s':[g['generation_total_s'] for g in pair],
            'thinking_tokens_total':sum(g['thought_tokens_total'] for g in pair),'caption_tokens_total':sum(g['caption_tokens_total'] for g in pair)}
    result['profile_totals']=profiles
    out=PROJECT/'reports/experiments';prior=out/'qwen38-official-retest.json'
    if prior.exists():
        previous=json.loads(prior.read_text())
        if previous.get('config',{}).get('seeds')==c['seeds']:
            result.update({k:previous[k] for k in ['verification','assistant_initial_review'] if k in previous})
    prior.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    review_path=out/'qwen38-official-retest-review.csv'
    # Keep notes only for retained run/task/result identities, pruning removed runs.
    existing={}
    retained_identities={(r['run_id'],r['task_id'],r['result_id']) for r in review}
    if review_path.exists():
        with review_path.open() as stream:
            for row in csv.DictReader(stream):
                identity=(row['run_id'],row['task_id'],row['result_id'])
                if identity in retained_identities:existing[identity]=row
    for row in review:existing.setdefault((row['run_id'],row['task_id'],row['result_id']),row)
    if review:
        with review_path.open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(review[0]));writer.writeheader();writer.writerows(existing.values())
    lines=['# Qwen3.8 v2 官方采样：当前四档结果','',f'当前保留 {total}/{expected} 条，来自 {calls} 次调用。基础种子 20261006；旧贪心对照与另一种子已按用户要求删除。','', '同一 camera2 五段、视频＋r3、6 fps、512000 像素，复用原始采样证据。任务种子按身份派生；无历史，preserve_thinking=False。总生成 4096、最终 caption 512。','', '关闭思考与开启思考采用各自官方推荐配置，所以它们是推荐方案整体比较；low/medium/xhigh 的其他采样设置相同，比较 effort 影响。当前只保留一组种子，不能据此评价多种子稳定性。','', '|组|种子|成功/完成/目标|失败|生成总耗时|思考 token|caption token|','|---|---:|---:|---:|---:|---:|---:|']
    for key,g in groups.items():
        profile,index=key.split('-s');lines.append(f'|{profile}|{index}|{g["success"]}/{g["completed"]}/5|{g["failed"]}|{g["generation_total_s"]:.2f} 秒|{g["thought_tokens_total"]}|{g["caption_tokens_total"]}|')
    lines+=['','## 当前保留结果与资源','', '|组|完整/目标|失败|平均生成秒/条|生成总秒|思考 token|caption token|','|---|---:|---:|---:|---:|---:|---:|']
    for profile,g in profiles.items():
        average=f'{g["generation_mean_s"]:.2f}' if g['generation_mean_s'] is not None else '—'
        lines.append(f'|{profile}|{g["success"]}/{g["expected"]}|{g["failed"]}|{average}|{g["generation_total_s"]:.2f}|{g["thinking_tokens_total"]}|{g["caption_tokens_total"]}|')
    lines+=['','|组与种子|任务总耗时秒|平均首 token 秒|思考阶段秒|caption 阶段秒|峰值 allocated GiB（GPU0/1）|峰值 reserved GiB（GPU0/1）|','|---|---:|---:|---:|---:|---|---|']
    for key,g in groups.items():
        if not g.get('completed') or 'peak_allocated_gib' not in g:continue
        allocated='/'.join(f'{g["peak_allocated_gib"][str(i)]:.2f}' for i in [0,1])
        reserved='/'.join(f'{g["peak_reserved_gib"][str(i)]:.2f}' for i in [0,1])
        lines.append(f'|{key}|{g["elapsed_total_s"]:.2f}|{g["first_token_mean_s"]:.2f}|{g["thinking_phase_total_s"]:.2f}|{g["caption_phase_total_s"]:.2f}|{allocated}|{reserved}|')
    lines+=['','任务总耗时包含输入校验、读取、首次权重加载、传输与生成；不含此前统一 CPU 准备，不能把其与生成的差值全算作预处理。组峰值为各任务最大值。每组五段；未完成运行时平均值仅按已有记录。', '',
        '参数依据：[Qwen3.8 官方 README](https://huggingface.co/Qwen/Qwen3.8-27B/blob/main/README.md#api-usage)。保留输入的像素、PTS、图片哈希和显式模板参数核对见 `reports/performance/qwen-official-input-audit.json`。每条结果的任务种子、模板摘要、尺寸、完整 token 与计时统计保存于同名 JSON 报告；渲染模板和完整采样证据保留在对应 runs 目录。']
    lines+=['','## 判断方式','', '分别检查描述是否清楚规范、关键操作覆盖，以及对象、方向和最后状态是否准确；资源数据与输出完整性另列，不合成总分。EOS完整不代表事实正确。结果清理属于用户的方案收敛选择，不是对准确性或稳定性的证明。','', '逐token计时有主机同步开销；所有组同口径。思考阶段含预填充，首token延迟另列，关闭组caption阶段含预填充。GPU峰值按allocated记录，不等于驱动总占用。未运行豆包或发布云端。']
    if result.get('verification'):
        v=result['verification']
        lines+=['','## 整理验收','', '```json',json.dumps(v,ensure_ascii=False,indent=2),'```']
    for task,variants in tasks.items():
        lines+=['','## '+task]
        for key,r in variants.items():
            lines+=['','### '+key,'',r.get('generated_caption') or ('待生成' if r['caption_status']=='pending' else '失败：'+str(r.get('error')))]
            if r.get('result_id'):
                def fmt(value):return '—' if value is None else f'{value:.2f}'
                lines+=['',f'状态 {r["caption_status"]}/{r.get("output_status")}；输入/思考/caption/分隔/终止 token：{r.get("input_tokens")}/{r.get("thinking_tokens")}/{r.get("caption_tokens")}/{r.get("delimiter_tokens")}/{r.get("terminal_tokens")}；首 token {fmt(r.get("first_token_seconds"))} 秒，思考 {fmt(r.get("thinking_seconds"))} 秒，caption {fmt(r.get("caption_seconds"))} 秒，生成 {fmt(r.get("generation_seconds"))} 秒，任务总耗时 {fmt(r.get("elapsed_seconds"))} 秒。',f'运行 `{r["run_id"]}`；结果 `{r["result_id"]}`；任务种子 `{r.get("task_seed")}`。']
    if result.get('assistant_initial_review'):lines+=['','## 初查','',result['assistant_initial_review']]
    (out/'qwen38-official-retest.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(groups,indent=2));print('Completed/calls:',total,calls)
if __name__=='__main__':main()
