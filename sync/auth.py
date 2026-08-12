# sync/auth.py
"""Supabase Auth：注册 / 登录 / 登出 / 刷新 token。

用标准库 urllib，避免引入 requests 依赖（减小打包体积）。
所有网络请求在调用方线程执行，本模块不阻塞 UI。
"""
import json
import urllib.request
import urllib.error
from typing import Callable

from sync.config import load_config, load_auth, save_auth, clear_auth


class AuthError(Exception):
    """认证相关错误，message 已是用户可读的中文"""
    pass


def _request(method: str, path: str, body: dict = None, access_token: str = None) -> dict:
    """调用 Supabase Auth API。
    返回解析后的 JSON。失败抛 AuthError。"""
    cfg = load_config()
    url = f"{cfg['supabase_url']}/auth/v1/{path}"
    headers = {
        "apikey": cfg["anon_key"],
        "Content-Type": "application/json",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        try:
            err_json = json.loads(err_body)
            msg = err_json.get("msg") or err_json.get("message") or err_body
        except json.JSONDecodeError:
            msg = err_body
        # 常见错误友好化
        if e.code == 400 and "already registered" in msg.lower():
            raise AuthError("该邮箱已注册，请直接登录")
        if e.code == 400 and "invalid credentials" in msg.lower():
            raise AuthError("邮箱或密码错误")
        if e.code == 400 and "password" in msg.lower():
            raise AuthError(f"密码不符合要求：{msg}")
        if e.code == 429:
            raise AuthError("请求过于频繁，请稍后再试")
        raise AuthError(f"登录失败（HTTP {e.code}）：{msg}")
    except urllib.error.URLError as e:
        raise AuthError(f"网络错误：{e.reason}")
    except Exception as e:
        raise AuthError(f"未知错误：{type(e).__name__}: {e}")


def sign_up(email: str, password: str) -> dict:
    """注册新用户。返回用户信息。
    注意：Supabase 默认可能需要邮箱验证，取决于项目配置。
    如果需要验证，access_token 可能为 None。"""
    resp = _request("POST", "signup", {"email": email, "password": password})
    # resp 结构：{user: {...}, session: {access_token, refresh_token, ...}}
    if resp.get("session"):
        auth = {
            "access_token": resp["session"]["access_token"],
            "refresh_token": resp["session"]["refresh_token"],
            "user_id": resp["user"]["id"],
            "email": resp["user"].get("email", email),
        }
        save_auth(auth)
        return auth
    # 需要邮箱验证的情况
    raise AuthError("注册成功，请到邮箱点击验证链接后再登录")


def sign_in(email: str, password: str) -> dict:
    """邮箱密码登录。返回认证信息并保存到本地。"""
    resp = _request("POST", "token?grant_type=password",
                    {"email": email, "password": password})
    # resp 结构：{access_token, refresh_token, user: {...}}
    auth = {
        "access_token": resp["access_token"],
        "refresh_token": resp["refresh_token"],
        "user_id": resp["user"]["id"],
        "email": resp["user"].get("email", email),
    }
    save_auth(auth)
    return auth


def sign_out():
    """登出：清除本地认证信息。
    不调用 Supabase 登出 API（避免网络请求失败导致本地无法登出）"""
    clear_auth()


def refresh_token() -> dict | None:
    """用 refresh_token 刷新 access_token。
    成功返回新认证信息，失败返回 None（调用方应让用户重新登录）。"""
    auth = load_auth()
    if not auth or "refresh_token" not in auth:
        return None
    try:
        resp = _request("POST", "token?grant_type=refresh_token",
                        {"refresh_token": auth["refresh_token"]})
        new_auth = {
            "access_token": resp["access_token"],
            "refresh_token": resp["refresh_token"],
            "user_id": resp["user"]["id"],
            "email": auth.get("email", ""),
        }
        save_auth(new_auth)
        return new_auth
    except AuthError:
        clear_auth()
        return None


def get_valid_access_token() -> str | None:
    """获取有效的 access_token。
    如果本地有，返回；否则返回 None（调用方应提示用户登录）。
    注意：不在这里自动刷新，由调用方决定。"""
    auth = load_auth()
    if not auth:
        return None
    return auth.get("access_token")


def get_user_id() -> str | None:
    """获取当前登录用户的 UUID"""
    auth = load_auth()
    if not auth:
        return None
    return auth.get("user_id")


def get_email() -> str | None:
    """获取当前登录用户邮箱"""
    auth = load_auth()
    if not auth:
        return None
    return auth.get("email")
