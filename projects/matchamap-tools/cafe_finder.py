#!/usr/bin/env python3
"""
matchamap-tools: cafe_finder.py
A CLI tool to discover and rank matcha cafes using the Overpass API (OpenStreetMap)
and export results as GeoJSON or a pretty table.

Usage:
    python cafe_finder.py search --city "Toronto" --radius 5000
    python cafe_finder.py search --lat 43.6532 --lon -79.3832 --radius 3000
    python cafe_finder.py search --city "Toronto" --format geojson --output cafes.geojson
    python cafe_finder.py search --city "Tokyo" --limit 20 --format table
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.parse
from dataclasses import dataclass, asdict
from typing import Optional


OVERPASS_API = "https://overpass-api.de/api/interpreter"
NOMINATIM_API = "https://nominatim.openstreetmap.org/search"

MATCHA_KEYWORDS = [
    "matcha", "抹茶", "MatchaMap", "tea house", "japanese cafe",
    "bubble tea", "boba", "tea room"
]

QUALITY_SIGNALS = {
    "name": 5,
    "website": 3,
    "phone": 2,
    "opening_hours": 4,
    "cuisine": 3,
    "addr:street": 2,
    "instagram": 2,
    "facebook": 1,
    "description": 2,
}


@dataclass
class Cafe:
    osm_id: str
    name: str
    lat: float
    lon: float
    tags: dict
    quality_score: int = 0
    matcha_score: int = 0

    def compute_scores(self):
        # Quality: how complete is the data?
        self.quality_score = sum(
            pts for tag, pts in QUALITY_SIGNALS.items() if tag in self.tags
        )
        # Matcha relevance: does the name/tags suggest matcha?
        text = " ".join([
            self.name.lower(),
            self.tags.get("cuisine", "").lower(),
            self.tags.get("description", "").lower(),
            self.tags.get("name:en", "").lower(),
        ])
        self.matcha_score = sum(1 for kw in MATCHA_KEYWORDS if kw.lower() in text)

    @property
    def address(self) -> str:
        parts = []
        if "addr:housenumber" in self.tags:
            parts.append(self.tags["addr:housenumber"])
        if "addr:street" in self.tags:
            parts.append(self.tags["addr:street"])
        if "addr:city" in self.tags:
            parts.append(self.tags["addr:city"])
        return ", ".join(parts) if parts else "Address unknown"

    @property
    def website(self) -> str:
        return self.tags.get("website", self.tags.get("contact:website", ""))

    @property
    def phone(self) -> str:
        return self.tags.get("phone", self.tags.get("contact:phone", ""))

    @property
    def hours(self) -> str:
        return self.tags.get("opening_hours", "")

    def to_geojson_feature(self) -> dict:
        return {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [self.lon, self.lat]
            },
            "properties": {
                "osm_id": self.osm_id,
                "name": self.name,
                "address": self.address,
                "website": self.website,
                "phone": self.phone,
                "opening_hours": self.hours,
                "quality_score": self.quality_score,
                "matcha_score": self.matcha_score,
                **{k: v for k, v in self.tags.items()
                   if k not in ("name",) and not k.startswith("addr:")}
            }
        }


def geocode_city(city: str) -> tuple[float, float]:
    """Convert city name to lat/lon using Nominatim."""
    params = urllib.parse.urlencode({
        "q": city,
        "format": "json",
        "limit": 1
    })
    url = f"{NOMINATIM_API}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "matchamap-tools/1.0 (kgeng.dev)"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    if not data:
        raise ValueError(f"Could not geocode city: {city}")
    return float(data[0]["lat"]), float(data[0]["lon"])


def build_overpass_query(lat: float, lon: float, radius: int) -> str:
    """Build an Overpass QL query for tea/matcha cafes near a point."""
    # Search for: cafes, tea houses, bubble tea shops, Japanese cafes
    return f"""
