"""Tests for csc.reporter."""
from __future__ import annotations

import json

import pytest

from csc.reporter import (
    ServiceReport,
    _analyse_service,
    _service_col_width,
    build_report,
    format_report,
    format_report_json,
)


# ---------------------------------------------------------------------------
# _analyse_service
# ---------------------------------------------------------------------------


class TestAnalyseService:
    def test_standard_block_service(self):
        cfg = {
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
            "user": "nobody",
        }
        r = _analyse_service("svc", cfg)
        assert r.cap_drop_all is True
        assert r.no_new_privileges is True
        assert r.non_root is True
        assert r.read_only_fs is False
        assert r.privileged is False

    def test_read_only_detected(self):
        r = _analyse_service("svc", {"read_only": True})
        assert r.read_only_fs is True

    def test_host_network_detected(self):
        r = _analyse_service("svc", {"network_mode": "host"})
        assert r.host_network is True

    def test_privileged_detected(self):
        r = _analyse_service("svc", {"privileged": True})
        assert r.privileged is True

    def test_cap_add_collected(self):
        r = _analyse_service("svc", {"cap_add": ["NET_ADMIN", "CHOWN"]})
        assert "NET_ADMIN" in r.cap_add
        assert "CHOWN" in r.cap_add

    def test_cap_drop_all_case_insensitive(self):
        r = _analyse_service("svc", {"cap_drop": ["all"]})
        assert r.cap_drop_all is True

    def test_root_user_detected(self):
        r = _analyse_service("svc", {"user": "root"})
        assert r.non_root is False

    def test_numeric_root_uid(self):
        r = _analyse_service("svc", {"user": "0"})
        assert r.non_root is False

    def test_empty_config(self):
        r = _analyse_service("svc", {})
        assert r.cap_drop_all is False
        assert r.non_root is False


# ---------------------------------------------------------------------------
# ServiceReport.impact
# ---------------------------------------------------------------------------


class TestImpact:
    def _report(
        self,
        cap_drop_all: bool = True,
        no_new_privileges: bool = True,
        non_root: bool = True,
        host_network: bool = False,
        privileged: bool = False,
        cap_add: list[str] | None = None,
    ) -> ServiceReport:
        return ServiceReport(
            name="x",
            cap_drop_all=cap_drop_all,
            no_new_privileges=no_new_privileges,
            non_root=non_root,
            host_network=host_network,
            privileged=privileged,
            cap_add=cap_add or [],
        )

    def test_low_impact(self):
        assert self._report().impact == "low"

    def test_medium_impact_missing_cap_drop(self):
        assert self._report(cap_drop_all=False).impact == "medium"

    def test_medium_impact_missing_no_new_priv(self):
        assert self._report(no_new_privileges=False).impact == "medium"

    def test_medium_impact_root_user(self):
        assert self._report(non_root=False).impact == "medium"

    def test_high_impact_host_network(self):
        assert self._report(host_network=True).impact == "high"

    def test_high_impact_cap_add(self):
        assert self._report(cap_add=["NET_ADMIN"]).impact == "high"

    def test_critical_privileged(self):
        assert self._report(privileged=True).impact == "critical"


# ---------------------------------------------------------------------------
# ServiceReport.notes
# ---------------------------------------------------------------------------


class TestNotes:
    def test_no_escalations_empty_notes(self):
        r = ServiceReport(name="x")
        assert r.notes == ""

    def test_host_network_in_notes(self):
        r = ServiceReport(name="x", host_network=True)
        assert "host-network" in r.notes

    def test_cap_add_in_notes(self):
        r = ServiceReport(name="x", cap_add=["NET_ADMIN"])
        assert "NET_ADMIN" in r.notes

    def test_privileged_in_notes(self):
        r = ServiceReport(name="x", privileged=True)
        assert "privileged" in r.notes


# ---------------------------------------------------------------------------
# build_report
# ---------------------------------------------------------------------------


class TestBuildReport:
    def test_sorted_by_impact_then_name(self):
        services = {
            "safe": {"cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"], "user": "nobody"},
            "risky": {"privileged": True},
            "medium": {},
        }
        reports = build_report(services)
        impacts = [r.impact for r in reports]
        # critical before medium before low
        assert impacts.index("critical") < impacts.index("medium")
        assert impacts.index("medium") < impacts.index("low")

    def test_empty_services(self):
        assert build_report({}) == []


# ---------------------------------------------------------------------------
# format_report
# ---------------------------------------------------------------------------


class TestFormatReport:
    def test_header_present(self):
        text = format_report([ServiceReport(name="svc")])
        assert "Security report" in text
        assert "cap_drop" in text
        assert "impact" in text

    def test_service_name_in_output(self):
        text = format_report([ServiceReport(name="myservice")])
        assert "myservice" in text

    def test_long_service_name_fits(self):
        """A service name longer than 16 chars must not truncate."""
        long_name = "a-very-long-service-name"
        text = format_report([ServiceReport(name=long_name)])
        assert long_name in text

    def test_impact_label_uppercase_for_high(self):
        r = ServiceReport(name="x", host_network=True)
        text = format_report([r])
        assert "HIGH" in text

    def test_impact_label_uppercase_for_critical(self):
        r = ServiceReport(name="x", privileged=True)
        text = format_report([r])
        assert "CRITICAL" in text


# ---------------------------------------------------------------------------
# format_report_json
# ---------------------------------------------------------------------------


class TestFormatReportJson:
    def test_valid_json(self):
        reports = [ServiceReport(name="svc", cap_drop_all=True)]
        result = format_report_json(reports)
        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert parsed[0]["name"] == "svc"

    def test_impact_and_notes_included(self):
        r = ServiceReport(name="x", privileged=True)
        parsed = json.loads(format_report_json([r]))
        assert parsed[0]["impact"] == "critical"
        assert "privileged" in parsed[0]["notes"]

    def test_empty_reports(self):
        result = format_report_json([])
        assert json.loads(result) == []


# ---------------------------------------------------------------------------
# _service_col_width
# ---------------------------------------------------------------------------


class TestServiceColWidth:
    def test_empty_reports_returns_minimum(self):
        """Empty list must return _MIN_SERVICE_COL without crashing (line 94)."""
        from csc.reporter import _MIN_SERVICE_COL
        assert _service_col_width([]) == _MIN_SERVICE_COL

    def test_short_name_uses_minimum(self):
        from csc.reporter import _MIN_SERVICE_COL
        reports = [ServiceReport(name="web")]
        assert _service_col_width(reports) == _MIN_SERVICE_COL

    def test_long_name_expands_column(self):
        long_name = "a" * 30
        reports = [ServiceReport(name=long_name)]
        assert _service_col_width(reports) == len(long_name) + 2
