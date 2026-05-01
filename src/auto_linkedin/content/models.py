"""Content descriptor models: Post, PostType, LinkedIn limits and rules.

LinkedIn distinguishes two distinct surfaces that we model as separate
PostTypes:

- **`link`** — a regular share-modal post that embeds a URL preview
  card. URL pattern after publish: `/feed/update/urn:li:activity:...`
- **`article`** — a long-form post authored in LinkedIn's article
  editor (dashboard → Create → "Publish an article"). URL pattern
  after publish: `/pulse/<slug-id>/`

These have unrelated UIs, unrelated permalink shapes, and unrelated
length limits. Don't conflate them.
"""
from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


class PostType(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    MULTI_IMAGE = "multi_image"
    VIDEO = "video"
    LINK = "link"          # share-modal post with URL preview card
    ARTICLE = "article"    # long-form via the dashboard article editor


# LinkedIn hard limits (web UI, April 2026).
CAPTION_MAX_CHARS = 3000        # share-modal text editor cap
ARTICLE_TITLE_MAX_CHARS = 150   # article editor textarea maxlength="150"
ARTICLE_BODY_MAX_CHARS = 110_000  # LinkedIn article body soft cap (well below the published 125k limit)
HASHTAG_MAX_COUNT = 30          # soft cap; LinkedIn has no documented limit
MULTI_IMAGE_MIN = 2
MULTI_IMAGE_MAX = 9

# Allowed media extensions in the share modal.
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".wmv", ".flv", ".avi"}


class Post(BaseModel):
    """Loaded post descriptor. Paths are absolute after loading.

    Mentions (`@handle`) are passed through as plain text — driving
    LinkedIn's typeahead picker is out of scope for v1.
    """

    type: PostType
    caption: str = ""           # body text (article body uses this field too)
    title: str | None = None    # required for ARTICLE only
    media: list[Path] = Field(default_factory=list)
    link_url: HttpUrl | None = None   # required for LINK only
    as_company: int | None = None
    schedule: datetime | None = None
    source_dir: Path

    @field_validator("as_company")
    @classmethod
    def _as_company_positive(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("as_company must be a positive LinkedIn org id")
        return v

    @field_validator("title")
    @classmethod
    def _title_max(cls, v: str | None) -> str | None:
        if v is not None and len(v) > ARTICLE_TITLE_MAX_CHARS:
            raise ValueError(
                f"Title is {len(v)} chars; LinkedIn article titles cap at "
                f"{ARTICLE_TITLE_MAX_CHARS}."
            )
        return v

    @model_validator(mode="after")
    def _validate_caption_for_type(self) -> Self:
        # Caption length cap depends on type. The article body uses the
        # caption field but has a much larger cap.
        cap = ARTICLE_BODY_MAX_CHARS if self.type == PostType.ARTICLE else CAPTION_MAX_CHARS
        if len(self.caption) > cap:
            label = "article body" if self.type == PostType.ARTICLE else "caption"
            raise ValueError(
                f"{label.capitalize()} is {len(self.caption)} chars; cap is {cap}."
            )
        # Hashtag cap only applies to the share-modal types — articles aren't
        # hashtag-driven the same way.
        if self.type != PostType.ARTICLE:
            hashtags = re.findall(r"#[\w一-鿿]+", self.caption)
            if len(hashtags) > HASHTAG_MAX_COUNT:
                raise ValueError(
                    f"Caption has {len(hashtags)} hashtags; soft cap is {HASHTAG_MAX_COUNT}. "
                    "Reduce to avoid algorithmic suppression."
                )
        return self

    @model_validator(mode="after")
    def _validate_media_and_per_type_rules(self) -> Self:
        for p in self.media:
            if not p.exists():
                raise ValueError(f"Media file does not exist: {p}")
            if not p.is_file():
                raise ValueError(f"Media path is not a file: {p}")

        if self.type == PostType.TEXT:
            if not self.caption.strip():
                raise ValueError("Text posts require a non-empty caption.")
            if self.media:
                raise ValueError("Text posts must not include any media.")
            if self.link_url is not None:
                raise ValueError("Text posts must not set link_url.")
            if self.title is not None:
                raise ValueError("Text posts must not set title (title is for articles only).")

        elif self.type == PostType.IMAGE:
            if len(self.media) != 1:
                raise ValueError(
                    f"Image posts require exactly 1 media file; got {len(self.media)}. "
                    "Use type: multi_image for 2-9 images."
                )
            if self.media[0].suffix.lower() not in IMAGE_EXTENSIONS:
                raise ValueError(
                    f"Unsupported image extension: {self.media[0].suffix}. "
                    f"Accepted: {sorted(IMAGE_EXTENSIONS)}"
                )
            if self.link_url is not None:
                raise ValueError("Image posts must not set link_url.")
            if self.title is not None:
                raise ValueError("Image posts must not set title.")

        elif self.type == PostType.MULTI_IMAGE:
            if not (MULTI_IMAGE_MIN <= len(self.media) <= MULTI_IMAGE_MAX):
                raise ValueError(
                    f"multi_image must have {MULTI_IMAGE_MIN}..{MULTI_IMAGE_MAX} items; "
                    f"got {len(self.media)}."
                )
            for p in self.media:
                if p.suffix.lower() not in IMAGE_EXTENSIONS:
                    raise ValueError(
                        f"multi_image only accepts images; got {p.suffix}. "
                        f"Accepted: {sorted(IMAGE_EXTENSIONS)}"
                    )
            if self.link_url is not None:
                raise ValueError("multi_image posts must not set link_url.")
            if self.title is not None:
                raise ValueError("multi_image posts must not set title.")

        elif self.type == PostType.VIDEO:
            if len(self.media) != 1:
                raise ValueError(
                    f"Video posts require exactly 1 media file; got {len(self.media)}."
                )
            if self.media[0].suffix.lower() not in VIDEO_EXTENSIONS:
                raise ValueError(
                    f"Unsupported video extension: {self.media[0].suffix}. "
                    f"Accepted: {sorted(VIDEO_EXTENSIONS)}"
                )
            if self.link_url is not None:
                raise ValueError("Video posts must not set link_url.")
            if self.title is not None:
                raise ValueError("Video posts must not set title.")

        elif self.type == PostType.LINK:
            if self.link_url is None:
                raise ValueError("Link posts require link_url (must be HTTPS).")
            if str(self.link_url).startswith("http://"):
                raise ValueError("link_url must be HTTPS, not HTTP.")
            if self.media:
                raise ValueError(
                    "Link posts must not include media; LinkedIn renders the "
                    "preview card from the URL's open-graph metadata."
                )
            if self.title is not None:
                raise ValueError("Link posts must not set title (title is for articles only).")

        elif self.type == PostType.ARTICLE:
            if not self.title or not self.title.strip():
                raise ValueError("Article posts require a non-empty title.")
            if not self.caption.strip():
                raise ValueError(
                    "Article posts require a non-empty body (use the `caption` field "
                    "for the article body)."
                )
            if self.media:
                raise ValueError(
                    "Article posts must not include media in `media:`. Cover-image "
                    "support is not implemented in v1."
                )
            if self.link_url is not None:
                raise ValueError(
                    "Article posts must not set link_url. To embed a URL, place it "
                    "inline in the article body."
                )

        return self
