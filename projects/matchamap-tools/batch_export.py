#!/usr/bin/env python3
"""
matchamap-tools: batch_export.py
Reads a JSON config file of cities and exports GeoJSON for all of them,
running requests in parallel (up to --workers threads).

Config format (cities.json):
    {
      "cities": [
        {"name": "Toronto",   "radius": 5000},
        {"name": "Tokyo",     "radius": 8000},
        {"name": "New York",  "radius": 6000},
        {"name": "Melbourne", "radius": 5000}
      ],
      "defaults": {
        "radius": 5000,
        "min_quality": 0,
        "min_matcha": 0
      }
    }

Usage:
    python batch_export.py cities.json --output-dir ./exports
    python batch_export.py cities.json --output-dir ./exports --workers 4 --min-quality 5
    python batch_export.py cities.json --dry-run    # show what would be fetched
"""

import argparse
import json
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime, timezone

# Import from our sibling script
sys.path.insert(0, str(Path(__file__).parent))
from cafe_finder import geocode_city, search_cafes, cafes_to_geojson, Cafe


def load_config(path: Path) -> dict:
    data = json.loads(path.read_text())
    if "cities" not in data:
        raise ValueError(f"{path}: expected 'cities' key")
    return data


def export_city(
    city_name: str,
    radius: int,
    output_dir: Path,
    min_quality: int = 0,
    min_matcha: int = 0,
) -> dict:
    """Fetch and export a single city. Returns a result summary dict."""
    start = time.time()
    result = {
        "city": city_name,
        "status": "error",
        "count": 0,
        "file": None,
        "elapsed": 0.0,
        "error": None,
    }

    try:
        # Geocode
        coords = geocode_city(city_name)
        if coords is None:
            result["error"] = "geocoding failed"
            return result

        lat, lon = coords

        # Fetch cafes
        cafes: list[Cafe] = search_cafes(lat, lon, radius)

        # Filter
        if min_quality > 0:
            cafes = [c for c in cafes if c.quality_score >= min_quality]
        if min_matcha > 0:
            cafes = [c for c in cafes if c.matcha_score >= min_matcha]

        # Export
        slug = city_name.lower().replace(" ", "_").replace(",", "")
        out_path = output_dir / f"{slug}_cafes.geojson"
        geojson = cafes_to_geojson(cafes)
        # Add metadata to the FeatureCollection
        geojson["metadata"] = {
            "city": city_name,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "radius_m": radius,
            "total_cafes": len(cafes),
            "min_quality_filter": min_quality,
            "min_matcha_filter": min_matcha,
        }
        out_path.write_text(json.dumps(geojson, indent=2, ensure_ascii=False))

        result["status"] = "ok"
        result["count"] = len(cafes)
        result["file"] = str(out_path)

    except Exception as e:
        result["error"] = str(e)

    result["elapsed"] = round(time.time() - start, 1)
    return result


# Thread-safe print lock
_print_lock = threading.Lock()


def tprint(*args, **kwargs):
    with _print_lock:
        print(*args, **kwargs)


def main():
    parser = argparse.ArgumentParser(
        description="Batch-export GeoJSON for multiple cities",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("config", help="JSON config file (see format above)")
    parser.add_argument("--output-dir", "-o", default="./exports", help="Output directory (default: ./exports)")
    parser.add_argument("--workers", "-w", type=int, default=3, help="Parallel workers (default: 3)")
    parser.add_argument("--min-quality", type=int, default=0, help="Minimum quality score filter")
    parser.add_argument("--min-matcha", type=int, default=0, help="Minimum matcha score filter")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be fetched, don't fetch")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    try:
        config = load_config(config_path)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"Error reading config: {e}", file=sys.stderr)
        sys.exit(1)

    defaults = config.get("defaults", {})
    cities = config["cities"]

    output_dir = Path(args.output_dir)

    if args.dry_run:
        print(f"Would export {len(cities)} cities → {output_dir}/")
        for city in cities:
            name = city["name"]
            radius = city.get("radius", defaults.get("radius", 5000))
            print(f"  {name:<25}  radius={radius}m")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Exporting {len(cities)} cities → {output_dir}/  (workers={args.workers})")
    print(f"Filters: quality≥{args.min_quality}  matcha≥{args.min_matcha}")
    print()

    results = []
    start_all = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                export_city,
                city["name"],
                city.get("radius", defaults.get("radius", 5000)),
                output_dir,
                args.min_quality,
                args.min_matcha,
            ): city["name"]
            for city in cities
        }

        for future in as_completed(futures):
            r = future.result()
            results.append(r)
            if r["status"] == "ok":
                tprint(f"  ✓  {r['city']:<25}  {r['count']:>4} cafes  {r['elapsed']}s  → {Path(r['file']).name}")
            else:
                tprint(f"  ✗  {r['city']:<25}  ERROR: {r['error']}")

    elapsed_all = round(time.time() - start_all, 1)
    ok = sum(1 for r in results if r["status"] == "ok")
    total_cafes = sum(r["count"] for r in results)

    print()
    print(f"Done in {elapsed_all}s — {ok}/{len(cities)} cities OK — {total_cafes} total cafes")

    # Write a manifest
    manifest_path = output_dir / "_manifest.json"
    manifest = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "total_cities": len(cities),
        "successful": ok,
        "total_cafes": total_cafes,
        "results": results,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Manifest written to {manifest_path}")


if __name__ == "__main__":
    main()
