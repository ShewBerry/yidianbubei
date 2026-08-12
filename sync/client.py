# sync/client.py
"""Supabase REST API 客户端封装。

只依赖标准库 urllib，不引入 requests。
提供 upsert / fetch / delete 等核心 REST 操作。
"""
import json
import urllib.request
import urllib.error
import urllib.parse
from typing import Any

from sync.config import load_config
from sync.auth import get_valid_access_token, refresh_token, get_user_id


class SyncError(Exception):
    """同步 API 错误"""
    pass


class AuthExpiredError(SyncError):
    """access_token 过期，调用方应让用户重新登录或刷新 token"""
    pass


def _build_headers(use_auth: bool = True, extra: dict = None) -> dict:
    cfg = load_config()
    headers = {
        "apikey": cfg["anon_key"],
        "Content-Type": "application/json",
    }
    if use_auth:
        token = get_valid_access_token()
        if not token:
            raise AuthExpiredError("未登录或登录已过期")
        headers["Authorization"] = f"Bearer {token}"
    if extra:
        headers.update(extra)
    return headers


def _do_request(method: str, path: str, body: Any = None,
                query: dict = None, extra_headers: dict = None,
                retry_on_auth_expired: bool = True) -> Any:
    """执行 REST API 请求，带 token 自动刷新重试一次。
    返回解析后的 JSON（DELETE 成功可能返回 None）。"""
    cfg = load_config()
    url = f"{cfg['supabase_url']}/rest/v1/{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query, doseq=True)

    try:
        headers = _build_headers(extra=extra_headers)
    except AuthExpiredError:
        if retry_on_auth_expired:
            # 尝试刷新 token
            if refresh_token():
                return _do_request(method, path, body, query, extra_headers, retry_on_auth_expired=False)
            raise

    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
            if not text:
                return None
            return json.loads(text)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        if e.code == 401 and retry_on_auth_expired:
            # token 过期，尝试刷新后重试
            if refresh_token():
                return _do_request(method, path, body, query, extra_headers, retry_on_auth_expired=False)
            raise AuthExpiredError("登录已过期，请重新登录")
        if e.code == 403:
            raise SyncError(f"权限不足：{err_body}")
        if e.code == 404:
            raise SyncError(f"资源不存在（表可能未建）：{err_body}")
        if e.code == 409:
            raise SyncError(f"冲突：{err_body}")
        if e.code == 429:
            raise SyncError("请求过于频繁，请稍后再试")
        raise SyncError(f"HTTP {e.code}: {err_body}")
    except urllib.error.URLError as e:
        raise SyncError(f"网络错误：{e.reason}")
    except TimeoutError:
        # urlopen 超时抛 TimeoutError，不在 URLError 层级，需单独捕获
        raise SyncError("请求超时，请检查网络后重试")


def upsert(table: str, rows: list[dict]) -> list[dict]:
    """批量 upsert（按主键合并）。
    rows 中每条记录必须包含主键字段（user_id + local_id）。
    返回 upsert 后的记录列表。"""
    if not rows:
        return []
    headers = {
        "Prefer": "return=representation,resolution=merge-duplicates",
    }
    return _do_request("POST", table, body=rows, extra_headers=headers)


def fetch_all(table: str, filters: dict = None, order: str = None,
              page_size: int = 1000) -> list[dict]:
    """查询表数据，自动分页。
    filters: {column: value} 等值过滤
    order: "column.asc" 或 "column.desc"
    """
    all_rows = []
    offset = 0
    while True:
        query = {"select": "*", "limit": page_size, "offset": offset}
        if filters:
            for col, val in filters.items():
                query[col] = f"eq.{val}"
        if order:
            query["order"] = order
        batch = _do_request("GET", table, query=query)
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return all_rows


def delete_by_local_ids(table: str, local_ids: list[int]) -> int:
    """按 local_id 批量删除（用户隔离由 RLS 保证）。
    返回删除条数（Supabase 不返回 body，这里返回请求数）。"""
    if not local_ids:
        return 0
    # Supabase DELETE 用 IN 过滤：local_id=in.(1,2,3)
    ids_str = f"in.({','.join(str(i) for i in local_ids)})"
    _do_request("DELETE", table, query={"local_id": ids_str})
    return len(local_ids)
