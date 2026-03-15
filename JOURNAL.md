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
