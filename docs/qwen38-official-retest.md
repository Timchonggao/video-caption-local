# Qwen3.8 v2 当前官方采样方案

当前只保留 sample_01 五个 camera2 原始子片段的四档官方结果，固定基础种子 20261006。每档五条，共 20 条，全部完整结束。

| 模式 | temperature | top_p | presence_penalty | 平均生成耗时 |
|---|---:|---:|---:|---:|
| 关闭思考 | 0.7 | 0.80 | 1.5 | 17.75 秒 |
| low | 1.0 | 0.95 | 0 | 63.84 秒 |
| medium | 1.0 | 0.95 | 0 | 68.36 秒 |
| xhigh | 1.0 | 0.95 | 0 | 151.47 秒 |

共同参数：do_sample=True、top_k=20、min_p=0、repetition_penalty=1，preserve_thinking=False。思考组显式设置对应 effort；非思考不注入 effort。presence penalty 只对本次生成中已出现的 token 惩罚一次，不影响 Prompt 或视频占位符。任务种子由基础种子与 task_id 派生。

输入保持视频＋六部分 r3、camera2、6 fps、每帧 512000 像素（实际 768×640），按真实 PTS 组织。无标注背景、历史或窗口。总生成上限 4096、caption 上限 512、输入保护 2 GiB。配置与生成证据已保存在每个运行目录，不能覆盖旧运行配置。

## 本地查看

Mac 保持已有 SSH 转发，打开 [本地 v2 看板](http://127.0.0.1:18788/?clip=sample_01_seg02_sub10&prompt=v2.camera2)。

- “思考模式”只提供关闭思考、low、medium、xhigh。
- “并排对照”展示关闭思考与选定 effort，不再选择实验批次或随机种子。
- “资源效率”和“采样输入”默认收起；采样图仍为高清真实帧，思考原文不在网页展示。
- 当前只包含 seg02_sub01、sub02、sub10、sub11、sub12。其余片段未纳入本轮，其他相机没有本轮结果；均不算失败。
- 评价继续绑定实际 run_id、task_id 和 result_id。

## 结果与整理

当前运行为 `qwen-sample01-v2-official-{off|low|medium|xhigh}-s1`。旧贪心思考对照及另一种子的六个运行已按用户要求删除，释放约 9.23 GiB；对应人工评价数为零。v1 和豆包结果保留。早期 `qwen-sample01-v2-video-r3` 仅作为独立高清采样证据来源，通过 configs/dashboard.json 隐藏，不作为实验选择。

[逐任务结果与资源报告](../reports/experiments/qwen38-official-retest.md)和[人工检查表](../reports/experiments/qwen38-official-retest-review.csv)只列当前 20 条。只保留一个基础种子是用户收敛方案的决定，不能用整理后的报告继续声称多种子稳定性。

从 pku_a800 仓库根目录可以重建报告，无需推理：

```bash
./env/bin/python project/scripts/report_qwen_official_retest.py
```

本批生成已完成，run_qwen_official_retest.py 与旧思考对照入口已退役，防止误启动已删除实验。后续扩大或改变配置必须使用新运行编号，可复用 `qwen-sample01-v2-official-off-s1` 的采样证据，并在 caption.py 中显式传入官方采样参数。工程方法见 [harness-usage.md](harness-usage.md)。本次没有新增 GPU 调用、豆包请求或云端发布。
