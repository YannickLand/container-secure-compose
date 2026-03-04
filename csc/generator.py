from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import ValidationError

from .models import AppConfig

CATEGORIES = ("services", "networks", "volumes")
META_KEY = "_meta"
BLOCKS_DIR_NAME = "building_blocks"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_blocks_dir(config_path: Path, blocks_dir: Optional[Path]) -> Path:
    """Resolve the building-blocks directory.

    Search order:
    1. Explicit --blocks-dir argument.
    2. building_blocks/ next to the config file.
    3. building_blocks/ in the current working directory.
    """
    if blocks_dir:
        resolved = Path(blocks_dir)
        if not resolved.is_dir():
            raise FileNotFoundError(f"--blocks-dir '{resolved}' does not exist.")
        return resolved

    for candidate in [
        config_path.parent / BLOCKS_DIR_NAME,
        Path.cwd() / BLOCKS_DIR_NAME,
    ]:
        if candidate.is_dir():
            return candidate

    raise FileNotFoundError(
        f"Could not find '{BLOCKS_DIR_NAME}/' directory. "
        "Use --blocks-dir to specify its location."
    )


def _load_block(blocks_dir: Path, category: str, name: str) -> Optional[dict]:
    """Load a building block YAML file; return None if not found."""
    path = blocks_dir / category / f"{name}.yaml"
    if not path.is_file():
        return None
    with path.open() as fh:
        return yaml.safe_load(fh) or {}


def _merge(source: dict, dest: dict, override: bool = False) -> list[str]:
    """Merge *source* into *dest* in-place.

    For list values: append items not already present.
    For scalar values:
      - override=True  → source value replaces dest value (used for explicit properties).
      - override=False → keep dest value, emit a warning (used for block-to-block merges).

    Returns a list of warning strings.
    """
    warnings: list[str] = []
    for key, value in source.items():
        if key == META_KEY:
            continue  # strip metadata
        if key not in dest:
            dest[key] = value
        elif isinstance(dest[key], list) and isinstance(value, list):
            for item in value:
                if item not in dest[key]:
                    dest[key].append(item)
        elif dest[key] == value:
            pass  # identical values, no action needed
        elif override:
            dest[key] = value
        else:
            warnings.append(
                f"scalar collision on '{key}': "
                f"keeping '{dest[key]}', ignoring '{value}'"
            )
    return warnings


def _check_incompatibilities(
    block_name: str,
    block_meta: dict,
    all_blocks: list[str],
) -> list[str]:
    """Return warning strings for any incompatible block pairings."""
    warnings: list[str] = []
    for incompatible in block_meta.get("incompatible_with", []):
        if incompatible in all_blocks:
            warnings.append(
                f"building block '{block_name}' declares itself incompatible "
                f"with '{incompatible}'"
            )
    return warnings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(config_path: Path) -> tuple[Optional[AppConfig], list[str]]:
    """Parse and validate an application config file.

    Returns (config, errors).  config is None when errors are non-empty.
    """
    try:
        with config_path.open() as fh:
            raw = yaml.safe_load(fh)
        return AppConfig.model_validate(raw), []
    except FileNotFoundError:
        return None, [f"Config file not found: '{config_path}'"]
    except yaml.YAMLError as exc:
        return None, [f"YAML parse error: {exc}"]
    except ValidationError as exc:
        return None, [f"Config validation error:\n{exc}"]


def generate(
    config_path: Path,
    blocks_dir: Optional[Path] = None,
) -> tuple[dict, list[str], list[str]]:
    """Generate a Docker Compose dict from a CSC application config.

    Returns:
        (compose_dict, warnings, errors)
        compose_dict is empty when errors are non-empty.
    """
    warnings: list[str] = []
    errors: list[str] = []

    config, load_errors = load_config(config_path)
    if load_errors:
        return {}, warnings, load_errors

    try:
        resolved_blocks_dir = _find_blocks_dir(config_path, blocks_dir)
    except FileNotFoundError as exc:
        return {}, warnings, [str(exc)]

    compose: dict = {}

    for category in CATEGORIES:
        entries = getattr(config, category, [])
        if not entries:
            continue

        compose[category] = {}
        seen: set[str] = set()

        for entry in entries:
            if entry.name in seen:
                warnings.append(
                    f"Duplicate {category[:-1]} name '{entry.name}' — skipping."
                )
                continue
            seen.add(entry.name)

            entry_cfg: dict = {}

            for block_name in entry.building_blocks:
                block = _load_block(resolved_blocks_dir, category, block_name)
                if block is None:
                    warnings.append(
                        f"[{entry.name}] Building block '{block_name}' not found "
                        f"in {resolved_blocks_dir / category}/ — skipped."
                    )
                    continue

                meta = block.get(META_KEY, {})
                for w in _check_incompatibilities(
                    block_name, meta, entry.building_blocks
                ):
                    warnings.append(f"[{entry.name}] {w}")

                for w in _merge(block, entry_cfg, override=False):
                    warnings.append(f"[{entry.name}] block '{block_name}': {w}")

            # Explicit properties override building block defaults
            if entry.properties:
                for w in _merge(entry.properties, entry_cfg, override=True):
                    warnings.append(f"[{entry.name}] properties: {w}")

            compose[category][entry.name] = entry_cfg

    # Build ordered output: version → services → networks → volumes
    ordered: dict = {}
    if config.version:
        ordered["version"] = config.version
    for key in ("services", "networks", "volumes"):
        if key in compose:
            ordered[key] = compose[key]

    return ordered, warnings, errors


def _make_dumper() -> type:
    """Return a PyYAML Dumper that indents list items consistently."""

    class _IndentedDumper(yaml.Dumper):
        def increase_indent(self, flow=False, indentless=False):
            return super().increase_indent(flow=flow, indentless=False)

    return _IndentedDumper


def write_compose(
    compose: dict,
    output_path: Path,
    source_config: Optional[Path] = None,
) -> None:
    """Write a compose dict to a YAML file, preceded by a header comment."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    header_lines = [
        "# Generated by container-secure-compose",
    ]
    if source_config is not None:
        header_lines.append(f"# Source: {source_config}")
    header_lines += [
        "#",
        "# Do not edit this file directly. Regenerate with:",
        f"#   csc generate {source_config or '<config>'}",
        "",
    ]
    header = "\n".join(header_lines) + "\n"

    body = yaml.dump(
        compose,
        default_flow_style=False,
        sort_keys=False,
        indent=2,
        Dumper=_make_dumper(),
    )

    with output_path.open("w") as fh:
        fh.write(header)
        fh.write(body)
