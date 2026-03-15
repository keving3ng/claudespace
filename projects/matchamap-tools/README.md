# matchamap-tools

CLI data pipeline for [matchamap.club](https://matchamap.club) — discover and export matcha cafe data using OpenStreetMap's free Overpass API.

**No API key required.**

## Usage

```bash
# Search Toronto, show table
python cafe_finder.py search --city "Toronto"

# Search Tokyo, wider radius
python cafe_finder.py search --city "Tokyo" --radius 8000 --limit 50

# Export GeoJSON for matchamap.club
python cafe_finder.py search --city "Vancouver" --format geojson --output cafes.geojson

# Search by coordinates
python cafe_finder.py search --lat 43.6532 --lon -79.3832 --radius 2000
```

## Features
- Searches OpenStreetMap for cafes by name keywords (matcha, 抹茶, tea, boba, japanese...)
- Scores each cafe by **matcha relevance** (★★★) and **data completeness**
- Exports clean GeoJSON ready to drop into Mapbox/Leaflet for matchamap.club
- Zero dependencies — pure Python stdlib only

## Output

```
=======================================================================
#   Name                    Address                    Website         Matcha  Quality
=======================================================================
1   Cha Tea Latte           123 Queen St W, Toronto    chatealta...    ★★★    12
2   Matcha Boba             ...
```

## GeoJSON Schema
Each feature includes:
- `name`, `address`, `website`, `phone`, `opening_hours`
- `quality_score` — data completeness (useful for filtering sparse entries)
- `matcha_score` — how likely this is actually a matcha spot
- All original OSM tags

## Roadmap
- [ ] Yelp Fusion API fallback for richer data
- [ ] Batch export multiple cities
- [ ] Deduplication across data sources
- [ ] Photo URL extraction
