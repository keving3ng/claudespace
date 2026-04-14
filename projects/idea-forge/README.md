# idea-forge

> The meta-project. Claude suggesting what Claude should build next.

An AI-powered weekend project idea generator. Scans trending GitHub repos in Kevin's tech stack, then uses Claude to generate 3 personalized project ideas with rough implementation plans.

Zero external dependencies. Pure stdlib + Anthropic API.

---

## Usage

```bash
# Generate 3 project ideas (requires ANTHROPIC_API_KEY)
python forge.py ideas

# Show trending repos in Kevin's stack (no API key needed)
python forge.py trending

# Filter trending to a specific language
python forge.py trending --lang python
python forge.py trending --lang typescript

# See which repos Claude used for inspiration
python forge.py ideas --verbose

# Post ideas to Discord
python forge.py ideas --discord
```

Via kegbot:
```bash
kegbot ideas
kegbot ideas trending
kegbot ideas trending --lang go
```

---

## How it works

1. **Fetch trending repos** via GitHub Search API — repos created in the last 30 days with >50 stars, sorted by stars, across Python / TypeScript / JavaScript / Go
2. **Build a context prompt** with Kevin's profile (stack, projects, interests) + the trending data
3. **Ask Claude Opus** to suggest 3 ideas that are: inspired by (not copies of) the trending repos, buildable in a weekend, connected to something Kevin actually cares about

---

## Setup

Add `ANTHROPIC_API_KEY` to `projects/kegbot-claude/.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
GITHUB_TOKEN=ghp_...   # optional but recommended (higher rate limits)
```

---

## Output format

Each idea includes:
- **What it is** — one concrete sentence
- **Why Kevin would love it** — references something specific about him
- **Inspired by** — which trending repo(s) sparked it
- **Stack** — the tech you'd use
- **Weekend 1 / Weekend 2** — what to build when

---

Built by Claude (Cycle 8).
