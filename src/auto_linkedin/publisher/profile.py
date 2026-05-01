"""Helpers for verifying LinkedIn posts before and after publishing.

The core idea: a LinkedIn activity URN (urn:li:activity:<id>) is the stable
post identifier. It appears as a `data-urn` attribute on every row in the
company admin "page posts" grid, and inside the post permalink path
`/feed/update/<urn>/`. We use it for two things:

1. Pre-publish dedup — fetch the latest post's caption and bail if it
   matches the caption we're about to publish (the previous run
   probably succeeded but its confirmation timed out).
2. Post-publish verification — compare the latest URN before and after
   clicking Post. A delta is the authoritative success signal, regardless
   of whether the success toast appears.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..utils.logging import get_logger
from . import selectors

if TYPE_CHECKING:
    from patchright.async_api import Page

log = get_logger(__name__)

# Activity URN: urn:li:activity:NNNNNNNNNNNNNNNNNNN (typically 19 digits, but allow any digit run).
_URN_RE = re.compile(r"urn:li:activity:(\d+)")


def urn_from_dataset(value: str | None) -> str | None:
    """Extract a normalized activity URN from a `data-urn` attribute value.

    Returns the canonical 'urn:li:activity:<id>' string, or None if the
    input doesn't match the activity-URN shape.
    """
    if not value:
        return None
    m = _URN_RE.search(value)
    return f"urn:li:activity:{m.group(1)}" if m else None


def urn_from_href(href: str | None) -> str | None:
    """Extract an activity URN from a post permalink path.

    Accepts:
      - /feed/update/urn:li:activity:7236789012345678901/
      - https://www.linkedin.com/feed/update/urn:li:activity:7236789012345678901/
    """
    if not href:
        return None
    m = _URN_RE.search(href)
    return f"urn:li:activity:{m.group(1)}" if m else None


def normalize_caption(s: str | None) -> str:
    """Collapse whitespace + case-fold for comparison. Empty / None → ''."""
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip().casefold()


def captions_match(a: str | None, b: str | None) -> bool:
    na, nb = normalize_caption(a), normalize_caption(b)
    return bool(na) and na == nb


async def latest_activity_urn(page: Page, page_id: int, *, timeout_ms: int = 15_000) -> str | None:
    """Navigate to the company's admin page-posts grid and return the URN
    of the first row, or None if the grid is empty or didn't render in time.
    """
    await page.goto(
        selectors.company_admin_page_posts_url(page_id),
        wait_until="domcontentloaded",
    )
    for css in selectors.ADMIN_GRID_ROW_ALTERNATIVES:
        loc = page.locator(css).first
        try:
            await loc.wait_for(state="visible", timeout=timeout_ms)
        except Exception:
            continue
        raw = await loc.get_attribute("data-urn")
        urn = urn_from_dataset(raw)
        if urn:
            return urn
    return None


async def fetch_post_caption_by_urn(page: Page, urn: str, *, timeout_ms: int = 15_000) -> str | None:
    """Navigate to /feed/update/<urn>/ and scrape the post body text.

    LinkedIn's og:description is sliced; DOM scrape of the post body is more
    reliable. Returns None if the body element is not found within timeout.
    """
    await page.goto(selectors.feed_update_url(urn), wait_until="domcontentloaded")
    for css in selectors.POST_BODY_TEXT_ALTERNATIVES:
        loc = page.locator(css).first
        try:
            await loc.wait_for(state="visible", timeout=timeout_ms)
        except Exception:
            continue
        text = await loc.inner_text()
        if text:
            return text.strip()
    return None
