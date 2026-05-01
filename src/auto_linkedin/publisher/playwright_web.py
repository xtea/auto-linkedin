"""The Playwright-web-driven LinkedIn publisher.

Drives the company-page admin "page posts" view (Path A from the
implementation plan): navigates directly to the admin URL, opens the
share modal from there, verifies the actor pill, types the caption,
uploads any media, clicks Post, and confirms via URN delta against the
pre-publish first-row URN.

Personal-feed posting is intentionally out of scope for v1 — every
publish call requires a resolved company page.
"""
from __future__ import annotations

import asyncio
import random
from pathlib import Path
from typing import TYPE_CHECKING

from ..auth.session import (
    ChallengeRequiredError,
    NotAuthenticatedError,
    detect_challenge,
    dismiss_popups,
    is_logged_in,
)
from ..browser.factory import launch_context
from ..config import AccountConfig, CompanyPage, PacingSettings, resolve_company_page
from ..content.models import Post, PostType
from ..utils.logging import get_logger
from . import selectors as sel
from .actor import actor_label_matches, read_actor_pill_text
from .base import PublishResult
from .profile import (
    captions_match,
    fetch_post_caption_by_urn,
    latest_activity_urn,
    urn_from_dataset,
)

if TYPE_CHECKING:
    from patchright.async_api import BrowserContext, Locator, Page

log = get_logger(__name__)


class WrongActorError(RuntimeError):
    """The share-modal opened with the wrong actor (admin permissions may have lapsed)."""


# Sentinel used internally; never leaves this module.
_ALREADY_PUBLISHED = object()


