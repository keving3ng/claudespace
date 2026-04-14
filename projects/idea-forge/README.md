# idea-forge

**AI project idea generator tailored to Kevin.**

Scans GitHub for newly-trending repos in your stack, hands them to Claude along with your profile and active projects, and gets back personalized weekend project ideas with implementation hints. Meta, recursive, slightly self-aware.

## Usage

```bash
# Generate 5 ideas from trending TypeScript, Python, Java, Kotlin repos
python ideas.py

# Just see what's trending (no Claude needed)
python ideas.py --raw

# Ideas focused on a specific language
python ideas.py --stack ts
python ideas.py --stack python

# Generate more or fewer ideas
python ideas.py --count 3

# Browse past idea sessions
python ideas.py --saved
python ideas.py --saved --index 1

# Via kegbot
kegbot ideas
kegbot ideas --stack ts --count 3
kegbot ideas --raw
```

## How it works

1. Searches GitHub for repos created in the last 30 days with 5+ stars
2. Fetches top results across TypeScript, Python, Java, Kotlin (4 per language)
3. Sends those trends + Kevin's full profile to Claude
4. Claude generates tailored project ideas with concrete features, stack recommendations, and a "Kevin's twist"
5. Saves every session to `saved_ideas.json` for future reference

## Setup

Requires `ANTHROPIC_API_KEY` in `.env` (or `projects/kegbot-claude/.env`).

`GITHUB_TOKEN` is optional but recommended — without it you get 10 GitHub API requests/minute, which is usually enough but can cause rate limiting if you run this frequently.

```bash
# .env (in this directory or the kegbot-claude directory)
ANTHROPIC_API_KEY=sk-ant-...
GITHUB_TOKEN=ghp_...    # optional
```

## Output example

```
🔭 idea-forge — scanning GitHub trends

   Stacks: typescript, python, java, kotlin
   Window: last 30 days

  🔍 typescript     → 4 repos  (top: ⭐1,234 some-cool-lib)
  🔍 python         → 4 repos  (top: ⭐892 another-tool)
  ...

   16 trending repos found

[claude] Generating ideas...

═════════════════════════════════════════════════════════════════
  💡  5 Project Ideas for Kevin  (2026-04-14)
═════════════════════════════════════════════════════════════════

**1. MatchaRank CLI**
*Pitch:* A command-line tool that pulls live Yelp/Google reviews...
...
```

## Files

- `ideas.py` — main script
- `saved_ideas.json` — auto-created, stores all past idea sessions

---

Built by Claude (Cycle 8). For when you need a spark.
