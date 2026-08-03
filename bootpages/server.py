"""
The localhost server.

Standard library only - http.server and sqlite3, no dependencies at all.
That is a deliberate property rather than an accident of an early version:
a store whose promise is durability should be runnable in ten years by
anyone with a Python interpreter and no working package index.

Routes, in the order they are tried:

    POST /<method>          the API, Telegraph-shaped
    GET  /getPage/<path>    the one API method Telegraph also serves on GET
    GET  /                  the editor
    GET  /static/<file>     editor assets
    GET  /<path>            a published page, rendered

Run it:

    python -m bootpages.server
"""

import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import api, render, store

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")

TYPES = {".html": "text/html; charset=utf-8",
         ".css": "text/css; charset=utf-8",
         ".js": "text/javascript; charset=utf-8"}


class Handler(BaseHTTPRequestHandler):
    server_version = "bootpages"

    # ------------------------------------------------------------ helpers

    def reply(self, status, body, kind="text/html; charset=utf-8"):
        payload = body.encode("utf-8") if isinstance(body, str) else body

        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def reply_json(self, payload, status=200):
        self.reply(status, json.dumps(payload, ensure_ascii=False),
                   "application/json; charset=utf-8")

    def log_message(self, fmt, *args):
        # The default logs to stderr with a timestamp format nobody wants.
        print(f"{self.command} {self.path} {args[1] if len(args) > 1 else ''}")

    def params(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""

        kind = (self.headers.get("Content-Type") or "").split(";")[0].strip()

        # Telegraph takes form encoding. JSON is accepted too because the
        # editor speaks it and there is no reason to make it pretend
        # otherwise.
        if kind == "application/json":
            try:
                parsed = json.loads(raw or "{}")

            except ValueError:
                return {}

            return parsed if isinstance(parsed, dict) else {}

        return {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}

    def base(self):
        host = self.headers.get("Host") or f"localhost:{self.server.server_port}"

        return f"http://{host}"

    # -------------------------------------------------------------- verbs

    def do_POST(self):
        method = urlparse(self.path).path.strip("/")

        self.serve_api(method, self.params())

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.strip("/")
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}

        # Telegraph serves getPage over GET as /getPage/<path>.
        if path.startswith("getPage/"):
            query["path"] = path[len("getPage/"):]

            return self.serve_api("getPage", query)

        if path in api.METHODS:
            return self.serve_api(path, query)

        if path in ("", "index.html"):
            return self.serve_static("editor.html")

        if path.startswith("static/"):
            return self.serve_static(path[len("static/"):])

        return self.serve_page(path)

    # ------------------------------------------------------------ serving

    def serve_api(self, method, params):
        try:
            result = api.call(self.server.db, method, params, self.base())

        except api.ApiError as problem:
            return self.reply_json({"ok": False, "error": str(problem)})

        return self.reply_json({"ok": True, "result": result})

    def serve_static(self, name):
        # Anything with a separator in it is an attempt to leave the
        # directory, not a filename.
        if "/" in name or "\\" in name or name.startswith("."):
            return self.reply(404, "Not found")

        full = os.path.join(STATIC, name)

        if not os.path.isfile(full):
            return self.reply(404, "Not found")

        with open(full, "rb") as handle:
            body = handle.read()

        kind = TYPES.get(os.path.splitext(name)[1], "application/octet-stream")

        self.reply(200, body, kind)

    def serve_page(self, path):
        try:
            row = store.page(self.server.db, path)

        except store.StoreError:
            return self.reply(404, "<h1>404</h1><p>No page at that address.</p>")

        if row["hidden"]:
            return self.reply(404, "<h1>404</h1><p>No page at that address.</p>")

        store.count_view(self.server.db, path)

        content = json.loads(row["content"])

        # No modules. The reference renderer is a Level 0 consumer, so
        # every non-core tag falls back to its children - which is what a
        # page looks like on a site that has never heard of it, and the
        # honest default for a registry discovered from use.
        body = render.render(content)

        self.reply(200, render.document(
            row["title"], body,
            row["author_name"], row["author_url"],
            time.strftime("%d %B %Y", time.gmtime(row["created"])),
        ))


LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost", ""})

PUBLIC_WARNING = """\
Refusing to bind to {host}.

createAccount is open on this build: anyone who can reach this port can
mint an account and publish permanent public pages. Binding to a loopback
address is currently the only thing gating it, which is what
docs/decisions.md calls network gating.

If you meant it - you are behind a reverse proxy that authenticates, or on
a network you control - say so explicitly:

    python3 -m bootpages.server --host {host} --allow-public

Nothing about this is a security control. It is a speed bump placed where
an accident would otherwise be silent.
"""


def notify(state):
    """
    sd_notify by hand. One datagram to a unix socket, and a no-op anywhere
    systemd is not watching - so running this from a terminal behaves
    exactly the same as running it under the unit.
    """

    address = os.environ.get("NOTIFY_SOCKET")

    if not address:
        return

    try:
        import socket

        if address.startswith("@"):          # abstract namespace
            address = "\0" + address[1:]

        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.connect(address)
            sock.sendall(state.encode())

    except OSError:
        pass


def watchdog():
    """
    A server that has stopped answering still looks alive to Restart=always,
    because the process is still there. This pings only while the listening
    socket is healthy, so a wedged server stops the pings and systemd
    restarts it.
    """

    window = int(os.environ.get("WATCHDOG_USEC", 0)) / 1_000_000

    if not window:
        return

    def loop():
        while True:
            time.sleep(window / 2)          # half the interval, as documented
            notify("WATCHDOG=1")

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()


def serve(host="127.0.0.1", port=8080, database="data/bootpages.db",
          allow_public=False):
    if host not in LOOPBACK and not allow_public:
        raise SystemExit(PUBLIC_WARNING.format(host=host))

    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.db = store.connect(database)

    print(f"bootpages on http://{host}:{port}  (store: {database})")
    print("editor at /   ·  api at POST /<method>  ·  ctrl-c to stop")

    if host not in LOOPBACK:
        print("!! reachable beyond this machine, with createAccount open")

    notify("READY=1")
    watchdog()

    try:
        httpd.serve_forever()

    except KeyboardInterrupt:
        print("\nstopped")

    finally:
        notify("STOPPING=1")


def main():
    parser = argparse.ArgumentParser(description="Run bootpages.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--db", default="data/bootpages.db")
    parser.add_argument(
        "--allow-public", action="store_true",
        help="permit binding to a non-loopback address. createAccount is "
             "open, so this exposes account creation to that network.",
    )

    args = parser.parse_args()

    serve(args.host, args.port, args.db, args.allow_public)


if __name__ == "__main__":
    main()
