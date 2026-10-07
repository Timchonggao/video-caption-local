# 当前运行说明

代码、数据读取和 GPU 推理运行在 pku_a800；Mac 通过 SSH 转发查看本地网页。v2.1 是整段 2 fps 的展示基线：138 个原始子片段 × camera2，r3 Prompt，无标注背景、历史或窗口。Qwen 168 条已完成；豆包按用户要求停在 94 条成功结果。公开 mentor 看板展示这 262 条成功 caption，豆包 off 缺失位置显示“待生成”；详见 [验收报告](../reports/experiments/v2_1/local-acceptance.md)和[云端发布说明](cloud-migration.md)。

本地保留 v1、v2、v2.1 供迭代比较，并增加已完成的 [v3 首片段窗口试验](v3-window-off.md)。云端由已验收的发布清单固定稳定结果，不显示版本选择；本次 v3 未发布云端。

## Caption 实验

- [v2.1 运行](full-v21.md)：任务范围、输入缓存、自动 Base64／Files 和结果记录。
- [v3 独立窗口试验](v3-window-off.md)：10 个首片段的 Qwen off，5 秒窗口、逐窗口结果与人工对照。
- [v2 官方方案](qwen38-official-retest.md)：原有五段、6 fps、四档官方参数历史对照。
- [v1 实验](sample01-experiments.md)：固定 12 帧的六相机基线。
- [执行与结果保存](harness-usage.md)：任务身份、输入证据、调用预算和续跑。

修改 Prompt、采样、代码或配置时建立独立运行，不覆盖历史结果。

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
- [早期窗口设计](window-v2.md)：保留旧设计背景；当前试验以 v3 独立窗口说明为准。
- [视觉输入实验](caption-input-experiments.md)：后续单因素比较方向。
- [云端发布](cloud-migration.md)：当前 v2.1 的低分辨率展示副本与更新流程。

本地继续用于实验迭代，不自动调用闭源 API或发布新实验。云端 mentor 看板通过发布清单固定已验收结果，使用低清视频及 JPEG 采样图；更新方式见 [云端说明](cloud-migration.md)。prompts/modules/ 保留升级方向，实际实验文本和哈希保存到 runs/<run_id>/config.json。

当前公开展示基线：[v2.1 部分结果发布](cloud-migration.md)。当前本地窗口试验：[v3 首片段窗口结果](v3-window-off.md)。
