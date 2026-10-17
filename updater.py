import hashlib
import os
import re
from urllib.parse import urlparse

REPO = "MikeHuang0618/stock-wallet"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
INSTALLER_NAME = "StockWallet-Setup.exe"
SUMS_NAME = "SHA256SUMS.txt"

TRUSTED_HOSTS = frozenset({
    "github.com",
    "api.github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
})

_VER_RE = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?")
_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


def parse_version(s):
    if not isinstance(s, str):
        return None
    m = _VER_RE.match(s.strip().lower())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)


def is_newer(latest, current):
    a, b = parse_version(latest), parse_version(current)
    return a is not None and b is not None and a > b


def version_str(s):
    v = parse_version(s)
    return "%d.%d.%d" % v if v else (s or "")


def select_asset(release, kind):
    for a in (release or {}).get("assets") or []:
        name = a.get("name") or ""
        if kind == "installer" and name == INSTALLER_NAME:
            return a
        if kind == "portable" and name.startswith("StockWallet-portable-") and name.endswith(".zip"):
            return a
    return None


def find_asset(release, name):
    return next((a for a in (release or {}).get("assets") or [] if a.get("name") == name), None)


def expected_sha256(asset, sums_text):
    digest = (asset or {}).get("digest") or ""
    if digest.lower().startswith("sha256:"):
        h = digest.split(":", 1)[1].strip()
        if _HEX64.match(h):
            return h.lower()
    name = (asset or {}).get("name")
    for line in (sums_text or "").splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and _HEX64.match(parts[0]) and parts[1].lstrip("*").strip() == name:
            return parts[0].lower()
    return None


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def verify_file(path, expected):
    if not expected:
        return False
    return sha256_file(path) == expected.strip().lower()


def is_trusted_download_url(url):
    if not isinstance(url, str) or not url:
        return False
    p = urlparse(url)
    return p.scheme == "https" and (p.hostname or "").lower() in TRUSTED_HOSTS


def summarize_release(release, current, kind):
    latest = version_str(release.get("tag_name"))
    newer = is_newer(latest, current)
    installer = select_asset(release, "installer")
    asset = select_asset(release, kind) if kind in ("installer", "portable") else None
    return {
        "ok": True,
        "current": version_str(current),
        "latest": latest,
        "newer": newer,
        "notes": release.get("body") or "",
        "published_at": release.get("published_at"),
        "html_url": release.get("html_url") or RELEASES_PAGE,
        "kind": kind,
        "can_install": bool(newer and kind == "installer" and installer),
        "asset_size": (asset or {}).get("size"),
    }


def install_kind(frozen, exe_path, exists=os.path.exists):
    if not frozen:
        return "source"
    if exists(os.path.join(os.path.dirname(exe_path), "unins000.exe")):
        return "installer"
    return "portable"
