"""
Where pages live.

SQLite, one file, no server to run alongside this one. A page is a
document, backing it up is copying a file, and restoring it is copying the
file back - which matters more than it sounds for a store whose entire
promise is that the bytes come back.

The store is neutral. It does not evaluate page content, does not
dereference anything a page points at, and does not vary what it returns by
who is asking. The single transformation it performs is canonicalising on
write, which preserves meaning and is what makes a digest mean anything.
"""

import os
import re
import secrets
import sqlite3
import time

from . import format as fmt

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    token        TEXT PRIMARY KEY,
    short_name   TEXT NOT NULL,
    author_name  TEXT NOT NULL DEFAULT '',
    author_url   TEXT NOT NULL DEFAULT '',
    created      REAL NOT NULL,
    -- Never exposed by the public API. Present from the first migration
    -- because adding a block path to a store that has promised permanence
    -- is close to impossible, and the first time it is needed it will be
    -- urgent.
    blocked      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS pages (
    path         TEXT PRIMARY KEY,
    token        TEXT NOT NULL,
    title        TEXT NOT NULL,
    author_name  TEXT NOT NULL DEFAULT '',
    author_url   TEXT NOT NULL DEFAULT '',
    -- The canonical bytes, exactly as hashed. Stored rather than recomputed
    -- so the digest cannot drift as libraries and languages change across
    -- the decades this is meant to survive.
    content      TEXT NOT NULL,
    revision     INTEGER NOT NULL DEFAULT 1,
    digest       TEXT NOT NULL,
    views        INTEGER NOT NULL DEFAULT 0,
    created      REAL NOT NULL,
    updated      REAL NOT NULL,
    hidden       INTEGER NOT NULL DEFAULT 0,
    deleted      INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS pages_by_account ON pages (token, created DESC);

-- Invite codes, for instances running in `invited` mode.
--
-- An invite is NOT a credential to an account: it is a one-time right to
-- create one. That difference is the whole reason the mode exists. A token
-- intercepted in transit lets someone publish as you, forever, with no way
-- to expire it. An intercepted invite lets a stranger create their own
-- account, once, and only until it is used or expires.
CREATE TABLE IF NOT EXISTS invites (
    code     TEXT PRIMARY KEY,
    note     TEXT NOT NULL DEFAULT '',
    created  REAL NOT NULL,
    expires  REAL,
    used_at  REAL,
    used_by  TEXT
);
"""


class StoreError(Exception):
    """Something the caller did wrong. The message is safe to return."""


def connect_for_counters(path="data/bootpages.db"):
    """
    A second connection, for the one write whose loss costs nothing.

    Every page view increments a counter, and under `synchronous=FULL`
    that means a physical fsync on the read path - measured at 9ms on an
    SSD and a full platter rotation on the spinning disk this is meant to
    run on. It was sixteen times the cost of the entire read.

    `NORMAL` in WAL mode does not fsync on each commit, which makes the
    same write 0.027ms. That is not the corruption risk it sounds like:
    WAL plus NORMAL cannot corrupt the database, it can only lose the last
    few commits to a power cut. Losing three view counts is nothing.

    Pages keep FULL, on the other connection. A page acknowledged and then
    lost is a broken promise; a counter is not.
    """

    db = connect(path)

    db.execute("PRAGMA synchronous=NORMAL")

    return db


def connect(path="data/bootpages.db"):
    directory = os.path.dirname(path)

    if directory:
        os.makedirs(directory, exist_ok=True)

    db = sqlite3.connect(path, check_same_thread=False)
    db.row_factory = sqlite3.Row

    # A page that was acknowledged and then lost to a crash is a broken
    # promise, not a performance question.
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.executescript(SCHEMA)

    return db


# --------------------------------------------------------------- accounts


def create_account(db, short_name, author_name="", author_url="",
                   mode="open", invite=None):
    """
    An account is a token and nothing else.

    No email, no password, no recovery. The token IS the identity, which is
    why losing it means losing the account and why this is the one call
    that must never be retried blindly.

    `mode` is enforced here rather than in the UI, so a client that skips
    the first-run screen gets exactly the same answer as one that does not.
    """

    if not short_name:
        raise StoreError("SHORT_NAME_REQUIRED")

    if mode == "admin":
        raise StoreError("ACCOUNT_CREATION_CLOSED")

    if mode == "invited":
        claim_invite(db, invite)

    token = secrets.token_hex(30)

    db.execute(
        "INSERT INTO accounts (token, short_name, author_name, author_url, created)"
        " VALUES (?, ?, ?, ?, ?)",
        (token, short_name[:32], author_name[:128], author_url[:512], time.time()),
    )
    db.commit()

    if mode == "invited":
        db.execute("UPDATE invites SET used_by = ? WHERE code = ?",
                   (token, invite))
        db.commit()

    return account(db, token)


def account(db, token):
    row = db.execute(
        "SELECT * FROM accounts WHERE token = ? AND blocked = 0", (token,)
    ).fetchone()

    if row is None:
        raise StoreError("ACCESS_TOKEN_INVALID")

    return row


def edit_account(db, token, **fields):
    allowed = {"short_name", "author_name", "author_url"}
    changes = {k: v for k, v in fields.items() if k in allowed and v is not None}

    if changes:
        assignments = ", ".join(f"{k} = ?" for k in changes)
        db.execute(
            f"UPDATE accounts SET {assignments} WHERE token = ?",
            (*changes.values(), token),
        )
        db.commit()

    return account(db, token)


def revoke(db, token):
    """
    Issue a new token for the same account and retire the old one.

    The pages stay; only the credential moves. This is the only recovery
    mechanism a tokens-are-identity design can offer.
    """

    account(db, token)           # raises if the token is not a real one
    new = secrets.token_hex(30)

    db.execute("UPDATE accounts SET token = ? WHERE token = ?", (new, token))
    db.execute("UPDATE pages SET token = ? WHERE token = ?", (new, token))
    db.commit()

    return account(db, new)


# ---------------------------------------------------------------- invites


def create_invite(db, note="", expires=None):
    """
    A one-time right to create an account.

    Shorter than a token on purpose. It is not a credential to anything
    that exists yet, so it can be read aloud, pasted into a chat, or
    written on paper without handing over an identity - and it stops
    working the moment it is used.
    """

    code = secrets.token_urlsafe(9)

    db.execute(
        "INSERT INTO invites (code, note, created, expires) VALUES (?, ?, ?, ?)",
        (code, note[:200], time.time(), expires),
    )
    db.commit()

    return code


def claim_invite(db, code):
    """
    Spend an invite, or refuse.

    Marked used before the account is created rather than after. If
    something fails in between, an invite is lost - which is a cheap thing
    to lose and trivially reissued. The other order risks a code being
    spendable twice under concurrency, which is the failure that matters.
    """

    if not code:
        raise StoreError("INVITE_REQUIRED")

    row = db.execute("SELECT * FROM invites WHERE code = ?", (code,)).fetchone()

    if row is None:
        raise StoreError("INVITE_INVALID")

    if row["used_at"] is not None:
        raise StoreError("INVITE_ALREADY_USED")

    if row["expires"] is not None and row["expires"] < time.time():
        raise StoreError("INVITE_EXPIRED")

    marked = db.execute(
        "UPDATE invites SET used_at = ? WHERE code = ? AND used_at IS NULL",
        (time.time(), code),
    )
    db.commit()

    # Zero rows means another request claimed it between the read above and
    # this write. Both callers asked honestly; only one may have it.
    if marked.rowcount != 1:
        raise StoreError("INVITE_ALREADY_USED")

    return row


def invites(db, unused_only=False):
    query = "SELECT * FROM invites"

    if unused_only:
        query += " WHERE used_at IS NULL"

    return db.execute(query + " ORDER BY created DESC").fetchall()


def any_accounts(db):
    """Whether this store has ever had an account. See server.first_run()."""

    return db.execute("SELECT 1 FROM accounts LIMIT 1").fetchone() is not None


# ------------------------------------------------------------------ paths

SLUG_STRIP = re.compile(r"[^a-zA-Z0-9]+")


def slug(title, when=None):
    """
    A path from a title, with a date suffix.

    Permanent once issued: a page's address is what consumers pin, embed
    and cite, so it can never be reassigned or reused - not even after a
    page is hidden.
    """

    stem = SLUG_STRIP.sub("-", title or "").strip("-")[:60] or "page"
    stamp = time.strftime("%m-%d", time.gmtime(when or time.time()))

    return f"{stem}-{stamp}"


def free_path(db, title):
    base = slug(title)
    candidate, suffix = base, 2

    while db.execute(
        "SELECT 1 FROM pages WHERE path = ?", (candidate,)
    ).fetchone():
        candidate = f"{base}-{suffix}"
        suffix += 1

    return candidate


# ------------------------------------------------------------------ pages


def create_page(db, token, title, content, author_name="", author_url=""):
    holder = account(db, token)
    canonical = fmt.canonical(content)

    path = free_path(db, title)
    now = time.time()

    db.execute(
        "INSERT INTO pages (path, token, title, author_name, author_url,"
        " content, revision, digest, created, updated)"
        " VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
        (path, holder["token"], (title or "Untitled")[:256],
         author_name[:128], author_url[:512],
         canonical, fmt.digest(content), now, now),
    )
    db.commit()

    return page(db, path)


def edit_page(db, token, path, title, content, author_name="", author_url=""):
    """
    Replace the page wholesale. There is no undo, and no partial edit.

    Safe to retry, unlike creation: writing the same content twice is the
    same as writing it once, which is exactly why a status page or a
    manifest can be republished on a timer without risk.
    """

    existing = page(db, path)

    if existing["token"] != token:
        account(db, token)          # raise ACCESS_TOKEN_INVALID if bogus
        raise StoreError("PAGE_ACCESS_DENIED")

    canonical = fmt.canonical(content)

    db.execute(
        "UPDATE pages SET title = ?, author_name = ?, author_url = ?,"
        " content = ?, revision = revision + 1, digest = ?, updated = ?"
        " WHERE path = ?",
        ((title or existing["title"])[:256], author_name[:128], author_url[:512],
         canonical, fmt.digest(content), time.time(), path),
    )
    db.commit()

    return page(db, path)


def page(db, path):
    row = db.execute(
        "SELECT * FROM pages WHERE path = ? AND deleted = 0", (path,)
    ).fetchone()

    if row is None:
        raise StoreError("PAGE_NOT_FOUND")

    return row


def page_list(db, token, offset=0, limit=50):
    account(db, token)

    rows = db.execute(
        "SELECT * FROM pages WHERE token = ? AND deleted = 0"
        " ORDER BY created DESC LIMIT ? OFFSET ?",
        (token, min(limit, 200), offset),
    ).fetchall()

    total = db.execute(
        "SELECT COUNT(*) FROM pages WHERE token = ? AND deleted = 0", (token,)
    ).fetchone()[0]

    return total, rows


def count_view(db, path):
    """
    One more reader.

    Deliberately not a per-viewer record: a counter increment retains
    nothing about who caused it, which is the whole of the privacy
    mechanism.
    """

    db.execute("UPDATE pages SET views = views + 1 WHERE path = ?", (path,))
    db.commit()
