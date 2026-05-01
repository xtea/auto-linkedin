"""Tests for publisher/actor.py URL builder and label matching."""
from __future__ import annotations

import pytest

from auto_linkedin.publisher.actor import (
    actor_label_matches,
    company_admin_url,
)


def test_company_admin_url_format() -> None:
    assert company_admin_url(111873058) == (
        "https://www.linkedin.com/company/111873058/admin/page-posts/published/"
    )


def test_company_admin_url_other_id() -> None:
    assert company_admin_url(99999999) == (
        "https://www.linkedin.com/company/99999999/admin/page-posts/published/"
    )


@pytest.mark.parametrize(
    "visible,expected,match",
    [
        ("Posting as My Company", "My Company", True),
        ("My Company", "My Company", True),
        ("posting as: My Company  (Admin)", "My Company", True),
        ("Jason Doe", "My Company", False),
        ("My Company", "Other Co", False),
        ("", "My Company", False),
        (None, "My Company", False),
        ("My Company", "", False),
    ],
)
def test_actor_label_matches(visible: str | None, expected: str, match: bool) -> None:
    assert actor_label_matches(visible, expected) is match
