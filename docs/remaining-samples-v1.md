# 其余九个样本：纯视觉 v1

两项工程优化已应用：缓存先匹配 preparation_key，再校验匹配输入；PNG 使用无损压缩等级 1。Prompt、原始边界、每片段 12 帧、真实 PTS 选帧、512000 像素预算和 256 token 上限不变。不使用标注背景、历史、窗口或闭源 API，不发布云端。

sample_01 的 144 条结果保持不变，其旧配置记录的是优化前代码。不要用修改后的代码续跑旧 run_id；需要重测 sample_01 时必须使用新 run_id。其余样本分别使用 qwen-sample02-v1 到 qwen-sample10-v1。

## 范围

|样本|原始片段|六路任务|
|---|---:|---:|
|02|8|48|
|03|3|18|
|04|5|30|
|05|8|48|
|06|12|72|
|07|39|234|
|08|11|66|
|09|17|102|
|10|11|66|
|合计|114|684|

## 启动（pku_a800 服务器）

先核对计划，不创建实验、不加载模型：

```bash
cd /root/workspace/video-caption-local
./env/bin/python project/scripts/run_remaining_v1.py
```

建议先完成 sample_02，人工看过再扩展：

```bash
./env/bin/python project/scripts/run_remaining_v1.py --sample sample_02 --apply
```

准备好后执行其余全部样本。以下后台运行不依赖 Mac SSH 保持连接，但服务器实例必须保持运行；系统重启不会自动续跑：

```bash
mkdir -p project/reports/performance
nohup ./env/bin/python -u project/scripts/run_remaining_v1.py --apply > project/reports/performance/remaining-v1-console.log 2>&1 &
echo $! > project/reports/performance/remaining-v1.pid
```

不要重复启动并行批次。查看输出：

```bash
tail -n 30 project/reports/performance/remaining-v1-console.log
```

预计数小时，不能承诺精确时间：684 条约为 sample_01 数量的 4.75 倍，新增 PNG/张量证据可能占数十 GiB。运行前可用 `df -h /root/workspace/video-caption-local` 检查 overlay 空间。

正常中断后重复同一命令可续跑；成功结果复用，失败仍保留。改变代码或实验配置会触发不可变配置保护，需新 run_id。最终应检查各 runs/qwen-sampleXX-v1/results.jsonl 的成功/失败数量，程序结束并不表示每条 caption 都成功。

## 查看

刷新本地看板，选择样本、原始子片段、相机以及 v1。看板按运行的 sample 信息匹配结果和进度；六路视频继续读取 CFS 高清原件。每个 runs/<run_id>/ 保存 config.json、tasks.jsonl、results.jsonl、metrics.json、run.log 和采样输入。不是新一轮 v2，也不改变已有 sample_01 的 caption。

## 验证

34 个 Python 测试通过，前端类型检查和构建通过。新增验证覆盖无关输入不读图片、匹配输入损坏重建、低压缩 PNG 像素一致性。没有重跑正式 GPU caption；实际全流程提速应通过下一批运行确认。