class PlaywrightWebPublisher:
    """Publishes a Post to a LinkedIn company page by driving linkedin.com."""

    def __init__(self, account: AccountConfig, session_file: Path) -> None:
        self.account = account
        self.session_file = session_file
        self._pacing = account.pacing
        self._last_seen_urn: str | None = None

    async def healthcheck(self) -> bool:
        if not self.session_file.exists():
            return False
        async with launch_context(self.account, self.session_file) as ctx:
            page = await ctx.new_page()
            return await is_logged_in(page)

    async def publish(
        self,
        post: Post,
        *,
        dry_run: bool = False,
        force: bool = False,
        page_id_override: int | None = None,
    ) -> PublishResult:
        if not self.session_file.exists():
            raise NotAuthenticatedError(
                f"No session file at {self.session_file}. "
                "Run `auto-li login` or `auto-li import-cookies` first."
            )

        target_page = resolve_company_page(
            self.account,
            cli_override=page_id_override,
            post_override=post.as_company,
        )
        log.info(
            "Publishing as company '%s' (id=%d) — type=%s, source=%s",
            target_page.display_name,
            target_page.id,
            post.type.value,
            post.source_dir.name,
        )

        async with launch_context(self.account, self.session_file) as ctx:
            page = await ctx.new_page()

            if not await is_logged_in(page):
                raise NotAuthenticatedError(
                    "Session appears invalid. Re-authenticate with `auto-li login`."
                )
            await dismiss_popups(page)

            pre_urn = await self._dedup_guard(ctx, target_page, post, force=force)
            if pre_urn is _ALREADY_PUBLISHED:
                urn = self._last_seen_urn
                return PublishResult(
                    ok=True,
                    already_published=True,
                    shortcode=urn,
                    url=sel.feed_update_url(urn) if urn else None,
                )

            await _pre_run_idle(page, self._pacing)
            try:
                result = await self._run_flow(
                    ctx,
                    page,
                    post,
                    target_page=target_page,
                    pre_urn=pre_urn if isinstance(pre_urn, str) else None,
                    dry_run=dry_run,
                )
            except (ChallengeRequiredError, WrongActorError):
                raise
            except Exception as e:
                await detect_challenge(page)
                raise RuntimeError(f"Publish failed: {e}") from e
            return result

    async def _dedup_guard(
        self,
        ctx: BrowserContext,
        target_page: CompanyPage,
        post: Post,
        *,
        force: bool,
    ) -> str | None | object:
        """Return the latest activity URN on the company's admin grid, the
        `_ALREADY_PUBLISHED` sentinel if its caption matches the incoming
        caption (and `force` is False), or None if the grid is empty.
        """
        check_page = await ctx.new_page()
        try:
            urn = await latest_activity_urn(check_page, target_page.id)
            if not urn:
                log.debug("No existing posts on company page; dedup skipped.")
                return None

            if force:
                log.debug("--force: skipping dedup check.")
                return urn

            if not post.caption:
                # Without a caption we can't reliably dedup; fall through.
                return urn

            latest_caption = await fetch_post_caption_by_urn(check_page, urn)
            if captions_match(latest_caption, post.caption):
                log.warning(
                    "Latest post (%s) already has this exact caption; "
                    "treating as already-published. Use --force to override.",
                    urn,
                )
                self._last_seen_urn = urn
                return _ALREADY_PUBLISHED
            return urn
        finally:
            await check_page.close()

    async def _run_flow(
        self,
        ctx: BrowserContext,
        page: Page,
        post: Post,
        *,
        target_page: CompanyPage,
        pre_urn: str | None,
        dry_run: bool,
    ) -> PublishResult:
        # Path A: navigate to the company admin "page posts" view; the share
        # modal opened from this scope auto-targets the company actor.
        await page.goto(sel.company_admin_page_posts_url(target_page.id), wait_until="domcontentloaded")
        await dismiss_popups(page)
        await _humanize_delay(self._pacing)

        # Open the share modal.
        await _click_first(page, sel.START_A_POST_BUTTON_ALTERNATIVES, label="Start a post")
        modal = await _wait_for_modal(page)

        # Verify the actor pill matches the configured display name. Falling
        # back to the personal profile here would silently post to the wrong
        # surface — abort instead.
        await _verify_actor(modal, target_page)

        # Caption first. LinkedIn's behaviour for article posts is to detect a
        # pasted URL inside the editor, so the order matters: type the URL
        # before any media is set.
        if post.type == PostType.ARTICLE:
            assert post.article_url is not None  # validated upstream
            article_text = (post.caption + ("\n\n" if post.caption else "") + str(post.article_url)).strip()
            await _fill_caption(modal, article_text)
            await _humanize_delay(self._pacing)
            await _wait_for_article_preview(modal)
        else:
            await _fill_caption(modal, post.caption)
            await _humanize_delay(self._pacing)

        # Media upload, if any.
        if post.type == PostType.IMAGE:
            await _upload_media(modal, post.media, kind="image")
            await _wait_for_uploads_done(modal, timeout_ms=120_000)
        elif post.type == PostType.MULTI_IMAGE:
            await _upload_media(modal, post.media, kind="image")
            await _wait_for_uploads_done(modal, timeout_ms=180_000)
        elif post.type == PostType.VIDEO:
            await _upload_media(modal, post.media, kind="video")
            await _wait_for_uploads_done(modal, timeout_ms=600_000)

        if dry_run:
            log.warning("Dry-run: reached the Post button but NOT clicking. Aborting.")
            return PublishResult(ok=True, dry_run=True)

        # Mouse jitter — extra LinkedIn-specific humanization before the
        # commit click.
        try:
            vp = self.account.viewport
            x = random.randint(int(vp.width * 0.4), int(vp.width * 0.6))
            y = random.randint(int(vp.height * 0.4), int(vp.height * 0.6))
            await page.mouse.move(x, y, steps=10)
        except Exception:
            pass

        await _click_post_button(modal)
        log.info("Post clicked; confirming publish...")

        urn = await _confirm_publish(
            ctx,
            target_page,
            pre_urn=pre_urn,
            timeout_ms=180_000,
        )
        url = sel.feed_update_url(urn) if urn else None
        return PublishResult(ok=True, shortcode=urn, url=url)


# ---------- helpers ----------


async def _pre_run_idle(page: Page, pacing: PacingSettings) -> None:
    """Scroll/dwell a bit before doing anything — LinkedIn's ML model
    watches for click-without-context behavior."""
    delay = random.uniform(pacing.pre_run_idle_seconds_min, pacing.pre_run_idle_seconds_max)
    log.debug("Pre-run idle %.1fs", delay)
    try:
        end_at = asyncio.get_event_loop().time() + delay
        while asyncio.get_event_loop().time() < end_at:
            await page.mouse.wheel(0, random.randint(100, 600))
            await asyncio.sleep(random.uniform(1.5, 4.0))
    except Exception:
        await asyncio.sleep(delay)


