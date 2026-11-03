# WeKnora Python Backend

架构与迁移路线见 [Python后端技术架构与从0到1迁移指南](../../docs/architecture/Python后端技术架构与从0到1迁移指南.md)，当前进度见 [Python后端重构进度管理](../../docs/progress/Python后端重构进度管理.md)。

## 启动服务

在 `PowerShell` 中执行：

```powershell
cd D:\programs\ai\WeKnora\python\backend
if (-not (Test-Path .venv)) { py -3.13 -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

日常启动只需执行：

```powershell
cd D:\programs\ai\WeKnora\python\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

无需激活虚拟环境。若 `pip.exe` 或 `uvicorn.exe` 报错并指向旧目录，请使用上面的 `python.exe -m` 命令。已有 `.venv` 时无需再次创建；缺少依赖时重新执行安装命令即可。若端口 `8080` 已被服务占用，请勿重复启动。

服务启动后可访问 `http://localhost:8080/health` 检查状态，接口文档位于 `http://localhost:8080/swagger/index.html`。
