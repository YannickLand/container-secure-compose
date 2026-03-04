"""Shared fixtures for container-secure-compose tests."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Paths into the test workspace
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent.parent
BLOCKS_DIR = ROOT / "building_blocks"
EXAMPLE_CONFIG = ROOT / "examples" / "ping-tracker" / "app_config.yaml"


@pytest.fixture()
def blocks_dir() -> Path:
    """Real building_blocks/ directory from the project root."""
    return BLOCKS_DIR


@pytest.fixture()
def example_config() -> Path:
    """Real ping-tracker app_config.yaml."""
    return EXAMPLE_CONFIG


# ---------------------------------------------------------------------------
# Helpers to create temporary configs / blocks
# ---------------------------------------------------------------------------


def write_yaml(path: Path, data: object) -> Path:
    """Write *data* as YAML to *path* and return *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        yaml.safe_dump(data, fh)
    return path


@pytest.fixture()
def tmp_app_config(tmp_path: Path):
    """Factory: call with a raw dict to get a temporary config Path."""

    def _factory(data: dict) -> Path:
        return write_yaml(tmp_path / "app_config.yaml", data)

    return _factory


@pytest.fixture()
def tmp_blocks(tmp_path: Path):
    """Factory: create a minimal building_blocks/ tree in tmp_path.

    Returns (blocks_dir, write_block) where write_block(category, name, data)
    drops a .yaml file into the appropriate category sub-directory.
    """
    bd = tmp_path / "building_blocks"
    bd.mkdir(parents=True, exist_ok=True)

    def _write(category: str, name: str, data: dict) -> Path:
        return write_yaml(bd / category / f"{name}.yaml", data)

    return bd, _write
