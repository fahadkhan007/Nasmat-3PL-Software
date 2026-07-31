"""
rider_parser.py
---------------
Parses نس.pdf (master roster) and rider_names.json (pre-extracted short names
from the final report) to build a complete rider_id → name lookup dictionary.

Lookup priority:
  1. rider_names.json  (exact short names from the approved report)
  2. نس.pdf            (full names, for any new riders not yet in the JSON)
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import pdfplumber

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
MASTER_PDF = BASE_DIR / "نس.pdf"
NAMES_JSON = BASE_DIR / "rider_names.json"

# Matches 6- or 7-digit rider IDs.
# Deliberately excludes 10-digit phone numbers (e.g. 2xxxxxxxxx).
_RIDER_ID_RE = re.compile(r"\b(\d{6,7})\b")
_PHONE_RE = re.compile(r"\b(2\d{9})\b")
_ROW_NUM_RE = re.compile(r"\s+\d{1,3}\s*$")


# ── Public API ─────────────────────────────────────────────────────────────────

def build_rider_lookup() -> dict[str, str]:
    """
    Return a dict mapping rider_id (str) → name (str).

    Short names from rider_names.json take priority over full names
    from the master PDF so the output always matches the approved report format.

    Raises:
        FileNotFoundError: if نس.pdf does not exist.
        RuntimeError:      if fewer than 10 riders are extracted (likely corrupt PDF).
    """
    master = _parse_master_pdf(MASTER_PDF)
    short = _load_names_json(NAMES_JSON)

    # Merge: master first (base), then override with verified short names
    lookup = {**master, **short}

    if len(lookup) < 10:
        raise RuntimeError(
            f"Rider lookup has only {len(lookup)} entries — PDF may be corrupt."
        )

    logger.info("Rider lookup built: %d entries (%d from JSON, %d from PDF)",
                len(lookup), len(short), len(master))
    return lookup


# ── Internal helpers ───────────────────────────────────────────────────────────

def _parse_master_pdf(path: Path) -> dict[str, str]:
    """
    Parse نس.pdf and return {rider_id: full_name}.

    Line format (RTL, extracted left-to-right by pdfplumber):
        <status...> <rider_id> نشيتسرقنه <city> <phone> <name...> <row_num>
    """
    if not path.exists():
        raise FileNotFoundError(f"Master PDF not found: {path}")

    rider_map: dict[str, str] = {}

    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue

                ids = _RIDER_ID_RE.findall(line)
                if not ids:
                    continue

                phone_match = _PHONE_RE.search(line)
                if not phone_match:
                    continue

                # Name appears AFTER the phone number, before trailing row number
                name_raw = line[phone_match.end():].strip()
                name_raw = _ROW_NUM_RE.sub("", name_raw).strip()

                # Rider ID: a 6-7 digit number that is NOT the phone number
                phone_digits = phone_match.group(1)
                for rid in ids:
                    if rid != phone_digits:
                        if name_raw:
                            rider_map[rid] = name_raw
                        break

    logger.debug("Parsed %d riders from master PDF", len(rider_map))
    return rider_map


def _load_names_json(path: Path) -> dict[str, str]:
    """Load pre-extracted short names from rider_names.json."""
    if not path.exists():
        logger.warning("rider_names.json not found — using full names only")
        return {}

    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("rider_names.json must be a JSON object {id: name}")

    return {str(k): str(v) for k, v in data.items()}
