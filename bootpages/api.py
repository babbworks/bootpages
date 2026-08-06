"""
The eight methods.

Shaped like Telegraph's on purpose: a flat call returning
{ok: true, result} or {ok: false, error}, with the same names and the same
parameters. A client written for Telegraph should work against this by
changing one base URL and nothing else.

Two fields are added to a page - `revision` and `digest`. Clients ignore
response fields they do not recognise, so adding them costs nothing in
compatibility and is what makes change control possible for anyone who
wants it.
"""

import json

from . import format as fmt
from . import store


class ApiError(Exception):
    """Returned as {ok: false, error}. The message is the error code."""


def parse_content(raw):
    """
    The `content` parameter arrives as a JSON string, as it does in
    Telegraph. Everything after this point is a node list.
    """

    if isinstance(raw, (list, tuple)):
        return list(raw)

    if not raw:
        return []

    try:
        parsed = json.loads(raw)

    except ValueError:
        raise ApiError("CONTENT_FORMAT_INVALID")

    if not isinstance(parsed, list):
        raise ApiError("CONTENT_FORMAT_INVALID")

    return parsed


def account_json(db, row):
    count = db.execute(
        "SELECT COUNT(*) FROM pages WHERE token = ? AND deleted = 0",
        (row["token"],),
    ).fetchone()[0]

    return {
        "short_name": row["short_name"],
        "author_name": row["author_name"],
        "author_url": row["author_url"],
        "access_token": row["token"],
        "page_count": count,
    }


def page_json(row, instance, content=False):
    payload = {
        "path": row["path"],
        # The pages origin, never the origin this request arrived on. The
        # editor hands out links to where pages live rather than back to
        # itself, and that split is what stops a script inside a page
        # reading the tokens the editor stores.
        "url": f"{instance.pages_url}/{row['path']}",
        "title": row["title"],
        "author_name": row["author_name"],
        "author_url": row["author_url"],
        "views": row["views"],
        # Not in Telegraph. `revision` orders edits, `digest` identifies
        # content - two different questions, so two answers. See
        # docs/format.md#revision-markers.
        "revision": row["revision"],
        "digest": row["digest"],
    }

    if content:
        payload["content"] = json.loads(row["content"])

    return payload


# --------------------------------------------------------------- dispatch


def call(db, method, params, instance):
    handler = METHODS.get(method)

    if handler is None:
        raise ApiError("METHOD_NOT_FOUND")

    try:
        return handler(db, params, instance)

    except store.StoreError as problem:
        raise ApiError(str(problem))

    except fmt.FormatError as problem:
        # The format's own message names the offending path, which is far
        # more use to whoever is debugging than a bare error code.
        raise ApiError(f"CONTENT_FORMAT_INVALID: {problem}")


def _create_account(db, params, instance):
    # The mode is enforced here, in the store, rather than by the client
    # choosing not to offer a button. A request that skips the first-run
    # screen gets exactly the same answer as one that does not.
    row = store.create_account(
        db,
        params.get("short_name", ""),
        params.get("author_name", ""),
        params.get("author_url", ""),
        mode=instance.mode,
        invite=params.get("invite"),
    )

    return account_json(db, row)


def _get_account_info(db, params, instance):
    row = store.account(db, params.get("access_token", ""))
    payload = account_json(db, row)

    # Telegraph returns only the fields asked for. Honoured because a
    # client asking for two fields should not be handed a token it did not
    # request.
    fields = params.get("fields")

    if fields:
        try:
            wanted = set(json.loads(fields))

        except ValueError:
            raise ApiError("FIELDS_INVALID")

        payload = {k: v for k, v in payload.items() if k in wanted}

    return payload


def _edit_account_info(db, params, instance):
    row = store.edit_account(
        db,
        params.get("access_token", ""),
        short_name=params.get("short_name"),
        author_name=params.get("author_name"),
        author_url=params.get("author_url"),
    )

    return account_json(db, row)


def _revoke_access_token(db, params, instance):
    return account_json(db, store.revoke(db, params.get("access_token", "")))


def _create_page(db, params, instance):
    row = store.create_page(
        db,
        params.get("access_token", ""),
        params.get("title", ""),
        parse_content(params.get("content")),
        params.get("author_name", ""),
        params.get("author_url", ""),
    )

    return page_json(row, instance, content=params.get("return_content") == "true")


def _edit_page(db, params, instance):
    row = store.edit_page(
        db,
        params.get("access_token", ""),
        params.get("path", ""),
        params.get("title", ""),
        parse_content(params.get("content")),
        params.get("author_name", ""),
        params.get("author_url", ""),
    )

    return page_json(row, instance, content=params.get("return_content") == "true")


def _get_page(db, params, instance):
    row = store.page(db, params.get("path", ""))
    ref = params.get("ref")

    if not ref:
        return page_json(row, instance,
                         content=params.get("return_content") == "true")

    # One block of the page, with a fingerprint of its own.
    #
    # `digest` keeps meaning what it always meant - the whole page - and
    # `ref_digest` is the branch. Overloading the existing field would
    # silently change what an old client thought it was comparing.
    try:
        nodes = fmt.subtree(json.loads(row["content"]), ref)

    except fmt.FormatError:
        raise ApiError("REF_NOT_FOUND")

    # Only what the subtree itself determines.
    #
    # Page-level fields are deliberately absent. `views` changes on every
    # read and `revision` on every edit anywhere, so including either would
    # make the body drift under an ETag that cannot see it - and the whole
    # point of this route is that the response is unchanged exactly when
    # the block is. A subscriber wanting page facts asks for the page.
    return {
        "path": row["path"],
        "ref": ref,
        "ref_url": f"{instance.pages_url}/{row['path']}#{ref}",
        "ref_digest": fmt.digest(nodes),
        "content": nodes,
    }


def _get_page_list(db, params, instance):
    total, rows = store.page_list(
        db,
        params.get("access_token", ""),
        int(params.get("offset") or 0),
        int(params.get("limit") or 50),
    )

    return {
        "total_count": total,
        "pages": [page_json(row, instance) for row in rows],
    }


def _get_instance_info(db, params, instance):
    """
    What this instance is, so a client knows what to offer.

    Not a Telegraph method - Telegraph has exactly one mode and never
    needed to say so. An instance here can be open, invited or
    admin-minted, and the first-run screen is a function of the answer
    rather than a static design.

    Everything returned is public by construction: a name, a sentence, the
    mode, and how to reach a human if the mode means asking one.
    """

    return instance.describe()


METHODS = {
    "getInstanceInfo": _get_instance_info,
    "createAccount": _create_account,
    "getAccountInfo": _get_account_info,
    "editAccountInfo": _edit_account_info,
    "revokeAccessToken": _revoke_access_token,
    "createPage": _create_page,
    "editPage": _edit_page,
    "getPage": _get_page,
    "getPageList": _get_page_list,
}
