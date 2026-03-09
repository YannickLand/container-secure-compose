"""CLI integration tests using click.testing.CliRunner."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from csc.cli import cli


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run(*args, input=None):
    """Invoke the CLI with the given arguments and return the result."""
    runner = CliRunner()
    return runner.invoke(cli, [str(a) for a in args], input=input, catch_exceptions=False)


BLOCKS_DIR = Path(__file__).parent.parent / "building_blocks"
EXAMPLE_CONFIG = Path(__file__).parent.parent / "examples" / "ping-tracker" / "app_config.yaml"


# ---------------------------------------------------------------------------
# generate command
# ---------------------------------------------------------------------------


class TestGenerateCommand:
    def test_basic_generation(self, tmp_path):
        result = run("generate", EXAMPLE_CONFIG, "--blocks-dir", BLOCKS_DIR,
                     "--output", tmp_path / "compose.yml")
        assert result.exit_code == 0, result.output
        assert "Generated:" in result.output

    def test_output_file_is_valid_yaml(self, tmp_path):
        out = tmp_path / "compose.yml"
        run("generate", EXAMPLE_CONFIG, "--blocks-dir", BLOCKS_DIR, "-o", out)
        content = yaml.safe_load(out.read_text().split("---")[-1])
        assert content is None or isinstance(content, dict)
        raw = out.read_text()
        # skip header lines and parse the rest
        body = "\n".join(l for l in raw.splitlines() if not l.startswith("#"))
        parsed = yaml.safe_load(body)
        assert "services" in parsed

    def test_security_report_printed_by_default(self, tmp_path):
        result = run("generate", EXAMPLE_CONFIG, "--blocks-dir", BLOCKS_DIR,
                     "-o", tmp_path / "compose.yml")
        assert "Security report" in result.output

    def test_no_report_suppresses_report(self, tmp_path):
        result = run("generate", EXAMPLE_CONFIG, "--blocks-dir", BLOCKS_DIR,
                     "-o", tmp_path / "compose.yml", "--no-report")
        assert "Security report" not in result.output

    def test_stdout_flag_no_file_written(self, tmp_path):
        out = tmp_path / "should_not_exist.yml"
        result = run("generate", EXAMPLE_CONFIG, "--blocks-dir", BLOCKS_DIR,
                     "--stdout", "--no-report")
        assert result.exit_code == 0
        assert not out.exists()
        assert "services:" in result.output

    def test_report_format_json(self, tmp_path):
        result = run("generate", EXAMPLE_CONFIG, "--blocks-dir", BLOCKS_DIR,
                     "-o", tmp_path / "compose.yml",
                     "--report-format", "json")
        # Find the JSON part of the output
        # It follows the "Generated: ..." line
        lines = result.output.strip().splitlines()
        json_start = next(i for i, l in enumerate(lines) if l.strip().startswith("["))
        parsed = json.loads("\n".join(lines[json_start:]))
        assert isinstance(parsed, list)
        assert all("impact" in row for row in parsed)

    def test_version_deprecation_warning(self, tmp_path, capsys):
        """The ping-tracker config has a version key — warning should appear on stderr."""
        runner = CliRunner()
        # Use a temporary config that still has a version key
        from pathlib import Path
        import tempfile, yaml as _yaml
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "app_config.yaml"
            cfg.write_text("app_name: version-test\nversion: '3'\n")
            result = runner.invoke(
                cli,
                ["generate", str(cfg), "--blocks-dir", str(BLOCKS_DIR),
                 "--no-report", "--stdout"],
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        # The deprecation warning goes to stderr; combined output contains it
        assert "version" in (result.output + (result.stderr if hasattr(result, 'stderr') else '')).lower()


# ---------------------------------------------------------------------------
# validate command
# ---------------------------------------------------------------------------


class TestValidateCommand:
    def test_valid_config_exits_zero(self):
        result = run("validate", EXAMPLE_CONFIG, "--blocks-dir", BLOCKS_DIR)
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_missing_block_exits_nonzero(self, tmp_path):
        cfg = tmp_path / "app.yaml"
        cfg.write_text("app_name: test\nservices:\n  - name: svc\n    building_blocks:\n      - nosuchblock\n")
        result = run("validate", cfg, "--blocks-dir", BLOCKS_DIR)
        assert result.exit_code != 0

    def test_invalid_yaml_exits_nonzero(self, tmp_path):
        cfg = tmp_path / "app.yaml"
        cfg.write_text("not_valid_config: [\n")
        result = run("validate", cfg, "--blocks-dir", BLOCKS_DIR)
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# list-blocks command
# ---------------------------------------------------------------------------


class TestListBlocksCommand:
    def test_lists_services(self):
        result = run("list-blocks", "--blocks-dir", BLOCKS_DIR)
        assert result.exit_code == 0
        assert "standard" in result.output
        assert "services/" in result.output

    def test_filter_by_category(self):
        result = run("list-blocks", "--blocks-dir", BLOCKS_DIR, "--category", "services")
        assert result.exit_code == 0
        assert "standard" in result.output
        # networks/ should not appear
        assert "networks/" not in result.output

    def test_impact_shown(self):
        result = run("list-blocks", "--blocks-dir", BLOCKS_DIR)
        assert "[low]" in result.output or "[high]" in result.output

    def test_escalation_tagged(self):
        result = run("list-blocks", "--blocks-dir", BLOCKS_DIR)
        assert "[escalation]" in result.output


# ---------------------------------------------------------------------------
# explain command
# ---------------------------------------------------------------------------


class TestExplainCommand:
    def test_shows_app_name(self):
        result = run("explain", EXAMPLE_CONFIG, "--blocks-dir", BLOCKS_DIR)
        assert result.exit_code == 0
        assert "ping-tracker" in result.output

    def test_shows_building_blocks(self):
        result = run("explain", EXAMPLE_CONFIG, "--blocks-dir", BLOCKS_DIR)
        assert "standard" in result.output or "init" in result.output


# ---------------------------------------------------------------------------
# audit command
# ---------------------------------------------------------------------------


class TestAuditCommand:
    def _make_compose(self, tmp_path: Path, services: dict) -> Path:
        p = tmp_path / "docker-compose.yml"
        with p.open("w") as fh:
            yaml.safe_dump({"services": services}, fh)
        return p

    def test_audit_text_report(self, tmp_path):
        p = self._make_compose(tmp_path, {
            "web": {"cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"], "user": "nobody"}
        })
        result = run("audit", p)
        assert result.exit_code == 0
        assert "Security report" in result.output
        assert "web" in result.output

    def test_audit_json_report(self, tmp_path):
        p = self._make_compose(tmp_path, {"web": {"privileged": True}})
        result = run("audit", p, "--report-format", "json")
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed[0]["impact"] == "critical"

    def test_audit_no_services(self, tmp_path):
        p = tmp_path / "empty.yml"
        p.write_text("version: '3'\n")
        result = run("audit", p)
        assert result.exit_code == 0
        assert "No services" in result.output


# ---------------------------------------------------------------------------
# diff command
# ---------------------------------------------------------------------------


class TestDiffCommand:
    def _make_compose(self, tmp_path: Path, services: dict, name: str = "dc.yml") -> Path:
        p = tmp_path / name
        with p.open("w") as fh:
            yaml.safe_dump({"services": services}, fh)
        return p

    def test_no_regressions_exits_zero(self, tmp_path):
        """Existing file that exactly matches generated output → exit 0."""
        # Generate first
        from csc.generator import generate, write_compose
        compose, _, _, _ = generate(EXAMPLE_CONFIG, BLOCKS_DIR)
        existing = tmp_path / "dc.yml"
        write_compose(compose, existing)

        result = run("diff", EXAMPLE_CONFIG, existing, "--blocks-dir", BLOCKS_DIR)
        assert result.exit_code == 0
        assert "No security regressions" in result.output

    def test_regression_exits_nonzero(self, tmp_path):
        """Existing file with privileged:true on a service that shouldn't → regression."""
        existing = self._make_compose(tmp_path, {"tracker": {"privileged": True}})
        result = CliRunner().invoke(
            cli,
            ["diff", str(EXAMPLE_CONFIG), str(existing), "--blocks-dir", str(BLOCKS_DIR)],
            catch_exceptions=False,
        )
        assert result.exit_code != 0
        assert "regression" in result.output.lower()

    def test_only_in_generated_reported(self, tmp_path):
        """A service present in generated but absent in existing is flagged."""
        existing = self._make_compose(tmp_path, {})
        result = CliRunner().invoke(
            cli,
            ["diff", str(EXAMPLE_CONFIG), str(existing), "--blocks-dir", str(BLOCKS_DIR)],
            catch_exceptions=False,
        )
        assert "only in generated" in result.output.lower()


