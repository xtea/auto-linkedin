"""Tests for AccountConfig.company_pages and resolve_company_page()."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from auto_linkedin.config import (
    AccountConfig,
    CompanyPage,
    resolve_company_page,
)


def _make_cfg(**overrides: object) -> AccountConfig:
    base: dict[str, object] = {
        "handle": "demo",
        "user_agent": "Mozilla/5.0 (test)",
        "company_pages": [
            CompanyPage(id=111, display_name="Page A"),
            CompanyPage(id=222, slug="page-b", display_name="Page B"),
        ],
        "default_company_page": 111,
    }
    base.update(overrides)
    return AccountConfig.model_validate(base)


def test_default_company_page_must_be_in_company_pages() -> None:
    with pytest.raises(ValidationError) as excinfo:
        AccountConfig.model_validate(
            {
                "handle": "demo",
                "user_agent": "Mozilla/5.0 (test)",
                "company_pages": [{"id": 111, "display_name": "Page A"}],
                "default_company_page": 999,
            }
        )
    assert "default_company_page=999" in str(excinfo.value)


def test_default_company_page_optional() -> None:
    cfg = AccountConfig.model_validate(
        {
            "handle": "demo",
            "user_agent": "Mozilla/5.0 (test)",
            "company_pages": [{"id": 111, "display_name": "Page A"}],
        }
    )
    assert cfg.default_company_page is None


def test_company_page_id_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        CompanyPage(id=0, display_name="Bad")
    with pytest.raises(ValidationError):
        CompanyPage(id=-5, display_name="Bad")


def test_resolve_uses_cli_override_first() -> None:
    cfg = _make_cfg()
    page = resolve_company_page(cfg, cli_override=222, post_override=111)
    assert page.id == 222


def test_resolve_uses_post_override_when_no_cli() -> None:
    cfg = _make_cfg()
    page = resolve_company_page(cfg, post_override=222)
    assert page.id == 222


def test_resolve_falls_back_to_default() -> None:
    cfg = _make_cfg()
    page = resolve_company_page(cfg)
    assert page.id == 111


def test_resolve_unknown_id_raises() -> None:
    cfg = _make_cfg()
    with pytest.raises(ValueError, match="not configured for this account"):
        resolve_company_page(cfg, cli_override=999)


def test_resolve_with_no_default_and_no_override_raises() -> None:
    cfg = AccountConfig.model_validate(
        {
            "handle": "demo",
            "user_agent": "Mozilla/5.0 (test)",
            "company_pages": [{"id": 111, "display_name": "Page A"}],
        }
    )
    with pytest.raises(ValueError, match="No company page selected"):
        resolve_company_page(cfg)


def test_resolve_with_empty_company_pages_raises() -> None:
    cfg = AccountConfig.model_validate(
        {
            "handle": "demo",
            "user_agent": "Mozilla/5.0 (test)",
            "company_pages": [],
        }
    )
    with pytest.raises(ValueError, match="No company pages configured"):
        resolve_company_page(cfg)


def test_find_page_returns_match() -> None:
    cfg = _make_cfg()
    p = cfg.find_page(222)
    assert p is not None and p.display_name == "Page B"
    assert cfg.find_page(999) is None
