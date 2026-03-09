"""Tests for csc.generator public and internal API."""
from __future__ import annotations

import pytest
import yaml

from csc.generator import (
    _check_incompatibilities,
    _find_blocks_dir,
    _validate_block_meta,
    compose_to_yaml_string,
    generate,
    load_config,
    write_compose,
)
from csc.models import AppConfig, BlockMeta

# ---------------------------------------------------------------------------
# _find_blocks_dir
# ---------------------------------------------------------------------------


class TestFindBlocksDir:
    def test_explicit_blocks_dir(self, tmp_path):
        bd = tmp_path / "myblocks"
        bd.mkdir()
        result = _find_blocks_dir(None, bd)
        assert result == bd

    def test_explicit_blocks_dir_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="does not exist"):
            _find_blocks_dir(None, tmp_path / "nope")

    def test_next_to_config(self, tmp_path):
        config = tmp_path / "app_config.yaml"
        bd = tmp_path / "building_blocks"
        bd.mkdir()
        result = _find_blocks_dir(config, None)
        assert result == bd

    def test_none_config_falls_back_to_cwd(self, tmp_path, monkeypatch):
        bd = tmp_path / "building_blocks"
        bd.mkdir()
        monkeypatch.chdir(tmp_path)
        result = _find_blocks_dir(None, None)
        assert result == bd

    def test_not_found_raises(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(FileNotFoundError, match="Could not find"):
            _find_blocks_dir(None, None)


# ---------------------------------------------------------------------------
# _validate_block_meta
# ---------------------------------------------------------------------------


class TestValidateBlockMeta:
    def test_valid_meta(self):
        meta, warnings = _validate_block_meta("myblock", {
            "name": "myblock",
            "description": "desc",
            "security_impact": "high",
            "escalation": True,
        })
        assert meta.security_impact == "high"
        assert meta.escalation is True
        assert warnings == []

    def test_invalid_impact_emits_warning(self):
        meta, warnings = _validate_block_meta("myblock", {"security_impact": "extreme"})
        assert len(warnings) == 1
        assert "invalid _meta" in warnings[0]
        assert isinstance(meta, BlockMeta)

    def test_empty_meta_uses_defaults(self):
        meta, warnings = _validate_block_meta("myblock", {})
        assert meta.security_impact == "low"
        assert meta.escalation is False
        assert warnings == []


# ---------------------------------------------------------------------------
# _check_incompatibilities
# ---------------------------------------------------------------------------


class TestCheckIncompatibilities:
    def _meta(self, incompatible_with: list[str]) -> BlockMeta:
        return BlockMeta(incompatible_with=incompatible_with)

    def test_no_conflict(self):
        metas = {"a": self._meta([]), "b": self._meta([])}
        assert _check_incompatibilities(["a", "b"], metas) == []

    def test_single_direction_conflict(self):
        metas = {
            "host-network": self._meta(["app-internal"]),
            "app-internal": self._meta([]),
        }
        warnings = _check_incompatibilities(["host-network", "app-internal"], metas)
        assert len(warnings) == 1
        assert "host-network" in warnings[0]

    def test_mutual_conflict_deduplicated(self):
        """If both blocks declare the incompatibility, only one warning is emitted."""
        metas = {
            "a": self._meta(["b"]),
            "b": self._meta(["a"]),
        }
        warnings = _check_incompatibilities(["a", "b"], metas)
        assert len(warnings) == 1

    def test_incompatible_block_not_present(self):
        """No warning when the incompatible block is not in the active list."""
        metas = {"a": self._meta(["b"])}
        assert _check_incompatibilities(["a"], metas) == []


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_valid_config(self, tmp_path):
        cfg = tmp_path / "app.yaml"
        cfg.write_text("app_name: myapp\n")
        app, errors = load_config(cfg)
        assert errors == []
        assert app is not None
        assert app.app_name == "myapp"

    def test_missing_file(self, tmp_path):
        app, errors = load_config(tmp_path / "nope.yaml")
        assert app is None
        assert any("not found" in e.lower() for e in errors)

    def test_yaml_syntax_error(self, tmp_path):
        cfg = tmp_path / "bad.yaml"
        cfg.write_text("app_name: [\n")
        app, errors = load_config(cfg)
        assert app is None
        assert any("YAML" in e for e in errors)

    def test_pydantic_validation_error(self, tmp_path):
        cfg = tmp_path / "bad.yaml"
        cfg.write_text("app_name: 123\nservices: not-a-list\n")
        app, errors = load_config(cfg)
        assert app is None
        assert any("validation" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


class TestGenerate:
    def test_ping_tracker_round_trip(self, example_config, blocks_dir):
        compose, app_config, warnings, errors = generate(example_config, blocks_dir)
        assert errors == []
        assert app_config is not None
        assert app_config.app_name == "ping-tracker"
        assert "services" in compose
        assert "tracker" in compose["services"]
        assert "ui" in compose["services"]
        assert "init" in compose["services"]

        # standard block should give cap_drop ALL on tracker
        tracker = compose["services"]["tracker"]
        assert "ALL" in [str(c).upper() for c in tracker.get("cap_drop", [])]

    def test_version_deprecation_warning(self, tmp_path, blocks_dir):
        """A config with a top-level 'version' key emits a deprecation warning."""
        cfg = tmp_path / "app_config.yaml"
        cfg.write_text("app_name: test\nversion: '3'\n")
        _, _, warnings, errors = generate(cfg, blocks_dir)
        assert errors == []
        assert any("version" in w.lower() for w in warnings)

    def test_unknown_block_warning(self, tmp_path, tmp_blocks):
        bd, write_block = tmp_blocks
        # Ensure the services subdirectory exists so _find_blocks_dir succeeds
        (bd / "services").mkdir(parents=True, exist_ok=True)
        cfg = tmp_path / "app_config.yaml"
        cfg.write_text("app_name: test\nservices:\n  - name: svc\n    building_blocks:\n      - nonexistent\n")
        compose, _, warnings, errors = generate(cfg, bd)
        assert errors == []
        assert any("not found" in w for w in warnings)

    def test_duplicate_service_warning(self, tmp_path, tmp_blocks):
        bd, write_block = tmp_blocks
        (bd / "services").mkdir(parents=True, exist_ok=True)
        cfg = tmp_path / "app_config.yaml"
        cfg.write_text(
            "app_name: test\nservices:\n"
            "  - name: svc\n  - name: svc\n"
        )
        _, _, warnings, _ = generate(cfg, bd)
        assert any("Duplicate" in w for w in warnings)

    def test_missing_blocks_dir_error(self, tmp_path, monkeypatch):
        """No building_blocks/ anywhere → error, not crash."""
        monkeypatch.chdir(tmp_path)
        cfg = tmp_path / "app_config.yaml"
        cfg.write_text("app_name: test\n")
        _, app_config, _, errors = generate(cfg)
        assert errors != []

    def test_generate_returns_app_config(self, example_config, blocks_dir):
        _, app_config, _, errors = generate(example_config, blocks_dir)
        assert errors == []
        assert isinstance(app_config, AppConfig)

    def test_properties_override_block(self, tmp_path, tmp_blocks):
        bd, write_block = tmp_blocks
        write_block("services", "standard", {
            "_meta": {"security_impact": "low"},
            "user": "nobody",
        })
        cfg = tmp_path / "app_config.yaml"
        cfg.write_text(
            "app_name: test\nservices:\n"
            "  - name: svc\n    building_blocks:\n      - standard\n"
            "    properties:\n      user: 1001\n"
        )
        compose, _, _, errors = generate(cfg, bd)
        assert errors == []
        assert compose["services"]["svc"]["user"] == 1001

    def test_bad_yaml_config_returns_errors(self, tmp_path, tmp_blocks):
        """generate() with invalid YAML returns errors early (line 172)."""
        bd, _ = tmp_blocks
        cfg = tmp_path / "app_config.yaml"
        cfg.write_text("app_name: [\n")  # intentionally broken YAML
        compose, app_config, _, errors = generate(cfg, bd)
        assert compose == {}
        assert app_config is None
        assert errors

    def test_invalid_meta_warning_propagated(self, tmp_path, tmp_blocks):
        """generate() propagates _validate_block_meta warnings (lines 219-220)."""
        bd, write_block = tmp_blocks
        write_block("services", "badmeta", {
            "_meta": {"security_impact": "INVALID_LEVEL"},
            "restart": "always",
        })
        cfg = tmp_path / "app_config.yaml"
        cfg.write_text(
            "app_name: test\nservices:\n"
            "  - name: svc\n    building_blocks:\n      - badmeta\n"
        )
        _, _, warnings, errors = generate(cfg, bd)
        assert errors == []
        assert any("invalid _meta" in w for w in warnings)

    def test_block_scalar_collision_warning_propagated(self, tmp_path, tmp_blocks):
        """generate() propagates _merge collision warnings when two blocks conflict (lines 223-224)."""
        bd, write_block = tmp_blocks
        write_block("services", "block-a", {
            "_meta": {"security_impact": "low"},
            "restart": "always",
        })
        write_block("services", "block-b", {
            "_meta": {"security_impact": "low"},
            "restart": "no",
        })
        cfg = tmp_path / "app_config.yaml"
        cfg.write_text(
            "app_name: test\nservices:\n"
            "  - name: svc\n    building_blocks:\n      - block-a\n      - block-b\n"
        )
        _, _, warnings, errors = generate(cfg, bd)
        assert errors == []
        assert any("collision" in w for w in warnings)

    def test_incompatibility_warning_propagated(self, tmp_path, tmp_blocks):
        """generate() propagates _check_incompatibilities warnings (lines 227-228)."""
        bd, write_block = tmp_blocks
        write_block("services", "block-x", {
            "_meta": {"security_impact": "low", "incompatible_with": ["block-y"]},
            "cap_drop": ["ALL"],
        })
        write_block("services", "block-y", {
            "_meta": {"security_impact": "low"},
            "network_mode": "host",
        })
        cfg = tmp_path / "app_config.yaml"
        cfg.write_text(
            "app_name: test\nservices:\n"
            "  - name: svc\n    building_blocks:\n      - block-x\n      - block-y\n"
        )
        _, _, warnings, errors = generate(cfg, bd)
        assert errors == []
        assert any("block-x" in w and "block-y" in w for w in warnings)


# ---------------------------------------------------------------------------
# write_compose / compose_to_yaml_string
# ---------------------------------------------------------------------------


class TestWriteCompose:
    def test_writes_file_with_header(self, tmp_path):
        out = tmp_path / "out" / "docker-compose.yml"
        write_compose({"services": {}}, out)
        content = out.read_text()
        assert "Generated by container-secure-compose" in content

    def test_creates_parent_dirs(self, tmp_path):
        out = tmp_path / "deep" / "nested" / "docker-compose.yml"
        write_compose({}, out)
        assert out.exists()

    def test_compose_to_yaml_string_no_file(self):
        result = compose_to_yaml_string({"services": {"web": {"image": "nginx"}}})
        assert "Generated by container-secure-compose" in result
        assert "nginx" in result
        # Strip header comment lines and parse the body
        body_lines = [ln for ln in result.splitlines() if not ln.startswith("#")]
        body = "\n".join(body_lines).strip()
        parsed = yaml.safe_load(body)
        assert parsed is not None
        assert parsed["services"]["web"]["image"] == "nginx"
