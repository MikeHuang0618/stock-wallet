import json

import pytest

import api


@pytest.fixture()
def a(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return api.Api()


def _syms(wl):
    return [it["sym"] for g in wl["groups"] for it in g["items"]]


def _read(name):
    with open(api._file(name), encoding="utf-8") as f:
        return json.load(f)


def test_save_failure_keeps_previous_file_intact(a):
    assert a._save("watchlist.json", {"version": 2, "groups": []})["ok"]
    r = a._save("watchlist.json", {"bad": object()})
    assert r["ok"] is False
    assert _read("watchlist.json") == {"version": 2, "groups": []}


def test_save_leaves_no_temp_files(a, tmp_path):
    a._save("alerts.json", [1, 2])
    a._save("alerts.json", {"bad": object()})
    leftovers = [p.name for p in (tmp_path / api.APP_NAME).iterdir() if p.name.startswith("alerts.json")]
    assert leftovers == ["alerts.json"]


def test_save_ai_config_preserves_manual_model_overrides(a):
    a._save("ai_config.json", {"provider": "claude", "keys": {}, "models": {"openai": "gpt-custom"}})
    a.save_ai_config({"provider": "openai", "prompt": "p", "keys": {"openai": "k"}})
    saved = _read("ai_config.json")
    assert saved["models"] == {"openai": "gpt-custom"}
    assert saved["provider"] == "openai" and saved["keys"] == {"openai": "k"}


def test_export_payload_includes_both_watchlists(a):
    a.save_watchlist([{"sym": "AAPL", "name": "Apple"}], "us")
    a.save_watchlist([{"sym": "2330.TW", "name": "台積電"}], "tw")
    data = a._export_payload(["watchlist"])
    assert _syms(data["watchlist"]) == ["AAPL"]
    assert _syms(data["watchlist_tw"]) == ["2330.TW"]


def test_import_applies_tw_watchlist(a):
    applied = a._apply_import({"watchlist": [{"sym": "MSFT", "name": "Microsoft"}],
                               "watchlist_tw": [{"sym": "2454.TW", "name": "聯發科"}]}, ["watchlist"])
    assert "觀察名單" in applied
    tw = a.get_watchlist("tw")
    assert _syms(tw) == ["2454.TW"]


def test_import_keys_preserves_models(a):
    a._save("ai_config.json", {"provider": "none", "keys": {"claude": "old"}, "models": {"claude": "m1"}})
    a._apply_import({"keys": {"openai": "new"}}, ["keys"])
    saved = _read("ai_config.json")
    assert saved["keys"] == {"claude": "old", "openai": "new"}
    assert saved["models"] == {"claude": "m1"}
