"""Security report: analyse a generated Docker Compose service map."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Security property checks
# ---------------------------------------------------------------------------

_ICONS = {True: "yes", False: "no", None: "-"}


@dataclass
class ServiceReport:
    name: str
    cap_drop_all: bool = False
    no_new_privileges: bool = False
    non_root: bool = False
    read_only_fs: bool = False
    host_network: bool = False
    privileged: bool = False
    cap_add: list[str] = field(default_factory=list)

    @property
    def impact(self) -> str:
        if self.privileged:
            return "critical"
        if self.host_network or self.cap_add:
            return "high"
        if not (self.cap_drop_all and self.no_new_privileges and self.non_root):
            return "medium"
        return "low"

    @property
    def notes(self) -> str:
        parts: list[str] = []
        if self.host_network:
            parts.append("host-network")
        if self.privileged:
            parts.append("privileged mode")
        if self.cap_add:
            parts.append(f"cap_add: {', '.join(self.cap_add)}")
        return "; ".join(parts)


def _analyse_service(name: str, cfg: dict[str, Any]) -> ServiceReport:
    cap_drop = cfg.get("cap_drop", [])
    security_opt = cfg.get("security_opt", [])
    user = str(cfg.get("user", "root"))

    return ServiceReport(
        name=name,
        cap_drop_all="ALL" in [str(c).upper() for c in cap_drop],
        no_new_privileges=any(
            "no-new-privileges" in str(opt) for opt in security_opt
        ),
        non_root=user not in ("root", "0", ""),
        read_only_fs=bool(cfg.get("read_only", False)),
        host_network=cfg.get("network_mode") == "host",
        privileged=bool(cfg.get("privileged", False)),
        cap_add=list(cfg.get("cap_add", [])),
    )


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

_IMPACT_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

_IMPACT_LABEL = {
    "low": "low",
    "medium": "medium",
    "high": "HIGH",
    "critical": "CRITICAL",
}

_COL_WIDTHS = {
    "service": 16,
    "cap_drop_all": 11,
    "no_new_priv": 13,
    "non_root": 11,
    "read_only": 11,
    "impact": 10,
    "notes": 0,  # fills remainder
}


def _row(r: ServiceReport) -> str:
    return (
        f"  {r.name:<{_COL_WIDTHS['service']}}"
        f"{_ICONS[r.cap_drop_all]:<{_COL_WIDTHS['cap_drop_all']}}"
        f"{_ICONS[r.no_new_privileges]:<{_COL_WIDTHS['no_new_priv']}}"
        f"{_ICONS[r.non_root]:<{_COL_WIDTHS['non_root']}}"
        f"{_ICONS[r.read_only_fs]:<{_COL_WIDTHS['read_only']}}"
        f"{_IMPACT_LABEL[r.impact]:<{_COL_WIDTHS['impact']}}"
        f"{r.notes}"
    )


def _header() -> str:
    return (
        f"  {'Service':<{_COL_WIDTHS['service']}}"
        f"{'cap_drop':<{_COL_WIDTHS['cap_drop_all']}}"
        f"{'no-new-priv':<{_COL_WIDTHS['no_new_priv']}}"
        f"{'non-root':<{_COL_WIDTHS['non_root']}}"
        f"{'read-only':<{_COL_WIDTHS['read_only']}}"
        f"{'impact':<{_COL_WIDTHS['impact']}}"
        f"notes"
    )


def _separator() -> str:
    total = sum(_COL_WIDTHS[k] for k in _COL_WIDTHS) + _COL_WIDTHS["service"] + 20
    return "  " + "-" * total


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_report(services: dict[str, Any]) -> list[ServiceReport]:
    return sorted(
        [_analyse_service(name, cfg) for name, cfg in services.items()],
        key=lambda r: (_IMPACT_ORDER[r.impact], r.name),
    )


def format_report(reports: list[ServiceReport]) -> str:
    lines = [
        "",
        "Security report",
        "---------------",
        _header(),
        _separator(),
    ]
    for r in reports:
        lines.append(_row(r))
    lines.append("")
    return "\n".join(lines)
