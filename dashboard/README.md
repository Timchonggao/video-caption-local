# 多相机 caption 看板

唯一系统说明见 ../docs/README.md。

main.tsx 为渲染入口，App.tsx 编排页面；components/ 分别负责样本栏、六路视频、片段选择、原始 JSON、模型结果和评价。hooks/ 管理数据读取与布局对齐；api.ts/types.ts 定义请求和数据合同。

本地服务：../scripts/serve_dashboard.py，从 ../metadata 和 CFS 读取数据，从 ../runs 读取结果；task_id/camera_id 用于结果和人工评价。

云端：functions/api/[[path]].ts、migrations/ 和 scripts/publish_mentor.py。configs/cloud_dashboard.json 定义 mentor 展示范围；D1 presentation 固定当前 v2，隐藏版本选择，保留 Qwen 四档和豆包。旧 v1 数据继续存储但不展示。视频使用低清副本，采样图使用压缩 JPEG；本地保留版本选择与高清输入。

当前公开五个片段的 25 条结果，部署与更新见 [云端说明](../docs/cloud-migration.md)。

本地与云端共用 CaptionPanel：模型在相机上方，四档思考按钮和单组／并排切换一致。“仅看有结果”居中放在片段列表下方，采样区精简为帧数、图片及相对时间；本地保留版本选择、实验进度和高清 PNG，云端固定 v2 并使用压缩 JPEG。原始采样证据仍保存在服务器/API。
