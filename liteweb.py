# -*- coding: utf-8 -*-
"""liteweb —— 只用标准库实现的极简 Web 微框架（Flask 子集兼容）。

为什么不用 Flask
----------------
原来 app.py 依赖 Flask，结果在没装 Flask 的解释器上直接 ModuleNotFoundError。
机器上往往有多个 Python（venv / 系统 / 商店版），双击 bat 时解析到哪个不确定，
于是「明明装了 Flask 却跑不起来」。这个模块把 HTTP 层换成标准库实现，
整个项目 0 第三方依赖，任何一个 Python 3.9+ 都能直接运行。

实现的 Flask 子集（够 app.py 用）
--------------------------------
  Flask(__name__, static_folder=None)
    .route/.get/.post         路由注册，支持 <name> / <int:name> / <path:name>
    .teardown_appcontext(fn)  请求结束后的清理回调
    .json.ensure_ascii        JSON 是否转义非 ASCII
    .run(host, port, threaded)
  request           .args（查询参数）/.get_json(force=True)/.method/.path
  g                 请求级命名空间，支持属性访问与 .pop()
  jsonify(obj)      返回 JSON 响应
  send_from_directory(dir, filename)   返回静态文件
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

__all__ = ["Flask", "request", "g", "jsonify", "send_from_directory"]


# ------------------------------------------------------------------ 响应对象
class _JSON:
    def __init__(self, data, status=200):
        self.data = data
        self.status = status
        self.headers = {}


class _File:
    def __init__(self, directory, filename, status=200):
        self.directory = directory
        self.filename = filename
        self.status = status
        self.headers = {}


class _Text:
    def __init__(self, body, status=200, content_type="text/plain; charset=utf-8"):
        self.body = body
        self.status = status
        self.headers = {"Content-Type": content_type}


class _Namespace:
    """像 Flask 的 g 一样：支持属性读写 + pop + in。"""

    def __init__(self):
        object.__setattr__(self, "_d", {})

    def __getattr__(self, k):
        try:
            return self._d[k]
        except KeyError:
            raise AttributeError(k)

    def __setattr__(self, k, v):
        self._d[k] = v

    def __delattr__(self, k):
        self._d.pop(k, None)

    def __contains__(self, k):
        return k in self._d

    def pop(self, k, default=None):
        return self._d.pop(k, default)

    def clear(self):
        self._d.clear()


class _Request:
    def __init__(self, method, path, query, body, headers, params):
        self.method = method
        self.path = path
        self.query = query
        self.body = body
        self.headers = headers
        self.view_args = params
        self.args = {k: v[0] for k, v in query.items()}
        self._json = None
        self._parsed = False

    def get_json(self, force=False, silent=True):
        if not self._parsed:
            self._parsed = True
            try:
                self._json = json.loads(self.body.decode("utf-8")) if self.body else None
            except Exception:
                self._json = None
        if self._json is None and force:
            return {}
        return self._json


class _Proxy:
    def __getattr__(self, name):
        r = getattr(_state, "request", None)
        if r is None:
            raise RuntimeError("在请求上下文之外访问 request")
        return getattr(r, name)


class _GProxy:
    """g 必须是「每线程一份」：HTTP 服务是多线程的，
    模块级全局命名空间会被并发请求互相踩。"""

    @staticmethod
    def _ns():
        ns = getattr(_state, "g", None)
        if ns is None:
            ns = _Namespace()
            _state.g = ns
        return ns

    def __getattr__(self, k):
        return getattr(self._ns(), k)

    def __setattr__(self, k, v):
        setattr(self._ns(), k, v)

    def __delattr__(self, k):
        delattr(self._ns(), k)

    def __contains__(self, k):
        return k in self._ns()

    def pop(self, k, default=None):
        return self._ns().pop(k, default)

    def clear(self):
        self._ns().clear()


_state = threading.local()
request = _Proxy()
g = _GProxy()


class _JsonCfg:
    ensure_ascii = False


# ------------------------------------------------------------------ 应用
class Flask:
    def __init__(self, import_name, static_folder=None, **kw):
        self.import_name = import_name
        self.static_folder = static_folder
        self.json = _JsonCfg()
        self._routes = []          # [(method, regex, score, [(name, conv)], func)]
        self._teardowns = []

    # ---- 路由注册 ----
    def _add(self, rule, endpoint, methods):
        pattern, names = self._compile(rule)
        score = len(re.sub(r"<[^>]+>", "", rule))     # 静态字符越多越具体
        for m in methods:
            self._routes.append((m.upper(), pattern, score, names, endpoint))

    @staticmethod
    def _compile(rule):
        names = []
        out = []
        i = 0
        while i < len(rule):
            c = rule[i]
            if c == "<":
                j = rule.find(">", i)
                if j < 0:
                    out.append(re.escape(c))
                    i += 1
                    continue
                spec = rule[i + 1:j]
                conv, _, name = spec.partition(":")
                if not name:
                    conv, name = "string", spec
                if conv == "int":
                    out.append("(?P<%s>[0-9]+)" % name)
                elif conv == "path":
                    out.append("(?P<%s>.+)" % name)
                else:
                    out.append("(?P<%s>[^/]+)" % name)
                names.append(name)
                i = j + 1
            else:
                out.append(re.escape(c))
                i += 1
        return re.compile("^" + "".join(out) + "$"), names

    def route(self, rule, methods=("GET",)):
        def deco(fn):
            self._add(rule, fn, methods)
            return fn
        return deco

    def get(self, rule):
        return self.route(rule, ("GET",))

    def post(self, rule):
        return self.route(rule, ("POST",))

    def teardown_appcontext(self, fn):
        self._teardowns.append(fn)
        return fn

    # ---- 分发 ----
    def _match(self, method, path):
        best = None
        for m, pattern, score, names, fn in self._routes:
            if m != method:
                continue
            mo = pattern.match(path)
            if not mo:
                continue
            if best is None or score > best[0]:
                best = (score, fn, mo.groupdict())
        return (best[1], best[2]) if best else (None, None)

    def handle(self, method, path, query, body, headers):
        fn, params = self._match(method, path)
        if fn is None:
            return _JSON({"error": "not found", "path": path}, 404)
        r = _Request(method, path, query, body, headers, params or {})
        _state.request = r
        g.clear()
        try:
            return fn(**(params or {}))
        finally:
            for cb in self._teardowns:
                try:
                    cb(None)
                except Exception:
                    pass
            _state.request = None

    # ---- 运行 ----
    def run(self, host="127.0.0.1", port=8000, debug=False, threaded=True, **kw):
        app = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            server_version = "liteweb"

            def log_message(self, fmt, *a):
                pass          # 保持控制台干净

            def _dispatch(self, method):
                parsed = urlparse(self.path)
                path = unquote(parsed.path)
                query = parse_qs(parsed.query)
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                try:
                    resp = app.handle(method, path, query, body, self.headers)
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    resp = _JSON({"error": str(e)}, 500)
                if isinstance(resp, tuple):
                    resp, status = resp[0], resp[1]
                else:
                    status = getattr(resp, "status", 200)
                self._send(resp, status)

            def do_GET(self):
                self._dispatch("GET")

            def do_POST(self):
                self._dispatch("POST")

            def do_HEAD(self):
                self._dispatch("GET")

            def _send(self, resp, status):
                headers = dict(getattr(resp, "headers", {}) or {})
                if isinstance(resp, _JSON):
                    payload = json.dumps(resp.data, ensure_ascii=app.json.ensure_ascii,
                                         default=str).encode("utf-8")
                    headers.setdefault("Content-Type", "application/json; charset=utf-8")
                elif isinstance(resp, _File):
                    full = os.path.join(resp.directory, resp.filename)
                    if not os.path.isfile(full):
                        self._raw(404, b"not found", {"Content-Type": "text/plain"})
                        return
                    with open(full, "rb") as f:
                        payload = f.read()
                    ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
                    if ctype.startswith("text/") or ctype in ("application/javascript",):
                        ctype += "; charset=utf-8"
                    headers.setdefault("Content-Type", ctype)
                elif isinstance(resp, _Text):
                    payload = resp.body.encode("utf-8")
                else:
                    payload = str(resp).encode("utf-8")
                    headers.setdefault("Content-Type", "text/plain; charset=utf-8")
                self._raw(status, payload, headers)

            def _raw(self, status, payload, headers):
                self.send_response(status)
                headers.setdefault("Content-Length", str(len(payload)))
                for k, v in headers.items():
                    self.send_header(k, v)
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(payload)

        httpd = ThreadingHTTPServer((host, port), Handler)
        httpd.daemon_threads = True
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            httpd.server_close()


def jsonify(*args, **kwargs):
    """Flask 的 jsonify：单个字典直接序列化，多个位置参数打包成数组。"""
    if len(args) == 1 and not kwargs:
        return _JSON(args[0])
    if args and kwargs:
        return _JSON(list(args) + [kwargs])
    if kwargs:
        return _JSON(kwargs)
    return _JSON(list(args))


def send_from_directory(directory, filename, **kw):
    return _File(directory, filename)
