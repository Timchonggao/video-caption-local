#!/usr/bin/env python3

import argparse
import importlib.util
import os
import sys
from pathlib import Path

# 当前服务器的工作目录
DEFAULT_LOCAL_WORK = Path(
    os.environ.get(
        "LOCAL_WORK",
        "/root/workspace/video-caption-local",
    )
)

# 使用当前已经存在的 Hugging Face 缓存
DEFAULT_CACHE_DIR = Path(
    os.environ.get(
        "HF_HUB_CACHE",
        DEFAULT_LOCAL_WORK / "huggingface" / "hub",
    )
)

# 当前服务器可以访问国内镜像，官方 huggingface.co 不可达
DEFAULT_ENDPOINT = os.environ.get(
    "HF_ENDPOINT",
    "https://hf-mirror.com",
)

# 在导入 huggingface_hub 之前设置环境变量
os.environ.setdefault("HF_HOME", str(DEFAULT_LOCAL_WORK / "huggingface"))
os.environ.setdefault("HF_HUB_CACHE", str(DEFAULT_CACHE_DIR))

from huggingface_hub import snapshot_download


HF_REPOS = {
    "qwen38": {
        "repo_id": "Qwen/Qwen3.8-27B",
        "description": "Qwen3.8-27B 视频理解模型",
    },
}


def check_environment(endpoint: str, cache_dir: Path, workers: int):
    """检查当前下载环境。"""
    print("\n" + "=" * 70)
    print("下载环境")
    print("=" * 70)
    print(f"Python:       {sys.executable}")
    print(f"Endpoint:     {endpoint}")
    print(f"Cache dir:    {cache_dir}")
    print(f"Workers:      {workers}")
    print(f"HF_HOME:      {os.environ.get('HF_HOME')}")
    print(f"HF_HUB_CACHE: {os.environ.get('HF_HUB_CACHE')}")

    hf_xet_installed = importlib.util.find_spec("hf_xet") is not None
    print(f"hf-xet:       {'installed' if hf_xet_installed else 'not installed'}")

    if hf_xet_installed and endpoint == "https://hf-mirror.com":
        print(
            "\n警告：当前环境安装了 hf-xet，"
            "镜像站下载可能再次进入 Xet 路径。"
        )

    cache_dir.mkdir(parents=True, exist_ok=True)


def show_dry_run(
    repo_id: str,
    endpoint: str,
    cache_dir: Path,
    workers: int,
):
    """只查看还需要下载哪些文件，不真正下载。"""
    print("\n正在检查缓存和待下载文件……")

    files = snapshot_download(
        repo_id=repo_id,
        endpoint=endpoint,
        cache_dir=str(cache_dir),
        max_workers=workers,
        dry_run=True,
    )

    pending = []
    total_bytes = 0

    for item in files:
        filename = getattr(item, "filename", "")
        file_size = getattr(item, "file_size", 0) or 0
        will_download = getattr(item, "will_download", False)

        if will_download:
            pending.append((filename, file_size))
            total_bytes += file_size

    print(f"\n待下载文件数量: {len(pending)}")
    print(f"待下载大小:     {total_bytes / 1024**3:.2f} GiB")

    for filename, file_size in pending:
        print(f"  {filename:<55} {file_size / 1024**3:.2f} GiB")


def download_repo(
    name: str,
    endpoint: str,
    cache_dir: Path,
    workers: int,
):
    """下载指定模型仓库，并复用已有缓存。"""
    config = HF_REPOS[name]
    repo_id = config["repo_id"]

    print("\n" + "=" * 70)
    print(f"开始下载: {config['description']}")
    print(f"Repo:     {repo_id}")
    print(f"Cache:    {cache_dir}")
    print("=" * 70)

    try:
        snapshot_path = snapshot_download(
            repo_id=repo_id,
            endpoint=endpoint,
            cache_dir=str(cache_dir),
            max_workers=workers,
        )

        print("\n下载完成")
        print(f"Snapshot path: {snapshot_path}")
        return Path(snapshot_path)

    except KeyboardInterrupt:
        print("\n下载被手动中断。已有内容会保留，下次运行会继续断点下载。")
        return None

    except Exception as error:
        print(f"\n下载失败: {type(error).__name__}: {error}")
        return None


def create_symlink(snapshot_path: Path, link_path: Path):
    """
    可选：创建一个便于使用的软链接。
    不复制权重，不额外占用几十 GB 磁盘空间。
    """
    link_path.parent.mkdir(parents=True, exist_ok=True)

    if link_path.exists() or link_path.is_symlink():
        if link_path.is_symlink() and link_path.resolve() == snapshot_path.resolve():
            print(f"软链接已存在: {link_path}")
            return

        raise FileExistsError(
            f"目标路径已存在，未覆盖: {link_path}"
        )

    link_path.symlink_to(snapshot_path, target_is_directory=True)
    print(f"已创建软链接: {link_path} -> {snapshot_path}")


def main():
    parser = argparse.ArgumentParser(
        description="在百度 A800 开发机上下载 Qwen3.8-27B 权重"
    )

    parser.add_argument(
        "--target",
        choices=["qwen38"],
        default="qwen38",
        help="下载目标，默认 qwen38",
    )

    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help=f"缓存目录，默认 {DEFAULT_CACHE_DIR}",
    )

    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help=f"下载地址，默认 {DEFAULT_ENDPOINT}",
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=2,
        help="并行下载文件数，默认 2。网络稳定时可尝试 4",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只检查还需要下载哪些文件，不真正下载",
    )

    parser.add_argument(
        "--link-dir",
        type=Path,
        default=None,
        help=(
            "下载完成后创建软链接，例如 "
            "/root/workspace/video-caption-local/models/Qwen3.8-27B"
        ),
    )

    args = parser.parse_args()

    if args.workers < 1:
        parser.error("--workers 必须大于等于 1")

    check_environment(
        endpoint=args.endpoint,
        cache_dir=args.cache_dir,
        workers=args.workers,
    )

    repo_id = HF_REPOS[args.target]["repo_id"]

    if args.dry_run:
        show_dry_run(
            repo_id=repo_id,
            endpoint=args.endpoint,
            cache_dir=args.cache_dir,
            workers=args.workers,
        )
        return

    snapshot_path = download_repo(
        name=args.target,
        endpoint=args.endpoint,
        cache_dir=args.cache_dir,
        workers=args.workers,
    )

    if snapshot_path is None:
        raise SystemExit(1)

    if args.link_dir is not None:
        create_symlink(snapshot_path, args.link_dir)

    print("\n模型已经可以用于后续部署。")
    print(f"模型路径: {snapshot_path}")


if __name__ == "__main__":
    main()

# 环境变量配置
# source /root/workspace/video-caption-local/env/bin/activate
# export LOCAL_WORK=/root/workspace/video-caption-local
# export HF_ENDPOINT=https://hf-mirror.com
# export HF_HOME="$LOCAL_WORK/huggingface"
# export HF_HUB_CACHE="$LOCAL_WORK/huggingface/hub"
# export HF_HUB_DISABLE_XET=1

# 先查看还缺哪些文件：
# python HF_download_server.py --dry-run

# 然后开始断点下载：
# python HF_download_server.py --workers 2

# 生成一个易记的模型路径，可以使用软链接：
# python HF_download_server.py \
#   --workers 2 \
#   --link-dir /root/workspace/video-caption-local/models/Qwen3.8-27B
# 软链接不会复制权重，实际模型仍然位于 Hugging Face 缓存中，因此不会额外占用约 50GB 磁盘空间。
# 后续加载模型时可以使用脚本输出的 Snapshot path，或者使用软链接路径。
