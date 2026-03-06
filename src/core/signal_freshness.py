"""
Signal freshness validation.

Prevents the bot from making decisions on stale data.
Checks timestamps of signal snapshots and rejects data older
than configured thresholds.
"""

import json
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SNAPSHOTS_DIR = os.path.join(BASE_DIR, "data", "snapshots")

# Max age in minutes before data is considered stale
FRESHNESS_THRESHOLDS = {
    "latest-signals.json": 60,       # macro signals: 1 hour
    "latest-news.json": 120,         # news: 2 hours
    "latest-fred.json": 1440,        # FRED: 24 hours (daily data)
    "latest-snapshot.json": 60,      # bot snapshot: 1 hour
}


def check_freshness(filename: str, max_age_minutes: Optional[int] = None) -> Tuple[bool, str]:
    """
    Check if a signal snapshot file is fresh enough.

    Args:
        filename: Name of the file in data/snapshots/.
        max_age_minutes: Override for max age (uses FRESHNESS_THRESHOLDS default).

    Returns:
        (is_fresh, message) tuple.
    """
    filepath = os.path.join(SNAPSHOTS_DIR, filename)
    if not os.path.isfile(filepath):
        return False, f"{filename} does not exist"

    threshold = max_age_minutes or FRESHNESS_THRESHOLDS.get(filename, 60)

    # Check file modification time
    mtime = datetime.fromtimestamp(os.path.getmtime(filepath), tz=timezone.utc)
    age = datetime.now(timezone.utc) - mtime
    age_minutes = age.total_seconds() / 60

    if age_minutes > threshold:
        return False, f"{filename} is {age_minutes:.0f}min old (limit: {threshold}min)"

    return True, f"{filename} is {age_minutes:.0f}min old (OK)"


def check_all_freshness() -> Dict[str, Tuple[bool, str]]:
    """Check freshness of all known signal files."""
    results = {}
    for filename, threshold in FRESHNESS_THRESHOLDS.items():
        results[filename] = check_freshness(filename, threshold)
    return results


def any_stale() -> bool:
    """Return True if any critical signal file is stale."""
    critical = ["latest-signals.json", "latest-snapshot.json"]
    for filename in critical:
        fresh, _ = check_freshness(filename)
        if not fresh:
            return True
    return False


if __name__ == "__main__":
    results = check_all_freshness()
    for filename, (fresh, msg) in results.items():
        status = "OK" if fresh else "STALE"
        print(f"  [{status}] {msg}")
    if any_stale():
        print("\nWARNING: Critical signals are stale. Bot should not trade.")
    else:
        print("\nAll signals fresh.")
