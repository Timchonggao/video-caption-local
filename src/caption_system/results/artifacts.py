"""Resolve local or explicitly configured CFS artifacts without allowing traversal."""
from pathlib import Path
from caption_system.config import PATHS


def artifact_directory(directory, config):
    directory = Path(directory)
    root = config.get('artifact_root')
    if not root:
        return directory / 'artifacts'
    base = Path(root).resolve()
    allowed = Path(PATHS['cache_root']).resolve()
    if not base.is_relative_to(allowed):
        raise ValueError('Artifact root must be inside configured CFS cache_root')
    return base / directory.name


def initialize_artifacts(directory, config):
    expected = artifact_directory(directory, config)
    expected.mkdir(parents=True, exist_ok=True)
    link = Path(directory) / 'artifacts'
    if config.get('artifact_root'):
        if link.is_symlink():
            if link.resolve() != expected.resolve():raise ValueError('Artifact link changed')
        elif link.exists():raise ValueError('External artifacts require a new run')
        else:link.symlink_to(expected, target_is_directory=True)
    return expected


def resolve_artifact(directory, relative):
    import json
    directory = Path(directory)
    relative = Path(relative)
    if relative.is_absolute() or not relative.parts or relative.parts[0] != 'artifacts' or '..' in relative.parts:
        raise ValueError('Invalid artifact path')
    config = json.loads((directory / 'config.json').read_text())
    allowed = artifact_directory(directory, config).resolve()
    path = (directory / relative).resolve()
    if not path.is_relative_to(allowed):raise ValueError('Artifact escapes configured directory')
    return path
