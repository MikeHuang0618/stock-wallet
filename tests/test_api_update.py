import hashlib

import pytest

import api
import updater as up

PAYLOAD = b"fake-installer-bytes" * 1000
GOOD_SHA = hashlib.sha256(PAYLOAD).hexdigest()
EXE_URL = "https://github.com/MikeHuang0618/stock-wallet/releases/download/v9.9.9/StockWallet-Setup.exe"


def _release(digest=None, extra_assets=()):
    exe = {"name": "StockWallet-Setup.exe", "browser_download_url": EXE_URL, "size": len(PAYLOAD)}
    if digest:
        exe["digest"] = "sha256:" + digest
    return {"tag_name": "v9.9.9", "html_url": "https://github.com/x/releases/tag/v9.9.9",
            "body": "notes", "assets": [exe, *extra_assets]}


class _Resp:
    def __init__(self, status=200, json_data=None, content=b"", text="", url=""):
        self.status_code = status
        self._json = json_data
        self._content = content
        self.text = text
        self.url = url
        self.headers = {"content-length": str(len(content))}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i:i + chunk_size]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Session:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, **kw):
        self.calls.append(url)
        r = self.routes.get(url)
        if r is None:
            return _Resp(404)
        return r


@pytest.fixture()
def a(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("TEMP", str(tmp_path / "tmp"))
    return api.Api()


def _use(a, routes):
    s = _Session(routes)
    a._local.session = s
    return s


def test_install_kind_detection(tmp_path):
    exe = tmp_path / "StockWallet.exe"
    exe.write_bytes(b"")
    assert up.install_kind(False, str(exe)) == "source"
    assert up.install_kind(True, str(exe)) == "portable"
    (tmp_path / "unins000.exe").write_bytes(b"")
    assert up.install_kind(True, str(exe)) == "installer"


def test_get_app_info_reports_version(a):
    info = a.get_app_info()
    assert info["version"] == api.APP_VERSION
    assert info["install_kind"] in ("source", "portable", "installer")


def test_check_update_summarizes_latest_release(a, monkeypatch):
    monkeypatch.setattr(api, "APP_VERSION", "0.10.0")
    monkeypatch.setattr(a, "_install_kind", lambda: "installer")
    _use(a, {up.LATEST_RELEASE_API: _Resp(json_data=_release(GOOD_SHA))})
    r = a.check_update()
    assert r["ok"] and r["newer"] and r["latest"] == "9.9.9" and r["can_install"]


def test_check_update_reports_http_failure(a):
    _use(a, {up.LATEST_RELEASE_API: _Resp(status=403)})
    r = a.check_update()
    assert r["ok"] is False and r["error"]


def test_check_update_caches_result(a):
    s = _use(a, {up.LATEST_RELEASE_API: _Resp(json_data=_release(GOOD_SHA))})
    a.check_update()
    a.check_update()
    assert s.calls.count(up.LATEST_RELEASE_API) == 1
    a.check_update(force=True)
    assert s.calls.count(up.LATEST_RELEASE_API) == 2


def test_download_installer_verifies_digest(a):
    _use(a, {EXE_URL: _Resp(content=PAYLOAD, url=EXE_URL)})
    seen = []
    path = a._download_installer(_release(GOOD_SHA), progress=seen.append)
    with open(path, "rb") as f:
        assert f.read() == PAYLOAD
    assert seen and seen[-1] == 100


def test_download_installer_uses_sums_file_when_no_digest(a):
    sums_url = "https://github.com/MikeHuang0618/stock-wallet/releases/download/v9.9.9/SHA256SUMS.txt"
    sums = {"name": "SHA256SUMS.txt", "browser_download_url": sums_url, "size": 100}
    _use(a, {EXE_URL: _Resp(content=PAYLOAD, url=EXE_URL),
             sums_url: _Resp(text=f"{GOOD_SHA}  StockWallet-Setup.exe\n", url=sums_url)})
    assert a._download_installer(_release(None, [sums]), progress=lambda p: None)


def test_download_installer_rejects_hash_mismatch_and_removes_file(a, tmp_path):
    _use(a, {EXE_URL: _Resp(content=PAYLOAD, url=EXE_URL)})
    with pytest.raises(RuntimeError, match="SHA-256"):
        a._download_installer(_release("00" * 32), progress=lambda p: None)
    leftovers = [p for p in (tmp_path / "tmp").rglob("*") if p.is_file()]
    assert leftovers == []


def test_download_installer_refuses_without_any_hash(a):
    s = _use(a, {EXE_URL: _Resp(content=PAYLOAD, url=EXE_URL)})
    with pytest.raises(RuntimeError, match="SHA-256"):
        a._download_installer(_release(None), progress=lambda p: None)
    assert EXE_URL not in s.calls


def test_download_installer_refuses_untrusted_redirect(a):
    _use(a, {EXE_URL: _Resp(content=PAYLOAD, url="https://evil.example/x.exe")})
    with pytest.raises(RuntimeError, match="來源"):
        a._download_installer(_release(GOOD_SHA), progress=lambda p: None)


def test_download_installer_rejects_unparseable_tag(a):
    rel = {**_release(GOOD_SHA), "tag_name": "../../evil"}
    _use(a, {EXE_URL: _Resp(content=PAYLOAD, url=EXE_URL)})
    with pytest.raises(RuntimeError, match="版本"):
        a._download_installer(rel, progress=lambda p: None)
