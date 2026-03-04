"""CLI entry point for container-secure-compose."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import click
import yaml

from . import __version__
from .generator import generate, load_config, write_compose, _find_blocks_dir, _load_block, CATEGORIES, META_KEY
from .reporter import build_report, format_report


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
@click.pass_context
def generate_cmd(
    ctx: click.Context,
    config: Path,
    output: Optional[Path],
    blocks_dir: Optional[Path],
    no_report: bool,
) -> None:
    """Generate a docker-compose.yml from CONFIG."""
    compose, warnings, errors = generate(config, blocks_dir)
    _emit_issues(warnings, errors, ctx)

    app_config, _ = load_config(config)
    app_name = app_config.app_name if app_config else "output"

    dest = output or Path("output") / app_name / "docker-compose.yml"
    write_compose(compose, dest, source_config=config)
    click.echo(f"Generated: {dest}")

    if not no_report and "services" in compose:
        reports = build_report(compose["services"])
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
    blocks_dir: Optional[Path],
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
def list_blocks(blocks_dir: Optional[Path], category: Optional[str]) -> None:
    """List all available building blocks."""
    try:
        resolved = _find_blocks_dir(Path.cwd() / "dummy.yaml", blocks_dir)
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
    blocks_dir: Optional[Path],
) -> None:
    """Show what each building block contributes per service. No files written."""
    app_config, errors = load_config(config)
    if errors:
        for e in errors:
            click.echo(f"  error: {e}", err=True)
        ctx.exit(1)
        return

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
