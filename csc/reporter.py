"""Security report: analyse a generated Docker Compose service map."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
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

_FIXED_WIDTHS = {
    "cap_drop_all": 11,
    "no_new_priv": 13,
    "non_root": 11,
    "read_only": 11,
    "impact": 10,
}
_MIN_SERVICE_COL = 16


def _service_col_width(reports: list[ServiceReport]) -> int:
    """Compute service column width dynamically to fit the longest name."""
    if not reports:
        return _MIN_SERVICE_COL
    return max(_MIN_SERVICE_COL, max(len(r.name) for r in reports) + 2)


def _row(r: ServiceReport, svc_width: int) -> str:
    return (
        f"  {r.name:<{svc_width}}"
        f"{_ICONS[r.cap_drop_all]:<{_FIXED_WIDTHS['cap_drop_all']}}"
        f"{_ICONS[r.no_new_privileges]:<{_FIXED_WIDTHS['no_new_priv']}}"
        f"{_ICONS[r.non_root]:<{_FIXED_WIDTHS['non_root']}}"
        f"{_ICONS[r.read_only_fs]:<{_FIXED_WIDTHS['read_only']}}"
        f"{_IMPACT_LABEL[r.impact]:<{_FIXED_WIDTHS['impact']}}"
        f"{r.notes}"
    )


def _header(svc_width: int) -> str:
    return (
        f"  {'Service':<{svc_width}}"
        f"{'cap_drop':<{_FIXED_WIDTHS['cap_drop_all']}}"
        f"{'no-new-priv':<{_FIXED_WIDTHS['no_new_priv']}}"
        f"{'non-root':<{_FIXED_WIDTHS['non_root']}}"
        f"{'read-only':<{_FIXED_WIDTHS['read_only']}}"
        f"{'impact':<{_FIXED_WIDTHS['impact']}}"
        f"notes"
    )


def _separator(svc_width: int) -> str:
    total = svc_width + sum(_FIXED_WIDTHS.values()) + 20
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
    svc_width = _service_col_width(reports)
    lines = [
        "",
        "Security report",
        "---------------",
        _header(svc_width),
        _separator(svc_width),
    ]
    for r in reports:
        lines.append(_row(r, svc_width))
    lines.append("")
    return "\n".join(lines)


def format_report_json(reports: list[ServiceReport]) -> str:
    """Return the security report as a JSON string."""
    rows = []
    for r in reports:
        d = asdict(r)
        d["impact"] = r.impact
        d["notes"] = r.notes
        rows.append(d)
    return json.dumps(rows, indent=2)
