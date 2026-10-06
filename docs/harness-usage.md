# Harness 输入准备与运行

当前实验入口为 scripts/run_sample01_v1.py，使用简短 Prompt 并输出纯文本。通用 caption.py 在未指定 --prompt 时组合四个模块，这是后续结构化能力；自定义纯文本 Prompt 用 --prompt，JSON 输出另加 --structured。两种入口的默认行为不同，当前实验以 sample01-experiments.md 为准。

## Dry-run

在项目根目录执行（服务器）：

```bash
env/bin/python project/scripts/run_sample01_v1.py
```

不加 --apply 不执行生成。Qwen 会加载本地 processor 并准备 CPU 张量，不加载 GPU 模型权重。生成 runs/<run_id>/preview.html、preview.json、inputs/ 和 artifacts/。HTML 是离线输入预览，可连同 artifacts/ 下载小规模预览后查看；本次未发布到云端。

API dry-run 可指定 --provider gemini 或 doubao 及 --model 实际模型 ID，无需凭据、不发网络请求。它保存正式发送的 JSON（无凭据）。请求大小预算是本系统配置，不能替代不同供应商真实限制。API token/费用估计暂不可用，明确显示未知；Qwen 记录实际准备的输入 token。

## 正式执行及续跑

在相同命令后加 --apply，保持同一 run 配置。输入未变化时读取已准备的请求或张量，不重新抽帧。API 凭据只从服务器环境读取。--max-calls 限制本次生成调用数，本地模型也遵守。

背景 --background none/sample/sample_and_fine_label；历史 --contextual。--context-missing-policy continue_without_context 明示缺失历史后继续；wait_for_predecessor 只准备视觉证据、等待确切前驱。dry-run 中缺失前驱时 context_final=false，不能视为最终连续链请求。

--task-id 是执行过滤，不改变原始前驱域。--limit 控制本次处理任务数。--rerun 显式生成新版本，不覆盖旧版本；上下文已变化仅标记，不自动级联生成。远端结果未知时默认阻止重试，--retry-unknown 是显式确认可能再次计费。

第一版调度保守串行：解码、模型请求、在内存准备队列各上限为 1，资源职责已分开，但尚未开放提高并发的参数。后续并行化不得破坏每相机上下文链。

--max-request-bytes 默认对 Qwen CPU 张量为 512 MiB，对 API JSON 为 32 MiB；--max-deviation-s 默认 1 秒，超出偏差的任务记录准备失败，可为实验显式调整。API 估计限制仍需按所选真实模型规格核实。

## 产物与恢复

config.json 固定配置与模块内容；tasks.jsonl 固定完整任务域；inputs/ 保存实际输入包；artifacts/ 保存 PNG、API 请求 JSON 或 Qwen CPU 张量；versions/ 保存不可变结果；attempts/ 保存调用状态；active.json 原子提交活动结果与上下文变化标记。results.jsonl 是兼容看板的投影，events.jsonl 为诊断事件。读取以 active.json 为准。

中断后 running 尝试标记 interrupted；远端调用还标记 unknown_remote_outcome。活动结果若已经提交，则恢复尝试完成状态。不承诺 API exactly-once。旧评价不会转移到新结果；无版本信息的旧评价继续保留。

缓存不自动删除。需要复现的运行保留 inputs/、artifacts/ 及视频内容版本。手动删除 artifacts/ 后请求会重新准备，不能再宣称使用原预览字节；已有成功结果不会因此自动触发付费生成。大文件仍保持 CFS 现有位置。

格式有效不代表视觉正确；第一版不做自动语义核查。未增加音频、位姿、质量审计、目标评分或自动视频重切。