async def _humanize_delay(pacing: PacingSettings) -> None:
    delay = random.uniform(pacing.min_step_delay_seconds, pacing.max_step_delay_seconds)
    log.debug("Humanized step delay %.1fs", delay)
    await asyncio.sleep(delay)


async def _click_first(page: Page, alternatives: tuple[str, ...], *, label: str) -> None:
    for css in alternatives:
        try:
            loc = page.locator(css).first
            await loc.wait_for(state="visible", timeout=5_000)
            await loc.click()
            log.debug("Clicked %s via selector %s", label, css)
            return
        except Exception:
            continue
    raise TimeoutError(f"Could not locate {label}. Selectors tried: {alternatives}")


async def _wait_for_modal(page: Page, *, timeout_ms: int = 15_000) -> Locator:
    for css in sel.SHARE_MODAL_ALTERNATIVES:
        loc = page.locator(css).first
        try:
            await loc.wait_for(state="visible", timeout=timeout_ms)
            return loc
        except Exception:
            continue
    raise TimeoutError("Share modal did not open.")


async def _verify_actor(modal: Locator, target: CompanyPage) -> None:
    visible = await read_actor_pill_text(modal)
    if visible is None:
        # No pill detected — selectors rotted or modal hasn't fully loaded.
        # Be conservative: fail rather than blast a post into the wrong surface.
        raise WrongActorError(
            "Could not read the share-modal actor pill. Refusing to post — "
            "selectors may need updating."
        )
    if not actor_label_matches(visible, target.display_name):
        raise WrongActorError(
            f"Share modal actor is '{visible.strip()}' but expected to contain "
            f"'{target.display_name}' (id={target.id}). Admin permissions on "
            f"the page may have lapsed; re-check on linkedin.com."
        )
    log.info("Actor verified: %s", visible.strip())


async def _fill_caption(modal: Locator, caption: str) -> None:
    if not caption:
        return
    for css in sel.CAPTION_EDITOR_ALTERNATIVES:
        loc = modal.locator(css).first
        try:
            await loc.wait_for(state="visible", timeout=8_000)
            await loc.click()
            await loc.type(caption, delay=random.randint(15, 45))
            log.debug("Caption filled via selector %s", css)
            return
        except Exception:
            continue
    raise TimeoutError("Could not locate the share-modal caption editor.")


async def _upload_media(modal: Locator, media: list[Path], *, kind: str) -> None:
    """Set files on the appropriate native file input.

    LinkedIn occasionally hides the native input until you click the
    toolbar 'Add a photo' / 'Add a video' button — try that as a
    pre-step if the direct set_input_files fails.
    """
    inputs = (
        sel.IMAGE_FILE_INPUT_ALTERNATIVES if kind == "image" else sel.VIDEO_FILE_INPUT_ALTERNATIVES
    )
    paths = [str(p) for p in media]

    if await _try_set_input_files(modal, inputs, paths):
        log.info("Uploaded %d %s file(s) (direct set)", len(media), kind)
        return

    # Fallback: click the toolbar trigger to surface the input.
    triggers = (
        sel.ADD_PHOTO_BUTTON_ALTERNATIVES if kind == "image" else sel.ADD_VIDEO_BUTTON_ALTERNATIVES
    )
    for css in triggers:
        try:
            await modal.locator(css).first.click(timeout=3_000)
            await asyncio.sleep(0.5)
            break
        except Exception:
            continue
    if not await _try_set_input_files(modal, inputs, paths):
        raise TimeoutError(f"Could not locate a {kind} file input in the share modal.")
    log.info("Uploaded %d %s file(s) (via toolbar trigger)", len(media), kind)


async def _try_set_input_files(
    modal: Locator, alternatives: tuple[str, ...], paths: list[str]
) -> bool:
    for css in alternatives:
        loc = modal.locator(css).first
        try:
            await loc.wait_for(state="attached", timeout=2_000)
            await loc.set_input_files(paths)
            return True
        except Exception:
            continue
    return False


