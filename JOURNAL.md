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
