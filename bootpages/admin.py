"""
Minting tokens and invite codes, from a shell.

    python3 -m bootpages.admin mint    --short-name morgen --author-name "Morgen"
    python3 -m bootpages.admin invite  --count 3 --note "for the design team"
    python3 -m bootpages.admin invites
    python3 -m bootpages.admin accounts

DELIBERATELY NOT AVAILABLE OVER HTTP
------------------------------------
There is no admin account, no admin endpoint and no admin screen. The
operator's credential is shell access to the machine.

That is a security decision rather than an omission. The editor keeps
author tokens in the browser, and an admin token sitting in that same
shelf would change what stealing the shelf costs: from "someone can publish
as you" to "someone can mint unlimited accounts on your instance". Same
attack, an order of magnitude more valuable target.

If browser administration is ever wanted, the right shape is a separate
path with its own authentication - not a row in the account list.
"""

import argparse
import time

from . import store
from .config import Instance


def show_token(row, heading="Account created"):
    """
    Print a token once, loudly, with what happens if it is lost.

    There is no email, no password and no recovery question. Whoever holds
    this string is the account; whoever loses it has lost the pages.
    """

    print()
    print(f"  {heading}")
    print(f"  {'-' * len(heading)}")
    print(f"  short name   {row['short_name']}      (private, never published)")
    print(f"  byline       {row['author_name'] or '(none)'}")
    print()
    print(f"  token        {row['token']}")
    print()
    print("  This token is the entire account. There is no password to reset")
    print("  and no address to recover it to - lose it and the pages are")
    print("  orphaned permanently. Save it somewhere before closing this.")
    print()


def cmd_mint(db, args, instance):
    row = store.create_account(
        db,
        args.short_name,
        args.author_name or "",
        args.author_url or "",
        # Minting from a shell is the way accounts exist in `admin` mode,
        # so this path is not subject to the instance's mode at all.
        mode="open",
    )

    show_token(row)


def cmd_invite(db, args, instance):
    expires = None

    if args.days:
        expires = time.time() + args.days * 86400

    print()

    for _ in range(max(1, args.count)):
        code = store.create_invite(db, args.note or "", expires)
        print(f"  {code}")

    print()
    print("  An invite is a one-time right to create an account, not a")
    print("  credential to one. If it is intercepted, the worst that happens")
    print("  is a stranger creates their own account - once.")

    if expires:
        print(f"  Expires {time.strftime('%Y-%m-%d', time.localtime(expires))}.")

    if instance.mode != "invited":
        print()
        print(f"  Note: this instance is in '{instance.mode}' mode, so these")
        print("  codes will not be accepted until it runs in 'invited' mode.")

    print()


def cmd_invites(db, args, instance):
    rows = store.invites(db, unused_only=args.unused)

    if not rows:
        print("no invites")
        return

    for row in rows:
        state = "used" if row["used_at"] else "unused"

        if row["expires"] and not row["used_at"] and row["expires"] < time.time():
            state = "expired"

        note = f"  {row['note']}" if row["note"] else ""
        print(f"{row['code']:<16} {state:<8}{note}")


def cmd_accounts(db, args, instance):
    """
    Every account, without its token.

    The tokens are in the database and the operator can read them - but
    printing them by default would put a screenful of permanent credentials
    into a terminal history for no reason.
    """

    rows = db.execute(
        "SELECT a.short_name, a.author_name, a.created, a.blocked,"
        " (SELECT COUNT(*) FROM pages p WHERE p.token = a.token"
        "  AND p.deleted = 0) AS pages"
        " FROM accounts a ORDER BY a.created"
    ).fetchall()

    if not rows:
        print("no accounts")
        return

    for row in rows:
        when = time.strftime("%Y-%m-%d", time.localtime(row["created"]))
        flag = "  BLOCKED" if row["blocked"] else ""
        print(f"{row['short_name']:<20} {row['pages']:>4} pages   {when}{flag}")


COMMANDS = {
    "mint": cmd_mint,
    "invite": cmd_invite,
    "invites": cmd_invites,
    "accounts": cmd_accounts,
}


def main():
    parser = argparse.ArgumentParser(
        prog="python3 -m bootpages.admin",
        description="Mint tokens and invite codes. Shell access is the "
                    "administrative credential; there is no admin account.",
    )
    parser.add_argument("--db", default=None)

    sub = parser.add_subparsers(dest="command", required=True)

    mint = sub.add_parser("mint", help="create an account and print its token")
    mint.add_argument("--short-name", required=True,
                      help="private, never published - how you tell accounts apart")
    mint.add_argument("--author-name", help="the public byline")
    mint.add_argument("--author-url")

    invite = sub.add_parser("invite", help="create one-time invite codes")
    invite.add_argument("--count", type=int, default=1)
    invite.add_argument("--note", help="what these were for")
    invite.add_argument("--days", type=int, help="expire after this many days")

    listing = sub.add_parser("invites", help="list invite codes")
    listing.add_argument("--unused", action="store_true")

    sub.add_parser("accounts", help="list accounts, without their tokens")

    args = parser.parse_args()

    instance = Instance(database=args.db)
    db = store.connect(instance.database)

    try:
        COMMANDS[args.command](db, args, instance)

    except store.StoreError as problem:
        raise SystemExit(f"error: {problem}")


if __name__ == "__main__":
    main()
