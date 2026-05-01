"""All linkedin.com selectors and URL builders live here.

LinkedIn revs its UI ~quarterly; this is the only file that needs patching
when selectors break.

Rules:
- Prefer aria-label / role / visible text and `data-test-*` attributes.
  Never raw class names.
- Keep fallbacks as ordered tuples — callers iterate from most-stable down.
"""
from __future__ import annotations


# Authoritative create-flow URL: the company admin "page posts" view.
# Path A (per implementation plan): opening the share modal from this URL
# auto-scopes the actor to the company, avoiding the actor-switcher.
def company_admin_page_posts_url(page_id: int) -> str:
    return f"https://www.linkedin.com/company/{page_id}/admin/page-posts/published/"


def company_admin_dashboard_url(page_id: int) -> str:
    return f"https://www.linkedin.com/company/{page_id}/admin/dashboard/"


def feed_update_url(urn: str) -> str:
    """Permalink for an activity URN. urn must include 'urn:li:activity:'."""
    return f"https://www.linkedin.com/feed/update/{urn}/"


# ---- Top-level "Start a post" trigger on the admin page-posts view ----
START_A_POST_BUTTON_ALTERNATIVES = (
    'button[aria-label*="Start a post"]',
    'button:has-text("Start a post")',
    '[data-test-share-box-trigger]',
)


# ---- Share-creation modal ----
SHARE_MODAL_ALTERNATIVES = (
    'div[role="dialog"][aria-labelledby*="share-creation"]',
    'div[data-test-share-box-modal]',
    'div[role="dialog"]:has(button:has-text("Post"))',
)

# Pill at the top of the modal showing "Posting as <Actor>". Used to verify
# Path A scoped the actor correctly.
ACTOR_PILL_ALTERNATIVES = (
    '[data-test-share-actor-name]',
    'button[aria-label*="Edit who can see your post"]',
    'div[role="dialog"] button:has-text("Posting as")',
)

# Text editor (contenteditable). LinkedIn uses Quill under the hood.
CAPTION_EDITOR_ALTERNATIVES = (
    'div[role="dialog"] div[role="textbox"][aria-label*="Text editor"]',
    'div[role="dialog"] div.ql-editor[contenteditable="true"]',
    'div[role="dialog"] [data-test-share-creation-text-editor]',
)


# ---- File inputs (image / video) ----
# We `set_input_files` directly on the native input rather than clicking the
# toolbar button — more reliable and skips a humanization step that LinkedIn
# fingerprints.
IMAGE_FILE_INPUT_ALTERNATIVES = (
    'div[role="dialog"] input[type="file"][accept*="image"]',
    'input[type="file"][accept*="image"]',
)
VIDEO_FILE_INPUT_ALTERNATIVES = (
    'div[role="dialog"] input[type="file"][accept*="video"]',
    'input[type="file"][accept*="video"]',
)

# Toolbar buttons (used as humanization clicks if a direct file-input set
# fails — clicking these reveals the input on some LinkedIn UI variants).
ADD_PHOTO_BUTTON_ALTERNATIVES = (
    'button[aria-label*="Add a photo"]',
    'button[aria-label*="Add photo"]',
    'button[aria-label*="image"]',
)
ADD_VIDEO_BUTTON_ALTERNATIVES = (
    'button[aria-label*="Add a video"]',
    'button[aria-label*="video"]',
)


# Upload-progress indicator. While visible, the Post button stays disabled.
UPLOAD_PROGRESS_ALTERNATIVES = (
    '[data-test-media-upload-progress]',
    'div[role="dialog"] [aria-label*="Uploading"]',
    'div[role="dialog"] progress',
)

# Article preview card: rendered ~2 s after the URL appears in the editor.
ARTICLE_PREVIEW_CARD_ALTERNATIVES = (
    'div[data-test-share-content-link-preview]',
    'div[role="dialog"] article[data-test-share-link-preview]',
    'div[role="dialog"] a[data-test-share-link-preview]',
)


# ---- Submit button ----
POST_BUTTON_ALTERNATIVES = (
    'div[role="dialog"] button:has-text("Post"):not([disabled])',
    'div[role="dialog"] button[aria-label*="Post"]:not([disabled])',
    'div[role="dialog"] button[data-test-share-modal-post-btn]:not([disabled])',
)


# ---- Success confirmation (toast / banner) ----
POST_SHARED_TEXT_ALTERNATIVES = (
    "Post successful",
    "Your post is now live",
    "Post shared",
    "Your post has been shared",
)
SUCCESS_TOAST_ROLE_SELECTOR = 'div[role="status"], div[role="alert"]'


# ---- Admin grid: data-urn attribute on the first row of published posts ----
ADMIN_GRID_ROW_ALTERNATIVES = (
    '[data-test-admin-page-posts-list] [data-urn]',
    'div[data-urn^="urn:li:activity:"]',
    'li[data-urn^="urn:li:activity:"]',
)


# ---- Post-permalink page: caption body text ----
POST_BODY_TEXT_ALTERNATIVES = (
    'div.feed-shared-update-v2__description',
    '[data-test-update-text]',
    'div.update-components-text',
)