async def _wait_for_uploads_done(modal: Locator, *, timeout_ms: int) -> None:
    """Poll until upload-progress indicators are gone AND the Post button
    is enabled. Either signal alone has been observed to lie on slow links.
    """
    end_at = asyncio.get_event_loop().time() + timeout_ms / 1000
    while asyncio.get_event_loop().time() < end_at:
        progress_visible = False
        for css in sel.UPLOAD_PROGRESS_ALTERNATIVES:
            try:
                if await modal.locator(css).first.is_visible(timeout=500):
                    progress_visible = True
                    break
            except Exception:
                continue
        post_enabled = False
        for css in sel.POST_BUTTON_ALTERNATIVES:
            try:
                if await modal.locator(css).first.is_visible(timeout=500):
                    post_enabled = True
                    break
            except Exception:
                continue
        if not progress_visible and post_enabled:
            return
        await asyncio.sleep(1.0)
    raise TimeoutError("Media upload did not finish within the deadline.")


async def _wait_for_article_preview(modal: Locator, *, timeout_ms: int = 30_000) -> None:
    end_at = asyncio.get_event_loop().time() + timeout_ms / 1000
    while asyncio.get_event_loop().time() < end_at:
        for css in sel.ARTICLE_PREVIEW_CARD_ALTERNATIVES:
            try:
                if await modal.locator(css).first.is_visible(timeout=500):
                    return
            except Exception:
                continue
        await asyncio.sleep(1.0)
    raise TimeoutError("Article preview card did not render within the deadline.")


async def _click_post_button(modal: Locator) -> None:
    for css in sel.POST_BUTTON_ALTERNATIVES:
        loc = modal.locator(css).first
        try:
            await loc.wait_for(state="visible", timeout=10_000)
            await loc.click()
            return
        except Exception:
            continue
    raise TimeoutError("Post button never became enabled.")


async def _confirm_publish(
    ctx: BrowserContext,
    target_page: CompanyPage,
    *,
    pre_urn: str | None,
    timeout_ms: int,
) -> str | None:
    """Confirm the post landed.

    Two signals; either one is sufficient:

    1. **Fast path:** a visible LinkedIn success toast.
    2. **Authoritative path:** the company admin grid's first-row URN
       differs from `pre_urn`. We always prefer the URN delta when we
       can read one — it's the only signal that survives toast races.
    """
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout_ms / 1000
    grace_until = loop.time() + 8.0

    # Fast-path: watch for a toast on every open page in the context.
    toast_seen = False
    while loop.time() < deadline:
        if not toast_seen:
            toast_seen = await _toast_visible_anywhere(ctx)

        if toast_seen or loop.time() > grace_until:
            urn = await _admin_grid_delta(ctx, target_page, pre_urn)
            if urn:
                return urn
            if toast_seen:
                await asyncio.sleep(3.0)
                urn = await _admin_grid_delta(ctx, target_page, pre_urn)
                if urn:
                    return urn
        await asyncio.sleep(2.0)

    # Final shot: the admin grid sometimes catches up after the deadline.
    urn = await _admin_grid_delta(ctx, target_page, pre_urn)
    if urn:
        return urn
    raise TimeoutError(
        "Publish confirmation not detected (no success toast and the admin "
        "grid first-row URN did not advance)."
    )


async def _toast_visible_anywhere(ctx: BrowserContext) -> bool:
    for page in ctx.pages:
        for msg in sel.POST_SHARED_TEXT_ALTERNATIVES:
            try:
                if await page.get_by_text(msg).first.is_visible(timeout=300):
                    return True
            except Exception:
                continue
    return False


async def _admin_grid_delta(
    ctx: BrowserContext, target_page: CompanyPage, pre_urn: str | None
) -> str | None:
    """Open a scratch page, read the admin grid's first URN; return it
    only if it differs from pre_urn.
    """
    probe = await ctx.new_page()
    try:
        urn = await latest_activity_urn(probe, target_page.id, timeout_ms=8_000)
        if urn and urn != pre_urn:
            return urn
        # Try the data-urn attribute directly via JS as a fallback.
        for css in sel.ADMIN_GRID_ROW_ALTERNATIVES:
            raw = await probe.evaluate(
                "(sel) => { const el = document.querySelector(sel); return el ? el.getAttribute('data-urn') : null; }",
                css,
            )
            urn2 = urn_from_dataset(raw)
            if urn2 and urn2 != pre_urn:
                return urn2
        return None
    finally:
        await probe.close()
