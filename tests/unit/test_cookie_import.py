from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_linkedin.auth.cookie_import import (
    convert_cookie_editor_json,
    convert_cookies_to_storage_state,
)


def _cookie(name: str, value: str = "x", **extra: object) -> dict:
    return {
        "name": name,
        "value": value,
        "domain": ".linkedin.com",
        "path": "/",
        "secure": True,
        "sameSite": "lax",
        **extra,
    }


def _full_export() -> list[dict]:
    return [
        _cookie("li_at", "abc"),
        _cookie("JSESSIONID", "xyz"),
        _cookie("liap"),
        _cookie("bcookie"),
        _cookie("bscookie"),
        _cookie("lidc"),
        _cookie("li_rm"),
        _cookie("lang"),
    ]


def test_converts_full_export(tmp_path: Path) -> None:
    src = tmp_path / "cookies.json"
    src.write_text(json.dumps(_full_export()))
    dst = tmp_path / "storage.json"
    summary = convert_cookie_editor_json(src, dst)
    assert summary["cookies_written"] == 8
    assert summary["missing_required"] == []
    assert summary["missing_recommended"] == []
    data = json.loads(dst.read_text())
    assert {c["name"] for c in data["cookies"]} == {c["name"] for c in _full_export()}


def test_rejects_missing_required_li_at(tmp_path: Path) -> None:
    """No li_at => hard fail."""
    src = tmp_path / "cookies.json"
    src.write_text(json.dumps([_cookie("JSESSIONID", "xyz")]))
    dst = tmp_path / "storage.json"
    with pytest.raises(ValueError, match="missing required"):
        convert_cookie_editor_json(src, dst)


def test_rejects_missing_required_jsessionid(tmp_path: Path) -> None:
    """No JSESSIONID => hard fail."""
    src = tmp_path / "cookies.json"
    src.write_text(json.dumps([_cookie("li_at", "abc")]))
    dst = tmp_path / "storage.json"
    with pytest.raises(ValueError, match="missing required"):
        convert_cookie_editor_json(src, dst)


def test_accepts_minimum_required_pair(tmp_path: Path) -> None:
    """li_at + JSESSIONID alone is enough; just warns about recommended."""
    src = tmp_path / "cookies.json"
    src.write_text(json.dumps([_cookie("li_at", "abc"), _cookie("JSESSIONID", "xyz")]))
    dst = tmp_path / "storage.json"
    summary = convert_cookie_editor_json(src, dst)
    assert summary["missing_required"] == []
    assert summary["cookies_written"] == 2


def test_reports_missing_recommended(tmp_path: Path) -> None:
    src = tmp_path / "cookies.json"
    src.write_text(
        json.dumps([
            _cookie("li_at"),
            _cookie("JSESSIONID"),
        ])
    )
    dst = tmp_path / "storage.json"
    summary = convert_cookie_editor_json(src, dst)
    assert summary["missing_recommended"] == sorted(
        ["liap", "bcookie", "bscookie", "lidc", "li_rm", "lang"]
    )


def test_filters_other_domains(tmp_path: Path) -> None:
    src = tmp_path / "cookies.json"
    src.write_text(
        json.dumps([
            *_full_export(),
            {
                "name": "tracker",
                "value": "y",
                "domain": ".example.com",
                "path": "/",
                "secure": True,
                "sameSite": "lax",
            },
        ])
    )
    dst = tmp_path / "storage.json"
    summary = convert_cookie_editor_json(src, dst)
    assert summary["cookies_written"] == 8
    data = json.loads(dst.read_text())
    assert all("linkedin.com" in c["domain"] for c in data["cookies"])


def test_rejects_non_list(tmp_path: Path) -> None:
    src = tmp_path / "cookies.json"
    src.write_text(json.dumps({"not": "a list"}))
    dst = tmp_path / "storage.json"
    with pytest.raises(ValueError, match="not a Cookie-Editor"):
        convert_cookie_editor_json(src, dst)


