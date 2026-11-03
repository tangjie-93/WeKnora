"""生成可重复更新的 Python 重构进度快照。

在 `refactor/python/backend` 下运行：
    py -3.13 scripts/update_refactor_progress.py
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

PYTHON_DIR = Path(__file__).resolve().parents[1]
CONTRACT_DIR = PYTHON_DIR / "tests" / "contract"
MATRIX = CONTRACT_DIR / "route_matrix.md"
OUTPUT = CONTRACT_DIR / "progress_snapshot.md"
FRONTEND_DIR = PYTHON_DIR.parents[2] / "frontend" / "src"


def matrix_counts() -> tuple[int, int, int, list[str], list[str]]:
    text = MATRIX.read_text(encoding="utf-8")
    swagger = int(re.search(r"Swagger 接口：`?(\d+)", text).group(1))
    frontend = int(re.search(r"前端实际调用：`?(\d+)", text).group(1))
    implemented = int(re.search(r"Python 已实现：`?(\d+)", text).group(1))
    missing = []
    frontend_missing = []
    for line in text.splitlines():
        if not line.startswith("|") or not re.search(r"\|\s*—\s*\|\s*$", line):
            continue
        columns = [column.strip() for column in line.strip("|").split("|")]
        if len(columns) >= 2:
            missing.append(columns[1].strip("`"))
            if len(columns) >= 5 and columns[3] == "✅":
                frontend_missing.append(columns[1].strip("`"))
    return swagger, frontend, implemented, missing, frontend_missing


def stage_status() -> list[str]:
    rows = []
    for report in sorted(CONTRACT_DIR.glob("stage_report_*.md")):
        text = report.read_text(encoding="utf-8")
        stage = re.search(r"阶段：\*\*(.+?)\*\*", text)
        result = re.search(r"结果：\*\*(.+?)\*\*", text)
        rows.append(f"| `{report.stem.removeprefix('stage_report_')}` | {stage.group(1) if stage else '未标注'} | {result.group(1) if result else '未标注'} | `{report.name}` |")
    return rows


def frontend_counts() -> tuple[int, int, int, int]:
    def count(directory: Path, pattern: str) -> int:
        return sum(1 for path in directory.rglob(pattern) if path.is_file()) if directory.is_dir() else 0

    return (
        count(FRONTEND_DIR / "api", "*.ts"),
        count(FRONTEND_DIR / "views", "*.vue"),
        count(FRONTEND_DIR / "stores", "*.ts"),
        count(FRONTEND_DIR, "*.test.*"),
    )


def main() -> None:
    swagger, frontend, implemented, missing, frontend_missing = matrix_counts()
    frontend_api, frontend_views, frontend_stores, frontend_tests = frontend_counts()
    coverage = implemented / frontend * 100 if frontend else 0
    lines = [
        "# Python 后端重构实时进度快照",
        "",
        f"生成日期：`{date.today().isoformat()}`",
        "",
        f"- Swagger 接口：`{swagger}`",
        f"- 前端实际调用：`{frontend}`",
        f"- Python 已实现：`{implemented}`",
        f"- 前端调用覆盖率：`{coverage:.1f}%`",
        f"- 全部契约缺失路由：`{len(missing)}`",
        f"- 前端调用但 Python 缺失：`{len(frontend_missing)}`",
        f"- 前端 API/页面/Store/测试文件：`{frontend_api}` / `{frontend_views}` / `{frontend_stores}` / `{frontend_tests}`",
        "",
        "## 阶段报告",
        "",
        "| 阶段 | 内容 | 结果 | 报告 |",
        "| --- | --- | --- | --- |",
        *stage_status(),
        "",
        "## 未实现路由（完整清单）",
        "",
        "详见 [route_matrix.md](./route_matrix.md)；下面列出前端已调用但 Python 缺失的路径，便于选取下一批迁移任务。",
        "",
        *[f"- `{path}`" for path in frontend_missing],
        "",
        "更新命令：`py -3.13 scripts/generate_route_matrix.py; py -3.13 scripts/update_refactor_progress.py`。",
        "",
    ]
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"written: {OUTPUT}")
    print(f"swagger={swagger} frontend={frontend} implemented={implemented} all_missing={len(missing)} frontend_missing={len(frontend_missing)}")


if __name__ == "__main__":
    main()
