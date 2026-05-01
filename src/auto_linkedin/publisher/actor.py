"""Actor (post-as) helpers.

For v1 we only support Path A: navigate directly to the company admin
"page posts" view, which auto-scopes the share-modal actor to that
company. We still verify the actor pill text matches the expected
company display_name — admin permissions can lapse silently and the
modal will fall back to the personal profile.

Path B (clicking the actor-switcher pill in the personal-feed share-box)
selectors live below for a future v2 fallback, but no driver code uses
them yet.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..utils.logging import get_logger
from . import selectors

if TYPE_CHECKING:
    from patchright.async_api import Locator

log = get_logger(__name__)


def company_admin_url(page_id: int) -> str:
    """Canonical URL we open to scope the actor to a company page."""
    return selectors.company_admin_page_posts_url(page_id)


def _normalize_actor_label(s: str | None) -> str:
    if not s:
        return ""
    # Strip the "Posting as " prefix LinkedIn shows on the modal pill, then
    # collapse whitespace and casefold for stable comparison.
    cleaned = re.sub(r"^posting as[:\s]*", "", s.strip(), flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip().casefold()


def actor_label_matches(visible: str | None, expected_display_name: str) -> bool:
    """Compare an actor pill's visible text against the configured display_name.

    Match is loose: the expected name needs only to be a substring of the
    visible label after normalization. LinkedIn occasionally pads pill
    text with role hints ("Posting as <Name> (Admin)" etc.).
    """
    visible_norm = _normalize_actor_label(visible)
    expected_norm = _normalize_actor_label(expected_display_name)
    if not visible_norm or not expected_norm:
        return False
    return expected_norm in visible_norm


async def read_actor_pill_text(modal: Locator) -> str | None:
    """Return the visible text of the modal's 'Posting as <Actor>' pill, or None."""
    for css in selectors.ACTOR_PILL_ALTERNATIVES:
        loc = modal.locator(css).first
        try:
            if await loc.is_visible(timeout=1_500):
                text = await loc.inner_text()
                if text:
                    return text.strip()
        except Exception:
            continue
    return None