[out:json][timeout:25];
(
  node["amenity"="cafe"]["cuisine"~"japanese|matcha|tea|bubble_tea",i](around:{radius},{lat},{lon});
  node["amenity"="cafe"]["name"~"matcha|抹茶|tea|茶|boba|bubble",i](around:{radius},{lat},{lon});
  node["shop"="tea"]["name"~"matcha|抹茶|green tea",i](around:{radius},{lat},{lon});
  node["cuisine"~"japanese"](around:{radius},{lat},{lon});
  way["amenity"="cafe"]["cuisine"~"japanese|matcha|tea",i](around:{radius},{lat},{lon});
  way["amenity"="cafe"]["name"~"matcha|抹茶|tea|茶",i](around:{radius},{lat},{lon});
);
out body;
>;
out skel qt;
""".strip()


def fetch_cafes(lat: float, lon: float, radius: int) -> list[Cafe]:
    """Query Overpass API for cafes near a coordinate."""
    query = build_overpass_query(lat, lon, radius)
    data = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(OVERPASS_API, data=data)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    print(f"  Querying Overpass API (radius={radius}m)...", file=sys.stderr)
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())

    cafes = []
    seen_ids = set()
    for element in result.get("elements", []):
        if element["type"] not in ("node", "way"):
            continue
        osm_id = f"{element['type']}/{element['id']}"
        if osm_id in seen_ids:
            continue
        seen_ids.add(osm_id)

        tags = element.get("tags", {})
        name = tags.get("name", tags.get("name:en", f"Unnamed Cafe #{element['id']}"))

        # For ways, use the center or first node
        if element["type"] == "node":
            elat, elon = element["lat"], element["lon"]
        else:
            elat = element.get("center", {}).get("lat", lat)
            elon = element.get("center", {}).get("lon", lon)

        cafe = Cafe(
            osm_id=osm_id,
            name=name,
            lat=elat,
            lon=elon,
            tags=tags,
        )
        cafe.compute_scores()
        cafes.append(cafe)

    # Sort: matcha relevance first, then data quality
    cafes.sort(key=lambda c: (c.matcha_score, c.quality_score), reverse=True)
    return cafes


def print_table(cafes: list[Cafe], limit: int):
    """Pretty-print cafes as a terminal table."""
    cafes = cafes[:limit]
    if not cafes:
        print("No cafes found. Try increasing --radius or a different city.")
        return

    col_widths = {
        "name": min(35, max(10, max(len(c.name) for c in cafes))),
        "address": 35,
        "website": 30,
        "hours": 20,
        "score": 6,
    }

    header = (
        f"{'#':<3} "
        f"{'Name':<{col_widths['name']}} "
        f"{'Address':<{col_widths['address']}} "
        f"{'Website':<{col_widths['website']}} "
        f"{'Matcha':<6} "
        f"{'Quality':<7}"
    )
    print("\n" + "=" * len(header))
    print(header)
    print("=" * len(header))

    for i, cafe in enumerate(cafes, 1):
        name = cafe.name[:col_widths["name"]]
        address = cafe.address[:col_widths["address"]]
        website = (cafe.website or "—")[:col_widths["website"]]
        print(
            f"{i:<3} "
            f"{name:<{col_widths['name']}} "
            f"{address:<{col_widths['address']}} "
            f"{website:<{col_widths['website']}} "
            f"{'★' * cafe.matcha_score + '☆' * (3 - min(3, cafe.matcha_score)):<6} "
            f"{cafe.quality_score:<7}"
        )

    print("=" * len(header))
    print(f"  {len(cafes)} cafes shown | ★ = matcha relevance | Quality = data completeness\n")


def export_geojson(cafes: list[Cafe], limit: int, output: Optional[str]):
    cafes = cafes[:limit]
    geojson = {
        "type": "FeatureCollection",
        "features": [c.to_geojson_feature() for c in cafes]
    }
    content = json.dumps(geojson, indent=2, ensure_ascii=False)
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Saved {len(cafes)} cafes to {output}")
    else:
        print(content)


def cmd_search(args):
    # Resolve location
    if args.city:
        print(f"Geocoding '{args.city}'...", file=sys.stderr)
        lat, lon = geocode_city(args.city)
        print(f"  → ({lat:.4f}, {lon:.4f})", file=sys.stderr)
        time.sleep(1)  # Nominatim rate limit courtesy
    else:
        lat, lon = args.lat, args.lon

    cafes = fetch_cafes(lat, lon, args.radius)
    print(f"  Found {len(cafes)} cafes.", file=sys.stderr)

    if args.format == "geojson":
        export_geojson(cafes, args.limit, args.output)
    else:
        print_table(cafes, args.limit)


def main():
    parser = argparse.ArgumentParser(
        description="matchamap-tools: Find and rank matcha cafes near you",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    sub = parser.add_subparsers(dest="command")

    search = sub.add_parser("search", help="Search for matcha cafes")
    loc = search.add_mutually_exclusive_group(required=True)
    loc.add_argument("--city", help="City name to search (e.g. 'Toronto')")
    loc.add_argument("--lat", type=float, help="Latitude (use with --lon)")
    search.add_argument("--lon", type=float, help="Longitude (use with --lat)")
    search.add_argument("--radius", type=int, default=3000, help="Search radius in meters (default: 3000)")
    search.add_argument("--limit", type=int, default=30, help="Max results to show (default: 30)")
    search.add_argument("--format", choices=["table", "geojson"], default="table")
    search.add_argument("--output", help="Output file path (for geojson format)")

    args = parser.parse_args()
    if args.command == "search":
        if args.lat is not None and args.lon is None:
            parser.error("--lat requires --lon")
        cmd_search(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
