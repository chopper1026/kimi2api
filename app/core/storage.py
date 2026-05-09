import json
import os
from typing import Any, Optional

from ..config import Config


def data_path(*parts: str) -> str:
    return os.path.join(Config.DATA_DIR, *parts)


def ensure_data_dir() -> None:
    os.makedirs(Config.DATA_DIR, exist_ok=True)


def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def atomic_write_json(path: str, data: Any, *, mode: Optional[int] = None) -> None:
    ensure_data_dir()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    if mode is not None:
        os.chmod(path, mode)


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def atomic_write_text(path: str, content: str, *, mode: Optional[int] = None) -> None:
    ensure_data_dir()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, path)
    if mode is not None:
        os.chmod(path, mode)
