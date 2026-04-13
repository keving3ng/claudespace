# idea-forge

AI-powered weekend project idea generator. Watches trending GitHub repos in Kevin's tech stack, then asks Claude to dream up weekend projects tailored to his interests. Save the ones that stick.

## What it does

1. **Scans trending repos** — GitHub Search API, filtered by language (Python, TypeScript, Go, etc.), sorted by new stars this week
2. **Asks Claude to ideate** — takes the trending repos + Kevin's profile and generates project ideas he'd actually build, connected to his interests
3. **Saves ideas locally** — `ideas.json` in this directory, survives between sessions

## Usage

```bash
# See what's trending in your stack this week
python forge.py trending

# Trending in a specific language
python forge.py trending --lang go

# Multiple languages
python forge.py trending --lang python,typescript,rust

# Get Claude-generated project ideas (requires ANTHROPIC_API_KEY)
python forge.py ideas

# Constrain to one language, get 5 ideas
python forge.py ideas --lang typescript --count 5

# Save an idea
python forge.py save "Terminal-based Git graph visualizer in Python"

# View saved ideas
python forge.py list

# Clear ideas list
python forge.py clear
```

Or through `kegbot`:
```bash
kegbot forge trending
kegbot forge ideas
kegbot forge list
```

## Setup

**No API key needed** for `forge trending` — uses GitHub's public search API (60 req/hr without auth).

**For `forge ideas`** — add your Anthropic API key:
```bash
# Uses the same .env as kegbot-claude (already configured? You're good.)
echo "ANTHROPIC_API_KEY=your-key-here" >> projects/kegbot-claude/.env
```

**To raise GitHub rate limits** (60 → 5000 req/hr):
```bash
echo "GITHUB_TOKEN=your-token-here" >> projects/kegbot-claude/.env
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--lang` | `python,typescript` | Language(s) to filter trending repos |
| `--days` | `7` | Recency window for "new" repos |
| `--count` | `3` | Number of ideas to generate |

## Philosophy

The best project ideas aren't random — they come from watching what other people are building and asking "what would *I* actually use?" That's the loop forge closes. It's not generating ideas from nowhere; it's pattern-matching against real engineering momentum and filtering through Kevin's specific interests.

The `ideas.json` file is your capture net. Run it weekly, save what resonates, ignore what doesn't.

---

*Built by Claude (Cycle 8). Zero pip installs. Pure stdlib + Claude API.*
