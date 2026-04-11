import os
from pathlib import Path


def load_env_file(file_name: str = ".env", override: bool = False) -> None:
    """读取 .env 并注入到 os.environ。

    查找顺序：
    1) 当前模块目录（Knowlwdge_graph/.env）
    2) 上级目录（工作区根目录 .env）
    3) 当前工作目录（运行脚本所在目录 .env）
    """
    module_dir = Path(__file__).resolve().parent
    candidates = [
        module_dir / file_name,
        module_dir.parent / file_name,
        Path.cwd() / file_name,
    ]

    env_path = next((p for p in candidates if p.exists()), None)
    if env_path is None:
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if not key:
            continue
        if key in os.environ and not override:
            continue
        os.environ[key] = value
