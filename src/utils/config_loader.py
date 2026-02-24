import os
from typing import Dict, Optional, List


_ENV_CACHE: Dict[str, str] = {}
_ENV_LOADED: bool = False
_ENV_SOURCES: List[str] = []


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env_paths() -> List[str]:
    root = _project_root()
    if os.path.basename(root) == "src":
        root = os.path.dirname(root)
    paths: List[str] = []
    explicit = os.getenv("DOTENV_PATH") or os.getenv("ENV_PATH")
    if explicit:
        paths.append(explicit)
    paths.append(os.path.join(root, "configs", ".env"))
    paths.append(os.path.join(root, ".env"))
    return paths


def _load_env_file() -> None:
    global _ENV_LOADED, _ENV_SOURCES
    if _ENV_LOADED:
        return
    for path in _env_paths():
        try:
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if not s or s.startswith("#"):
                        continue
                    if "=" not in s:
                        continue
                    k, v = s.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k:
                        _ENV_CACHE[k] = v
            _ENV_SOURCES.append(path)
        except Exception:
            continue
    _ENV_LOADED = True


def get(key: str, default: Optional[str] = None) -> Optional[str]:
    if not _ENV_LOADED:
        _load_env_file()
    return _ENV_CACHE.get(key, default)


def get_int(key: str, default: int) -> int:
    val = get(key)
    try:
        return int(val) if val is not None else default
    except Exception:
        return default


def get_float(key: str, default: float) -> float:
    val = get(key)
    try:
        return float(val) if val is not None else default
    except Exception:
        return default


def get_bool(key: str, default: bool) -> bool:
    val = get(key)
    if val is None:
        return default
    s = val.strip().lower()
    if s in ("1", "true", "yes", "on"):  # basic truthy
        return True
    if s in ("0", "false", "no", "off"):
        return False
    return default


def debug_sources() -> List[str]:
    if not _ENV_LOADED:
        _load_env_file()
    return list(_ENV_SOURCES)


def reload() -> None:
    global _ENV_CACHE, _ENV_LOADED, _ENV_SOURCES
    _ENV_CACHE = {}
    _ENV_LOADED = False
    _ENV_SOURCES = []
    _load_env_file()
