"""
Subscribing to one block of a page.

The crown jewel is `test_a_watcher_is_not_woken_by_changes_elsewhere`. An
earlier version of this combined the page revision into the subtree ETag,
which meant every edit anywhere woke every watcher - the feature, defeated
by one extra term, and invisible to any test that only edited the block it
was watching.
"""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from bootpages import api, server, store
from bootpages.config import Instance

PORT = 8571


@pytest.fixture
def live(tmp_path):
    """A running pages origin, with one page carrying an id."""

    path = str(tmp_path / "t.db")
    instance = Instance(database=path, port=PORT - 1, pages_port=PORT,
                        pages_url="https://page.example")
    db = store.connect(path)
    account = store.create_account(db, "a", mode="open")

    page = store.create_page(db, account["token"], "Ref Demo", [
        {"tag": "p", "attrs": {"id": "intro"}, "children": ["opening"]},
        {"tag": "p", "attrs": {}, "children": ["untagged"]},
    ])

    httpd = server.listener(instance, db, "pages", "127.0.0.1", PORT)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.2)

    yield {"db": db, "token": account["token"], "path": page["path"],
           "instance": instance,
           "url": f"http://127.0.0.1:{PORT}/getPage/{page['path']}"}

    httpd.shutdown()


def fetch(url, headers=None):
    request = urllib.request.Request(url, headers=headers or {})

    try:
        response = urllib.request.urlopen(request)
        return response.status, dict(response.headers), response.read()

    except urllib.error.HTTPError as problem:
        return problem.code, dict(problem.headers), problem.read()


# ------------------------------------------------------------- the payload


def test_a_ref_response_carries_only_what_the_subtree_determines(live):
    """
    No `views`, which changes on every read, and no `revision`, which
    changes on every edit anywhere. Either would make the body drift under
    an ETag that cannot see it.
    """

    _, _, body = fetch(live["url"] + "?ref=intro")
    result = json.loads(body)["result"]

    assert set(result) == {"path", "ref", "ref_url", "ref_digest", "content"}
    assert result["content"][0]["children"] == ["opening"]
    assert result["ref_url"].endswith("#intro")


def test_an_unknown_ref_is_loud(live):
    status, _, body = fetch(live["url"] + "?ref=nope")

    assert status == 404
    assert json.loads(body)["error"] == "REF_NOT_FOUND"


# ------------------------------------------------------------ the property


def test_a_watcher_is_not_woken_by_changes_elsewhere(live):
    """
    The reason per-block subscription is worth having at all.
    """

    _, headers, _ = fetch(live["url"] + "?ref=intro")
    etag = headers["ETag"]

    store.edit_page(live["db"], live["token"], live["path"], "Ref Demo", [
        {"tag": "p", "attrs": {"id": "intro"}, "children": ["opening"]},
        {"tag": "p", "attrs": {}, "children": ["completely rewritten"]},
    ])

    status, _, _ = fetch(live["url"] + "?ref=intro",
                         {"If-None-Match": etag})

    assert status == 304, "an edit to another block woke the watcher"


def test_a_title_only_edit_does_not_wake_a_watcher(live):
    _, headers, _ = fetch(live["url"] + "?ref=intro")
    etag = headers["ETag"]

    store.edit_page(live["db"], live["token"], live["path"], "A New Title", [
        {"tag": "p", "attrs": {"id": "intro"}, "children": ["opening"]},
        {"tag": "p", "attrs": {}, "children": ["untagged"]},
    ])

    assert fetch(live["url"] + "?ref=intro",
                 {"If-None-Match": etag})[0] == 304


def test_editing_the_watched_block_does_wake_a_watcher(live):
    _, headers, _ = fetch(live["url"] + "?ref=intro")
    etag = headers["ETag"]

    store.edit_page(live["db"], live["token"], live["path"], "Ref Demo", [
        {"tag": "p", "attrs": {"id": "intro"}, "children": ["CHANGED"]},
        {"tag": "p", "attrs": {}, "children": ["untagged"]},
    ])

    assert fetch(live["url"] + "?ref=intro",
                 {"If-None-Match": etag})[0] == 200


# --------------------------------------------------------------- the origin


def test_cors_is_present_so_a_browser_consumer_can_read_it(live):
    _, headers, _ = fetch(live["url"] + "?ref=intro")

    assert headers.get("Access-Control-Allow-Origin") == "*"


def test_cors_is_absent_from_rendered_pages(live):
    _, headers, _ = fetch(f"http://127.0.0.1:{PORT}/{live['path']}")

    assert "Access-Control-Allow-Origin" not in headers


def test_writing_methods_are_unreachable_on_the_pages_origin(live):
    """
    The origin split is not weakened by adding one read route to it.
    """

    for method in ("getPageList", "createPage", "editPage", "createAccount"):
        status, _, _ = fetch(f"http://127.0.0.1:{PORT}/{method}")

        assert status == 404, f"{method} answered on the pages origin"


def test_a_page_named_like_a_method_is_not_shadowed(live):
    """
    Namespace protection survives the new route.
    """

    assert "createPage" in api.METHODS
    assert fetch(f"http://127.0.0.1:{PORT}/createPage")[0] == 404
