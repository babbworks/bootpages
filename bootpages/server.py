"""
The server.

Standard library only - http.server and sqlite3, no dependencies at all.
That is a deliberate property rather than an accident of an early version:
a store whose promise is durability should be runnable in ten years by
anyone with a Python interpreter and no working package index.

TWO ORIGINS, ONE PROCESS
------------------------
The editor and published pages are served on different origins, because
the editor keeps author tokens in browser storage and published pages are
untrusted content. Same-origin policy is what stops a script inside a page
reading that storage - and it is enforced by the browser, keyed on origin
(scheme, host, port). Two processes would buy nothing extra against this,
so one process runs both listeners.

    editor origin   the editor, its assets, and the API
    pages  origin   rendered pages and their stylesheet - nothing else

Neither serves the other's routes. A script that somehow ran on a page
cannot reach the API from its own origin, and the editor never renders
stored content.

Run it:

    python3 -m bootpages.server
"""

import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import api, render, store
from .config import ConfigError, Instance

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")

TYPES = {".html": "text/html; charset=utf-8",
         ".css": "text/css; charset=utf-8",
         ".js": "text/javascript; charset=utf-8"}

# Applied everywhere. nosniff stops a browser guessing a content type it
# was told, and no-referrer keeps a page's address out of the logs of
# whoever hosts an image it points at.
COMMON_HEADERS = (
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
)

# A published page executes nothing. This is the header that says so, and
# it holds regardless of any bug in the renderer - a defence at a different
# layer from "there is no path by which author text becomes markup".
#
# frame-ancestors is deliberately open: bootpages are *meant* to be
# embedded by consuming sites, so refusing to be framed would break the
# thing they are for.
PAGE_CSP = (
    "default-src 'none'; "
    "style-src 'self'; "
    "img-src 'self' https: data:; "
    "media-src 'self' https:; "
    "frame-src https:; "
    "frame-ancestors *; "
    "base-uri 'none'; "
    "form-action 'none'"
)

# The editor is the opposite case. It must never be framed, because a
# clickjacked token field is a real attack against a credential that cannot
# be revoked by anyone but its holder.
EDITOR_HEADERS = (
    ("X-Frame-Options", "DENY"),
    ("Content-Security-Policy", "frame-ancestors 'none'; base-uri 'none'"),
)


class Handler(BaseHTTPRequestHandler):
    """
    One handler, two roles. `self.server.role` is "editor" or "pages", and
    every route check consults it - so a route existing on one origin is
    not a route that exists on the other.
    """

    server_version = "bootpages"

    # ------------------------------------------------------------ helpers

    @property
    def role(self):
        return self.server.role

    @property
    def instance(self):
        return self.server.instance

    def reply(self, status, body, kind="text/html; charset=utf-8"):
        payload = body.encode("utf-8") if isinstance(body, str) else body

        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(payload)))
        # Every reply carries the same headers; only the body is withheld
        # on HEAD. A consumer checking whether a page still exists should
        # get the same answer either way.

        for name, value in COMMON_HEADERS:
            self.send_header(name, value)

        if self.role == "pages":
            self.send_header("Content-Security-Policy", PAGE_CSP)
        else:
            for name, value in EDITOR_HEADERS:
                self.send_header(name, value)

        self.end_headers()

        if self.command != "HEAD":
            self.wfile.write(payload)

    def reply_json(self, payload, status=200):
        self.reply(status, json.dumps(payload, ensure_ascii=False),
                   "application/json; charset=utf-8")

    def not_found(self):
        self.reply(404, "<h1>404</h1><p>No page at that address.</p>")

    def log_message(self, format, *args):
        print(f"[{self.role}] {self.command} {self.path}")

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

    # -------------------------------------------------------------- verbs

    def do_POST(self):
        # The API lives on the editor origin only. A script running on a
        # published page has no same-origin route to it.
        if self.role != "editor":
            return self.not_found()

        self.serve_api(urlparse(self.path).path.strip("/"), self.params())

    def do_HEAD(self):
        # Same routing, same headers, no body. reply() withholds the body
        # by checking self.command.
        self.do_GET()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.strip("/")
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}

        if self.role == "pages":
            return self.get_pages(path)

        return self.get_editor(path, query)

    def get_editor(self, path, query):
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

        # Deliberately not a page. Stored content is never rendered on the
        # origin that holds tokens.
        return self.not_found()

    def get_pages(self, path):
        # The stylesheet is the one asset this origin serves, because a
        # page needs it and inlining would mean loosening style-src.
        if path == "static/page.css":
            return self.serve_static("page.css")

        if not path or path in api.METHODS or path.startswith("getPage/"):
            return self.not_found()

        return self.serve_page(path)

    # ------------------------------------------------------------ serving

    def serve_api(self, method, params):
        try:
            result = api.call(self.server.db, method, params, self.instance)

        except api.ApiError as problem:
            return self.reply_json({"ok": False, "error": str(problem)})

        return self.reply_json({"ok": True, "result": result})

    def serve_static(self, name):
        # Anything with a separator in it is an attempt to leave the
        # directory, not a filename.
        if "/" in name or "\\" in name or name.startswith("."):
            return self.not_found()

        full = os.path.join(STATIC, name)

        if not os.path.isfile(full):
            return self.not_found()

        with open(full, "rb") as handle:
            body = handle.read()

        kind = TYPES.get(os.path.splitext(name)[1], "application/octet-stream")

        self.reply(200, body, kind)

    def serve_page(self, path):
        try:
            row = store.page(self.server.db, path)

        except store.StoreError:
            return self.not_found()

        if row["hidden"]:
            return self.not_found()

        store.count_view(self.server.db, path)

        # No modules. The reference renderer is a Level 0 consumer, so
        # every non-core tag falls back to its children - which is what a
        # page looks like on a site that has never heard of it, and the
        # honest default for a registry discovered from use.
        body = render.render(json.loads(row["content"]))

        self.reply(200, render.document(
            row["title"], body,
            row["author_name"], row["author_url"],
            time.strftime("%d %B %Y", time.gmtime(row["created"])),
        ))


