"""Audit the five Ark calls and compare raw captions with accepted Qwen video+r3; no API."""
import json,statistics
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1]

def main():
    c=json.loads((PROJECT/'configs/doubao_seed21_lite_video_r3.json').read_text());folder=PROJECT/'runs'/c['run_id']
    rows={r['task_id']:r for line in (folder/'results.jsonl').read_text().splitlines() for r in [json.loads(line)]}
    config=json.loads((folder/'config.json').read_text())
    reference=json.loads((PROJECT/'reports/experiments/qwen-v2-video-r3.json').read_text())
    items=[]
    for task in c['tasks']:
        r=rows[task]
        if r['caption_status']!='success' or r['finish_reason']!='stop' or r['reported_model']!=c['model']:
            raise ValueError('Failed/truncated or unexpected model response')
        if r['usage']['completion_tokens_details']['reasoning_tokens']!=0:raise ValueError('Unexpected reasoning usage')
        bundle=json.loads((folder/'inputs'/(r['input_id']+'.json')).read_text());export=bundle['request']['video_export']
        if export['audio'] or any(not export['source_interval_s'][0]<=f['source_time_s']<export['source_interval_s'][1] for f in export['frames']):raise ValueError('Export boundary/audio mismatch')
        item={k:r.get(k) for k in ['task_id','result_id','generated_caption','usage','generation_seconds','elapsed_seconds','reported_model','finish_reason','request_id']}
        item.update(requested_fps=5,provider_sampling_known=False,video_bytes=export['bytes'],source_dimensions=export['source_dimensions'],source_frame_count=export['source_frame_count'],
                    qwen_D=reference['results'][task]['generated_caption'])
        items.append(item)
    attempts=len(list((folder/'attempts').glob('*.json')))
    if attempts!=5:raise ValueError('Expected exactly five model attempts')
    summary={'run_id':c['run_id'],'success':5,'attempts':attempts,'requested_fps':5,'actual_provider_frames':'unknown',
        'quality_status':'unreviewed','cloud_published':False,'prompt_matches_r3':config['prompt_modules'][0]['text']==(PROJECT/c['prompt_file']).read_text(),
        'prompt_tokens':sum(r['usage']['prompt_tokens'] for r in items),'completion_tokens':sum(r['usage']['completion_tokens'] for r in items),
        'api_roundtrip_total_s':sum(r['generation_seconds'] for r in items),'api_roundtrip_mean_s':statistics.mean(r['generation_seconds'] for r in items),'results':items}
    out=PROJECT/'reports/experiments'
    prior=out/'doubao-seed21-lite-video-r3.json'
    if prior.exists():
        previous=json.loads(prior.read_text())
        if 'verification' in previous:summary['verification']=previous['verification']
    (out/'doubao-seed21-lite-video-r3.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
    lines=['# Seed 2.1 Lite：五段视频 r3 测试','',f'运行：{c["run_id"]}；模型：{c["model"]}。5/5 成功，正好 5 次请求，无自动重试、无截断，thinking disabled，reasoning_tokens 全部为 0。','',f'API 请求总耗时 {summary["api_roundtrip_total_s"]:.2f} 秒，平均 {summary["api_roundtrip_mean_s"]:.2f} 秒；输入 {summary["prompt_tokens"]}、输出 {summary["completion_tokens"]} token。不估算费用，以账单为准。','', '## 比较边界','', '沿用同一六部分 r3；camera2 原始子片段，无音频，上传原分辨率 1600×1300 的 H264 发布副本，保持原始半开区间及实际源帧时间。请求 5 fps，但实际服务端帧数和处理尺寸未返回。短视频可能采用服务端最小帧数规则，不能把 1.5×5 当作实际观察数量。','', 'Qwen 视频＋r3 为本地 6 fps 已保存帧；豆包为服务端采样/压缩，故这是完整服务效果比较，不是严格隔离模型能力的同帧对照。API 耗时包含传输及服务处理，不等同于 Qwen GPU generate 计时。未设置 temperature，使用服务默认值；没有重复测稳定性。没有运行额外的图片公平对照或其他样本，也未发布云端。','', '## 初查','', '- sub01 明确使用 removes/pulls out，相比 Qwen 的插入/挂上描述，动作方向更接近画面；人物姿态、衣架材质和细节仍需核对。','- sub02 没有声称衣服挂好，但是否准确保留取出动作与对象切换，需要复核；输出采用第一人称 I，与其他片段风格不一致。','- sub10 描述拉回衣架、放下并松手，不再补写挂好衣服；材质 black plastic 未可靠确认。','- sub11 描述更完整，但 long-sleeve、摇动及折叠顺序需检查，详细不等于准确。','- sub12 仍写第二件衣服叠放，与此前末尾画面初查有出入，不能认定幻觉问题已解决。','', '语义质量保持 unreviewed，用户应独立检查描述质量、事实准确性和资源效率，不自动合成总分。','', '|任务|API 请求耗时|输入/输出 token|源视频帧数（非服务端采样）|','|---|---:|---:|---:|']
    for r in items:lines.append(f'|{r["task_id"]}|{r["generation_seconds"]:.2f} 秒|{r["usage"]["prompt_tokens"]}/{r["usage"]["completion_tokens"]}|{r["source_frame_count"]}|')
    for r in items:
        lines+=['','## '+r['task_id'],'','### Seed 2.1 Lite','',r['generated_caption'],'','### Qwen D：视频＋r3','',r['qwen_D']]
    (out/'doubao-seed21-lite-video-r3.md').write_text('\n'.join(lines)+'\n')
    print({k:v for k,v in summary.items() if k!='results'})
if __name__=='__main__':main()
