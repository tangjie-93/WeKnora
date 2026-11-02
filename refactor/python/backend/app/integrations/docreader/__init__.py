"""docreader 集成。

当前阶段使用本地解析器（`parser.py`）实现与 docreader 相同的输入输出契约。
接入 gRPC 时，只需替换本模块的 `parse_and_split` 实现为调用 `docreader/proto`。
"""

from __future__ import annotations

from app.integrations.docreader.parser import parse_document, split_text

__all__ = ["parse_and_split", "parse_document", "split_text"]


def parse_and_split(
    filename: str, content: bytes, chunk_size: int = 600, chunk_overlap: int = 80
) -> tuple[str, list[str]]:
    text = parse_document(filename, content)
    return text, split_text(text, chunk_size, chunk_overlap)
