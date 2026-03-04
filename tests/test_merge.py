"""Tests for csc.generator._merge()."""
from __future__ import annotations

import pytest

from csc.generator import _merge


class TestMergeListDedup:
    def test_new_key_is_added(self):
        dest: dict = {}
        _merge({"cap_drop": ["ALL"]}, dest)
        assert dest == {"cap_drop": ["ALL"]}

    def test_list_items_appended_without_duplicates(self):
        dest = {"cap_drop": ["ALL"]}
        _merge({"cap_drop": ["ALL", "NET_ADMIN"]}, dest)
        assert dest["cap_drop"] == ["ALL", "NET_ADMIN"]

    def test_list_no_duplicates_added(self):
        dest = {"ports": ["80:80"]}
        _merge({"ports": ["80:80"]}, dest)
        assert dest["ports"] == ["80:80"]  # no duplicate


class TestMergeScalars:
    def test_no_override_keeps_dest(self):
        dest = {"user": "nobody"}
        warnings = _merge({"user": "root"}, dest, override=False)
        assert dest["user"] == "nobody"
        assert any("user" in w for w in warnings)

    def test_override_replaces_dest(self):
        dest = {"user": "nobody"}
        warnings = _merge({"user": "root"}, dest, override=True)
        assert dest["user"] == "root"
        assert warnings == []

    def test_identical_value_no_warning(self):
        dest = {"restart": "always"}
        warnings = _merge({"restart": "always"}, dest, override=False)
        assert warnings == []


class TestMergeMetaStripped:
    def test_meta_key_not_copied(self):
        dest: dict = {}
        _merge({"_meta": {"description": "x"}, "user": "nobody"}, dest)
        assert "_meta" not in dest
        assert dest["user"] == "nobody"


class TestMergeNestedDict:
    def test_nested_dict_merged(self):
        dest: dict = {"deploy": {"resources": {"limits": {"memory": "128m"}}}}
        src = {"deploy": {"resources": {"limits": {"cpus": "0.5"}}}}
        _merge(src, dest)
        assert dest["deploy"]["resources"]["limits"] == {"memory": "128m", "cpus": "0.5"}

    def test_nested_dict_override_replaces_leaf_scalar(self):
        dest = {"deploy": {"resources": {"limits": {"memory": "128m"}}}}
        src = {"deploy": {"resources": {"limits": {"memory": "256m"}}}}
        _merge(src, dest, override=True)
        assert dest["deploy"]["resources"]["limits"]["memory"] == "256m"

    def test_nested_dict_no_override_keeps_leaf(self):
        dest = {"deploy": {"resources": {"limits": {"memory": "128m"}}}}
        src = {"deploy": {"resources": {"limits": {"memory": "256m"}}}}
        warnings = _merge(src, dest, override=False)
        assert dest["deploy"]["resources"]["limits"]["memory"] == "128m"
        assert any("memory" in w for w in warnings)
