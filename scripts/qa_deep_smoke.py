"""深度 API 冒烟 — 本地跑: python scripts/qa_deep_smoke.py"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@dataclass
class QAReport:
    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    warned: list[str] = field(default_factory=list)

    def ok(self, msg: str) -> None:
        self.passed.append(msg)

    def fail(self, msg: str) -> None:
        self.failed.append(msg)

    def warn(self, msg: str) -> None:
        self.warned.append(msg)


def _start_server(port: int) -> None:
    import uvicorn
    from friday.auth import ensure_api_token, set_api_token
    from friday.server import app

    token = ensure_api_token()
    os.environ["FRIDAY_API_TOKEN"] = token
    os.environ["FRIDAY_PORT"] = str(port)
    set_api_token(token)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")


class Client:
    def __init__(self, port: int, token: str) -> None:
        self.base = f"http://127.0.0.1:{port}"
        self.token = token

    def request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        *,
        auth: bool = True,
        timeout: float = 15.0,
    ) -> tuple[int, dict | list | str]:
        data = None
        headers: dict[str, str] = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if auth:
            headers["X-Friday-Token"] = self.token
        req = urllib.request.Request(
            self.base + path,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                try:
                    return resp.status, json.loads(raw)
                except json.JSONDecodeError:
                    return resp.status, raw
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                return exc.code, json.loads(raw)
            except json.JSONDecodeError:
                return exc.code, raw


def wait_health(port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/api/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                if body.get("status") == "ok":
                    return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


def run_ws_ping(port: int, token: str) -> tuple[bool, str]:
    try:
        import websocket  # type: ignore
    except ImportError:
        return False, "websocket-client 未安装，跳过 WS 测试"

    url = f"ws://127.0.0.1:{port}/ws/chat?token={token}"
    messages: list[str] = []

    def on_message(_ws, message: str) -> None:
        messages.append(message)

    def on_error(_ws, error: Exception) -> None:
        messages.append(f"ERR:{error}")

    ws = websocket.WebSocketApp(url, on_message=on_message, on_error=on_error)
    t = threading.Thread(target=lambda: ws.run_forever(ping_interval=None), daemon=True)
    t.start()
    time.sleep(0.8)
    ws.close()
    t.join(timeout=2.0)
    if any(m.startswith("ERR:") for m in messages):
        return False, messages[0]
    return True, "connected"


def main() -> int:
    from friday.auth import ensure_api_token

    port = 18888
    token = ensure_api_token()
    threading.Thread(target=_start_server, args=(port,), daemon=True).start()
    if not wait_health(port):
        print("FATAL: server did not become ready")
        return 1

    c = Client(port, token)
    r = QAReport()

    # auth
    st, _ = c.request("GET", "/api/settings", auth=False)
    if st == 401:
        r.ok("未授权请求返回 401")
    else:
        r.fail(f"未授权 settings 应 401，得 {st}")

    st, bad = c.request("GET", "/api/settings", auth=True)
    if st == 401:
        r.fail("错误 token 仍应 401")
    # wrong token via custom header omitted — use wrong env not easy; skip

    # health body
    st, body = c.request("GET", "/api/health", auth=False)
    if st == 200 and isinstance(body, dict) and body.get("status") == "ok":
        r.ok("health status=ok")
    else:
        r.fail(f"health 异常: {st} {body}")

    endpoints_get = [
        "/api/settings",
        "/api/sessions",
        "/api/rules",
        "/api/skills",
        "/api/plugins",
        "/api/plugins/catalog",
        "/api/changelog",
        "/api/autostart",
        "/api/artifacts/summary",
        "/api/model-providers",
        "/api/mcp/servers",
        "/api/python-env",
        "/api/operations?limit=5",
        "/api/schedules",
        "/api/status-bar",
        "/api/version",
        "/api/runtime/status",
        "/api/diagnostics/logs?lines=5",
        "/api/portable/audit",
        "/api/updates/check",
    ]
    for path in endpoints_get:
        st, _ = c.request("GET", path)
        if st == 200:
            r.ok(f"GET {path}")
        else:
            r.fail(f"GET {path} -> {st}")

    # session lifecycle
    st, sess = c.request("POST", "/api/sessions", {"title": "QA深度"})
    if st != 200 or not isinstance(sess, dict) or not sess.get("id"):
        r.fail(f"创建会话失败 {st}")
        sid = ""
    else:
        sid = str(sess["id"])
        r.ok("POST /api/sessions 创建")
        st, detail = c.request("GET", f"/api/sessions/{sid}")
        if st == 200:
            r.ok("GET session detail")
        else:
            r.fail(f"GET session detail {st}")
        st, _ = c.request("PATCH", f"/api/sessions/{sid}", {"title": "QA重命名"})
        if st == 200:
            r.ok("PATCH rename session")
        else:
            r.fail(f"rename session {st}")
        st, _ = c.request("POST", f"/api/sessions/{sid}/activate")
        if st == 200:
            r.ok("POST activate session")
        else:
            r.fail(f"activate {st}")
        st, _ = c.request("DELETE", f"/api/sessions/{sid}")
        if st == 200:
            r.ok("DELETE session")
        else:
            r.fail(f"delete session {st}")

    st, _ = c.request("GET", "/api/sessions/no-such-id")
    if st == 404:
        r.ok("GET 不存在会话返回 404")
    else:
        r.fail(f"missing session 应 404，得 {st}")

    req_headers = {"Accept": "application/json", "X-Friday-Token": "bad-token"}
    try:
        req = urllib.request.Request(
            c.base + "/api/settings",
            headers=req_headers,
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            st = resp.status
    except urllib.error.HTTPError as exc:
        st = exc.code
    if st == 401:
        r.ok("错误 token 返回 401")
    else:
        r.fail(f"错误 token 应 401，得 {st}")

    st, diag = c.request("POST", "/api/settings/diagnose", {"api_key": ""})
    if st == 200 and isinstance(diag, dict) and "llm" in diag:
        r.ok("POST /api/settings/diagnose")
    else:
        r.fail(f"diagnose {st} {diag}")

    # cancel edge
    st, cancel = c.request("POST", "/api/chat/cancel", {"session_id": "no-such-session"})
    if st == 200 and isinstance(cancel, dict) and cancel.get("ok") is False:
        r.ok("cancel 无 agent 返回 ok=false")
    else:
        r.warn(f"cancel 边界: {st} {cancel}")

    # plugin install invalid
    st, inst = c.request("POST", "/api/plugins/install", {"source": "not-a-repo"})
    if st in (400, 422, 500):
        r.ok("无效插件源被拒绝")
    elif st == 200:
        r.fail("无效插件源不应 200")
    else:
        r.warn(f"无效插件源 HTTP {st}: {inst}")

    # rules CRUD
    st, rule = c.request("POST", "/api/rules", {
        "title": "QA临时规则",
        "content": "测试用，可删",
        "enabled": True,
        "always_apply": False,
    })
    if st == 200 and isinstance(rule, dict) and rule.get("id"):
        rid = rule["id"]
        r.ok("POST /api/rules")
        st, _ = c.request("DELETE", f"/api/rules/{rid}")
        if st == 200:
            r.ok("DELETE /api/rules")
        else:
            r.fail(f"delete rule {st}")
    else:
        r.fail(f"create rule {st} {rule}")

    # artifacts gc dry run via query — FastAPI bool query
    st, gc = c.request("POST", "/api/artifacts/gc?dry_run=true")
    if st == 200 and isinstance(gc, dict):
        r.ok("POST /api/artifacts/gc?dry_run=true")
    else:
        r.fail(f"artifacts gc {st} {gc}")

    # settings test merge failure path (mock-free: empty key)
    st, test = c.request("POST", "/api/settings/test", {"api_key": ""})
    if st == 200 and isinstance(test, dict) and test.get("ok") is False:
        r.ok("settings/test 空 key 返回 ok=false JSON")
    else:
        r.fail(f"settings/test {st} {test}")

    # catalog product check
    st, cat = c.request("GET", "/api/plugins/catalog")
    if st == 200 and isinstance(cat, dict) and len(cat.get("catalog") or []) >= 2:
        r.ok("插件 catalog 含推荐项")
    elif st == 200 and isinstance(cat, dict) and cat.get("catalog") == []:
        r.warn("插件 catalog 为空（产品层：推荐列表未配置）")
    else:
        r.fail(f"plugins/catalog {st} {cat}")

    ws_ok, ws_msg = run_ws_ping(port, token)
    if ws_ok:
        r.ok(f"WebSocket /ws/chat {ws_msg}")
    else:
        r.warn(f"WebSocket: {ws_msg}")

    print("=== QA 深度冒烟 ===")
    print(f"通过 {len(r.passed)} | 失败 {len(r.failed)} | 警告 {len(r.warned)}")
    for line in r.failed:
        print(f"  FAIL: {line}")
    for line in r.warned:
        print(f"  WARN: {line}")
    if r.failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
