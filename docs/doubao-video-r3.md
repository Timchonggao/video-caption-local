# Seed 2.1 Lite 视频 caption

当前收敛状态（2026-10-07）：只保留六条成功 caption。Base64 的五条用于本地和云端看板；Files 默认的一条留在服务器作为传输验证记录，网页不提供 Files 运行选项。384、640、1024 等视觉预算探索的运行、缓存、失败记录、配置和报告已经删除。

## 保留的结果

| 传输方法 | 运行 | 成功条数 | 输出上限 | 展示范围 |
| --- | --- | ---: | ---: | --- |
| Base64 MP4 + Chat API | `doubao-seed21-lite-sample01-video-r3` | 5 | 512 token | 本地及云端看板 |
| Files API + Chat API | `doubao-seed21-lite-sample01-files-default-sub01-20261007` | 1 | 4096 token | 服务器记录，暂不在网页展示 |

五段为 `sample_01_seg02_sub01、sub02、sub10、sub11、sub12`，均为 camera2；Files 默认记录仅为 `sub01`。结果、输入视频、请求及返回用量按原样保留，没有重跑。两种记录的输出上限不同，不能把它们当作严格单因素效果对照。成功生成不等于事实准确，仍需结合画面人工检查。

两种方法都使用六部分 r3、高清原视频导出的原始子片段、无音频、请求 5 fps、thinking disabled。不加入标注背景、历史或窗口。

“默认参数”表示不设置 `min_frame_tokens`、`max_frame_tokens`、`max_video_tokens`；也不发送 `temperature`、`top_p` 等生成采样覆盖值，沿用服务默认。模型、Prompt、请求 fps、关闭思考和输出上限仍显式记录。保留的 Files 上传预处理为 `{"video":{"fps":5.0}}`。

请求 5 fps 不是服务端实际抽帧证据。服务没有返回实际观察帧和处理尺寸，不能把源视频尺寸或本地帧数当成模型真正看到的输入。

## 查看已有记录

本地网页选择 v2 → 豆包 → camera2；“仅看有结果”可以缩小到这五段。Files 默认结果不出现在模型运行选择中，Qwen 的选项不受影响。云端原本只列入 Base64 五段，本轮无需重新发布。

报告：

- [Base64 五段报告](../reports/experiments/doubao-seed21-lite-video-r3.md)
- [Files 默认单段报告](../reports/experiments/doubao-seed21-lite-sample01-files-default-sub01-20261007-files-report.md)
- [清理记录](../reports/experiments/doubao-consolidation-20261007.json)

在 pku_a800 仓库根目录重新生成 Files 只读报告，不上传文件、不请求模型：

```bash
./env/bin/python project/scripts/report_doubao_files.py
```

## 当前运行入口与后续 Files 能力

`project/scripts/run_doubao_video_r3.py` 默认读取 `configs/doubao_seed21_lite_video_r3.json`，使用 Base64。不带 `--apply` 仅做本地准备；`--apply` 才允许请求；成功结果续跑复用，不自动重试。

```bash
# 默认准备原有首段，不访问方舟。
./env/bin/python project/scripts/run_doubao_video_r3.py

# 原有五段的续跑入口；仅在明确需要续跑时使用。
source ~/.config/seed-caption/env
./env/bin/python project/scripts/run_doubao_video_r3.py --all --apply
```

Files 传输适配、上传缓存和只读报告能力保留。单段默认记录对应配置为 `configs/doubao_files_default_sub01_20261007.json`；`configs/doubao_seed21_lite_video_r3_files.json` 仅保留为后续五段实验模板，不是当前默认入口，也未完成这份模板的五段运行。后续扩大 Files 测试需另行确定范围并使用新的运行编号，不覆盖已有六条记录。

Files 源片段先导出为无音频 MP4，再上传并等待 active，最后通过 file_id 调用 Chat API。有效 file_id 可复用；上传或请求结果不确定时停止，不自动重试。文件默认有效期 7 天，本轮未删除远端 Files，也未新增上传或模型调用。
