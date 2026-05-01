from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from auto_linkedin.content.loader import discover_posts, load_post
from auto_linkedin.content.models import (
    CAPTION_MAX_CHARS,
    HASHTAG_MAX_COUNT,
    PostType,
)


def _write_post(
    tmp_path: Path, *, body: dict, media_files: list[tuple[str, bytes]] | None = None
) -> Path:
    post_dir = tmp_path / "my-post"
    media_dir = post_dir / "media"
    media_dir.mkdir(parents=True)
    for name, content in media_files or []:
        (media_dir / name).write_bytes(content)
    (post_dir / "post.yaml").write_text(yaml.safe_dump(body))
    return post_dir


# ---- text ----


def test_load_text_post(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path,
        body={"type": "text", "caption": "hello world #x"},
    )
    post = load_post(post_dir)
    assert post.type == PostType.TEXT
    assert post.media == []
    assert post.caption == "hello world #x"
    assert post.link_url is None
    assert post.title is None


def test_text_post_requires_caption(tmp_path: Path) -> None:
    post_dir = _write_post(tmp_path, body={"type": "text", "caption": "   "})
    with pytest.raises(Exception, match="non-empty caption"):
        load_post(post_dir)


def test_text_post_rejects_media(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path,
        body={"type": "text", "caption": "hi", "media": ["./media/a.jpg"]},
        media_files=[("a.jpg", b"\xff\xd8\xff")],
    )
    with pytest.raises(Exception, match="must not include any media"):
        load_post(post_dir)


# ---- image ----


def test_load_image_post(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path,
        body={"type": "image", "caption": "look", "media": ["./media/a.jpg"]},
        media_files=[("a.jpg", b"\xff\xd8\xff")],
    )
    post = load_post(post_dir)
    assert post.type == PostType.IMAGE
    assert len(post.media) == 1


def test_image_rejects_multiple(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path,
        body={"type": "image", "media": ["./media/a.jpg", "./media/b.jpg"]},
        media_files=[("a.jpg", b"\xff\xd8\xff"), ("b.jpg", b"\xff\xd8\xff")],
    )
    with pytest.raises(Exception, match="exactly 1"):
        load_post(post_dir)


def test_image_rejects_video_extension(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path,
        body={"type": "image", "media": ["./media/a.mp4"]},
        media_files=[("a.mp4", b"\x00\x00")],
    )
    with pytest.raises(Exception, match="Unsupported image extension"):
        load_post(post_dir)


# ---- multi_image ----


def test_multi_image_rejects_one(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path,
        body={"type": "multi_image", "media": ["./media/a.jpg"]},
        media_files=[("a.jpg", b"\xff\xd8\xff")],
    )
    with pytest.raises(Exception, match="multi_image must have"):
        load_post(post_dir)


def test_multi_image_accepts_two(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path,
        body={"type": "multi_image", "media": ["./media/a.jpg", "./media/b.jpg"]},
        media_files=[("a.jpg", b"\xff\xd8\xff"), ("b.jpg", b"\xff\xd8\xff")],
    )
    post = load_post(post_dir)
    assert post.type == PostType.MULTI_IMAGE
    assert len(post.media) == 2


def test_multi_image_accepts_nine(tmp_path: Path) -> None:
    files = [(f"i{i}.jpg", b"\xff\xd8\xff") for i in range(9)]
    body = {"type": "multi_image", "media": [f"./media/{n}" for n, _ in files]}
    post_dir = _write_post(tmp_path, body=body, media_files=files)
    post = load_post(post_dir)
    assert len(post.media) == 9


def test_multi_image_rejects_ten(tmp_path: Path) -> None:
    files = [(f"i{i}.jpg", b"\xff\xd8\xff") for i in range(10)]
    body = {"type": "multi_image", "media": [f"./media/{n}" for n, _ in files]}
    post_dir = _write_post(tmp_path, body=body, media_files=files)
    with pytest.raises(Exception, match="multi_image must have"):
        load_post(post_dir)


def test_multi_image_rejects_video_among_images(tmp_path: Path) -> None:
    files = [("a.jpg", b"\xff\xd8\xff"), ("b.mp4", b"\x00\x00")]
    body = {"type": "multi_image", "media": ["./media/a.jpg", "./media/b.mp4"]}
    post_dir = _write_post(tmp_path, body=body, media_files=files)
    with pytest.raises(Exception, match="only accepts images"):
        load_post(post_dir)


# ---- video ----


def test_video_accepts_mp4(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path,
        body={"type": "video", "media": ["./media/v.mp4"]},
        media_files=[("v.mp4", b"\x00\x00")],
    )
    post = load_post(post_dir)
    assert post.type == PostType.VIDEO


def test_video_rejects_image(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path,
        body={"type": "video", "media": ["./media/a.jpg"]},
        media_files=[("a.jpg", b"\xff\xd8\xff")],
    )
    with pytest.raises(Exception, match="Unsupported video extension"):
        load_post(post_dir)


def test_video_requires_one_file(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path,
        body={"type": "video", "media": ["./media/v.mp4", "./media/v2.mp4"]},
        media_files=[("v.mp4", b"\x00\x00"), ("v2.mp4", b"\x00\x00")],
    )
    with pytest.raises(Exception, match="exactly 1"):
        load_post(post_dir)


