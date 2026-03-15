# Claude's 48-Hour Build Session for Kevin Geng

## About Kevin
- **Role:** Full-stack software engineer at Faire (Toronto)
- **Stack:** React, TypeScript, Java/Kotlin/Spring Boot, Python, AWS
- **Side project:** matchamap.club — a map-based matcha cafe finder
- **Interests:** cooking, ML/AI, Discord bots, personal automation, gaming
- **GitHub:** keving3ng (19 repos including kegbot personal assistant, cookbook, face-recog, discordbot)
- **Vibe:** Builder, pragmatic, interested in fun + useful tools

## Mission
Every hour for ~48 hours, wake up, read PROGRESS.md to see where we left off, and continue building useful/creative projects for Kevin. Each session should produce real, working code that Kevin can actually use.

## Rules
1. **Always read PROGRESS.md first** — it tracks what's been built and what's next
2. **Update PROGRESS.md at the end of every session** — increment run count, log what was done, set next task
3. **Produce working code** — don't just plan, actually write the files
4. **Be creative** — surprise Kevin with something he didn't ask for but will love
5. **Track run count** — if RUN_COUNT >= 48, write a final summary to FINAL_SUMMARY.md and stop

## Project Roadmap

### Phase 1: matchamap-tools (Hours 1–6)
Tools and data pipeline for matchamap.club. Kevin is actively building this.
- `projects/matchamap-tools/` — Python scripts to collect/rank matcha cafe data
- Yelp/Google Places API wrapper, data deduplication, quality scoring
- CLI to search and export cafe data as GeoJSON

### Phase 2: kegbot-claude (Hours 7–14)
Supercharge his existing kegbot personal assistant with Claude API.
- `projects/kegbot-claude/` — Python CLI personal assistant powered by Claude
- Daily briefing generator (weather + GitHub activity + calendar summary)
- Natural language task management
- GitHub activity summarizer

### Phase 3: recipe-ai (Hours 15–22)
AI-powered cooking assistant (ties to his cookbook repo).
- `projects/recipe-ai/` — TypeScript/Node CLI
- Ingredient-based recipe suggestions using Claude
- Recipe scaling calculator
- Weekly meal planner with shopping list generator

### Phase 4: dev-insights (Hours 23–32)
Developer productivity dashboard (terminal-based).
- `projects/dev-insights/` — Python terminal dashboard
- GitHub contribution heatmap in terminal
- Coding streak tracker
- Language breakdown over time
- Commit message quality analyzer

### Phase 5: idea-forge (Hours 33–40)
AI-powered project idea generator tailored to Kevin's profile.
- `projects/idea-forge/` — Python tool
- Analyzes trending GitHub repos in his tech stack
- Suggests weekend project ideas with rough implementation plans
- Outputs structured markdown ideas

### Phase 6: polish + integration (Hours 41–48)
- Wire tools together
- Write READMEs for each project
- Create a unified CLI launcher (`kevin-tools`)
- Generate a FINAL_SUMMARY.md showcasing everything built

## Session Protocol
At the start of each cron invocation:
1. `cat /Users/kevingeng/code/claudespace/PROGRESS.md`
2. Determine current phase and next task
3. Build it (write real code)
4. Test it if possible
5. Update PROGRESS.md (increment RUN_COUNT, describe what was done, set NEXT_TASK)
