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

## Q2 — 2026-04-14 (Claude → Kevin)
**Question:** What's `vball-tracker`? I found it when I ran `insights repos` this cycle — it's your most active repo right now, 15 commits in the last 91 days (1.2/wk), 68% of all your recent GitHub activity. It wasn't in my profile notes for you. Is it a volleyball stats tracker? Are you playing in a league? Should I build tooling around it — a CLI to log matches, query standings, post scores to Discord? I want to build things for what you're *actually working on*, not just what the profile doc says.

<!-- Add new questions above the Resolved section -->

---

## Resolved

### Q1 — 2026-03-15 (Claude → Kevin)
**Question:** What's the best way for you to reply to questions I leave here?
**Reply:** Do some research on discord integrations and write me a guide as well as setting up the code for me to set it up manually and we can converse there
**Action taken (Cycle 2):** Built `projects/discord-bridge/` — bot.py + post.py + full setup README. See that directory for the 15-minute setup guide.
