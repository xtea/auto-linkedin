from __future__ import annotations

from auto_linkedin.publisher.profile import (
    captions_match,
    normalize_caption,
    urn_from_dataset,
    urn_from_href,
)

# ---- urn_from_dataset ----


def test_urn_from_dataset_canonical() -> None:
    assert (
        urn_from_dataset("urn:li:activity:7236789012345678901")
        == "urn:li:activity:7236789012345678901"
    )


def test_urn_from_dataset_extracts_from_longer_string() -> None:
    raw = "urn:li:activity:7236789012345678901,urn:li:fs_socialActor:..."
    assert urn_from_dataset(raw) == "urn:li:activity:7236789012345678901"


def test_urn_from_dataset_none_or_unrelated() -> None:
    assert urn_from_dataset(None) is None
    assert urn_from_dataset("") is None
    assert urn_from_dataset("urn:li:share:1234") is None  # share, not activity
    assert urn_from_dataset("nothing-here") is None


# ---- urn_from_href ----


def test_urn_from_href_relative() -> None:
    href = "/feed/update/urn:li:activity:7236789012345678901/"
    assert urn_from_href(href) == "urn:li:activity:7236789012345678901"


def test_urn_from_href_absolute() -> None:
    href = "https://www.linkedin.com/feed/update/urn:li:activity:7236789012345678901/"
    assert urn_from_href(href) == "urn:li:activity:7236789012345678901"


def test_urn_from_href_with_query_string() -> None:
    href = "/feed/update/urn:li:activity:7236789012345678901/?trk=feed"
    assert urn_from_href(href) == "urn:li:activity:7236789012345678901"


def test_urn_from_href_none_or_unrelated() -> None:
    assert urn_from_href(None) is None
    assert urn_from_href("") is None
    assert urn_from_href("/feed/") is None
    assert urn_from_href("/feed/update/foobar/") is None


# ---- normalize_caption ----


def test_normalize_caption_collapses_whitespace_and_casefolds() -> None:
    assert normalize_caption("  Hello  World\n\nFoo\t") == "hello world foo"
    assert normalize_caption("FOO") == "foo"


def test_normalize_caption_none_and_empty() -> None:
    assert normalize_caption(None) == ""
    assert normalize_caption("   ") == ""


# ---- captions_match ----


def test_captions_match_true_with_formatting_differences() -> None:
    a = "Hello world #tag\n\nNewline"
    b = "hello  world #tag\nnewline"
    assert captions_match(a, b)


def test_captions_match_false_on_different_content() -> None:
    assert not captions_match("a", "b")


def test_captions_match_false_when_one_empty() -> None:
    # Empty captions should never match — otherwise two empty-caption posts
    # would always be marked duplicates of each other.
    assert not captions_match("", "something")
    assert not captions_match(None, "something")
    assert not captions_match("", "")


def test_captions_match_with_unicode() -> None:
    a = "Excited to launch — see what's new!"
    b = "Excited to launch — see what's new!  "
    assert captions_match(a, b)
