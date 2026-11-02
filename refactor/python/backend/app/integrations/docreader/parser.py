"""文档解析与分块。

生产环境由 `docreader/`（Python gRPC 服务）承担，本模块提供同契约的本地实现，
保证在没有 grpc 服务时全链路仍可运行：

- `.md` / `.txt` / `.markdown` / `.csv` / `.json`：按 UTF-8 直接读取
- `.pdf`：pypdf 抽取文本
- `.docx`：python-docx 抽取段落

分块策略对齐 `docreader/splitter`：按段落聚合到 `chunk_size`，保留 `chunk_overlap`。
"""

from __future__ import annotations

import io
import re
from pathlib import Path

from app.core.errors import ERR_BAD_REQUEST, AppError

TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".csv", ".json", ".log", ".yaml", ".yml"}


def parse_document(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()

    if suffix in TEXT_SUFFIXES:
        return content.decode("utf-8", errors="ignore")

    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)

    if suffix == ".docx":
        from docx import Document

        document = Document(io.BytesIO(content))
        return "\n\n".join(p.text for p in document.paragraphs)

    raise AppError(
        ERR_BAD_REQUEST,
        f"unsupported file type: {suffix or 'unknown'}",
        400,
    )


def split_text(
    text: str, chunk_size: int = 600, chunk_overlap: int = 80
) -> list[str]:
    """按段落聚合分块，超长段落再按句子切分。"""
    text = re.sub(r"\r\n?", "\n", text).strip()
    if not text:
        return []

    chunk_size = max(100, chunk_size)
    chunk_overlap = max(0, min(chunk_overlap, chunk_size // 2))

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    units: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= chunk_size:
            units.append(paragraph)
            continue
        sentences = [s for s in re.split(r"(?<=[。！？.!?])\s*", paragraph) if s.strip()]
        buffer = ""
        for sentence in sentences:
            if len(buffer) + len(sentence) <= chunk_size:
                buffer += sentence
            else:
                if buffer:
                    units.append(buffer)
                buffer = sentence
        if buffer:
            units.append(buffer)

    chunks: list[str] = []
    current = ""
    for unit in units:
        if not current:
            current = unit
        elif len(current) + 2 + len(unit) <= chunk_size:
            current = f"{current}\n\n{unit}"
        else:
            chunks.append(current)
            tail = current[-chunk_overlap:] if chunk_overlap else ""
            current = f"{tail}{unit}" if tail else unit
    if current:
        chunks.append(current)

    return [c.strip() for c in chunks if c.strip()]
