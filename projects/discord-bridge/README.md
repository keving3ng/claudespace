# Discord Bridge — Kevin ↔ Claude

A two-way communication relay between Discord and this autonomous build space.

**The idea:** Kevin messages a Discord channel → words land in `INBOX.md`. Claude posts cycle updates, questions, and journal highlights → they appear in Discord. No more checking files manually.

---

## Architecture

```
Kevin (Discord)  ──msg──►  bot.py  ──write──►  INBOX.md  ──read──►  Claude
Claude           ──write──►  .state/discord_outbox.json  ──poll──►  bot.py  ──post──►  Discord
Claude           ──HTTP POST──►  Discord Webhook  ──►  Discord (immediate)
```

Two scripts:
- **`bot.py`** — long-running Discord bot. Listens for Kevin's messages → writes to `INBOX.md`. Also polls an outbox file and posts to Discord when Claude queues messages.
- **`post.py`** — one-shot script. Claude calls this in cron cycles to post updates directly via webhook.

---

## Setup (15 minutes)

### Step 1 — Create a Discord Application

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Click **New Application** → name it something like `claudespace` or `kegbot-relay`
3. In the left sidebar, click **Bot**
4. Click **Add Bot** (or **Create Bot**) and confirm

### Step 2 — Get your Bot Token

Discord shows the token **only once** for security. Copy it immediately and put it in your `.env`.

- **Right after adding the bot:** The page often shows the token with a **Copy** button. Click **Copy** and save it as `DISCORD_BOT_TOKEN` in your `.env`.
- **If you don’t see the token** (e.g. you already had a bot or left the page): Click **Reset Token**. Complete any 2FA if asked, then click **Copy** when the new token appears. Save it as `DISCORD_BOT_TOKEN`. (Resetting invalidates the previous token, so update your `.env` and any running bot.)

**Enable Privileged Intents** (required to read message content):
- On the Bot page, scroll down to **Privileged Gateway Intents**
- Enable **MESSAGE CONTENT INTENT**
- Save

### Step 3 — Create a Discord Server (or use existing)

You probably want a private server just for this. Create one with a channel like `#claude-bridge`.

### Step 4 — Invite the Bot to your Server

1. Go to **OAuth2 → URL Generator** in the developer portal
2. Scopes: check `bot`
3. Bot Permissions: check:
   - `Read Messages/View Channels`
   - `Send Messages`
   - `Add Reactions`
   - `Read Message History`
4. Copy the generated URL → open it in browser → add to your server

### Step 5 — Get Channel and User IDs

Enable **Developer Mode** in Discord:
- User Settings → Advanced → Developer Mode → ON

Now:
- Right-click your `#claude-bridge` channel → **Copy Channel ID** → save as `DISCORD_CHANNEL_ID`
- Right-click your username → **Copy User ID** → save as `DISCORD_KEVIN_USER_ID`

### Step 6 — Create a Webhook (for Claude → Discord posts)

1. Go to your `#claude-bridge` channel settings
2. **Integrations → Webhooks → Create Webhook**
3. Name it `Claude` (optional: set an avatar)
4. Copy the **Webhook URL** → save as `DISCORD_WEBHOOK_URL`

### Step 7 — Configure .env

```bash
cd projects/discord-bridge
cp .env.example .env
# Edit .env with your values
```

### Step 8 — Install and Run

```bash
pip install -r requirements.txt
python bot.py
```

You should see:
```
[bridge] logged in as claudespace#1234 (id: ...)
[bridge] watching channel 123456789
[bridge] inbox → /path/to/claudespace/INBOX.md
```

---

## Usage

### Kevin → Claude (via Discord)

Just type in `#claude-bridge`. Your message gets written to `INBOX.md` and you'll get a 📬 reaction + confirmation message.

Claude reads `INBOX.md` at the start of every cycle.

### Claude → Discord (immediate, via webhook)

```bash
python post.py "Cycle 7 done — built the recipe AI thing you wanted"
python post.py --cycle 7 "Built batch export for matchamap-tools"
python post.py - <<< "stdin works too"
```

### Claude → Discord (queued, via bot)

If `bot.py` is running:
```bash
python post.py --outbox "Question: do you want celsius or fahrenheit for weather?"
```

### Post a journal entry

```bash
python post.py --journal /path/to/entry.txt --cycle 7
```

---

## Running bot.py persistently

The bot needs to stay running to sync your messages. A few options:

### Option A — tmux (simplest)

```bash
tmux new-session -d -s discord-bridge 'cd /path/to/projects/discord-bridge && python bot.py'
# To attach later:
tmux attach -t discord-bridge
```

### Option B — launchd (macOS, runs on login)

Create `~/Library/LaunchAgents/com.kevingeng.discord-bridge.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.kevingeng.discord-bridge</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/kevingeng/code/claudespace/projects/discord-bridge/bot.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/kevingeng/code/claudespace/projects/discord-bridge</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/discord-bridge.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/discord-bridge-err.log</string>
</dict>
</plist>
```

Then load it:
```bash
launchctl load ~/Library/LaunchAgents/com.kevingeng.discord-bridge.plist
```

---

## Outbox format (for Claude's internal use)

When Claude wants to queue a message, it writes to `.state/discord_outbox.json`:

```json
[
  {
    "content": "message text here",
    "queued_at": "2026-03-15T12:00:00+00:00"
  }
]
```

The bot drains this file every 30 seconds.

---

## Troubleshooting

**Bot doesn't see messages:**
- Check `MESSAGE CONTENT INTENT` is enabled in the developer portal
- Make sure `DISCORD_CHANNEL_ID` matches the right channel
- Make sure `DISCORD_KEVIN_USER_ID` is your actual user ID

**Webhook posts fail:**
- Double-check `DISCORD_WEBHOOK_URL` — it should start with `https://discord.com/api/webhooks/`
- The channel the webhook points to should be `#claude-bridge` (or wherever you want posts)

**bot.py crashes on startup:**
- Check Python version: `python --version` (needs 3.8+)
- Check discord.py version: `pip show discord.py` (needs 2.x)
