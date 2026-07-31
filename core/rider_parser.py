"""
rider_parser.py
---------------
Loads the verified rider_id → Arabic name mapping from rider_names.json.

rider_names.json is the single source of truth for all rider names.
It was manually verified against the official نس.pdf roster.
To add a new rider, simply add their entry to rider_names.json.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR   = Path(__file__).parent.parent
NAMES_JSON = BASE_DIR / "rider_names.json"


def build_rider_lookup() -> dict[str, str]:
    """
    Return a dict mapping rider_id (str) → Arabic name (str).

    Raises:
        FileNotFoundError: if rider_names.json does not exist.
        RuntimeError:      if fewer than 10 entries are loaded.
    """
    lookup = _load_names_json(NAMES_JSON)

    if len(lookup) < 10:
        raise RuntimeError(
            f"rider_names.json has only {len(lookup)} entries — file may be corrupt or empty."
        )

    logger.info("Rider lookup loaded: %d entries from rider_names.json", len(lookup))
    return lookup


def _load_names_json(path: Path) -> dict[str, str]:
    """Load rider names from rider_names.json."""
    if not path.exists():
        raise FileNotFoundError(f"rider_names.json not found: {path}")

    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("rider_names.json must be a JSON object {id: name}")

    return {str(k): str(v) for k, v in data.items()}
