"""生成接口契约清单：swagger 接口 × 前端调用 × Python 实现状态。

用法（在 python/backend/ 目录下）：
    python scripts/generate_route_matrix.py

输出：tests/contract/route_matrix.md
"""

from __future__ import annotations

import json
import re
from pathlib import Path

PYTHON_DIR = Path(__file__).resolve().parents[1]
# backend → python → refactor → 仓库根
REPO_ROOT = PYTHON_DIR.parents[2]
SWAGGER = REPO_ROOT / "docs" / "swagger.json"
FRONTEND_API = REPO_ROOT / "frontend" / "src" / "api"
ROUTES_DIR = PYTHON_DIR / "app" / "api" / "v1" / "routes"
OUTPUT = PYTHON_DIR / "tests" / "contract" / "route_matrix.md"

METHODS = {"get", "post", "put", "delete", "patch"}

_FRONTEND_PATTERN = re.compile(r"/api/v1/[A-Za-z0-9_\-/{}$.:]+")
_DECORATOR_PATTERN = re.compile(r"@router\.(get|post|put|delete|patch)\(\s*\"([^\"]*)\"")
_PREFIX_PATTERN = re.compile(r"APIRouter\([^)]*prefix=\"([^\"]*)\"")


def normalize(path: str) -> str:
    path = re.sub(r"\$\{[^}]*\}", "{}", path)
    path = re.sub(r"\{[^}]*\}", "{}", path)
    path = re.sub(r":[A-Za-z_][A-Za-z0-9_]*", "{}", path)
    path = path.rstrip("/")
    return path or "/"


def load_swagger_routes() -> set[tuple[str, str]]:
    if not SWAGGER.exists():
        return set()
    spec = json.loads(SWAGGER.read_text(encoding="utf-8"))
    routes: set[tuple[str, str]] = set()
    for path, operations in spec.get("paths", {}).items():
        for method in operations:
            if method.lower() in METHODS:
                routes.add((method.upper(), normalize(path)))
    return routes


def load_frontend_routes() -> set[tuple[str, str]]:
    """前端只取能确定 HTTP 方法的部分：通过调用 GET/POST 的上下文匹配。"""
    calls: set[tuple[str, str]] = set()
    if not FRONTEND_API.is_dir():
        return calls
    for ts_file in FRONTEND_API.rglob("*.ts"):
        text = ts_file.read_text(encoding="utf-8", errors="ignore")
        for match in re.finditer(
            r"\b(get|post|put|delete|patch)(?:<[^>]*>)?\(\s*[`'\"]([^`'\"]+)[`'\"]",
            text,
        ):
            method, path = match.group(1).upper(), match.group(2)
            if "/api/v1/" in path:
                calls.add((method, normalize(path.split("?")[0])))
    return calls


def load_python_routes() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    if not ROUTES_DIR.is_dir():
        return found
    for py_file in ROUTES_DIR.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        prefix_match = _PREFIX_PATTERN.search(text)
        prefix = prefix_match.group(1) if prefix_match else ""
        for match in _DECORATOR_PATTERN.finditer(text):
            method, path = match.group(1).upper(), match.group(2)
            full = f"/api/v1{prefix}{path}"
            found.add((method, normalize(full)))
    return found


def main() -> None:
    swagger = load_swagger_routes()
    frontend = load_frontend_routes()
    implemented = load_python_routes()

    all_routes = sorted(swagger | frontend | implemented, key=lambda item: (item[1], item[0]))

    lines = [
        "# 接口契约清单",
        "",
        "由 `scripts/generate_route_matrix.py` 自动生成，请勿手工编辑。",
        "",
        f"- Swagger 接口：{len(swagger)}",
        f"- 前端实际调用：{len(frontend)}",
        f"- Python 已实现：{len(implemented)}",
        "",
        "| 方法 | 路径 | Swagger | 前端调用 | Python 实现 |",
        "|---|---|---|---|---|",
    ]
    done = 0
    for method, path in all_routes:
        row = (method, path)
        impl = "✅" if row in implemented else "—"
        if row in implemented:
            done += 1
        lines.append(
            f"| {method} | `{path}` | {'✅' if row in swagger else '—'} | "
            f"{'✅' if row in frontend else '—'} | {impl} |"
        )

    lines += [
        "",
        f"**覆盖率（以前端实际调用为分母）：** {done}/{len(frontend) or 1}",
        "",
    ]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"written: {OUTPUT}")
    print(f"swagger={len(swagger)} frontend={len(frontend)} implemented={len(implemented)}")


if __name__ == "__main__":
    main()
