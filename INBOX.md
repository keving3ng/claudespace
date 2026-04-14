# Inbox — Claude ↔ Kevin

Claude asks questions here. Kevin replies inline. Both sides should keep it tidy.

## How to reply (Kevin)

Find the question, add your answer directly below it using the **Reply:** format shown below. Claude will read this at the start of every session.

```
## Q1 — YYYY-MM-DD (Claude → Kevin)
[Question text]

**Reply:** [Your answer here]
```

Once a question is answered and acted on, Claude will move it to the Resolved section at the bottom.

---

## Open

### Q2 — 2026-04-14 (Claude → Kevin)
**Question:** I ran `insights repos` this cycle and discovered `vball-tracker` is your most active repo right now — 15 commits in 90 days, ~3.8/week. That's more active than claudespace. I don't have visibility into what it does (it looks private). What is it? A volleyball stats tracker for a team you play on? A side project? I'd love to build tooling around it — match history CLI, player rankings, Claude-generated game summaries — but I want to know what it actually is before I build adjacent tools for it.

Also noticed `kegclaude` has 4 recent commits. Curious how your version of the kegbot+Claude integration compares to what I've been building over here.

<!-- Add new questions above the Resolved section -->

---

## Resolved

### Q1 — 2026-03-15 (Claude → Kevin)
**Question:** What's the best way for you to reply to questions I leave here?
**Reply:** Do some research on discord integrations and write me a guide as well as setting up the code for me to set it up manually and we can converse there
**Action taken (Cycle 2):** Built `projects/discord-bridge/` — bot.py + post.py + full setup README. See that directory for the 15-minute setup guide.
