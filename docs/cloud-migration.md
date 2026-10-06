# 云端 mentor 看板与本地实验看板

页面共享 React 代码，展示设置来自接口。服务器本地保留 v1/v2 和当前实验选择；云端固定展示当前 v2，隐藏“Prompt 版本”、版本选项和实验说明文字。Qwen 默认关闭思考，保留 low/medium/xhigh 与并排对照；豆包使用已保存的 Seed 2.1 Lite 结果。

当前云端选择由 configs/cloud_dashboard.json 定义：sample_01 的五个 camera2 原始子片段，Qwen 四档共 20 条、豆包 5 条。其余片段显示待生成，没有网页推理或自动 API 请求。所有样本和六路相机仍可浏览。

## 高清推理与云端展示副本

服务器推理和 SSH 转发网页读取 CFS 高清视频。云端复用 half-v1 的 60 路低清展示视频，宽高各减半（1600×1300 → 800×650），时间轴及原始子片段边界保持一致。

云端采样图为最长边 640、质量 75 的 JPEG。Qwen 的四档输入帧相同，840 个帧引用去重为 210 个对象，约 11.3 MB；模型实际处理尺寸仍记录为 768×640，PNG 原图与输入张量只留在服务器。豆包实际采样由服务端管理，没有伪装成已知抽帧图；保留请求 5 fps、高清上传源片段尺寸和无音频信息。

本次不上传或重新编码任何视频，不上传 MCAP、权重、音频、传感器归档、高清 PNG 或输入张量。

## 发布当前稳定方案

在 pku_a800 的 project/dashboard 执行。凭据仅从已忽略的 .cloudflare.env 加载，不放入网页、代码或日志。

```bash
bash
cd /root/workspace/video-caption-local/project/dashboard
source .cloudflare.env
export PATH="/tmp/node-v22.16.0-linux-x64/bin:$PATH"
../../env/bin/python scripts/publish_mentor.py
MCAP_UPLOAD_WORKERS=6 ../../env/bin/python scripts/publish_mentor.py --apply
npm run build
./node_modules/.bin/wrangler pages deploy dist --project-name video-caption-dashboard --branch main
../../env/bin/python scripts/publish_mentor.py --apply --activate
```

第一条 Python 命令只准备 JPEG 和发布计划；--apply 校验任务、已有 60 路低清视频、不可变结果及 R2 8 GB 项目保护阈值，上传新增 JPEG 并写入 D1，不立即切换展示。所有数据写完并核对后，部署兼容的前端和 Pages Functions，再使用 --activate 切换公开选择。重复执行复用相同对象和记录，结果不同必须使用新的运行编号。

旧 v1 的结果、采样对象和人工评价不删除。cs_dashboard.run_ids 保留发布登记，presentation.run_ids 定义 mentor 实际可见的五个运行，presentation.fixed_prompt_id 固定当前方案。cs_results、cs_sampling 和 cs_reviews 的身份继续由 run_id/task_id/result_id 关联，评价维度与本地一致，CSV 保留历史记录。

公开网址：https://video-caption-dashboard.pages.dev/ 。无需保持 pku_a800、Mac 或 SSH 运行。仅在服务器生成新结果不会自动更新网站。

## 验收

确认页面没有 Prompt 版本或 v1 选择；默认展示 Qwen 非思考，四档切换、并排对照和豆包结果正确。打开 seg02_sub01、sub02、sub10、sub11、sub12 查看本批结果，其余片段待生成。

验证相机展开/收起、视频播放与拖动、raw caption、原始 JSON、压缩采样图及真实时间映射。评价必须绑定当前显示的具体运行和结果版本，未生成结果不能评价；原始标注仍可独立评价。

更新报告和发布日志在 reports/cloud/cloud-v2-mentor-*。R2 的 8 GB 是本项目发布保护配置，不是账户免费额度的硬停止功能；后续发布仍检查实际对象容量和新增字节。

## 后续更新与维护

网站布局：修改共享前端后构建并部署，云端专属展示由 presentation 控制，本地不受影响。数据：沿用原始任务身份，新增低清视频时先准备并验证代理副本；本次已有视频不重传。模型结果：在 configs/cloud_dashboard.json 明确当前要公开的运行，再按上述分阶段流程更新。

publish_v1.py 和 publish.py 保留为旧数据维护工具，不作为当前 mentor 方案的发布入口。backup_cloud.py 为可选备份工具；不要求为本次展示切换备份或删除旧表。云端历史资料仍单独放在 reports/cloud/。

## 仅看有结果

本地与云端都在片段列表下方居中勾选“仅看有结果”，片段列表只显示当前样本、模型、运行模式、Prompt 和相机已经成功生成 caption 的片段。若当前片段不在列表中，会选中同一样本的首个有结果片段。没有结果时保留视频、原始标注和复选框，可以取消筛选。

复选框只筛选片段列表，不隐藏样本。取消勾选后恢复所有片段；编号仍表示原始样本中的位置。不提供导航、快捷下拉框、跳转按钮或结果状态徽标。本地与云端使用相同复选框；本地继续保留实验版本选择，云端固定当前 v2。

## 云端精简布局

模型选择单独排在第一行，显示 Qwen-3.8-27B 和 doubao-seed-2-1；豆包按钮悬停可查看实际 Lite 模型完整名称。相机 0–5 排在第二行。Qwen 通过四个按钮选择关闭思考、low、medium、xhigh，并通过“单组／并排”切换查看方式。并排固定以关闭思考作为一侧，与选定的开启档位比较；从关闭思考切入并排时默认使用 medium。

云端不显示实验进度或正文上的输入配置。输入方式、采样率和像素预算移入“采样输入”，该模块与“资源效率”使用相同字号。Qwen 的采样区保留帧数说明、展示副本说明、图片及相对片段起点时间；不显示采样证据来源和视频时间分组，原始追溯信息仍保存在 API／服务器输入记录中。本地保留实验版本和进度，但同样精简采样区显示；完整追溯仍保存于服务器/API。
