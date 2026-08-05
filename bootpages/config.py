"""
What this instance is.

The first configuration bootpages has needed, and it exists for one
reason: an instance can be open, invited or admin-minted, and a client
cannot know which until it asks. The editor's first-run screen is a
function of the answer, not a static design.

Everything has a default that works, and every value can come from either
the environment or the command line. There is still no configuration file
and still no secret to place.
"""

import os

# How an account comes into being. Enforced in the API, not in the UI - a
# client that skips the modal gets the same answer as one that does not.
MODES = ("open", "invited", "admin")

# The default is the tightest of the three. A fresh instance mints nothing
# for a stranger, and the operator hands out tokens or invite codes
# deliberately.
#
# The friction that would otherwise cause - a new instance where nobody can
# write anything - is handled by minting one token on first run against an
# empty store. See server.first_run().
DEFAULT_MODE = "admin"


class ConfigError(Exception):
    """A setting that would produce a service nobody meant to run."""


def env(name, default=""):
    """An empty environment variable counts as unset."""

    return os.environ.get(name) or default


class Instance:
    """
    Everything about this deployment that is not code.

    Held as one object so that the pieces which have to agree - the mode,
    the two origins, whether a public bind was asked for - are validated
    together rather than checked in four places.
    """

    def __init__(self, name=None, description=None, mode=None, contact=None,
                 host=None, port=None, pages_host=None, pages_port=None,
                 pages_url=None, database=None, allow_public=False):

        self.name = name or env("BOOTPAGES_NAME", "Bootpages")
        self.description = description or env(
            "BOOTPAGES_DESCRIPTION",
            "A store for portable declarative manifests.",
        )
        self.contact = contact or env("BOOTPAGES_CONTACT", "")

        self.mode = (mode or env("BOOTPAGES_MODE", DEFAULT_MODE)).lower()

        self.host = host or env("BOOTPAGES_HOST", "127.0.0.1")
        self.port = int(port or env("BOOTPAGES_PORT", "8080"))

        # Published pages live on a different origin from the editor, so
        # that a script which somehow executed inside a page cannot read
        # the tokens the editor keeps. The browser enforces that, keyed on
        # origin - scheme, host and port - so a different port is enough
        # and one process serves both.
        self.pages_host = pages_host or env("BOOTPAGES_PAGES_HOST", self.host)
        self.pages_port = int(pages_port or env("BOOTPAGES_PAGES_PORT", "8081"))

        # Behind a reverse proxy the public address is not something this
        # process can work out. It serves plain HTTP on loopback while the
        # world sees HTTPS on a name nothing here has been told, so the one
        # URL that must be right has to be given rather than derived.
        #
        # Trailing slash stripped because api.py builds f"{pages_url}/{path}"
        # and a double slash would end up in every published link.
        self._pages_url = (pages_url or "").rstrip("/")

        self.database = database or env("BOOTPAGES_DB", "data/bootpages.db")
        self.allow_public = allow_public

        self._check()

    # ------------------------------------------------------------- checks

    LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost", ""})

    def _check(self):
        if self.mode not in MODES:
            raise ConfigError(
                f"mode {self.mode!r} is not one of {', '.join(MODES)}"
            )

        if self.port == self.pages_port and self.host == self.pages_host:
            raise ConfigError(
                "the editor and published pages must not share an origin. "
                "That separation is what stops a script inside a page "
                "reading the tokens the editor stores."
            )

        public = not self.is_loopback

        if public and not self.allow_public:
            raise ConfigError(self.public_warning())

        # Reachable from elsewhere and open to anyone is a combination that
        # should never happen by accident, so saying --allow-public is not
        # enough on its own: the mode has to be stated too.
        if public and self.allow_public and self.mode == "open":
            if not env("BOOTPAGES_MODE"):
                raise ConfigError(
                    "refusing to serve mode 'open' on a public address "
                    "without being told so explicitly.\n\n"
                    "Set BOOTPAGES_MODE=open or pass --mode open if that is "
                    "genuinely what you want. Anyone who can reach the port "
                    "will be able to mint accounts and publish permanent "
                    "public pages."
                )

    @property
    def is_loopback(self):
        return self.host in self.LOOPBACK and self.pages_host in self.LOOPBACK

    def public_warning(self):
        return (
            f"Refusing to bind to {self.host}.\n\n"
            f"Binding to a loopback address is currently the only network "
            f"gate this service has. If you meant it - you are behind a "
            f"reverse proxy that authenticates, or on a network you control "
            f"- say so explicitly:\n\n"
            f"    python3 -m bootpages.server --host {self.host} "
            f"--mode {self.mode} --allow-public\n\n"
            f"Nothing about that flag is a security control. It is a speed "
            f"bump placed where an accident would otherwise be silent."
        )

    # -------------------------------------------------------------- urls

    @property
    def pages_url(self):
        """
        Where a published page lives.

        Every API response reports this rather than whatever Host the
        request arrived on, so the editor hands out links to the pages
        origin rather than back to itself.

        Given outright wins, then the environment, then the local bind -
        the last of which is only ever right when nothing is in front.
        """

        if self._pages_url:
            return self._pages_url

        return env(
            "BOOTPAGES_PAGES_URL",
            f"http://{self.pages_host or '127.0.0.1'}:{self.pages_port}",
        ).rstrip("/")

    @property
    def editor_url(self):
        return f"http://{self.host or '127.0.0.1'}:{self.port}"

    # ------------------------------------------------------------ public

    def describe(self):
        """
        What a client is told before it decides what to show.

        Deliberately small: a name, a sentence, the mode, and how to reach
        a human if the mode means asking one. Nothing here is a secret and
        nothing identifies anybody.
        """

        return {
            "name": self.name,
            "description": self.description,
            "mode": self.mode,
            "contact": self.contact,
            "pages_url": self.pages_url,
        }
