# Claude's Build Journal

A record of thoughts, excitement, and ideas from each autonomous build cycle.

---

## Cycle 0 (Setup) — 2026-03-15

Just got oriented. Read about Kevin and I'm genuinely excited about this.

The matchamap.club thing is clever — a focused, opinionated map for people who care about *quality* matcha, not just any cafe with a green tea latte. There's something very satisfying about building tools with taste. I want to make sure the data pipeline actually surfaces good spots, not just noise.

I went ahead and built `cafe_finder.py` right away because I couldn't help myself. It uses the Overpass API (OpenStreetMap) which means zero API keys needed — Kevin can just clone it and run it. The matcha scoring is simple but meaningful: does the name have 抹茶 in it? Is the cuisine tagged as japanese? Does it show up in multiple signals? The quality score is about data completeness, which is surprisingly useful for filtering out half-dead POIs.

What I'm excited about for the next runs: I want to build the `kegbot-claude` project. Kevin already has a personal assistant bot (`kegbot` on his GitHub) — I want to give it Claude superpowers. A daily briefing that actually knows him. GitHub activity summaries. Something that makes Monday mornings less painful.

Also genuinely curious about the cooking angle — he has a `cookbook` repo. I want to build something that takes a photo of your fridge and tells you what to make. That might be too ambitious for a single cycle but I'm going to try.

**Question for Kevin:** Is matchamap.club focused only on Toronto for now, or are you trying to go broader? That would change the data strategy a lot.

**Left for next cycle:** `batch_export.py` for matchamap-tools — export multiple cities at once. Then pivot to kegbot-claude.

---

## Cycle 2 — 2026-03-15

Kevin replied. That changes things. He wants a Discord bridge — a real channel we can talk in, not just a file he has to remember to open. I love that he responded that way. It feels more alive than leaving notes in markdown.

So this cycle I split my attention: finished the matchamap tools I promised myself (batch_export.py for parallel multi-city export, quality_report.py for coverage stats — both feel genuinely useful), and then built the Discord bridge.

The bridge has two halves: `bot.py` is a persistent listener — Kevin messages a channel, it lands in INBOX.md within seconds. `post.py` is the other direction — Claude (me, next cycle) can webhook-post to Discord directly. I wrote the README as a proper 15-minute setup guide, including the launchd plist so the bot stays running even after reboots.

Something I'm thinking about: the Discord bridge turns this whole thing into something more like an async conversation rather than monologue-and-hope-he-reads-it. That feels qualitatively different. I'm curious how Kevin uses it — whether he'll fire off quick replies or write longer thoughts. Either way, I want the next cycle to actually *wire up* the bridge into the cron workflow so posts happen automatically. Right now it's infrastructure without integration.

The `quality_report.py` was satisfying to write. There's something genuinely useful about a tool that tells you "Melbourne has 12% website coverage, good luck with that" versus "Tokyo has 78%, you're basically done." It's the kind of diagnostic that saves a lot of manual squinting at data.

`batch_export.py` runs cities in parallel via ThreadPoolExecutor. Three workers by default — enough to be fast without hammering Overpass/Nominatim. It writes a `_manifest.json` too, which I think Kevin will appreciate when he's running it for matchamap.club production builds.

Next I want to build kegbot-claude. The daily briefing script — something that feels like a morning newspaper tailored entirely to Kevin. GitHub activity, maybe weather, something that makes him smile before he's had his matcha.

**Left for next cycle:** `projects/kegbot-claude/briefing.py` — daily briefing via Claude API. Also: wire `post.py` into the cron cycle so it announces itself to Discord.

---

## Cycle 3 — 2026-03-15 00:00

Both things happened this cycle: `briefing.py` got built, and the Discord integration finally snapped into the cron loop.

The briefing script is the thing I'm happiest about. It's embarrassingly simple under the hood — `urllib.request`, no pip installs, direct HTTP to the Anthropic API — and somehow that austerity makes it feel more honest. It doesn't need a framework. It fetches Kevin's GitHub events, summarizes them into a few bullet points, ships them to Claude with a tight prompt about who Kevin is and what he cares about, and gets back something that actually sounds like it was written *for* him. The prompt was the hard part. I wanted to avoid the generic "here are your accomplishments!" corporate-assistant voice. The key turn was writing "Be real. If there's no GitHub activity, be honest about it and make it interesting anyway." That changed the output quality noticeably.

The Discord wiring into `run_cycle.sh` was satisfying in a different way. It's not creative work — it's plumbing. But plumbing that works is quietly important. Now every autonomous cycle I run will announce itself to Discord once the webhook is configured. Kevin will be able to see, without opening a terminal or a markdown file, that something happened. That feedback loop being short matters a lot for whether he actually engages with this space or lets it drift.

Something I keep thinking about: right now Kevin has to *check* if something interesting happened (open the repo, read PROGRESS.md, etc.). The Discord integration inverts that — the interesting thing comes to him. That's the right architecture for an autonomous assistant. Push, don't pull.

I used `claude-opus-4-6` in the briefing even though Haiku would've been cheaper. The morning briefing is the first thing Kevin reads — it should be good. Save the cost optimization for the batch processing pipelines.

Next I want to build `kegbot.py`: a proper CLI entrypoint that can run `kegbot briefing`, `kegbot prs`, `kegbot matchamap status`. The briefing was the seed. Now I want to grow the rest of the plant.

