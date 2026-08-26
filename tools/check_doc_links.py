"""Check that every external link in the documentation still resolves.

The docs cite AWS pages, archive portals, model cards, and standards documents,
and those URLs rot quietly: a host reorganizes and a link that shipped fine a
year ago starts answering 404. Nothing in the offline test suite can notice,
because noticing requires the network.

That is also why this check is deliberately NOT part of the pull-request gate.
AKT Reader's premise is that everything runs offline and deterministically, and
a network call in the PR gate would make contributors' builds depend on the
reachability of someone else's website. It runs on a schedule instead, where a
failure is a maintenance signal rather than a blocked contribution.

Boundary note: the no-egress guarantee enforced by ``tests/test_no_egress.py``
covers the ``src/aktreader`` package. This script lives in ``tools/``, uses the
network on purpose, and is invoked only by the scheduled maintenance workflow —
it never ships with, or is imported by, the package.

Exit code 0 when every link resolves, 1 when any does not.
"""

from __future__ import annotations

import argparse
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

_TIMEOUT_SECONDS = 30
# Plain courtesy to the documentation hosts, and enough of a gap that a burst
# of requests is not mistaken for scraping.
_DELAY_SECONDS = 0.4
_USER_AGENT = "aktreader-doc-link-check (+https://github.com/jakegold1647/aktreader)"

# Statuses meaning "ask again later" rather than "this link is gone". A 404 is a
# real answer and is not retried. A timeout or a 503 is the host having a moment,
# and reporting that as rot is how a weekly maintenance signal earns a reputation
# for crying wolf - after which nobody reads it.
_RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
_RETRY_DELAY_SECONDS = 3.0

# Some archive portals answer 403 to anything that does not look like a
# browser. A 403 that clears with a browser User-Agent is bot filtering, not
# rot; a 403 that persists is reported.
_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# Hosts whose bot protection runs a JavaScript challenge no plain HTTP client
# can pass, so a script cannot distinguish rot from filtering. These are
# skipped and counted separately; verify them in a browser when they change.
# nli.org.il: confirmed loading in a real browser on 2026-08-25 while
# answering 403 to every scripted client.
_BROWSER_ONLY_HOSTS = frozenset({"www.nli.org.il"})

# Markdown link forms the docs actually use: inline links, autolinks, and
# reference definitions.
_LINK_PATTERNS = (
    re.compile(r"\]\((?P<url>https?://[^)\s]+)\)"),
    re.compile(r"<(?P<url>https?://[^>\s]+)>"),
    re.compile(r"^\[[^\]]+\]:\s*(?P<url>https?://\S+)", re.MULTILINE),
)

# Loopback and link-local hosts appear in the self-hosted service docs as
# examples of the supported boundary; they are not public links to verify.
_NON_PUBLIC_HOST = re.compile(
    r"^https?://(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]|169\.254\.)", re.IGNORECASE
)


def documentation_links() -> dict[str, list[str]]:
    """Map each unique external URL to the ``file:line`` locations citing it."""

    links: dict[str, list[str]] = {}
    for path in sorted(REPO_ROOT.rglob("*.md")):
        if ".git" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in _LINK_PATTERNS:
            for match in pattern.finditer(text):
                url = match.group("url").rstrip(".,;")
                if _NON_PUBLIC_HOST.match(url) or "{" in url or "}" in url:
                    continue
                line = text.count("\n", 0, match.start()) + 1
                location = f"{path.relative_to(REPO_ROOT).as_posix()}:{line}"
                links.setdefault(url, []).append(location)
    return links


def _status(url: str, user_agent: str = _USER_AGENT) -> int | str:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except Exception as error:  # noqa: BLE001 - any failure is worth reporting
        return type(error).__name__


def _status_with_retry(url: str) -> int | str:
    """Fetch a status, asking a second time when the first answer was not final.

    One attempt makes a weekly check as reliable as the flakiest host it
    touches. A definitive 404 is taken at its word; anything transient gets one
    more try after a pause.
    """

    code = _status(url)
    if code == 200:
        return code
    if code == 403:
        code = _status(url, user_agent=_BROWSER_USER_AGENT)
        return code
    if isinstance(code, str) or code in _RETRYABLE_STATUS:
        time.sleep(_RETRY_DELAY_SECONDS)
        code = _status(url)
    return code


def check_doc_links() -> tuple[list[str], int, int]:
    """Return problems, the count of links checked, and the count skipped.

    Skipped links live on hosts in ``_BROWSER_ONLY_HOSTS``.
    """

    links = documentation_links()
    problems: list[str] = []
    skipped = 0
    for url in sorted(links):
        host = urllib.parse.urlparse(url).netloc
        if host in _BROWSER_ONLY_HOSTS:
            skipped += 1
            continue
        code = _status_with_retry(url)
        if code != 200:
            citations = ", ".join(links[url][:5])
            problems.append(f"{url} returned {code}; cited by {citations}.")
        time.sleep(_DELAY_SECONDS)
    return problems, len(links) - skipped, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--format",
        choices=("text", "github"),
        default="text",
        help="github emits one ::error workflow command per problem",
    )
    args = parser.parse_args()

    problems, link_count, skipped = check_doc_links()
    skipped_note = f" ({skipped} browser-only link(s) skipped)" if skipped else ""
    if not problems:
        print(f"Documentation links OK: {link_count} unique links all resolve{skipped_note}.")
        return 0

    for problem in problems:
        if args.format == "github":
            print(f"::error title=Documentation link check::{problem}")
        else:
            print(f"ERROR: {problem}")
    print(f"{len(problems)} unreachable link(s) across {link_count} checked.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
