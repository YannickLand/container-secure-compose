from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .models import AppConfig, BlockMeta

CATEGORIES = ("services", "networks", "volumes")
META_KEY = "_meta"
BLOCKS_DIR_NAME = "building_blocks"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_blocks_dir(config_path: Path | None, blocks_dir: Path | None) -> Path:
    """Resolve the building-blocks directory.

    Search order:
    1. Explicit --blocks-dir argument.
    2. building_blocks/ next to the config file (when config_path is given).
    3. building_blocks/ in the current working directory.
    """
    if blocks_dir:
        resolved = Path(blocks_dir)
        if not resolved.is_dir():
            raise FileNotFoundError(f"--blocks-dir '{resolved}' does not exist.")
        return resolved

    candidates: list[Path] = []
    if config_path is not None:
        candidates.append(config_path.parent / BLOCKS_DIR_NAME)
    candidates.append(Path.cwd() / BLOCKS_DIR_NAME)

    for candidate in candidates:
        if candidate.is_dir():
            return candidate

    raise FileNotFoundError(
        f"Could not find '{BLOCKS_DIR_NAME}/' directory. "
        "Use --blocks-dir to specify its location."
    )


def _validate_block_meta(
    block_name: str, raw_meta: dict[str, Any]
) -> tuple[BlockMeta, list[str]]:
    """Parse and validate the ``_meta`` section of a building block.

    Returns ``(meta, warnings)``.  On validation failure a default ``BlockMeta``
    is returned along with warning messages so generation can continue.
    """
    from pydantic import ValidationError as _VE

    try:
        return BlockMeta.model_validate(raw_meta), []
    except _VE as exc:
        return BlockMeta(), [f"building block '{block_name}' has invalid _meta: {exc}"]


def _load_block(blocks_dir: Path, category: str, name: str) -> dict[str, Any] | None:
    """Load a building block YAML file; return None if not found."""
    path = blocks_dir / category / f"{name}.yaml"
    if not path.is_file():
        return None
    with path.open() as fh:
        return yaml.safe_load(fh) or {}


def _merge(source: dict[str, Any], dest: dict[str, Any], override: bool = False) -> list[str]:
    """Merge *source* into *dest* in-place.

    For list values: append items not already present.
    For dict values: recurse (override applies to leaf scalars).
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
        elif isinstance(dest[key], dict) and isinstance(value, dict):
            child_warnings = _merge(value, dest[key], override=override)
            warnings.extend(child_warnings)
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
    all_blocks: list[str], metas: dict[str, BlockMeta]
) -> list[str]:
    """Return warning strings for any incompatible block pairings.

    Checks both directions: if A declares incompatibility with B, a warning is
    emitted regardless of whether B also declares incompatibility with A.
    Already-reported pairs are deduplicated.
    """
    warnings: list[str] = []
    reported: set[frozenset[str]] = set()
    for block_name, meta in metas.items():
        for incompatible in meta.incompatible_with:
            if incompatible in all_blocks:
                pair: frozenset[str] = frozenset({block_name, incompatible})
                if pair not in reported:
                    reported.add(pair)
                    warnings.append(
                        f"building block '{block_name}' declares itself incompatible "
                        f"with '{incompatible}'"
                    )
    return warnings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(config_path: Path) -> tuple[AppConfig | None, list[str]]:
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
    blocks_dir: Path | None = None,
) -> tuple[dict[str, Any], AppConfig | None, list[str], list[str]]:
    """Generate a Docker Compose dict from a CSC application config.

    Returns:
        (compose_dict, app_config, warnings, errors)
        compose_dict is empty and app_config is None when errors are non-empty.
    """
    warnings: list[str] = []
    errors: list[str] = []

    config, load_errors = load_config(config_path)
    if load_errors:
        return {}, None, warnings, load_errors

    assert config is not None

    if config.version is not None:
        warnings.append(
            "The top-level 'version' key is deprecated in Compose v2+ and will be "
            "ignored by modern Docker Compose. Consider removing it from your config."
        )

    try:
        resolved_blocks_dir = _find_blocks_dir(config_path, blocks_dir)
    except FileNotFoundError as exc:
        return {}, None, warnings, [str(exc)]

    compose: dict[str, Any] = {}

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

            entry_cfg: dict[str, Any] = {}
            loaded_metas: dict[str, BlockMeta] = {}

            for block_name in entry.building_blocks:
                block = _load_block(resolved_blocks_dir, category, block_name)
                if block is None:
                    warnings.append(
                        f"[{entry.name}] Building block '{block_name}' not found "
                        f"in {resolved_blocks_dir / category}/ — skipped."
                    )
                    continue

                raw_meta = block.get(META_KEY, {})
                meta, meta_warnings = _validate_block_meta(block_name, raw_meta)
                for w in meta_warnings:
                    warnings.append(f"[{entry.name}] {w}")
                loaded_metas[block_name] = meta

                for w in _merge(block, entry_cfg, override=False):
                    warnings.append(f"[{entry.name}] block '{block_name}': {w}")

            # Bidirectional incompatibility check across all loaded blocks
            for w in _check_incompatibilities(entry.building_blocks, loaded_metas):
                warnings.append(f"[{entry.name}] {w}")

            # Explicit properties override building block defaults
            if entry.properties:
                for w in _merge(entry.properties, entry_cfg, override=True):
                    warnings.append(f"[{entry.name}] properties: {w}")

            compose[category][entry.name] = entry_cfg

    # Build ordered output: version → services → networks → volumes
    ordered: dict[str, Any] = {}
    if config.version:
        ordered["version"] = config.version
    for key in ("services", "networks", "volumes"):
        if key in compose:
            ordered[key] = compose[key]

    return ordered, config, warnings, errors


def _make_dumper() -> type[yaml.Dumper]:
    """Return a PyYAML Dumper that indents list items consistently."""

    class _IndentedDumper(yaml.Dumper):
        def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
            return super().increase_indent(flow=flow, indentless=False)

    return _IndentedDumper


def write_compose(
    compose: dict[str, Any],
    output_path: Path,
    source_config: Path | None = None,
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


def compose_to_yaml_string(
    compose: dict[str, Any],
    source_config: Path | None = None,
) -> str:
    """Return the compose YAML as a string (with header comment), without writing to disk."""
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
    return header + body
