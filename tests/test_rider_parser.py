"""
test_rider_parser.py
--------------------
Tests for core/rider_parser.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.rider_parser import build_rider_lookup, _load_names_json, NAMES_JSON

# All 54 rider IDs that appear in the sample CSV
EXPECTED_IDS = {
    "4709799", "4755316", "2263271", "1992968", "4708653",
    "3498086", "4709687", "4764075", "4709004", "4787594",
    "1415555", "560936",  "4762042", "4755090", "4713319",
    "4709983", "4731150", "4763080", "4710069", "4720151",
    "2599508", "1970411", "4711773", "4713967", "4709367",
    "4765348", "4718027", "4754922", "1155879", "4709141",
    "4540734", "4715629", "2522864", "2522853", "4729398",
    "2163868", "4479913", "4751287", "4758971", "4709297",
    "2821411", "4233904", "4712171", "2419500", "4760747",
    "4712134", "4749087", "2432283", "4714902", "4765751",
    "4747188", "4712210", "4779470", "4709983",
}


class TestLoadNamesJson:
    def test_returns_dict(self):
        result = _load_names_json(NAMES_JSON)
        assert isinstance(result, dict)

    def test_non_empty(self):
        result = _load_names_json(NAMES_JSON)
        assert len(result) >= 54, f"Expected ≥54 entries, got {len(result)}"

    def test_six_digit_id_present(self):
        result = _load_names_json(NAMES_JSON)
        assert "560936" in result, "6-digit rider ID 560936 must be present"

    def test_all_names_non_empty(self):
        result = _load_names_json(NAMES_JSON)
        for rid, name in result.items():
            assert name.strip(), f"Empty name for rider {rid}"

    def test_all_keys_are_strings(self):
        result = _load_names_json(NAMES_JSON)
        for k, v in result.items():
            assert isinstance(k, str)
            assert isinstance(v, str)

    def test_arabic_names_present(self):
        result = _load_names_json(NAMES_JSON)
        arabic_names = [v for v in result.values() if any(ord(c) > 0x600 for c in v)]
        assert len(arabic_names) >= 50, "Expected mostly Arabic names"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            _load_names_json(tmp_path / "missing.json")


class TestBuildRiderLookup:
    def test_returns_dict(self):
        assert isinstance(build_rider_lookup(), dict)

    def test_covers_all_54_csv_ids(self):
        lookup = build_rider_lookup()
        for rid in EXPECTED_IDS:
            assert rid in lookup, f"Rider {rid} missing from lookup"

    def test_minimum_entry_count(self):
        assert len(build_rider_lookup()) >= 54

    def test_all_names_non_empty(self):
        for rid, name in build_rider_lookup().items():
            assert name.strip(), f"Empty name for rider {rid}"
