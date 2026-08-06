"""
Publish a Markdown file to a bootpages instance.

    python3 tools/publish.py docs/guide.md --title "How bootpages works"
    python3 tools/publish.py docs/guide.md --title "..." --path Guide-08-05

Reads the token from BOOTPAGES_TOKEN, or prompts for it without echoing.
With --path it edits an existing page rather than creating a new one,
which is how a document gets a second draft: a path is permanent, so
republishing means editing, never re-creating.

--dry-run prints the node list and posts nothing.

This is deliberately not a Markdown implementation. It handles the subset
a technical document needs and refuses anything else, because a converter
that silently drops what it does not understand is how a published page
comes to differ from its source without anyone noticing.

Headings map to h3 and h4 because those are what the format defines.
There is no h1 or h2 in CORE_TAGS: render.document() emits the h1 for the
title itself, so content headings start below it.
"""

import argparse
import getpass
import json
import os
import re
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bootpages import format as fmt              # noqa: E402

# Inline spans, tested in this order. Links first: their text may contain
# other spans, and matching them later would break the URL apart.
INLINE = (
    (re.compile(r"\[([^\]]+)\]\(([^)]+)\)"), "a"),
    (re.compile(r"`([^`]+)`"), "code"),
    (re.compile(r"\*\*([^*]+)\*\*"), "strong"),
    (re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)"), "em"),
)


class SourceError(Exception):
    """Something in the Markdown this refuses to guess about."""


def inline(text):
    """A run of text as nodes, with spans marked up."""

    for pattern, tag in INLINE:
        match = pattern.search(text)

        if not match:
            continue

        before = inline(text[:match.start()])
        after = inline(text[match.end():])

        if tag == "a":
            node = {"tag": "a",
                    "attrs": {"href": match.group(2)},
                    "children": inline(match.group(1))}
        else:
            node = {"tag": tag, "children": inline(match.group(1))}

        return before + [node] + after

    return [text] if text else []


def blocks(source):
    """Markdown to a node list. Raises rather than guessing."""

    nodes = []
    lines = source.split("\n")
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            index += 1

        elif stripped.startswith("```"):
            index += 1
            code = []

            while index < len(lines) and not lines[index].strip().startswith("```"):
                code.append(lines[index])
                index += 1

            if index >= len(lines):
                raise SourceError("unclosed code fence")

            index += 1
            nodes.append({"tag": "pre",
                          "children": [{"tag": "code",
                                        "children": ["\n".join(code)]}]})

        elif stripped in ("---", "***", "___"):
            nodes.append({"tag": "hr"})
            index += 1

        elif stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            text = stripped.lstrip("#").strip()

            # Everything above h4 collapses to h3. The format has no h1 or
            # h2, and silently dropping a heading would be worse than
            # flattening one.
            nodes.append({"tag": "h4" if level >= 4 else "h3",
                          "children": inline(text)})
            index += 1

        elif stripped.startswith(("- ", "* ")):
            items = []

            while index < len(lines) and lines[index].strip().startswith(("- ", "* ")):
                items.append({"tag": "li",
                              "children": inline(lines[index].strip()[2:])})
                index += 1

            nodes.append({"tag": "ul", "children": items})

        elif re.match(r"^\d+\.\s", stripped):
            items = []

            while index < len(lines) and re.match(r"^\d+\.\s", lines[index].strip()):
                text = re.sub(r"^\d+\.\s+", "", lines[index].strip())
                items.append({"tag": "li", "children": inline(text)})
                index += 1

            nodes.append({"tag": "ol", "children": items})

        elif stripped.startswith(">"):
            quoted = []

            while index < len(lines) and lines[index].strip().startswith(">"):
                quoted.append(lines[index].strip().lstrip(">").strip())
                index += 1

            nodes.append({"tag": "blockquote",
                          "children": inline(" ".join(quoted))})

        elif stripped.startswith("|"):
            # Tables are a module, not a core tag. Refusing is honest;
            # rendering them as paragraphs would not be.
            raise SourceError(
                f"line {index + 1}: tables are not a core tag. Rewrite as a "
                f"list, or implement the table module first."
            )

        else:
            para = []

            while index < len(lines) and lines[index].strip() and \
                    not lines[index].strip().startswith(("#", "- ", "* ", ">", "```", "|")) and \
                    not re.match(r"^\d+\.\s", lines[index].strip()):
                para.append(lines[index].strip())
                index += 1

            nodes.append({"tag": "p", "children": inline(" ".join(para))})

    return nodes


def call(base, method, params):
    request = urllib.request.Request(
        f"{base}/{method}",
        data=json.dumps(params).encode(),
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)

    except urllib.error.URLError as problem:
        raise SystemExit(f"error: cannot reach {base}: {problem}")

    if not payload.get("ok"):
        raise SystemExit(f"error: {payload.get('error')}")

    return payload["result"]


def main():
    parser = argparse.ArgumentParser(prog="python3 tools/publish.py")
    parser.add_argument("source")
    parser.add_argument("--title", required=True)
    parser.add_argument("--author-name", default="")
    parser.add_argument("--path", help="edit this existing page instead of "
                                       "creating a new one")
    parser.add_argument("--base", default=os.environ.get(
        "BOOTPAGES_EDITOR_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    with open(args.source, encoding="utf-8") as handle:
        source = handle.read()

    try:
        nodes = blocks(source)

    except SourceError as problem:
        raise SystemExit(f"error: {problem}")

    # Validate before sending. The instance would reject a malformed node
    # list anyway; failing here names the offending path locally.
    fmt.normalise(nodes)

    if args.dry_run:
        print(json.dumps(nodes, indent=2, ensure_ascii=False))
        print(f"\n{len(nodes)} top-level nodes, "
              f"digest {fmt.digest(nodes)}", file=sys.stderr)
        return

    token = os.environ.get("BOOTPAGES_TOKEN")

    if not token:
        # getpass needs a terminal. Without one it either reads nothing or
        # echoes the token, and both failures are quiet - so say so
        # instead, because the alternative is a confusing empty prompt.
        if not sys.stdin.isatty():
            raise SystemExit(
                "error: no token.\n\n"
                "There is no terminal here to prompt on. Either set it in "
                "the environment:\n\n"
                "    read -s BOOTPAGES_TOKEN; export BOOTPAGES_TOKEN\n\n"
                "or run this from an interactive shell."
            )

        token = getpass.getpass("token: ")

    if not token.strip():
        raise SystemExit("error: empty token")

    params = {"access_token": token, "title": args.title,
              "author_name": args.author_name, "content": nodes}

    if args.path:
        params["path"] = args.path
        result = call(args.base, "editPage", params)

    else:
        result = call(args.base, "createPage", params)

    print(result["url"])


if __name__ == "__main__":
    main()