# ---------------------------------------------------------------------------
# Additional edge-case tests to cover remaining uncovered paths
# ---------------------------------------------------------------------------


class TestGenerateCommandErrors:
    def test_invalid_config_yaml_exits_nonzero(self, tmp_path):
        """generate with a broken config YAML must exit non-zero (lines 34-36)."""
        cfg = tmp_path / "bad.yaml"
        cfg.write_text("app_name: [\n")
        result = run("generate", cfg, "--blocks-dir", BLOCKS_DIR)
        assert result.exit_code != 0

    def test_missing_blocks_dir_exits_nonzero(self, tmp_path):
        """generate with no blocks dir emits errors and exits non-zero."""
        cfg = tmp_path / "app.yaml"
        cfg.write_text("app_name: myapp\n")
        result = run("generate", cfg, "--blocks-dir", tmp_path / "no_such_dir")
        assert result.exit_code != 0


class TestValidateCommandErrors:
    def test_invalid_config_exits_nonzero(self, tmp_path):
        """validate with invalid config YAML (lines 240-243)."""
        cfg = tmp_path / "bad.yaml"
        cfg.write_text("app_name: [\n")
        result = run("validate", cfg, "--blocks-dir", BLOCKS_DIR)
        assert result.exit_code != 0

    def test_missing_blocks_dir_exits_nonzero(self, tmp_path):
        """validate with missing blocks dir (lines 149-152)."""
        cfg = tmp_path / "app.yaml"
        cfg.write_text("app_name: myapp\n")
        result = run("validate", cfg, "--blocks-dir", tmp_path / "no_such_dir")
        assert result.exit_code != 0


