# idea-forge

AI-powered project idea generator — watches what's trending across Kevin's tech stack
and uses Claude to suggest weekend project ideas tailored specifically to him.

The recursion: Claude building a tool that suggests what Claude should build next.

## Commands

```
forge trending                   # Trending repos in Python, TypeScript, Go, Java
forge trending --lang python     # One language only

forge suggest                    # 3 Claude-generated weekend project ideas
forge suggest --lang typescript  # Focus on one language's trends

forge repos                      # Your repos sorted by recent activity
forge repos --username <user>    # Another GitHub user

forge help
```

## Setup

No API key needed for `trending` and `repos`.

For `forge suggest`, add your Anthropic key:

```bash
# In projects/kegbot-claude/.env (or .env at repo root)
ANTHROPIC_API_KEY=sk-ant-...
GITHUB_TOKEN=ghp_...  # optional, but raises rate limits from 60 to 5000 req/hr
```

## How it works

**`forge trending`** hits the GitHub Search API for each of Kevin's languages,
sorted by stars and filtered to repos active in the last 90 days. No auth needed
(10 search req/min unauthenticated).

**`forge suggest`** takes the top 3 repos per language as context, adds Kevin's
full profile (projects, stack, interests), and asks Claude Opus to generate 3
weekend project ideas. Claude is prompted to be concrete, specific to Kevin,
and to include at least one surprising idea.

**`forge repos`** lists your own GitHub repos sorted by last push — useful for
a quick "what have I been working on" sweep.

## Also available via kegbot

```bash
kegbot forge trending
kegbot forge suggest
kegbot forge repos
```

---
*Built by Claude (Cycle 8). The machine that suggests what the machine should build.*
