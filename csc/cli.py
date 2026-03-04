"""CLI entry point for container-secure-compose."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import click
import yaml

from . import __version__
from .generator import (
    CATEGORIES,
    META_KEY,
    _find_blocks_dir,
    _load_block,
    compose_to_yaml_string,
    generate,
    load_config,
    write_compose,
)
from .reporter import build_report, format_report, format_report_json

# ---------------------------------------------------------------------------
# Helpers shared between commands
# ---------------------------------------------------------------------------


def _emit_issues(warnings: list[str], errors: list[str], ctx: click.Context) -> None:
    for w in warnings:
        click.echo(f"  warning: {w}", err=True)
    if errors:
        for e in errors:
            click.echo(f"  error:   {e}", err=True)
        ctx.exit(1)


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group()
@click.version_option(__version__, prog_name="csc")
def cli() -> None:
    """container-secure-compose — privilege-minimised Docker Compose generator.

    \b
    Generate secure Docker Compose configurations from an abstract application
    description using composable building blocks.
    """


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("config", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output", "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output path for docker-compose.yml. Defaults to output/<app_name>/docker-compose.yml.",
)
@click.option(
    "--blocks-dir", "-b",
    type=click.Path(path_type=Path),
    default=None,
    help="Directory containing building blocks. Defaults to building_blocks/ next to the config or in CWD.",
)
@click.option(
    "--no-report",
    is_flag=True,
    default=False,
    help="Suppress the security report.",
)
@click.option(
    "--stdout",
    is_flag=True,
    default=False,
    help="Print the generated docker-compose.yml to stdout instead of writing a file.",
)
@click.option(
    "--report-format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Security report output format.",
)
@click.pass_context
def generate_cmd(
    ctx: click.Context,
    config: Path,
    output: Path | None,
    blocks_dir: Path | None,
    no_report: bool,
    stdout: bool,
    report_format: str,
) -> None:
    """Generate a docker-compose.yml from CONFIG."""
    compose, app_config, warnings, errors = generate(config, blocks_dir)
    _emit_issues(warnings, errors, ctx)

    app_name = app_config.app_name if app_config else "output"

    if stdout:
        click.echo(compose_to_yaml_string(compose, source_config=config))
    else:
        dest = output or Path("output") / app_name / "docker-compose.yml"
        write_compose(compose, dest, source_config=config)
        click.echo(f"Generated: {dest}")

    if not no_report and "services" in compose:
        reports = build_report(compose["services"])
        if report_format == "json":
            click.echo(format_report_json(reports))
        else:
            click.echo(format_report(reports))


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("config", type=click.Path(exists=True, path_type=Path))
@click.option("--blocks-dir", "-b", type=click.Path(path_type=Path), default=None)
@click.pass_context
def validate(
    ctx: click.Context,
    config: Path,
    blocks_dir: Path | None,
) -> None:
    """Validate CONFIG without generating any output."""
    app_config, errors = load_config(config)
    if errors:
        for e in errors:
            click.echo(f"  error: {e}", err=True)
        ctx.exit(1)
        return

    # Resolve blocks dir so any path errors are caught here
    try:
        resolved = _find_blocks_dir(config, blocks_dir)
    except FileNotFoundError as exc:
        click.echo(f"  error: {exc}", err=True)
        ctx.exit(1)
        return

    # Check that every referenced building block exists
    issues: list[str] = []
    for category in CATEGORIES:
        entries = getattr(app_config, category, [])
        for entry in entries:
            for block_name in entry.building_blocks:
                block_path = resolved / category / f"{block_name}.yaml"
                if not block_path.is_file():
                    issues.append(
                        f"[{entry.name}] building block '{block_name}' not found "
                        f"at {block_path}"
                    )

    if issues:
        for issue in issues:
            click.echo(f"  error: {issue}", err=True)
        ctx.exit(1)
    else:
        click.echo(f"Config is valid. ({config})")


# ---------------------------------------------------------------------------
# list-blocks
# ---------------------------------------------------------------------------


@cli.command("list-blocks")
@click.option("--blocks-dir", "-b", type=click.Path(path_type=Path), default=None)
@click.option(
    "--category", "-c",
    type=click.Choice(["services", "networks", "volumes"]),
    default=None,
    help="Filter by category.",
)
def list_blocks(blocks_dir: Path | None, category: str | None) -> None:
    """List all available building blocks."""
    try:
        resolved = _find_blocks_dir(None, blocks_dir)
    except FileNotFoundError as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)

    categories = [category] if category else list(CATEGORIES)

    for cat in categories:
        cat_dir = resolved / cat
        if not cat_dir.is_dir():
            continue

        blocks = sorted(cat_dir.glob("*.yaml"))
        if not blocks:
            continue

        click.echo(f"\n{cat}/")
        for block_path in blocks:
            with block_path.open() as fh:
                content = yaml.safe_load(fh) or {}
            meta = content.get(META_KEY, {})
            name = block_path.stem
            desc = meta.get("description", "")
            impact = meta.get("security_impact", "?")
            escalation = meta.get("escalation", False)
            esc_tag = " [escalation]" if escalation else ""
            click.echo(f"  {name:<30} [{impact}]{esc_tag}")
            if desc:
                click.echo(f"    {desc.strip()}")
    click.echo("")


# ---------------------------------------------------------------------------
# explain
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("config", type=click.Path(exists=True, path_type=Path))
@click.option("--blocks-dir", "-b", type=click.Path(path_type=Path), default=None)
@click.pass_context
def explain(
    ctx: click.Context,
    config: Path,
    blocks_dir: Path | None,
) -> None:
    """Show what each building block contributes per service. No files written."""
    app_config, errors = load_config(config)
    if errors:
        for e in errors:
            click.echo(f"  error: {e}", err=True)
        ctx.exit(1)
        return

    assert app_config is not None

    try:
        resolved = _find_blocks_dir(config, blocks_dir)
    except FileNotFoundError as exc:
        click.echo(f"error: {exc}", err=True)
        ctx.exit(1)
        return

    click.echo(f"\nApplication: {app_config.app_name}")

    for cat in CATEGORIES:
        entries = getattr(app_config, cat, [])
        if not entries:
            continue
        click.echo(f"\n{cat}/")
        for entry in entries:
            click.echo(f"  {entry.name}")
            for block_name in entry.building_blocks:
                block = _load_block(resolved, cat, block_name)
                if block is None:
                    click.echo(f"    [{block_name}]  (not found)")
                    continue
                meta = block.get(META_KEY, {})
                desc = meta.get("description", "no description")
                impact = meta.get("security_impact", "?")
                escalation = " [escalation]" if meta.get("escalation") else ""
                click.echo(f"    [{block_name}]  {desc.strip()}  (impact: {impact}{escalation})")
            if entry.properties:
                keys = ", ".join(entry.properties.keys())
                click.echo(f"    [properties]  {keys}")
    click.echo("")


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("compose_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--report-format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Security report output format.",
)
def audit(compose_file: Path, report_format: str) -> None:
    """Audit an existing docker-compose.yml and print a security report.

    COMPOSE_FILE may be any Compose YAML — not necessarily generated by csc.
    """
    try:
        with compose_file.open() as fh:
            compose = yaml.safe_load(fh) or {}
    except yaml.YAMLError as exc:
        click.echo(f"  error: YAML parse error: {exc}", err=True)
        sys.exit(1)

    services = compose.get("services", {})
    if not services:
        click.echo("No services found in compose file.")
        return

    reports = build_report(services)
    if report_format == "json":
        click.echo(format_report_json(reports))
    else:
        click.echo(f"Auditing: {compose_file}")
        click.echo(format_report(reports))


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

_IMPACT_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


@cli.command()
@click.argument("config", type=click.Path(exists=True, path_type=Path))
@click.argument("compose_file", type=click.Path(exists=True, path_type=Path))
@click.option("--blocks-dir", "-b", type=click.Path(path_type=Path), default=None)
@click.pass_context
def diff(
    ctx: click.Context,
    config: Path,
    compose_file: Path,
    blocks_dir: Path | None,
) -> None:
    """Compare what csc would generate against an existing COMPOSE_FILE.

    Highlights security regressions (properties in the generated output that
    are absent or weaker in the existing file) and additions.
    """
    from .reporter import _analyse_service  # noqa: PLC0415

    compose, app_config, warnings, errors = generate(config, blocks_dir)
    _emit_issues(warnings, errors, ctx)

    try:
        with compose_file.open() as fh:
            existing = yaml.safe_load(fh) or {}
    except yaml.YAMLError as exc:
        click.echo(f"  error: YAML parse error: {exc}", err=True)
        ctx.exit(1)
        return

    gen_services: dict[str, Any] = compose.get("services", {})
    ext_services: dict[str, Any] = existing.get("services", {})

    if not gen_services:
        click.echo("Generated compose has no services — nothing to diff.")
        return

    # Fields compared in the diff (attribute on ServiceReport → label)
    _BOOL_FIELDS: list[tuple[str, str]] = [
        ("cap_drop_all", "cap_drop: ALL"),
        ("no_new_privileges", "no-new-privileges"),
        ("non_root", "non-root user"),
        ("read_only_fs", "read_only filesystem"),
    ]

    regressions: list[str] = []
    improvements: list[str] = []
    only_generated: list[str] = []
    only_existing: list[str] = []

    all_services = sorted(set(gen_services) | set(ext_services))

    for svc in all_services:
        if svc not in gen_services:
            only_existing.append(svc)
            continue
        if svc not in ext_services:
            only_generated.append(svc)
            continue

        gen_r = _analyse_service(svc, gen_services[svc])
        ext_r = _analyse_service(svc, ext_services[svc])

        for attr, label in _BOOL_FIELDS:
            gen_val: bool = getattr(gen_r, attr)
            ext_val: bool = getattr(ext_r, attr)
            if gen_val and not ext_val:
                regressions.append(f"  [{svc}] missing '{label}' in existing file")
            elif not gen_val and ext_val:
                improvements.append(f"  [{svc}] '{label}' only in existing file")

        gen_impact = _IMPACT_ORDER[gen_r.impact]
        ext_impact = _IMPACT_ORDER[ext_r.impact]
        if ext_impact > gen_impact:
            regressions.append(
                f"  [{svc}] impact regression: generated={gen_r.impact}, existing={ext_r.impact}"
            )
        elif ext_impact < gen_impact:
            improvements.append(
                f"  [{svc}] impact improvement: generated={gen_r.impact}, existing={ext_r.impact}"
            )

    click.echo(f"\nDiff: {config}  →  {compose_file}\n")

    if only_generated:
        click.echo("Services only in generated output (missing from existing file):")
        for s in only_generated:
            click.echo(f"  + {s}")
        click.echo("")

    if only_existing:
        click.echo("Services only in existing file (not in generated output):")
        for s in only_existing:
            click.echo(f"  - {s}")
        click.echo("")

    if regressions:
        click.echo("Security regressions in existing file vs. generated:")
        for line in regressions:
            click.echo(line)
        click.echo("")
    else:
        click.echo("No security regressions detected.")

    if improvements:
        click.echo("Differences (existing more restrictive than generated):")
        for line in improvements:
            click.echo(line)
        click.echo("")

    if regressions:
        ctx.exit(1)