# ------------------------------------------------------------------ notify


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
    because the process is still there. Silence is what tells the
    difference.
    """

    window = int(os.environ.get("WATCHDOG_USEC", 0)) / 1_000_000

    if not window:
        return

    def loop():
        while True:
            time.sleep(window / 2)          # half the interval, as documented
            notify("WATCHDOG=1")

    threading.Thread(target=loop, daemon=True).start()


# ---------------------------------------------------------------- first run


def first_run(db, instance):
    """
    Mint one account against an empty store, and print its token.

    The default mode is `admin`, which would otherwise mean a fresh
    instance where nobody can write anything until someone runs the CLI.
    This removes that friction without opening a hole: anyone able to start
    the server already has shell access and could mint a token anyway.

    Once any account exists this never happens again.
    """

    if instance.mode == "open" or store.any_accounts(db):
        return

    from .admin import show_token

    row = store.create_account(db, "first", "", "", mode="open")

    show_token(row, heading="First account on this instance")


# -------------------------------------------------------------------- run


def listener(instance, db, role, host, port):
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.db = db
    httpd.role = role
    httpd.instance = instance

    return httpd


def serve(instance):
    db = store.connect(instance.database)

    editor = listener(instance, db, "editor", instance.host, instance.port)
    pages = listener(instance, db, "pages", instance.pages_host,
                     instance.pages_port)

    print(f"{instance.name}  ·  mode: {instance.mode}")
    print(f"  editor  {instance.editor_url}")
    print(f"  pages   {instance.pages_url}")

    if not instance.is_loopback:
        print("  !! reachable beyond this machine")

    first_run(db, instance)

    threading.Thread(target=pages.serve_forever, daemon=True).start()

    notify("READY=1")
    watchdog()

    try:
        editor.serve_forever()

    except KeyboardInterrupt:
        print("\nstopped")

    finally:
        notify("STOPPING=1")


def main():
    parser = argparse.ArgumentParser(description="Run bootpages.")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--pages-host")
    parser.add_argument("--pages-port", type=int)
    parser.add_argument("--db")
    parser.add_argument("--name")
    parser.add_argument("--description")
    parser.add_argument("--contact")
    parser.add_argument(
        "--mode", choices=("open", "invited", "admin"),
        help="how accounts come into being. admin (the default) refuses "
             "createAccount entirely; tokens are minted with "
             "python3 -m bootpages.admin.",
    )
    parser.add_argument(
        "--allow-public", action="store_true",
        help="permit binding to a non-loopback address.",
    )

    args = parser.parse_args()

    try:
        instance = Instance(
            name=args.name, description=args.description, mode=args.mode,
            contact=args.contact, host=args.host, port=args.port,
            pages_host=args.pages_host, pages_port=args.pages_port,
            database=args.db, allow_public=args.allow_public,
        )

    except ConfigError as problem:
        raise SystemExit(f"\n{problem}\n")

    serve(instance)


if __name__ == "__main__":
    main()