# ---- link (share-modal post with URL preview card) ----


def test_link_requires_url(tmp_path: Path) -> None:
    post_dir = _write_post(tmp_path, body={"type": "link", "caption": "read this"})
    with pytest.raises(Exception, match="link_url"):
        load_post(post_dir)


def test_link_accepts_https_url(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path,
        body={
            "type": "link",
            "caption": "read this",
            "link_url": "https://example.com/blog/x",
        },
    )
    post = load_post(post_dir)
    assert post.type == PostType.LINK
    assert str(post.link_url).startswith("https://")


def test_link_rejects_http_url(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path,
        body={
            "type": "link",
            "caption": "read this",
            "link_url": "http://example.com/blog/x",
        },
    )
    with pytest.raises(Exception, match="HTTPS"):
        load_post(post_dir)


def test_link_rejects_media(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path,
        body={
            "type": "link",
            "caption": "read this",
            "link_url": "https://example.com/blog/x",
            "media": ["./media/a.jpg"],
        },
        media_files=[("a.jpg", b"\xff\xd8\xff")],
    )
    with pytest.raises(Exception, match="must not include media"):
        load_post(post_dir)


# ---- article (long-form via dashboard editor) ----


def test_article_requires_title(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path, body={"type": "article", "caption": "Body of the article."}
    )
    with pytest.raises(Exception, match="non-empty title"):
        load_post(post_dir)


def test_article_requires_body(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path, body={"type": "article", "title": "My Article"}
    )
    with pytest.raises(Exception, match="non-empty body"):
        load_post(post_dir)


def test_article_accepts_title_and_body(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path,
        body={
            "type": "article",
            "title": "My Article",
            "caption": "First paragraph.\n\nSecond paragraph.",
        },
    )
    post = load_post(post_dir)
    assert post.type == PostType.ARTICLE
    assert post.title == "My Article"
    assert "Second paragraph" in post.caption


def test_article_title_max_chars(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path,
        body={"type": "article", "title": "x" * 151, "caption": "body"},
    )
    with pytest.raises(Exception, match="article titles cap at 150"):
        load_post(post_dir)


def test_article_body_can_be_long(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path,
        body={"type": "article", "title": "T", "caption": "x" * 50_000},
    )
    post = load_post(post_dir)
    assert len(post.caption) == 50_000


def test_article_rejects_media(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path,
        body={
            "type": "article",
            "title": "My Article",
            "caption": "Body",
            "media": ["./media/a.jpg"],
        },
        media_files=[("a.jpg", b"\xff\xd8\xff")],
    )
    with pytest.raises(Exception, match="must not include media"):
        load_post(post_dir)


def test_article_rejects_link_url(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path,
        body={
            "type": "article",
            "title": "T",
            "caption": "Body",
            "link_url": "https://example.com",
        },
    )
    with pytest.raises(Exception, match="must not set link_url"):
        load_post(post_dir)


# ---- caption / hashtag rules ----


def test_caption_at_max_accepted(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path,
        body={"type": "text", "caption": "x" * CAPTION_MAX_CHARS},
    )
    post = load_post(post_dir)
    assert len(post.caption) == CAPTION_MAX_CHARS


def test_caption_over_max_rejected(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path,
        body={"type": "text", "caption": "x" * (CAPTION_MAX_CHARS + 1)},
    )
    with pytest.raises(Exception, match="cap is"):
        load_post(post_dir)


def test_hashtag_soft_cap(tmp_path: Path) -> None:
    caption = " ".join(f"#tag{i}" for i in range(HASHTAG_MAX_COUNT + 1))
    post_dir = _write_post(tmp_path, body={"type": "text", "caption": caption})
    with pytest.raises(Exception, match="hashtags"):
        load_post(post_dir)


# ---- as_company ----


def test_as_company_must_be_positive(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path, body={"type": "text", "caption": "hi", "as_company": 0}
    )
    with pytest.raises(Exception, match="as_company"):
        load_post(post_dir)


def test_as_company_optional(tmp_path: Path) -> None:
    post_dir = _write_post(tmp_path, body={"type": "text", "caption": "hi"})
    post = load_post(post_dir)
    assert post.as_company is None


def test_as_company_set(tmp_path: Path) -> None:
    post_dir = _write_post(
        tmp_path,
        body={"type": "text", "caption": "hi", "as_company": 111873058},
    )
    post = load_post(post_dir)
    assert post.as_company == 111873058


# ---- discovery ----


def test_discover_posts(tmp_path: Path) -> None:
    _write_post(tmp_path, body={"type": "text", "caption": "a"})
    (tmp_path / "nested").mkdir()
    _write_post(tmp_path / "nested", body={"type": "text", "caption": "b"})
    found = discover_posts(tmp_path)
    assert len(found) == 2


def test_missing_media_fails(tmp_path: Path) -> None:
    post_dir = tmp_path / "my-post"
    post_dir.mkdir()
    (post_dir / "post.yaml").write_text(
        yaml.safe_dump({"type": "image", "media": ["./media/missing.jpg"]})
    )
    with pytest.raises(Exception, match="does not exist"):
        load_post(post_dir)