def test_samesite_normalization(tmp_path: Path) -> None:
    src = tmp_path / "cookies.json"
    raw = _full_export()
    raw[0]["sameSite"] = "no_restriction"
    raw[1]["sameSite"] = "strict"
    src.write_text(json.dumps(raw))
    dst = tmp_path / "storage.json"
    convert_cookie_editor_json(src, dst)
    data = json.loads(dst.read_text())
    li_at = next(c for c in data["cookies"] if c["name"] == "li_at")
    jsess = next(c for c in data["cookies"] if c["name"] == "JSESSIONID")
    assert li_at["sameSite"] == "None"
    assert jsess["sameSite"] == "Strict"


# ---- Netscape cookies.txt format ----


def _netscape_row(
    domain: str, name: str, value: str, *, http_only: bool = False, secure: bool = True
) -> str:
    line = "\t".join([
        domain,
        "TRUE",
        "/",
        "TRUE" if secure else "FALSE",
        "1999999999",
        name,
        value,
    ])
    return f"#HttpOnly_{line}" if http_only else line


def _netscape_full() -> str:
    rows = [
        "# Netscape HTTP Cookie File",
        "# comment",
        "",
        _netscape_row(".linkedin.com", "li_at", "abc", http_only=True),
        _netscape_row(".linkedin.com", "JSESSIONID", "xyz"),
        _netscape_row(".linkedin.com", "liap", "p"),
        _netscape_row(".linkedin.com", "bcookie", "b"),
        _netscape_row(".linkedin.com", "bscookie", "bs"),
        _netscape_row(".linkedin.com", "lidc", "l"),
        _netscape_row(".linkedin.com", "li_rm", "r"),
        _netscape_row(".linkedin.com", "lang", "en_US"),
        _netscape_row(".example.com", "other", "ignored"),
    ]
    return "\n".join(rows) + "\n"


def test_netscape_auto_detect(tmp_path: Path) -> None:
    src = tmp_path / "cookies.txt"
    src.write_text(_netscape_full())
    dst = tmp_path / "storage.json"
    summary = convert_cookies_to_storage_state(src, dst)
    assert summary["format"] == "netscape"
    assert summary["cookies_written"] == 8
    assert summary["total_parsed"] >= 9  # includes the example.com row
    assert summary["missing_required"] == []
    assert summary["missing_recommended"] == []
    data = json.loads(dst.read_text())
    assert all("linkedin.com" in c["domain"] for c in data["cookies"])
    li_at = next(c for c in data["cookies"] if c["name"] == "li_at")
    assert li_at["httpOnly"] is True
    assert li_at["value"] == "abc"


def test_netscape_rejects_missing_required(tmp_path: Path) -> None:
    rows = [
        "# Netscape HTTP Cookie File",
        _netscape_row(".linkedin.com", "li_at", "abc"),
        # missing JSESSIONID
    ]
    src = tmp_path / "cookies.txt"
    src.write_text("\n".join(rows) + "\n")
    dst = tmp_path / "storage.json"
    with pytest.raises(ValueError, match="missing required"):
        convert_cookies_to_storage_state(src, dst)


def test_netscape_ignores_comments_and_blank_lines(tmp_path: Path) -> None:
    src = tmp_path / "cookies.txt"
    src.write_text(_netscape_full())
    dst = tmp_path / "storage.json"
    convert_cookies_to_storage_state(src, dst)
    data = json.loads(dst.read_text())
    assert all(c["name"] for c in data["cookies"])


def test_auto_detect_routes_json(tmp_path: Path) -> None:
    src = tmp_path / "cookies.json"
    src.write_text(json.dumps(_full_export()))
    dst = tmp_path / "storage.json"
    summary = convert_cookies_to_storage_state(src, dst)
    assert summary["format"] == "cookie-editor-json"
