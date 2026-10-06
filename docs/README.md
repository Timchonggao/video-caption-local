# 当前运行说明

代码、数据读取和 GPU 推理运行在 pku_a800 服务器；Mac 通过 SSH 转发查看本地网页。v1 六相机结果继续保留；当前 v2 仅对 sample_01 的五个 camera2 原始子片段进行参数复测，不自动扩大到全部 24 段。

## Caption 实验

v1 是纯视觉简短描述：每个原始片段均匀抽取 12 帧，不是 12 fps；不提供标注背景，不传递历史，不做窗口汇总。配置见 configs/sample01_v1.json，Prompt 见 prompts/sample01_baseline_v1.txt。

当前 v2 使用视频＋六部分 r3、6 fps、每帧 512000 像素，采用官方采样方法。保留基础种子 20261006 的关闭思考与 low/medium/xhigh 四档，每档五段，共 20 条；结果与查看方式见 [Qwen 官方方案](qwen38-official-retest.md)。旧贪心思考对照和另一种子结果已清理，早期视频基线仅作为采样证据来源。

从仓库根目录准备一个任务，不执行生成：

```bash
env/bin/python project/scripts/run_sample01_v1.py
```

确认输入后加 --apply 生成。完整运行与续跑见 [sample01-experiments.md](sample01-experiments.md)；输入证据、调用预算和结果保存见 [harness-usage.md](harness-usage.md)。修改 Prompt、代码或配置必须建立新运行编号。

## 本地看板

服务器启动：

```bash
env/bin/python project/scripts/serve_dashboard.py
```

Mac 保持以下转发连接：

```bash
ssh -F /dev/null -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=60 -o ServerAliveCountMax=3 -i ~/.ssh/id_ed25519 -p 5221 -L 127.0.0.1:18788:127.0.0.1:18788 root@180.76.72.94
```

浏览器打开 http://127.0.0.1:18788/ 。选择样本、原始片段、版本、相机与模型；raw caption 查看原始标注，详细 JSON 查看原始标注字段。尚无生成结果时显示“待生成”。新结果生成后刷新页面；前端变更需重新构建，Python 服务或索引变更需重启服务。

视频与权重由 configs/paths.json 引用 CFS，结果保存到 runs/，人工评价保存到 dashboard/.local/reviews.sqlite。数据检查报告位于 reports/data-checks/；云端历史资料位于 reports/cloud/。不按 is_success 或时间／帧有效性排除任务，不改变原始片段边界。

## 工程与后续方向

- [工程契约](caption-engineering.md)：任务身份、输入证据、结果版本与评价绑定。
- [窗口与汇总](window-v2.md)：后续可选能力，不是当前 v1 配置。
- [视觉输入实验](caption-input-experiments.md)：后续单因素比较方向。
- [后续云端发布](cloud-migration.md)：稳定后发布低分辨率展示副本。

本地继续用于实验迭代，不自动调用闭源 API或发布新实验。云端 mentor 看板固定当前 v2，展示五段的 Qwen 四档和豆包共 25 条，使用低清视频及 JPEG 采样图；更新方式见 [云端说明](cloud-migration.md)。prompts/modules/ 保留升级方向，实际实验文本和哈希保存到 runs/<run_id>/config.json。
