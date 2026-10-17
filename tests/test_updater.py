import hashlib

import pytest

import updater as up


@pytest.mark.parametrize("s,expected", [
    ("v0.10.0", (0, 10, 0)), ("0.9.0", (0, 9, 0)), ("1.2", (1, 2, 0)),
    ("v1.2.3-beta.1", (1, 2, 3)), (" V2.0.1 ", (2, 0, 1)),
])
def test_parse_version_accepts_common_forms(s, expected):
    assert up.parse_version(s) == expected


@pytest.mark.parametrize("s", ["", None, "latest", "v", "1", "a.b.c"])
def test_parse_version_rejects_garbage(s):
    assert up.parse_version(s) is None


def test_is_newer_compares_numerically_not_lexically():
    assert up.is_newer("v0.10.0", "0.9.0")
    assert not up.is_newer("v0.9.0", "0.9.0")
    assert not up.is_newer("v0.8.5", "0.9.0")


def test_is_newer_false_when_either_side_unparseable():
    assert not up.is_newer("nightly", "0.9.0")
    assert not up.is_newer("v1.0.0", "dev")


RELEASE = {
    "tag_name": "v0.11.0", "html_url": "https://github.com/o/r/releases/tag/v0.11.0",
    "body": "notes", "published_at": "2026-11-01T00:00:00Z",
    "assets": [
        {"name": "SHA256SUMS.txt", "browser_download_url": "https://github.com/o/r/releases/download/v0.11.0/SHA256SUMS.txt", "size": 200},
        {"name": "StockWallet-Setup.exe", "browser_download_url": "https://github.com/o/r/releases/download/v0.11.0/StockWallet-Setup.exe",
         "size": 50_000_000, "digest": "sha256:" + "ab" * 32},
        {"name": "StockWallet-portable-v0.11.0.zip", "browser_download_url":
         "https://github.com/o/r/releases/download/v0.11.0/p.zip", "size": 60_000_000},
    ],
}


def test_select_asset_installer_and_portable():
    assert up.select_asset(RELEASE, "installer")["name"] == "StockWallet-Setup.exe"
    assert up.select_asset(RELEASE, "portable")["name"] == "StockWallet-portable-v0.11.0.zip"


def test_select_asset_missing_returns_none():
    assert up.select_asset({"assets": []}, "installer") is None
    assert up.select_asset(RELEASE, "source") is None


def test_expected_sha256_prefers_asset_digest():
    asset = up.select_asset(RELEASE, "installer")
    assert up.expected_sha256(asset, None) == "ab" * 32


def test_expected_sha256_from_sums_file():
    asset = {"name": "StockWallet-Setup.exe"}
    sums = f"{'CD' * 32}  StockWallet-Setup.exe\n{'ef' * 32} *StockWallet-portable-v1.zip\n"
    assert up.expected_sha256(asset, sums) == "cd" * 32


def test_expected_sha256_none_when_unavailable():
    assert up.expected_sha256({"name": "StockWallet-Setup.exe"}, "deadbeef  other.exe") is None
    assert up.expected_sha256({"name": "x", "digest": "md5:abc"}, None) is None


def test_sha256_file_and_verify(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"stock-wallet")
    digest = hashlib.sha256(b"stock-wallet").hexdigest()
    assert up.sha256_file(str(p)) == digest
    assert up.verify_file(str(p), digest.upper())
    assert not up.verify_file(str(p), "00" * 32)
    assert not up.verify_file(str(p), None)


@pytest.mark.parametrize("url,ok", [
    ("https://github.com/o/r/releases/download/v1/StockWallet-Setup.exe", True),
    ("https://objects.githubusercontent.com/github-production-release-asset/1", True),
    ("https://release-assets.githubusercontent.com/github-production-release-asset/1", True),
    ("http://github.com/o/r/x.exe", False),
    ("https://github.com.evil.example/x.exe", False),
    ("https://evil.example/github.com/x.exe", False),
    ("", False), (None, False),
])
def test_is_trusted_download_url(url, ok):
    assert up.is_trusted_download_url(url) is ok


def test_summarize_release_newer_installer_can_install():
    s = up.summarize_release(RELEASE, "0.10.0", "installer")
    assert s["ok"] and s["newer"] and s["latest"] == "0.11.0" and s["current"] == "0.10.0"
    assert s["can_install"] is True
    assert s["asset_size"] == 50_000_000
    assert s["html_url"].endswith("v0.11.0") and s["notes"] == "notes"


def test_summarize_release_portable_cannot_self_install():
    s = up.summarize_release(RELEASE, "0.10.0", "portable")
    assert s["newer"] and s["can_install"] is False


def test_summarize_release_not_newer():
    s = up.summarize_release(RELEASE, "0.11.0", "installer")
    assert s["newer"] is False and s["can_install"] is False


def test_summarize_release_installer_without_asset_cannot_install():
    rel = {**RELEASE, "assets": [a for a in RELEASE["assets"] if not a["name"].endswith(".exe")]}
    assert up.summarize_release(rel, "0.10.0", "installer")["can_install"] is False
