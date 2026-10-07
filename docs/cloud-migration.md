# 云端 mentor 看板发布

云端固定展示 v2.1 的已生成结果：10 个样本、138 个原始子片段，Qwen off 138 条和首片段 low/medium/xhigh 各 10 条，豆包 off 84 条和首片段 on 10 条，共 262 条成功 caption。豆包 off 的另外 54 个片段显示“待生成”。服务器本地看板仍可切换 v1、v2、v2.1。

Caption 用 CFS 高清视频生成。云端复用 R2 已有的 60 路 800×650 展示视频；Qwen 抽帧在发布时另做最长边 640、质量 75 的 JPEG 副本。豆包请求 2 fps，服务端实际抽帧未知。云端不保存模型密钥、MCAP、权重、高清 PNG 或输入张量，也不触发推理。

## 发布命令

在 pku_a800 执行；凭据只从已忽略的 `.cloudflare.env` 加载：

```bash
cd /root/workspace/video-caption-local/project/dashboard
source .cloudflare.env
export PATH="/tmp/node-v22.16.0-linux-x64/bin:$PATH"

../../env/bin/python scripts/publish_mentor.py --config ../configs/cloud_dashboard_v21.json
MCAP_UPLOAD_WORKERS=4 ../../env/bin/python scripts/publish_mentor.py --config ../configs/cloud_dashboard_v21.json --apply
npm test
npm run build
./node_modules/.bin/wrangler pages deploy dist --project-name video-caption-dashboard --branch main
../../env/bin/python scripts/publish_mentor.py --config ../configs/cloud_dashboard_v21.json --apply --activate
```

第一步只在服务器准备 JPEG，并只读查询 D1/R2：检查样本、138 个片段、828 个任务、60 个视频及新旧对象容量。8 GB 是项目发布保护值，并非账户计费硬限制。`--apply` 冻结 262 条 `run_id/task_id/result_id`、备存原展示配置，增量上传 JPEG、写 D1 并回读验证；旧页面仍展示此前稳定版。部署兼容页面后，`--activate` 要求所有对象与记录已暂存且结果身份未变化，最后才切换 `presentation.run_ids` 与 `fixed_prompt_id`。运行命令幂等，不会重新上传视频或覆盖已有评价。

发布状态在 `dashboard/.local/cloud-sampling/mentor-v2_1/`：`cloud-preflight.json`、`release-manifest.json`、`previous-publication.json`。增量报告在 `reports/cloud/cloud-v21-partial-publication.json`。旧运行和旧评价保存在 D1，当前 mentor 页只读取六个 v2.1 运行。布局、视频或模型结果需要更新时，仍按预演、暂存、部署、激活的顺序执行，并使用新的结果身份；本次已停止的豆包请求不会因发布而重启。

## 验收与回退

打开 https://video-caption-dashboard.pages.dev/ ，核对六个运行、262 条成功结果、十个样本、六路视频、首片段思考切换、后续片段仅 off、“仅看有结果”、采样图片、评价目标和 CSV。公开页面没有版本选择、服务器绝对路径或原始思考文本。评价写入绑定当前 `run_id/task_id/result_id`；未生成的豆包位置不能进行模型评价。

若激活后公开页面异常，先运行 `../../env/bin/python scripts/rollback_mentor_v21.py` 预览回退目标，再运行同一命令并加 `--apply`，恢复先前展示配置；新暂存对象和记录保留。公开网页无需服务器、Mac 或 SSH 保持运行；服务器本地网页则需要 SSH 端口转发。
