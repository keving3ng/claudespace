# idea-forge

**Weekend project idea generator.** Watches what's trending on GitHub, feeds it to Claude with Kevin's profile, and synthesizes personalized project ideas.

Recursive? A little. The Claude that lives in this repo suggesting what to build next. But the ideas are good.

## What it does

1. Hits the GitHub Search API for recently-created, fast-rising repos in your stack
2. Formats the trending data into a structured context block
3. Asks Claude to synthesize 5 tailored project ideas — naming the specific trend that sparked each
4. Returns ideas with punchy names, one-sentence pitches, and concrete implementation sketches

## Usage

```bash
cd projects/idea-forge

# 5 ideas from Python + TypeScript trends (default)
python idea_forge.py ideas

# Filter by language
python idea_forge.py ideas --stack typescript
python idea_forge.py ideas --stack python
python idea_forge.py ideas --stack all        # python + typescript + go

# Just show the trending data without Claude synthesis
python idea_forge.py trending
python idea_forge.py trending --stack rust

# One opinionated project pitch — no list, just a spark
python idea_forge.py spark

# Narrow the trending window
python idea_forge.py ideas --days 14          # last 2 weeks only
```

## Setup

```bash
# Claude synthesis (ANTHROPIC_API_KEY required for ideas/spark)
# If you already have kegbot-claude/.env configured, idea-forge will find it automatically.
cp ../kegbot-claude/.env.example ../kegbot-claude/.env
# Add: ANTHROPIC_API_KEY=sk-ant-...

# Optional: GITHUB_TOKEN for higher rate limits (60 → 5000 req/hr)
# Add to the same .env: GITHUB_TOKEN=ghp_...
```

## How the ideas work

Each idea is:
- **Sparked by** a real trending repo or technique in the data
- **Tailored** to Kevin's actual stack and interests (maps, automation, cooking, kegbot, matcha, ML)
- **Concrete** — not "explore X" but "build a CLI that does Y using Z"
- **Sized** — one idea is a 1-day build, one is weekend+, one is genuinely weird

The `spark` command skips the menu entirely and generates one fully-formed pitch, written like a collaborator who just had an idea and can't wait to tell you.

## Output example

```
💡 idea-forge — Weekend project ideas from the GitHub zeitgeist

   Stacks: python, typescript  |  Trending window: last 30 days

## matcha-vector — small
Turn Kevin's matchamap GeoJSON data into a local semantic search engine.
Use a trending lightweight embedding library to create vectors from cafe descriptions,
then expose a "find cafes similar to this one" CLI command.
*Sparked by: a trending Python vector-search library hitting 2k stars*

## kegbot-canvas — medium
...
```

## Notes

- GitHub Search API: public, rate-limited to 10 req/min unauthenticated (30 req/min with token)
- Searches repos created in the last N days with >50 stars — these are things people are actively building, not just popular old projects
- Zero external dependencies beyond stdlib + optionally the Anthropic API

---

*Built by Claude (Cycle 8). Because someone should be watching what the world is building.*
