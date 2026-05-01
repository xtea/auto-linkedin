"""Global settings and per-account config loading."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Viewport(BaseModel):
    width: int = 1440
    height: int = 900


class ProxySettings(BaseModel):
    server: str
    bypass: str | None = None
    username: str | None = None
    password: str | None = None


class PacingSettings(BaseModel):
    max_posts_per_day: int = 2
    min_step_delay_seconds: float = 30
    max_step_delay_seconds: float = 180
    pre_run_idle_seconds_min: float = 60
    pre_run_idle_seconds_max: float = 180

    @field_validator("max_step_delay_seconds")
    @classmethod
    def _max_gte_min(cls, v: float, info: object) -> float:
        values = getattr(info, "data", {})
        if v < values.get("min_step_delay_seconds", 0):
            raise ValueError("max_step_delay_seconds must be >= min_step_delay_seconds")
        return v


class CompanyPage(BaseModel):
    """A LinkedIn company page the account can post as."""

    id: int
    slug: str | None = None
    display_name: str

    @field_validator("id")
    @classmethod
    def _positive_id(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Company page id must be a positive LinkedIn org id")
        return v


class AccountConfig(BaseModel):
    handle: str
    company_pages: list[CompanyPage] = Field(default_factory=list)
    default_company_page: int | None = None
    browser: Literal["patchright", "camoufox"] = "patchright"
    user_agent: str
    viewport: Viewport = Field(default_factory=Viewport)
    locale: str = "en-US"
    timezone: str = "America/Los_Angeles"
    proxy: ProxySettings | None = None
    pacing: PacingSettings = Field(default_factory=PacingSettings)
    headless: bool = False

    @model_validator(mode="after")
    def _default_page_must_be_configured(self) -> AccountConfig:
        if self.default_company_page is None:
            return self
        ids = {p.id for p in self.company_pages}
        if self.default_company_page not in ids:
            raise ValueError(
                f"default_company_page={self.default_company_page} is not listed in "
                f"company_pages (ids: {sorted(ids) or 'none configured'})"
            )
        return self

    def find_page(self, page_id: int) -> CompanyPage | None:
        for p in self.company_pages:
            if p.id == page_id:
                return p
        return None


class Settings(BaseSettings):
    """Process-wide settings, overridable via env or .env."""

    model_config = SettingsConfigDict(
        env_prefix="AUTO_LI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    account: str = "demo"
    sessions_dir: Path = Path("./sessions")
    content_dir: Path = Path("./content")
    config_dir: Path = Path("./config")
    queue_db: Path = Path("./sessions/queue.db")
    log_level: str = "INFO"

    def session_file(self, account: str) -> Path:
        return self.sessions_dir / f"{account}.json"

    def account_config_file(self, account: str) -> Path:
        return self.config_dir / f"{account}.yaml"


def load_account_config(path: Path) -> AccountConfig:
    if not path.exists():
        raise FileNotFoundError(
            f"Account config not found: {path}. "
            f"Copy config/account.example.yaml to {path.name} and edit it."
        )
    raw = yaml.safe_load(path.read_text())
    return AccountConfig.model_validate(raw)


def resolve_company_page(
    cfg: AccountConfig,
    *,
    cli_override: int | None = None,
    post_override: int | None = None,
) -> CompanyPage:
    """Pick a company page using the canonical resolution chain.

    Order: CLI flag > post.yaml `as_company` > account.default_company_page.
    Raises ValueError if no source resolves to a configured page.
    """
    candidate = cli_override or post_override or cfg.default_company_page
    if candidate is None:
        if not cfg.company_pages:
            raise ValueError(
                "No company pages configured. Add at least one entry under "
                "`company_pages:` in your account YAML."
            )
        raise ValueError(
            "No company page selected. Pass --as <page_id>, set `as_company` "
            "in post.yaml, or set `default_company_page` in account YAML."
        )
    page = cfg.find_page(candidate)
    if page is None:
        configured_ids = sorted(p.id for p in cfg.company_pages)
        configured_str = str(configured_ids) if configured_ids else "(none)"
        raise ValueError(
            f"Company page {candidate} is not configured for this account. "
            f"Configured ids: {configured_str}."
        )
    return page
