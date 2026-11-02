"""应用配置，对齐仓库根目录 `.env.example` 的变量命名。"""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

# app/core/config.py → parents[0]=core, [1]=app, [2]=backend
PYTHON_DIR = Path(__file__).resolve().parents[2]
# backend → python → 仓库根
REPO_ROOT = PYTHON_DIR.parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PYTHON_DIR / ".env", REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # A. 运行时
    app_host: str = "0.0.0.0"
    app_port: int = 8080
    log_level: str = "info"
    auto_migrate: bool = True
    cors_allow_origins: str = "*"

    # B. 数据库
    db_driver: str = "postgres"
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "postgres"
    db_password: str = "postgres"
    db_name: str = "WeKnora"
    db_path: str = "./data/weknora.db"

    # B. Redis
    stream_manager_type: str = "memory"
    redis_addr: str = ""
    redis_password: str = ""
    redis_db: int = 0
    redis_prefix: str = "stream:"

    # F. 认证
    jwt_secret: str = ""
    system_aes_key: str = ""
    weknora_auth_registration_mode: str = "self_serve"

    # E. 文档解析
    docreader_addr: str = "localhost:50051"
    docreader_transport: str = "grpc"

    # G. 真实大模型（可选，供 scripts/seed_models.py 写入默认模型）
    # 任何 OpenAI 兼容服务均可：DeepSeek / 百炼 / OpenAI / 硅基流动 / Ollama ...
    llm_seed_tenant_id: int = 1
    llm_chat_base_url: str = ""
    llm_chat_model: str = ""
    llm_chat_api_key: str = ""
    # 第二个对话模型（非默认），用于同时挂 DeepSeek 与 ChatGPT
    llm_chat2_base_url: str = ""
    llm_chat2_model: str = ""
    llm_chat2_api_key: str = ""
    llm_embedding_base_url: str = ""
    llm_embedding_model: str = ""
    llm_embedding_api_key: str = ""
    llm_embedding_dimension: int = 1024
    # 访问境外模型（OpenAI）时的代理，例如 http://127.0.0.1:7890
    llm_proxy: str = ""

    @property
    def effective_jwt_secret(self) -> str:
        # Go 端在 JWT_SECRET 为空时启动即随机生成；这里保持同样语义。
        if not self.jwt_secret:
            return _RANDOM_JWT_SECRET
        return self.jwt_secret

    @property
    def database_url(self) -> str:
        if self.db_driver.lower() == "sqlite":
            path = Path(self.db_path)
            if not path.is_absolute():
                path = (PYTHON_DIR / path).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite+aiosqlite:///{path.as_posix()}"
        user = quote_plus(self.db_user)
        password = quote_plus(self.db_password)
        return (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def sqlite_path(self) -> Path:
        path = Path(self.db_path)
        if not path.is_absolute():
            path = (PYTHON_DIR / path).resolve()
        return path


_RANDOM_JWT_SECRET = secrets.token_urlsafe(48)


@lru_cache
def get_settings() -> Settings:
    return Settings()