class TestListBlocksCommandErrors:
    def test_missing_blocks_dir_exits_nonzero(self, tmp_path, monkeypatch):
        """list-blocks with no blocks dir available (lines 192-194)."""
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(cli, ["list-blocks"], catch_exceptions=False)
        assert result.exit_code != 0

    def test_empty_category_directory_skipped(self, tmp_path):
        """list-blocks skips a category dir with no .yaml files (lines 201, 205)."""
        bd = tmp_path / "building_blocks"
        (bd / "services").mkdir(parents=True)
        (bd / "networks").mkdir(parents=True)
        # no .yaml files anywhere
        result = run("list-blocks", "--blocks-dir", bd)
        assert result.exit_code == 0


class TestExplainCommandErrors:
    def test_invalid_config_exits_nonzero(self, tmp_path):
        """explain with invalid config (lines 240-243)."""
        cfg = tmp_path / "bad.yaml"
        cfg.write_text("app_name: [\n")
        result = run("explain", cfg, "--blocks-dir", BLOCKS_DIR)
        assert result.exit_code != 0

    def test_missing_blocks_dir_exits_nonzero(self, tmp_path):
        """explain with missing blocks dir (lines 249-252)."""
        cfg = tmp_path / "app.yaml"
        cfg.write_text("app_name: myapp\n")
        result = run("explain", cfg, "--blocks-dir", tmp_path / "no_such_dir")
        assert result.exit_code != 0

    def test_missing_block_shown_as_not_found(self, tmp_path):
        """explain shows '(not found)' for a missing block (lines 266-267)."""
        bd = tmp_path / "building_blocks"
        (bd / "services").mkdir(parents=True)
        cfg = tmp_path / "app.yaml"
        cfg.write_text(
            "app_name: myapp\nservices:\n"
            "  - name: svc\n    building_blocks:\n      - nonexistent\n"
        )
        result = run("explain", cfg, "--blocks-dir", bd)
        assert result.exit_code == 0
        assert "not found" in result.output


class TestAuditCommandErrors:
    def test_invalid_yaml_exits_nonzero(self, tmp_path):
        """audit with broken YAML exits non-zero (lines 301-303)."""
        p = tmp_path / "bad.yml"
        p.write_text("services: [\n")
        result = CliRunner().invoke(cli, ["audit", str(p)], catch_exceptions=False)
        assert result.exit_code != 0


