from __future__ import annotations

from pathlib import Path

import pytest

from agy_doctor_mux.plugin_builder import (
    KEBAB_RE,
    scaffold_native_plugin,
    validate_native_plugin_bundle,
)


def test_scaffold_produces_valid_bundle(tmp_path: Path) -> None:
    result = scaffold_native_plugin(tmp_path / "plug", name="my-plugin")
    assert result["name"] == "my-plugin"
    manifest = Path(result["target_dir"]) / "plugin.json"
    assert manifest.is_file()
    assert "my-plugin" in manifest.read_text(encoding="utf-8")


def test_scaffold_name_must_be_kebab_case(tmp_path: Path) -> None:
    bad_name = "MyPlugin"
    assert not KEBAB_RE.match(bad_name)
    scaffold_native_plugin(tmp_path / "bad", name=bad_name)
    report = validate_native_plugin_bundle(tmp_path / "bad")
    assert report["valid"] is False
    joined = " ".join(report["errors"])
    assert "kebab-case" in joined


@pytest.mark.parametrize("bad_name", ["Bad_Name", "UPPER", "has space"])
def test_validate_rejects_non_kebab_names(tmp_path: Path, bad_name: str) -> None:
    scaffold_native_plugin(tmp_path / "x", name=bad_name)
    report = validate_native_plugin_bundle(tmp_path / "x")
    assert report["valid"] is False
    assert any("kebab-case" in err for err in report["errors"])
