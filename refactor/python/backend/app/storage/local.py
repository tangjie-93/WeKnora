"""本地文件存储，对应 Go 端 `service/file/local.go`。

路径约定：`{root}/{tenant_id}/{knowledge_id}/{filename}`
"""

from __future__ import annotations

import re
from pathlib import Path

from app.core.config import PYTHON_DIR

ROOT = PYTHON_DIR / "data" / "uploads"


def _safe(name: str) -> str:
    cleaned = re.sub(r"[^\w.\-]+", "_", name).strip("._")
    return cleaned or "file"


def save_bytes(tenant_id: int, knowledge_id: str, filename: str, content: bytes) -> str:
    target_dir = ROOT / str(tenant_id) / knowledge_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / _safe(filename)
    target.write_bytes(content)
    # 与 Go 端一致：返回可持久化的引用路径
    return f"local://{tenant_id}/{knowledge_id}/{target.name}"


def read_bytes(file_path: str) -> bytes:
    return resolve(file_path).read_bytes()


def resolve(file_path: str) -> Path:
    if file_path.startswith("local://"):
        relative = file_path.removeprefix("local://")
        return ROOT / relative
    return Path(file_path)


def delete(file_path: str) -> None:
    try:
        resolve(file_path).unlink(missing_ok=True)
    except OSError:
        pass
