"""
How an account comes into being, and what stops one.

Enforced in the store rather than in the UI, so these tests exercise the
thing that actually decides. A client that skips the first-run screen gets
the same answers as one that does not.
"""

import time

import pytest

from bootpages import store
from bootpages.config import ConfigError, Instance


@pytest.fixture
def db(tmp_path):
    return store.connect(str(tmp_path / "t.db"))


# --------------------------------------------------------------- modes


def test_open_mode_lets_anyone_in(db):
    row = store.create_account(db, "someone", mode="open")

    assert row["short_name"] == "someone"
    assert len(row["token"]) == 60


def test_admin_mode_refuses_outright(db):
    """
    The default. A fresh instance mints nothing for a stranger; the
    operator hands out tokens deliberately.
    """

    with pytest.raises(store.StoreError, match="ACCOUNT_CREATION_CLOSED"):
        store.create_account(db, "someone", mode="admin")


def test_invited_mode_needs_a_code(db):
    with pytest.raises(store.StoreError, match="INVITE_REQUIRED"):
        store.create_account(db, "someone", mode="invited")


def test_a_short_name_is_always_required(db):
    with pytest.raises(store.StoreError, match="SHORT_NAME_REQUIRED"):
        store.create_account(db, "", mode="open")


# -------------------------------------------------------------- invites


def test_an_invite_works_once(db):
    """
    The property that makes invites worth having over handing out tokens:
    an invite is a one-time right to create an account, not a credential to
    one. Intercepted, the worst outcome is a stranger creates their own.
    """

    code = store.create_invite(db, note="design team")

    row = store.create_account(db, "designer", mode="invited", invite=code)
    assert row["short_name"] == "designer"

    with pytest.raises(store.StoreError, match="INVITE_ALREADY_USED"):
        store.create_account(db, "again", mode="invited", invite=code)


def test_an_unknown_code_is_refused(db):
    with pytest.raises(store.StoreError, match="INVITE_INVALID"):
        store.create_account(db, "someone", mode="invited", invite="nope")


def test_an_expired_code_is_refused(db):
    code = store.create_invite(db, expires=time.time() - 1)

    with pytest.raises(store.StoreError, match="INVITE_EXPIRED"):
        store.create_account(db, "someone", mode="invited", invite=code)


def test_validation_failures_do_not_burn_the_invite(db):
    """
    The short name is checked before the invite is claimed, so submitting
    the form wrong does not cost somebody their one-time code. Burning it
    on a typo would be a miserable thing to do to a new user.

    The narrower window - between the claim and the insert - is handled the
    other way round, on purpose: see claim_invite, where an invite lost to
    a crash is cheap and reissuable, while one spendable twice under
    concurrency is the failure that matters.
    """

    code = store.create_invite(db)

    with pytest.raises(store.StoreError, match="SHORT_NAME_REQUIRED"):
        store.create_account(db, "", mode="invited", invite=code)

    assert len(store.invites(db, unused_only=True)) == 1

    # And it still works afterwards.
    assert store.create_account(db, "designer", mode="invited", invite=code)


def test_the_invite_records_which_account_used_it(db):
    code = store.create_invite(db)
    row = store.create_account(db, "designer", mode="invited", invite=code)

    used = store.invites(db)[0]

    assert used["used_by"] == row["token"]
    assert used["used_at"] is not None


def test_any_accounts_reports_an_empty_store(db):
    """What first_run() consults, so a fresh instance is usable at once."""

    assert store.any_accounts(db) is False

    store.create_account(db, "first", mode="open")

    assert store.any_accounts(db) is True


# --------------------------------------------------------------- config


def test_the_default_mode_is_the_tightest():
    assert Instance().mode == "admin"


def test_an_unknown_mode_is_refused():
    with pytest.raises(ConfigError, match="not one of"):
        Instance(mode="wideopen")


def test_the_two_origins_may_not_collide():
    """
    Same origin means one localStorage, which means a script inside a
    published page could read the tokens the editor keeps. That separation
    is the whole reason there are two listeners.
    """

    with pytest.raises(ConfigError, match="must not share an origin"):
        Instance(port=8080, pages_port=8080)


def test_a_public_bind_is_refused_by_default():
    with pytest.raises(ConfigError, match="Refusing to bind"):
        Instance(host="0.0.0.0")


def test_a_public_bind_is_allowed_when_asked_for():
    instance = Instance(host="0.0.0.0", mode="admin", allow_public=True)

    assert instance.is_loopback is False


def test_public_and_open_together_need_saying_twice(monkeypatch):
    """
    Reachable from elsewhere AND open to anyone is the combination that
    should never happen by accident, so --allow-public alone is not enough.
    """

    monkeypatch.delenv("BOOTPAGES_MODE", raising=False)

    with pytest.raises(ConfigError, match="without being told so explicitly"):
        Instance(host="0.0.0.0", mode="open", allow_public=True)


def test_pages_url_is_its_own_origin():
    instance = Instance(port=8080, pages_port=8081)

    assert instance.pages_url.endswith(":8081")
    assert instance.editor_url.endswith(":8080")


def test_describe_carries_no_secret():
    described = Instance().describe()

    assert set(described) == {"name", "description", "mode", "contact", "pages_url"}