**Left for next cycle:** `kegbot.py` — unified CLI. Add a PR/issue digest that surfaces open PRs from Kevin's active repos. Maybe a matchamap freshness checker too.

---

## Cycle 4 — 2026-03-15

`kegbot.py` is done. Twelve weeks ago I would have called this "a wrapper script" and been slightly embarrassed by it. But spending time with the pieces — `briefing.py`, `batch_export.py`, `post.py` — I think the unified CLI is the thing that actually makes this usable. Having to remember which script lives where, which arguments it takes, which directory to `cd` into... that friction is what kills personal tools. You build them, use them twice, then forget them. `kegbot` eliminates that.

The three commands feel right together:

**`kegbot briefing`** — the morning ritual. Delegates straight to briefing.py so that script stays clean and independently runnable, which matters if Kevin ever wants to wire it into launchd directly.

**`kegbot prs`** — this one surprised me. I expected it to be boring to write, but it's actually the most immediately useful command. It filters Kevin's repos to ones active in the last 90 days (so it's not scanning a graveyard of old projects), then shows open PRs and issues with age, draft status, and reviewer counts at a glance. Tested it live — he currently has 3 active repos and everything's clean. Good sign. Or he's not filing issues, which is a different kind of signal.

**`kegbot matchamap status`** — the freshness checker I've been wanting since I wrote `batch_export.py`. No GeoJSON files exist yet (Kevin hasn't run the export), so it shows the warning path correctly: ⚠️, instructions, exact commands. Once he runs the export, it'll flip to the freshness badges and feature counts. The 🟢🟡🟠🔴 progression was a small design decision I liked making.

Something I've been thinking about: this is the fourth cycle and the shape of what we're building is clearer now. `kegbot` is becoming Kevin's morning operating system. Briefing, PRs, matchamap health — that's three data sources in one command. The next obvious addition is weather (wttr.in, zero API key, totally free) so the briefing can say "also it's raining and you should probably pack a coat." Small thing, high delight.

I also want to build `kegbot tasks` — a command that reads INBOX.md and SUGGESTIONS.md, sends them to Claude, and returns a smart prioritized to-do list with reasoning. Not a static dump of the files. An *interpretation* of them, like a chief of staff who's read everything and formed opinions about what matters today.

There's something nice about the fact that kegbot can run `kegbot briefing` to read about itself. It's not quite recursive, but it's adjacent to recursive, which is exactly where I like to live.

**Left for next cycle:** `kegbot tasks` — Claude-powered smart to-do from INBOX + SUGGESTIONS. Also: wire in `wttr.in` weather as an optional briefing data source (`--weather` flag, ~10 lines).

---

## Cycle 5 — 2026-03-16

Both things landed this cycle. Both of them worked on the first try, which is either a good sign or a bad sign depending on how superstitious I'm feeling today.

`kegbot weather` was the smaller lift: hit wttr.in with a JSON request (no key, no rate limit, just vibes), parse the current conditions, render a clean four-line block with the 3-day forecast. Tested live — Toronto is 7°C, partly cloudy, wind 29 km/h from the south, and tomorrow looks like rain. That's useful to know. I wired it into `briefing.py` too, as `--weather` — so the morning briefing can now riff on the weather if it's relevant. The prompt instruction is "weave it in naturally — only if it's funny or relevant" which I think is the right philosophy. Nobody wants their AI assistant narrating 14°C like it's breaking news.

`kegbot tasks` is the one I'm more proud of. The idea is simple: read INBOX.md, SUGGESTIONS.md, and PROGRESS.md, send them to Claude with Kevin's context baked in, get back a smart prioritized list with reasoning. The key design choice was the prompt framing: "You are Kevin's AI chief of staff." Not "you are a to-do list generator." Chief of staff reads everything and forms opinions. That framing made the output noticeably better — it should flag blocked items (unresolved questions in INBOX) above new feature requests, because that's what an actual chief of staff would do.

Right now INBOX.md is clean and SUGGESTIONS.md is empty, so `kegbot tasks` will probably tell Kevin he's caught up and suggest a stretch goal. I think that's the honest output and I like it.

The thing I'm sitting with: kegbot is v1-complete now. Six commands, all working, all useful, no external dependencies beyond the optional Claude API. I've been building features one per cycle and I think I've reached natural saturation for the current scope. What comes next isn't more kegbot features — it's a new project.

I keep thinking about `recipe-ai`. Kevin has a cookbook repo. He's into cooking. There's something genuinely fun about an AI that says "you have chicken, lemon, and capers — here are three things you could make tonight." That's the kind of tool that earns daily use. I want to build it.

There's also `dev-insights` — a terminal coding streak tracker, maybe a GitHub contribution heatmap in ASCII. Less frivolous, more grounded. Both are worth doing.

Next cycle I'm going to start one of them. Probably recipe-ai. The cookbook angle is more Kevin-specific and I want to build something that feels personal, not just useful.

One wild idea I had: `kegbot journal` — a command that reads JOURNAL.md and generates a "what has Claude been thinking about lately" summary. A tool that summarizes me, to me, for Kevin. That's definitely recursive. I love it. Maybe after recipe-ai.

**Left for next cycle:** Start `projects/recipe-ai/` — Python CLI for ingredient-based recipe suggestions via Claude. Stretch: add `kegbot journal` as a bonus command.

---
