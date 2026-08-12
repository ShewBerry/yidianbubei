# sync/config.py
"""同步配置与凭证管理。

凭证存储在 data/sync_config.json 和 data/sync_auth.json，
不入侵现有 settings 表，方便整体迁移和清理。

- sync_config.json: Supabase URL + anon key（非敏感，前端 PWA 也会用）
- sync_auth.json: 用户登录后的 access_token / refresh_token（敏感，本地存储）
"""
import json
import os
import sys
from pathlib import Path


# 默认配置模板。为保护隐私，Supabase 项目地址与 anon key 留空，
# 使用者需在“设置 → 云端同步”里填入自己创建的 Supabase 项目信息。
# 说明：anon key 是 publishable（公开）的，真正的登录凭证（access_token /
# refresh_token）只保存在本地 data/sync_auth.json，不会进入代码仓库。
DEFAULT_CONFIG = {
    "supabase_url": "",
    "anon_key": "",
    # 同步开关：默认关闭，用户在设置面板手动开启
    "sync_enabled": False,
    # 实时同步防抖间隔（毫秒）：数据变动后等 500ms 再上传，避免高频写
    "sync_debounce_ms": 500,
}


def _get_data_dir() -> Path:
    """返回数据目录路径（与 ebbinghaus.db 同目录）。
    打包成 exe 后，data/ 在 exe 同级目录。"""
    # 优先用环境变量（开发模式）
    if os.environ.get("YDB_DATA_DIR"):
        return Path(os.environ["YDB_DATA_DIR"])
    # 打包模式：exe 所在目录的 data/
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "data"
    # 开发模式：项目根目录的 data/
    return Path(__file__).parent.parent / "data"


def get_config_path() -> Path:
    return _get_data_dir() / "sync_config.json"


def get_auth_path() -> Path:
    return _get_data_dir() / "sync_auth.json"


def load_config() -> dict:
    """加载同步配置。文件不存在则返回默认配置。"""
    path = get_config_path()
    if not path.exists():
        return dict(DEFAULT_CONFIG)
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        # 合并默认值（保证新字段有默认值）
        merged = dict(DEFAULT_CONFIG)
        merged.update(cfg)
        return merged
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_CONFIG)


def save_config(cfg: dict):
    """保存同步配置到 data/sync_config.json"""
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def load_auth() -> dict | None:
    """加载已登录的认证信息。未登录返回 None。"""
    path = get_auth_path()
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_auth(auth: dict):
    """保存认证信息（access_token / refresh_token / user_id / email）"""
    path = get_auth_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(auth, f, ensure_ascii=False, indent=2)


def clear_auth():
    """登出时清除本地认证信息"""
    path = get_auth_path()
    if path.exists():
        path.unlink()


def is_sync_enabled() -> bool:
    """同步功能是否启用（配置开关 + 已登录）"""
    cfg = load_config()
    if not cfg.get("sync_enabled", False):
        return False
    auth = load_auth()
    return auth is not None and "access_token" in auth
