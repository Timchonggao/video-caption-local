# v2.1 运行与部分结果发布

本轮在 pku_a800 生成 10 个样本的全部 138 个原始子片段 × camera2。整段视频输入，2 fps，六部分 r3；不使用标注、历史或窗口。每个样本按源时间排序的第一个片段另做思考对照。

计划为 Qwen 168 条、豆包 148 条。Qwen 已完成；豆包按用户要求停止，off 成功 84 条、失败 1 条、未运行 53 条，on 成功 10 条。公开 mentor 看板已发布 **262 条成功结果**，缺失的豆包 off 显示“待生成”。运行配置和任务选择在 `configs/full_v21.json`，实际 Prompt、代码哈希、采样参数冻结于各运行的 `config.json`。

## 运行与续跑

在仓库根目录执行：

```bash
# 只查看范围，不准备输入、不调用模型。
./env/bin/python project/scripts/run_full_v21.py

# 规定的试跑：首片段各档位，以及最长片段 off。
source ~/.config/seed-caption/env
./env/bin/python -u project/scripts/run_full_v21.py --phase pilot --apply

# 试跑通过后，全量续跑；已有成功结果不新增调用。
./env/bin/python -u project/scripts/run_full_v21.py --phase full --apply

# 可只运行一种模型；例如 --provider qwen 或 --provider doubao。
./env/bin/python project/scripts/report_full_v21.py --require-complete
```

大体积采样图、CPU 张量及共享视频导出保存在配置的 CFS cache_root；项目 `runs/` 保存配置、输入清单、结果、日志、活动版本和调用记录，artifacts 通过受校验的链接引用 CFS。CFS 读取器只允许配置内的该运行目录，不接受任意文件路径。

Qwen 采用官方四档采样，基础种子 20261006 按 task_id 派生；2 GiB 输入保护、每帧 512000 像素、总生成 4096 token、最终 caption 512 token。各档位独立保存相同首片段的真实 PTS 证据。低帧率无法保证捕获所有短动作，事实质量需结合完整视频人工检查。

豆包使用 Chat API 的默认生成采样，2 fps 请求；off 输出上限 512 token，on 4096 token。满足文件小于 50 MB 且完整 Base64 请求小于 63 MB 时选 Base64，否则 Files。Files 只设置 fps，不配置视觉 token 预算。off/on 复用同一份无音频高清视频，已激活 file_id 可共享。服务端实际采样帧和尺寸未知，不把本地视频元数据当成模型观察证据。

没有累计费用停止阈值。费用估算采用报告注明的公开单价，实际账单为准。未知远端请求结果不自动重试；失败与截断保留，不能当成功。受控重试需查明原因并显式选择，不以续跑隐式重发付费请求。

## 查看与发布

本地网页选择 v2.1；首片段显示多档思考及并排对照，其他片段仅 off。原有 v2 结果保留用于迭代比较。模型评价始终绑定具体 run_id/task_id/result_id。

`reports/experiments/v2_1/summary.md`、同名 JSON 和 `comparisons.csv` 汇总身份、缺口、耗时、token、显存及费用。

本次固定 262 条成功结果，使用 `configs/cloud_dashboard_v21.json` 分阶段暂存和激活；公开发布与回退详情见 [云端说明](cloud-migration.md)：

```bash
cd project/dashboard
source .cloudflare.env
export PATH="/tmp/node-v22.16.0-linux-x64/bin:$PATH"
../../env/bin/python scripts/publish_mentor.py --config ../configs/cloud_dashboard_v21.json
../../env/bin/python scripts/publish_mentor.py --config ../configs/cloud_dashboard_v21.json --apply
npm test
npm run build
./node_modules/.bin/wrangler pages deploy dist --project-name video-caption-dashboard --branch main
../../env/bin/python scripts/publish_mentor.py --config ../configs/cloud_dashboard_v21.json --apply --activate
```

云端固定当前稳定结果，不显示版本选择；旧后台结果和评价保留。复用已上传的 60 路低清视频，只增加结果及最长边 640、质量 75 的 JPEG 采样图。R2 发布前核对已有对象与新增字节，维持 8 GB 项目保护值。数据与采样写入核验完毕后才切换公开展示。

## 并行执行

2026-10-07 用户批准将剩余组并行运行，之后明确停止豆包 off。以下命令仅作历史运行入口记录，**当前不要执行豆包续跑**。每个运行有独立锁、单请求并发和成功结果复用，不要为同一运行重复开进程。

```bash
source ~/.config/seed-caption/env
./env/bin/python -u project/scripts/run_full_v21.py --phase full --provider doubao --mode off --apply
# 在另一个服务器终端执行：
./env/bin/python -u project/scripts/run_full_v21.py --phase full --provider doubao --mode on --apply
```

并行后，各组累计耗时可能重叠，不能相加当作整体墙钟时间。
