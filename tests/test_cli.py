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
        result = runner.invoke(
            cli,
            ["generate", str(EXAMPLE_CONFIG), "--blocks-dir", str(BLOCKS_DIR),
             "-o", str(tmp_path / "compose.yml")],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "version" in result.output.lower()


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