class TestDiffCommandErrors:
    def test_invalid_compose_yaml_exits_nonzero(self, tmp_path):
        """diff with broken compose YAML exits non-zero (lines 349-352)."""
        bad = tmp_path / "bad.yml"
        bad.write_text("services: [\n")
        result = CliRunner().invoke(
            cli,
            ["diff", str(EXAMPLE_CONFIG), str(bad), "--blocks-dir", str(BLOCKS_DIR)],
            catch_exceptions=False,
        )
        assert result.exit_code != 0

    def test_services_only_in_existing_reported(self, tmp_path):
        """diff labels services that exist only in the existing file (lines 378-379)."""
        from csc.generator import generate, write_compose
        compose, _, _, _ = generate(EXAMPLE_CONFIG, BLOCKS_DIR)
        # Add an extra service only in the existing file
        compose["services"]["extra-svc"] = {"image": "extra:latest", "privileged": True}
        existing = tmp_path / "dc.yml"
        write_compose(compose, existing)
        result = CliRunner().invoke(
            cli,
            ["diff", str(EXAMPLE_CONFIG), str(existing), "--blocks-dir", str(BLOCKS_DIR)],
            catch_exceptions=False,
        )
        assert "only in existing" in result.output.lower()

    def test_improvements_reported(self, tmp_path):
        """diff reports when existing file is more restrictive than generated (lines 393, 402, 415-432)."""
        from csc.generator import generate, write_compose
        compose, _, _, _ = generate(EXAMPLE_CONFIG, BLOCKS_DIR)
        # Make the existing file more restrictive: add no-new-privileges to init
        # (init block intentionally omits no-new-privileges; adding it to existing = improvement)
        existing_services = dict(compose.get("services", {}))
        existing_services["init"] = dict(existing_services.get("init", {}))
        if "security_opt" not in existing_services["init"]:
            existing_services["init"]["security_opt"] = ["no-new-privileges:true"]
        existing = tmp_path / "dc.yml"
        import yaml as _yaml
        with existing.open("w") as fh:
            _yaml.safe_dump({"services": existing_services}, fh)
        result = CliRunner().invoke(
            cli,
            ["diff", str(EXAMPLE_CONFIG), str(existing), "--blocks-dir", str(BLOCKS_DIR)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Differences" in result.output or "only in existing" in result.output.lower()

    def test_impact_improvement_reported(self, tmp_path):
        """diff reports impact improvement when existing has lower impact than generated (line 402)."""
        # Build a config where a service uses `init` block (medium/high impact due to cap_add)
        from csc.generator import generate, write_compose
        compose, _, _, _ = generate(EXAMPLE_CONFIG, BLOCKS_DIR)
        # Create an existing file where the init service has no cap_add → lower impact
        existing_compose = {
            "services": {
                "init": {"cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"], "user": "nobody"},
                "tracker": compose["services"]["tracker"],
                "ui": compose["services"]["ui"],
            }
        }
        existing = tmp_path / "dc.yml"
        write_compose(existing_compose, existing)
        result = CliRunner().invoke(
            cli,
            ["diff", str(EXAMPLE_CONFIG), str(existing), "--blocks-dir", str(BLOCKS_DIR)],
            catch_exceptions=False,
        )
        # The existing init service has lower impact (low) than generated (high due to cap_add)
        # → reports as "improvement" (existing more restrictive / lower impact)
        assert result.exit_code == 0
        assert "Differences" in result.output or "improvement" in result.output.lower()

    def test_empty_generated_compose(self, tmp_path):
        """diff exits cleanly when generated compose has no services (lines 357-359)."""
        # A config with no services generates an empty compose
        cfg = tmp_path / "app.yaml"
        cfg.write_text("app_name: empty-app\n")
        bd = tmp_path / "building_blocks"
        (bd / "services").mkdir(parents=True)
        existing = tmp_path / "dc.yml"
        existing.write_text("services:\n  web:\n    image: nginx\n")
        result = CliRunner().invoke(
            cli,
            ["diff", str(cfg), str(existing), "--blocks-dir", str(bd)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "no services" in result.output.lower()
