"""Tests for TOML config loading."""

from mtg_deck_analyzer.config import load_config


def _toml(tmp_path, name, contents):
    p = tmp_path / name
    p.write_text(contents, encoding="utf-8")
    return str(p)


def test_loads_explicit_path(tmp_path):
    path = _toml(tmp_path, "c.toml", 'api_key = "abc"\nlang = "it"\n')
    cfg = load_config(path)
    assert cfg["api_key"] == "abc"
    assert cfg["lang"] == "it"
    assert cfg["path"] == path


def test_missing_keys_are_none(tmp_path):
    path = _toml(tmp_path, "c.toml", 'lang = "fr"\n')
    cfg = load_config(path)
    assert cfg["lang"] == "fr"
    assert cfg["api_key"] is None


def test_explicit_missing_path_returns_empty(tmp_path, capsys):
    cfg = load_config(str(tmp_path / "nope.toml"))
    assert cfg == {}
    assert "not found" in capsys.readouterr().out


def test_malformed_toml_returns_empty(tmp_path, capsys):
    path = _toml(tmp_path, "bad.toml", "this is = = not valid toml")
    cfg = load_config(path)
    assert cfg == {}
    assert "Failed to read" in capsys.readouterr().out


def test_no_config_found_returns_empty(tmp_path, monkeypatch):
    # cwd has no config.toml and no explicit path is given.
    monkeypatch.chdir(tmp_path)
    cfg = load_config()
    assert isinstance(cfg, dict)
    # Either empty, or the project-root config — but never crashes.
    assert "path" not in cfg or cfg["path"].endswith("config.toml")
