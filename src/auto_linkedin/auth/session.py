"""Session state checks: logged-in detection, challenge detection."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..utils.logging import get_logger

if TYPE_CHECKING:
    from patchright.async_api import Page

log = get_logger(__name__)

LINKEDIN_URL = "https://www.linkedin.com/"
LINKEDIN_FEED_URL = "https://www.linkedin.com/feed/"
LINKEDIN_LOGIN_URL = "https://www.linkedin.com/login"

# URL substrings that indicate LinkedIn is blocking us from posting.
# Includes /login (bare redirect when session is dead) and /authwall (public-page wall).
CHALLENGE_URL_MARKERS = (
    "/checkpoint/challenge/",
    "/checkpoint/lg/",
    "/checkpoint/rm/",
    "/uas/login",
    "/authwall",
)

# li_at is the primary auth cookie; without it the session is dead.
SESSION_COOKIE_NAMES = {"li_at", "JSESSIONID"}


class ChallengeRequiredError(RuntimeError):
    """LinkedIn issued a checkpoint / login redirect / authwall. Manual action needed."""


class NotAuthenticatedError(RuntimeError):
    """No valid session; user must run `auto-li login` or `import-cookies`."""


async def is_logged_in(page: Page) -> bool:
    """Navigate to the LinkedIn feed and confirm we landed on the authenticated home.

    We hit `/feed/` (not the company admin URL) because the feed is the
    cheapest authenticated surface and avoids permission-related noise.
    Unauthenticated landing redirects to /login, /uas/login, or the bare
    homepage; the page title in those states never contains "Feed".

    Two signals are checked, both required:
      1. The final URL is on /feed/ (no challenge / login redirect).
      2. The document title contains "Feed" — set only on the
         authenticated feed view.
    """
    await page.goto(LINKEDIN_FEED_URL, wait_until="domcontentloaded")

    current = page.url
    log.debug("current URL after navigation: %s", current)
    if _is_challenge_url(current) or _looks_like_unauth_landing(current):
        return False
    if "/feed/" not in current:
        return False

    import asyncio as _asyncio
    await _asyncio.sleep(2.0)
    await dismiss_popups(page)

    try:
        title = await page.title()
    except Exception:
        title = ""
    # Authenticated feed pages have titles like "Feed | LinkedIn" or
    # "(N) Feed | LinkedIn". Unauthenticated landings are "LinkedIn",
    # "Sign Up | LinkedIn", "LinkedIn Login", etc.
    return "Feed" in title


def _is_challenge_url(url: str) -> bool:
    return any(marker in url for marker in CHALLENGE_URL_MARKERS)


def _looks_like_unauth_landing(url: str) -> bool:
    """Detect bare unauthenticated landing pages.

    LinkedIn sends dead sessions to `https://www.linkedin.com/` (homepage,
    promo content) or `https://www.linkedin.com/login` rather than always
    going through /uas/login. We treat both as "not logged in".
    """
    if "/login" in url and "/feed/" not in url:
        return True
    return url.rstrip("/") in {"https://www.linkedin.com", "https://linkedin.com"}


# Texts of the dismiss buttons LinkedIn shows on first visit / post-login.
_POPUP_DISMISS_TEXTS = (
    "Got it",
    "Skip",
    "Maybe later",
    "Dismiss",
    "Not now",
    "No thanks",
    "Close",
    "Cancel",
)


async def dismiss_popups(page: Page, *, rounds: int = 3) -> int:
    """Click through any 'Got it' / 'Skip' / 'Maybe later' popups LinkedIn shows.

    Returns the number of popups dismissed. Safe to call when none are present.
    """
    dismissed = 0
    for _ in range(rounds):
        clicked_this_round = False
        for text in _POPUP_DISMISS_TEXTS:
            loc = page.get_by_role("button", name=text).first
            try:
                if await loc.is_visible(timeout=1_500):
                    await loc.click()
                    dismissed += 1
                    clicked_this_round = True
                    log.debug("dismissed popup via '%s'", text)
                    break
            except Exception:
                continue
        if not clicked_this_round:
            break
    return dismissed


async def detect_challenge(page: Page) -> None:
    """Raise ChallengeRequiredError if the current page is a challenge/login redirect."""
    current = page.url
    if _is_challenge_url(current):
        raise ChallengeRequiredError(
            f"LinkedIn redirected to {current}. "
            "Re-authenticate with `auto-li login` and retry."
        )
