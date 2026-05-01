"""Content descriptor models: Post, PostType, LinkedIn limits and rules."""
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
    ARTICLE = "article"


# LinkedIn hard limits (web UI, April 2026).
CAPTION_MAX_CHARS = 3000
HASHTAG_MAX_COUNT = 30  # soft cap; LinkedIn has no documented limit
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
    caption: str = ""
    media: list[Path] = Field(default_factory=list)
    article_url: HttpUrl | None = None
    as_company: int | None = None
    schedule: datetime | None = None
    source_dir: Path  # where post.yaml lives, for logging

    @field_validator("caption")
    @classmethod
    def _caption_limits(cls, v: str) -> str:
        if len(v) > CAPTION_MAX_CHARS:
            raise ValueError(
                f"Caption is {len(v)} chars; LinkedIn caps captions at {CAPTION_MAX_CHARS}."
            )
        hashtags = re.findall(r"#[\w一-鿿]+", v)
        if len(hashtags) > HASHTAG_MAX_COUNT:
            raise ValueError(
                f"Caption has {len(hashtags)} hashtags; soft cap is {HASHTAG_MAX_COUNT}. "
                "Reduce to avoid algorithmic suppression."
            )
        return v

    @field_validator("as_company")
    @classmethod
    def _as_company_positive(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("as_company must be a positive LinkedIn org id")
        return v

    @model_validator(mode="after")
    def _validate_media_for_type(self) -> Self:
        # Existence check applies to any provided media (text/article should have none).
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
            if self.article_url is not None:
                raise ValueError("Text posts must not set article_url.")

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
            if self.article_url is not None:
                raise ValueError("Image posts must not set article_url.")

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
            if self.article_url is not None:
                raise ValueError("multi_image posts must not set article_url.")

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
            if self.article_url is not None:
                raise ValueError("Video posts must not set article_url.")

        elif self.type == PostType.ARTICLE:
            if self.article_url is None:
                raise ValueError("Article posts require article_url (must be HTTPS).")
            if str(self.article_url).startswith("http://"):
                raise ValueError("article_url must be HTTPS, not HTTP.")
            if self.media:
                raise ValueError(
                    "Article posts must not include media; LinkedIn renders the "
                    "preview card from the URL's open-graph metadata."
                )

        return self
