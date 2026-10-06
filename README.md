# Video Caption System

面向多相机 MCAP 数据的可追溯视频 caption 系统。系统按照原始
`sub_segments_info` 边界建立稳定任务，保留六路相机用于人工核对，并支持
Qwen 本地推理、豆包 API、结果版本管理、本地看板及 Cloudflare mentor 看板。

## Repository scope

本仓库只保存代码、Prompt、配置模板、测试、必要的元数据和网页源码。以下内容不进入 Git：

- 原始 MCAP、提取视频、模型权重和云端视频副本；
- `runs/` 中的抽帧、输入张量、模型输出和运行日志；
- `reports/` 中可重新生成的报告与截图；
- API Token、Cloudflare 凭据、本地评价数据库和前端构建产物。

这些大文件继续由 CFS、BOS 或 R2 管理。仓库中的配置和元数据不包含视频或权重本体。

## Structure

```text
src/caption_system/   MCAP、视频、模型、流水线与结果管理
scripts/              命令入口
configs/              实验配置与本机路径模板
prompts/              当前 Prompt 与后续模块
metadata/             稳定样本、片段与任务索引
tests/                Python 测试
dashboard/            React 前端、Pages Functions 与 D1 migrations
docs/                 设计、运行和部署说明
third_party/          固定版本的第三方工具
```

## Setup

初始化第三方依赖：

```bash
git submodule update --init --recursive
git -C third_party/das-datakit apply ../../docs/patches/das-datakit-mcap-decoder.patch
```

创建 Python 环境，并根据服务器 CUDA 版本安装相符的 PyTorch 构建：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

复制本机路径配置：

```bash
cp configs/paths.example.json configs/paths.json
```

编辑 `configs/paths.json`，或使用下列环境变量覆盖对应值：

```text
CAPTION_DATASET_ROOT
CAPTION_MEDIA_ROOT
CAPTION_MODEL_PATH
CAPTION_PROXY_ROOT
```

`configs/paths.json` 只属于当前机器，已被 Git 忽略。API 凭据也只从环境变量读取，不能写入仓库。

## Validation

在仓库根目录执行：

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
cd dashboard && npm ci && npm test && npm run build
```

## Usage

本地看板：

```bash
.venv/bin/python scripts/serve_dashboard.py
```

通用 caption 入口：

```bash
.venv/bin/python scripts/caption.py --help
```

当前实验设计、续跑规则和云端发布方式见 [docs/README.md](docs/README.md)。

## Data and secrets

仓库不得提交 MCAP、视频、权重、运行张量、人工评价数据库或任何访问凭据。
Cloudflare 凭据保存在 `dashboard/.cloudflare.env`，豆包凭据由服务器环境提供；二者均已排除在版本控制之外。
