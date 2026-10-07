# v3 第一组：独立 5 秒窗口

本组仅选 10 个样本各自第一个原始子片段的 camera2。保持 v2.1 的 Qwen 官方非思考采样、2 fps、每帧 512000 像素、高清源视频和 512 token 最终描述上限。每个窗口只看自己的画面，不读取原始标注或前一窗口 caption；多窗口由同一 Qwen 模型根据已保存的窗口文字汇总。正式任务仍是原始子片段，不改变片段边界。

运行编号为 `qwen-first10-v3-w5-off-r1`，配置见 `configs/v3_first_windows.json`。最终窗口 Prompt 和汇总 Prompt 分别见 `prompts/v3_window_r1.txt`、`prompts/v3_summary_r1.txt`，运行时的文本快照保存在 `runs/qwen-first10-v3-w5-off-r1/config.json`。十条片段共 17 个窗口；五条多窗口片段另有五次汇总，因此总计 22 次本地模型调用。

在仓库根目录运行以下命令。默认只打印计划；准备阶段不调用 GPU。已成功的正式结果会复用，失败结果需要检查后显式使用 `--retry-failed`。

```bash
env/bin/python project/scripts/run_v3_window_off.py
env/bin/python project/scripts/run_v3_window_off.py --phase prepare
env/bin/python project/scripts/run_v3_window_off.py --phase run --max-calls 22
env/bin/python project/scripts/report_v3_window_off.py
```

结果和窗口版本保存在 `project/runs/qwen-first10-v3-w5-off-r1/`；高分辨率采样图与处理器张量在 CFS 的配置缓存目录。对照报告见 `project/reports/experiments/v3_window_off/comparison.md`，逐条人工检查表见同目录 `review.csv`。本地看板选择“v3 · 5 秒窗口试验”，在“窗口结果与追溯”展开各窗口。v2.1 仍可切换查看，云端 mentor 版未更新。

本轮五条不超过 5 秒的片段并未真正切分，只检验直接采用窗口结果的路径。其余五条同时改变了窗口 Prompt 的观察范围措辞，随机种子按窗口任务身份派生，多窗口还增加了文字汇总；与 v2.1 的差异不能严格只归因于切分。生成成功只表示技术链路完整，事实准确性需结合连续视频人工裁定。
