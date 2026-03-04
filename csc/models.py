from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ConfigEntry(BaseModel):
    """A single service, network, or volume entry in the application config."""

    name: str
    building_blocks: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)


class AppConfig(BaseModel):
    """Top-level application configuration."""

    app_name: str
    version: str | None = None
    services: list[ConfigEntry] = Field(default_factory=list)
    networks: list[ConfigEntry] = Field(default_factory=list)
    volumes: list[ConfigEntry] = Field(default_factory=list)


ImpactLevel = Literal["low", "medium", "high", "critical"]


class BlockMeta(BaseModel):
    """Schema for the ``_meta`` section of a building block file."""

    name: str | None = None
    description: str | None = None
    security_impact: ImpactLevel = "low"
    escalation: bool = False
    incompatible_with: list[str] = Field(default_factory=list)
