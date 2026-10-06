# Seed 2.1 Lite 视频 caption

## 当前 Files API 设计（2026-10-06）

入口默认读取 configs/doubao_seed21_lite_video_r3_files.json，独立运行编号 doubao-seed21-lite-sample01-video-r3-files。流程为：按原始子片段导出无音频高清视频 → 流式上传 Files API → 等待状态 active → Chat API 通过 video_url.file_id 引用。无需另建 TOS Bucket，也不向公开看板上传原件。

固定 Seed 2.1 Lite、camera2、r3、5 fps、thinking disabled、max_tokens=4096。temperature/top_p 不传，保持服务默认。新运行不记录未生效的 frames/max_pixels；实际处理尺寸和采样帧未知。窗口、标注背景和历史本轮不引入。

配置中的 min_frame_tokens、max_frame_tokens、max_video_tokens 默认 null，表示不传、沿用服务策略。填写正整数后，入口将其放入上传请求的 preprocess_configs.video。当前 Files 上传路径已实测并加入校验：min_frame_tokens 为16–128，max_frame_tokens 为128–640；这些范围来自真实错误响应，不直接套用原生视频策略或embedding文档。max_video_tokens=81920已通过，完整取值范围仍由方舟校验。更改预算必须使用新 run_id。可选 CLI 参数同名，使用连字符，如 --max-frame-tokens。

2026-10-07 的单段探索见 reports/experiments/doubao-files-visual-budget-exploration-sub01-20261007.md。显式128/384/81920输入6880 token，128/640/81920输入10975 token，与默认组相同；两档参数均有完整回显，但实际处理尺寸仍未知。640未显示比默认更多的输入用量，事实错误仍在，不能将其称为已经验证的准确性升级。旧结果不变，本轮仅新增两次caption请求，没有发布云端。

### 启动与续跑

从 pku_a800 仓库根目录执行：

```bash
# 只准备首段：导出视频和保存请求模板，不上传、不推理。
./env/bin/python project/scripts/run_doubao_video_r3.py

# --all 不带 --apply 可准备五段；首次真实验证仅一条。
source ~/.config/seed-caption/env
./env/bin/python project/scripts/run_doubao_video_r3.py --apply

# 首条本次 Files 结果成功且未截断后，才允许扩展五段。
./env/bin/python project/scripts/run_doubao_video_r3.py --all --apply

# 只读取已保存结果并生成资源报告，不调用 API。
./env/bin/python project/scripts/report_doubao_files.py
```

--config 可指定复制并修改后的配置文件。没有 --apply 的准备阶段不会访问 Files API。旧 Base64 模式仍可显式使用 --video-transport base64；旧配置/结果不可覆盖，先前 output4096 配置也继续保留。

每个输入目录保存 source_clip.mp4、不可变 request.json（file_id 是本地占位符）、ark_file.json（实际 ID/状态/过期时间/预处理回显）和实际提交的 resolved_request.json。上传前校验视频哈希；multipart 分块读取，不将完整视频编码进 JSON。默认单文件保护 512 MB，文件有效期 7 天，可配置 1–30 天；默认等待处理 300 秒，每 2 秒查询状态。

已有有效 file_id 会先查询状态，再复用；成功 caption 续跑不再请求模型。处理超时保留 file_id，重新显式运行可以继续等待，不重复上传。预处理失败、文件过期/被删除或回显参数不一致会停止提交 caption，不静默重传或降低预算。上传/推理的网络结果不确定时不自动重试；确认后可用 --retry-unknown 显式承认可能存在已接受的请求。过期文件需要新运行重新上传。现阶段不自动删除远端文件。

结果记录 model_call_attempted、实际文件元数据、请求的预处理配置、上传/处理等待/caption 请求阶段耗时，以及包括这些阶段的 generation_seconds。elapsed_seconds 还包含本地准备与校验。文件回显缺少预算字段时 preprocessing_echo_verified=false，不把“参数已接受”写成“已验证实际视觉分辨率”。采样仍标为 provider_sampling_known=false，不能把原视频帧当作服务端实际观察帧。

教程与字段依据：[Files API](https://docs.volcengine.com/docs/ark/file-api?lang=zh)、[视频理解](https://docs.volcengine.com/docs/ark/video-understanding?lang=zh)、[官方 SDK 视频预处理类型](https://github.com/volcengine/volcengine-python-sdk/blob/master/volcenginesdkarkruntime/types/file_create_params.py)。代码已做离线模拟测试，尚未验证账号实际上传权限、预算上限或产生新的 caption。

## 已完成的旧 Base64 记录

配置：configs/doubao_seed21_lite_video_r3.json；运行：doubao-seed21-lite-sample01-video-r3。使用原六部分 r3，camera2，原始子片段无音频，Base64 MP4，Chat API，请求 5 fps，thinking disabled，512 token 上限。

已完成首段一次验证及另外四段，共 5 次请求，无自动重试。实际服务端帧数和处理尺寸未知；上传源视频保持 1600×1300，不能宣称模型使用相同尺寸。视频文件小于 50 MB，请求体小于 64 MB，并受配置 63 MB 保护。首条成功且不截断后才允许五段扩展，准备或请求异常会保存记录并停止。

在 pku_a800 仓库根目录执行（凭据仅服务器配置，不写入日志或运行配置）：

```bash
source ~/.config/seed-caption/env
./env/bin/python project/scripts/run_doubao_video_r3.py
./env/bin/python project/scripts/run_doubao_video_r3.py --apply
./env/bin/python project/scripts/run_doubao_video_r3.py --all --apply
```

默认只准备首段，不发送 API；--apply 才请求。成功结果续跑复用。超时记为 unknown_remote_outcome，不自动重试；人工确认后通过通用 CLI 的 --retry-unknown 明确处理，避免重复请求。修改代码/配置后使用新 run_id，不能修改旧运行的代码哈希。

报告入口：scripts/report_doubao_video_r3.py。本地网页选择 v2、camera2、豆包，查看当前运行；输入/输出 token 为实际返回用量，耗时为含传输的 API 往返，显存不可见，不伪装为 0。采样区说明服务端实际帧未返回，不把本地源视频帧当作模型观察。

结果位于 reports/experiments/doubao-seed21-lite-video-r3.md 和同名 JSON。语义质量需要用户确认；没执行严格同帧图片对照、没扩大到 24 条，未发布云端。
