"""Explicit, isolated authentication configuration; never load a dotenv file."""

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from app.domain.auth import unavailable

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def checked_path(path: Path) -> Path:
    """Reject symlinks in every existing path component without resolving them."""
    path = Path(os.path.abspath(path))
    for component in (*reversed(path.parents), path):
        if component.is_symlink():
            raise ValueError("Symbolic links are not allowed")
    return path


def check_owned_file(path: Path) -> os.stat_result:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("Expected a private, owned regular file")
    return info


@dataclass(frozen=True)
class AuthSettings:
    db_path: Path
    jwt_secret: str | None = None

    def __post_init__(self):
        path = Path(self.db_path)
        if not path.is_absolute():
            path = BACKEND_ROOT / path
        object.__setattr__(self, "db_path", Path(os.path.abspath(path)))


def load_auth_settings() -> AuthSettings:
    return AuthSettings(
        Path(os.environ.get("WEKNORA_AUTH_DB_PATH", BACKEND_ROOT / ".local/auth/auth.sqlite3")),
        os.environ.get("JWT_SECRET"),
    )


def load_secret(settings: AuthSettings) -> str:
    """Read one persistent secret at app creation, or validate explicit injection."""
    try:
        secret = settings.jwt_secret
        if secret is None:
            path = checked_path(Path(f"{settings.db_path}.jwt-secret"))
            check_owned_file(path)
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "r", encoding="utf-8") as stream:
                if os.fstat(stream.fileno()) != path.stat():
                    raise ValueError("Secret file changed")
                secret = stream.read(4097).strip()
        if not isinstance(secret, str) or not 32 <= len(secret.encode("utf-8")) <= 4096:
            raise ValueError("Invalid secret length")
        return secret
    except (OSError, ValueError, UnicodeError):
        raise unavailable() from None
