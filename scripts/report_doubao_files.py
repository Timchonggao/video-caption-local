"""Read Files API run results without uploading, polling or calling a model."""
import argparse
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
FIELDS = ['task_id','result_id','caption_status','generated_caption','error','execution_status',
          'model_call_attempted','provider_transport','remote_file','requested_preprocessing',
          'preprocessing_echo_verified','file_reused','file_upload_seconds','file_processing_seconds',
          'caption_request_seconds','generation_seconds','elapsed_seconds','input_tokens','generated_tokens',
          'finish_reason','source_video_dimensions','provider_sampling_known']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',default='doubao-seed21-lite-sample01-files-default-sub01-20261007')
    args=parser.parse_args()
    if not args.run or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in args.run):
        parser.error('Invalid run ID')
    folder=PROJECT/'runs'/args.run
    if not (folder/'config.json').exists():
        raise SystemExit('本运行尚未准备或生成；此报告入口不执行推理。')
    config=json.loads((folder/'config.json').read_text())
    if config.get('transport')!='files_api_chat':
        raise ValueError('Expected a Files API video run')
    active=json.loads((folder/'active.json').read_text()).get('selection',{}) if (folder/'active.json').exists() else {}
    rows=[]
    for tid,rid in active.items():
        value=json.loads((folder/'versions'/(rid+'.json')).read_text())
        if value['task_id']!=tid:raise ValueError('Result identity mismatch')
        rows.append({k:value.get(k) for k in FIELDS})
    result={'run_id':args.run,'model':config['model_name'],'expected':len(config.get('experiment_task_ids') or []),
            'success':sum(r['caption_status']=='success' for r in rows),'failed':sum(r['caption_status']=='failed' for r in rows),
            'quality_status':'unreviewed','file_preprocess_configs':config['file_preprocess_configs'],
            'actual_attempts':len(list((folder/'attempts').glob('*.json'))),'results':rows}
    output=PROJECT/'reports/experiments';output.mkdir(parents=True,exist_ok=True)
    stem=output/(args.run+'-files-report')
    stem.with_suffix('.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    def number(value):return '未记录' if value is None else f'{value:.2f}'
    lines=['# 豆包 Files API 视频结果','',f'运行：{args.run}；成功 {result["success"]}，失败 {result["failed"]}，目标 {result["expected"]}。',
           '', f'相机 {config.get("camera")}，请求 {config.get("sampling_fps")} fps，Prompt {config.get("prompt_id")}，thinking {config.get("thinking")}，输出上限 {config.get("max_new_tokens")}；生成采样参数保持服务默认。',
           ('未设置 min_frame_tokens、max_frame_tokens、max_video_tokens，沿用服务默认视觉处理。'
            if set(config['file_preprocess_configs']['video']) == {'fps'} else '视觉预算以保存的请求配置为准。'),
           '服务端实际采样帧和处理尺寸未返回，不作推定；预处理回显通过不等于逐帧画面已核验。',
           '', '|任务|状态|上传秒|文件处理秒|caption请求秒|Files总秒|输入/输出token|',
           '|---|---|---:|---:|---:|---:|---:|']
    for row in rows:
        lines.append(f'|{row["task_id"]}|{row["caption_status"]}|{number(row["file_upload_seconds"])}|{number(row["file_processing_seconds"])}|{number(row["caption_request_seconds"])}|{number(row["generation_seconds"])}|{row["input_tokens"]}/{row["generated_tokens"]}|')
        lines+=['','## '+row['task_id'],'',row['generated_caption'] or row.get('error') or '未完成']
    stem.with_suffix('.md').write_text('\n'.join(lines)+'\n')
    print(f'报告已保存：成功 {result["success"]} / 失败 {result["failed"]}；未调用 API。')


if __name__=='__main__':main()
