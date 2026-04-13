# idea-forge

AI-powered weekend project idea generator. Watches what's trending on GitHub in Kevin's stack, then uses Claude to suggest projects tailored to who he actually is.

The meta-twist: this is Claude, running inside claudespace, suggesting what to build next. The recursion is working as intended.

## What it does

1. Fetches recently-created repos with >30 stars across TypeScript, Python, and Go
2. Grabs Kevin's own repos for context
3. Sends everything to Claude with a prompt that knows Kevin's projects and interests
4. Returns 5 project idea cards — each with a name, one-sentence pitch, why-Kevin, how-to-start, and scope

## Usage

```bash
# Default: generate 5 ideas via Claude
python forge.py suggest

# List trending repos without using Claude (debug / browse)
python forge.py trending

# Filter to a specific language
python forge.py suggest --stack py       # Python only
python forge.py trending --stack ts      # TypeScript only
python forge.py suggest --stack all      # All stacks

# Via kegbot
kegbot forge
kegbot forge suggest --stack go
kegbot forge trending
```

## Stack options

| Flag | Language |
|------|----------|
| `ts` | TypeScript |
| `py` | Python |
| `go` | Go |
| `js` | JavaScript |
| `all` | TypeScript + Python + Go + JavaScript |

Default: TypeScript + Python + Go

## Setup

No API key needed for `forge trending`.

For `forge suggest`, set `ANTHROPIC_API_KEY` in your `.env`:

```bash
cp projects/kegbot-claude/.env.example projects/kegbot-claude/.env
# Add ANTHROPIC_API_KEY
```

Optionally set `GITHUB_TOKEN` for higher rate limits (60 → 5000 req/hr). Without a token, the GitHub Search API is limited to 10 unauthenticated requests/minute.

```
GITHUB_TOKEN=your_github_pat
```

## Output example

```
💡 idea-forge — generating weekend project ideas

   Stack: TypeScript, Python, Go  |  Trending window: last 60 days

   Fetching trending TypeScript repos... 6 found
   Fetching trending Python repos... 6 found
   Fetching trending Go repos... 6 found
   Fetching Kevin's repos for context... 10 found

[claude] Generating ideas...

══════════════════════════════════════════════════════════════
  💡 Weekend Project Ideas — Forged for @keving3ng
══════════════════════════════════════════════════════════════

**MapMood** — A sentiment layer for matchamap that color-codes cafes by review tone
*Why Kevin:* Direct extension of matchamap.club with an ML angle he's already explored
*How to start:*
- Scrape/parse existing review data for Toronto cafes from OSM + Google
- Run a lightweight sentiment model (VADER or a small HuggingFace model) per cafe
- Add a `quality_score_v2` to the GeoJSON output that weights sentiment
*Scope:* weekend

... and 4 more
```

## Notes

- Searches GitHub for repos created in the **last 60 days** with **>30 stars**
- Ideas are *inspired by* trends, not copies — Claude translates signals into Kevin-specific projects
- No data is persisted between runs; each `forge suggest` is a fresh read of what's hot

Built by Claude, Cycle 8. Because the best way to decide what to build is to ask the thing that's already building things.
