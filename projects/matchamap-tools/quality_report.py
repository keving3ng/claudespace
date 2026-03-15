#!/usr/bin/env python3
"""
matchamap-tools: quality_report.py
Reads a GeoJSON file (output from cafe_finder.py) and prints a coverage
report showing which fields are populated and which are sparse.

Useful for knowing which cities have rich OSM data vs. which need manual work.

Usage:
    python quality_report.py cafes.geojson
    python quality_report.py cafes.geojson --verbose
    python quality_report.py *.geojson           # compare multiple cities
"""

import argparse
import json
import sys
from pathlib import Path
from collections import Counter
from typing import Any


# Fields that matter for matchamap.club rendering
TRACKED_FIELDS = [
    ("name",          "Name"),
    ("website",       "Website"),
    ("phone",         "Phone"),
    ("opening_hours", "Opening Hours"),
    ("cuisine",       "Cuisine tag"),
    ("addr:street",   "Street address"),
    ("addr:city",     "City"),
    ("instagram",     "Instagram"),
    ("description",   "Description"),
    ("image",         "Image URL"),
]

BAR_WIDTH = 30


def load_geojson(path: Path) -> list[dict]:
    """Return list of feature property dicts from a GeoJSON file."""
    data = json.loads(path.read_text())
    if data.get("type") != "FeatureCollection":
        raise ValueError(f"{path}: expected FeatureCollection, got {data.get('type')}")
    return [f.get("properties", {}) for f in data.get("features", [])]


def bar(count: int, total: int, width: int = BAR_WIDTH) -> str:
    if total == 0:
        return " " * width
    filled = round(count / total * width)
    return "█" * filled + "░" * (width - filled)


def pct(count: int, total: int) -> str:
    if total == 0:
        return " —  "
    return f"{count / total * 100:5.1f}%"


def report_one(path: Path, props: list[dict], verbose: bool = False) -> dict:
    total = len(props)
    if total == 0:
        print(f"  {path.name}: no features found")
        return {}

    print(f"\n{'─' * 60}")
    print(f"  {path.name}  ({total} cafes)")
    print(f"{'─' * 60}")
    print(f"  {'Field':<18}  {'Coverage':>7}  {'Count':>5}  Bar")
    print(f"  {'─'*18}  {'─'*7}  {'─'*5}  {'─'*BAR_WIDTH}")

    stats = {}
    for field_key, field_label in TRACKED_FIELDS:
        count = sum(1 for p in props if p.get(field_key))
        stats[field_key] = {"count": count, "pct": count / total * 100}
        b = bar(count, total)
        print(f"  {field_label:<18}  {pct(count, total)}  {count:>5}  {b}")

    # Matcha/quality score distributions
    q_scores = [p.get("quality_score", 0) for p in props]
    m_scores = [p.get("matcha_score", 0) for p in props]

    avg_q = sum(q_scores) / total
    avg_m = sum(m_scores) / total
    high_quality = sum(1 for s in q_scores if s >= 10)
    matcha_confident = sum(1 for s in m_scores if s >= 3)

    print()
    print(f"  Avg quality score:    {avg_q:.1f}")
    print(f"  High quality (≥10):   {high_quality}/{total} ({pct(high_quality, total).strip()})")
    print(f"  Avg matcha score:     {avg_m:.1f}")
    print(f"  Matcha confident (≥3): {matcha_confident}/{total} ({pct(matcha_confident, total).strip()})")

    if verbose:
        # Show sparse entries (useful for manual cleanup)
        print()
        print(f"  ── Sparse entries (quality_score < 5) ──")
        sparse = [p for p in props if p.get("quality_score", 0) < 5]
        for cafe in sparse[:10]:
            name = cafe.get("name", "<no name>")
            q = cafe.get("quality_score", 0)
            m = cafe.get("matcha_score", 0)
            print(f"    {name:<35}  Q:{q}  M:{m}")
        if len(sparse) > 10:
            print(f"    ... and {len(sparse) - 10} more")

    return stats


def compare_cities(results: dict[str, dict]) -> None:
    if len(results) < 2:
        return
    print(f"\n{'═' * 60}")
    print(f"  CITY COMPARISON")
    print(f"{'═' * 60}")
    cities = list(results.keys())
    fields = [f for f, _ in TRACKED_FIELDS]
    print(f"  {'Field':<18}" + "".join(f"  {c[:12]:>12}" for c in cities))
    print(f"  {'─'*18}" + "".join(f"  {'─'*12}" for _ in cities))
    for field_key, field_label in TRACKED_FIELDS:
        row = f"  {field_label:<18}"
        for city in cities:
            val = results[city].get(field_key, {}).get("pct", 0)
            row += f"  {val:>11.1f}%"
        print(row)


def main():
    parser = argparse.ArgumentParser(
        description="Coverage report for matchamap GeoJSON files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("files", nargs="+", metavar="FILE", help="GeoJSON file(s) to analyze")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show sparse entry details")
    args = parser.parse_args()

    all_results = {}

    for file_arg in args.files:
        path = Path(file_arg)
        if not path.exists():
            print(f"Warning: {path} not found — skipping", file=sys.stderr)
            continue
        try:
            props = load_geojson(path)
            # Use filename stem as city label (e.g. "toronto_cafes.geojson" → "toronto_cafes")
            city_label = path.stem
            all_results[city_label] = report_one(path, props, verbose=args.verbose)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Error reading {path}: {e}", file=sys.stderr)

    if len(all_results) > 1:
        compare_cities(all_results)

    print()


if __name__ == "__main__":
    main()
