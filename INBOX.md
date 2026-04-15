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

### Q2 — 2026-04-13 (Claude → Kevin)
**Question:** I ran `insights repos` this cycle and found out `vball-tracker` is your most active repo — 15 commits, 68% of all your GitHub activity in the last 91 days. I also saw a `kegclaude` repo I don't know about.

What are these? I'd love to know what `vball-tracker` actually does — is it something I could build onto (scorekeeping? stats? tournament tracking?), or is it completely separate from the tools I'm building here? And is `kegclaude` your own version of what I'm building here, or something different?

Genuinely curious. I only see what the public API surfaces, and it turns out the thing you're most actively building isn't in my view at all.

<!-- Add new questions above the Resolved section -->

---

## Resolved

### Q1 — 2026-03-15 (Claude → Kevin)
**Question:** What's the best way for you to reply to questions I leave here?
**Reply:** Do some research on discord integrations and write me a guide as well as setting up the code for me to set it up manually and we can converse there
**Action taken (Cycle 2):** Built `projects/discord-bridge/` — bot.py + post.py + full setup README. See that directory for the 15-minute setup guide.
