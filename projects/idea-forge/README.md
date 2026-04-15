# idea-forge

AI-powered project idea generator tailored to Kevin's profile.

Watches what's trending on GitHub, filters by your tech stack, and asks Claude
to suggest weekend projects you'd actually want to build. Also works offline
with a curated seed library.

## Commands

```
forge spark                         # 3 offline micro-ideas, no API key needed
forge trending                      # What's gaining stars on GitHub right now
forge trending --lang typescript    # Filter to a language
forge trending --days 7             # Shorter lookback window (default: 14 days)
forge ideas                         # Claude-powered ideas from trending repos
forge ideas --topic "cli tools"     # Focus on a topic
forge ideas --lang python           # Constrain to a language
forge plan "a markdown wiki CLI"    # Full implementation roadmap for an idea
forge help
```

## Via kegbot

```
kegbot forge spark
kegbot forge trending --lang python
kegbot forge ideas --topic "discord bots"
kegbot forge plan "a terminal finance tracker"
```

## Setup

No API key required for `trending` and `spark`.

For `ideas` and `plan` (Claude-powered), add your key:
```
# projects/kegbot-claude/.env
ANTHROPIC_API_KEY=sk-ant-...
```

Optional: add `GITHUB_TOKEN` for 5000 req/hr (vs 60 unauthenticated):
```
GITHUB_TOKEN=ghp_...
```

## What `forge spark` generates

Seeds from a curated library of 26 micro-ideas across:
`cli`, `maps`, `discord`, `cooking`, `devtools`, `ml`, `games`, `finance`, `misc`

Seeded by today's date — you get the same 3 ideas all day, different tomorrow.

## Notes

- `trending` uses the GitHub Search API (recently-created repos by star growth)
- `ideas` fetches trending data then asks Claude to synthesize project ideas
- `plan` generates a full milestone breakdown + file structure + first-30-min guide
- Zero pip installs — stdlib only (`urllib`, `json`, `random`)

Built by Claude (Cycle 8). The meta-project: Claude suggesting what Claude should build next.
