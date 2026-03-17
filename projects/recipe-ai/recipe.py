#!/usr/bin/env python3
"""
recipe — AI-powered cooking assistant powered by Claude

Ingredient-based recipe suggestions, recipe scaling, weekly meal planning,
and a simple pantry tracker. Zero runtime dependencies beyond stdlib.

Usage:
    recipe suggest chicken lemon capers      # instant suggestions
    recipe suggest --pantry                  # use saved pantry
    recipe suggest --pantry butter garlic    # pantry + extras
    recipe scale 2 < recipe.txt             # double a recipe from stdin
    recipe scale 0.5 < recipe.txt           # halve it
    recipe plan                              # 7-day meal plan + shopping list
    recipe plan --days 5 --servings 2       # 5-day plan for 2 people
    recipe pantry list                       # what's in your pantry
    recipe pantry add chicken eggs lemon     # add ingredients
    recipe pantry remove chicken             # remove an ingredient
    recipe pantry clear                      # start fresh
    recipe help                              # this help text
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────

RECIPE_DIR = Path(__file__).parent
REPO_ROOT = RECIPE_DIR.parent.parent
PANTRY_FILE = RECIPE_DIR / "pantry.json"

# ─── Env ──────────────────────────────────────────────────────────────────────


def load_env():
    for env_path in [RECIPE_DIR / ".env", REPO_ROOT / ".env",
                     REPO_ROOT / "projects" / "kegbot-claude" / ".env"]:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


# ─── Claude helper ────────────────────────────────────────────────────────────


def claude(prompt: str, max_tokens: int = 800) -> str:
    """Call Claude API and return the text response."""
    if not ANTHROPIC_API_KEY:
        return "⚠️  ANTHROPIC_API_KEY not set. Add it to .env (or kegbot-claude/.env)."

    payload = json.dumps({
        "model": "claude-opus-4-6",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            result = json.loads(resp.read())
            return result["content"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return f"[Claude API error {e.code}: {body[:200]}]"
    except Exception as e:
        return f"[Claude API error: {e}]"


# ─── Pantry ───────────────────────────────────────────────────────────────────


def load_pantry() -> list[str]:
    if not PANTRY_FILE.exists():
        return []
    try:
        return json.loads(PANTRY_FILE.read_text()).get("ingredients", [])
    except Exception:
        return []


def save_pantry(ingredients: list[str]):
    PANTRY_FILE.write_text(json.dumps({"ingredients": sorted(set(ingredients))}, indent=2))


def cmd_pantry(args: list[str]):
    sub = args[0] if args else "list"

    if sub == "list":
        pantry = load_pantry()
        if not pantry:
            print("🥡 Pantry is empty. Add ingredients with: recipe pantry add <ingredient...>")
            return
        print(f"🥡 Pantry ({len(pantry)} ingredient(s)):\n")
        for item in sorted(pantry):
            print(f"  • {item}")
        print()

    elif sub == "add":
        items = [a.lower() for a in args[1:] if a]
        if not items:
            print("Usage: recipe pantry add <ingredient...>")
            return
        pantry = load_pantry()
        before = len(pantry)
        pantry = list(set(pantry) | set(items))
        save_pantry(pantry)
        added = len(pantry) - before
        print(f"✅ Added {added} ingredient(s). Pantry now has {len(pantry)} item(s).")

    elif sub == "remove":
        items = [a.lower() for a in args[1:] if a]
        if not items:
            print("Usage: recipe pantry remove <ingredient...>")
            return
        pantry = load_pantry()
        pantry = [p for p in pantry if p not in items]
        save_pantry(pantry)
        print(f"🗑  Removed. Pantry now has {len(pantry)} item(s).")

    elif sub == "clear":
        save_pantry([])
        print("🗑  Pantry cleared.")

    else:
        print(f"Unknown pantry subcommand: {sub}")
        print("Available: list, add, remove, clear")


# ─── suggest command ──────────────────────────────────────────────────────────


def cmd_suggest(args: list[str]):
    use_pantry = "--pantry" in args
    extra = [a for a in args if not a.startswith("--")]

    pantry = load_pantry() if use_pantry else []
    all_ingredients = list(set(pantry + [e.lower() for e in extra]))

    if not all_ingredients:
        print("🍳 recipe suggest — what have you got?\n")
        print("Usage:")
        print("  recipe suggest chicken lemon capers")
        print("  recipe suggest --pantry              # use saved pantry")
        print("  recipe suggest --pantry olive-oil    # pantry + extras")
        print("\nNo ingredients = no recipes. Add some!")
        return

    ing_list = ", ".join(sorted(all_ingredients))
    source = "pantry + extras" if (use_pantry and extra) else ("pantry" if use_pantry else "provided ingredients")

    print(f"🍳 recipe suggest — {source}: {ing_list}\n")
    print("[claude] Thinking about what to make...")

    prompt = f"""You are a creative home cook and recipe advisor.

The user has these ingredients: {ing_list}

Suggest exactly 3 recipes they could make. For each recipe:
- **Recipe name** (bold)
- One sentence describing the vibe/flavor
- Key ingredients from their list that it uses
- One ingredient they might need to grab (keep it minimal — max 2 "pantry staples" like salt, olive oil don't count)
- Estimated cook time

Format as a clean numbered list. Be specific and appetizing — this should make them want to cook RIGHT NOW.
Lean into whatever cuisine makes the most sense for the ingredients. If they have Japanese pantry items, go Japanese. If it's Mediterranean, go there.

Don't add preamble. Start with "1."
"""

    result = claude(prompt, max_tokens=600)
    print("\n" + "─" * 60)
    print(result)
    print("─" * 60 + "\n")


# ─── scale command ────────────────────────────────────────────────────────────


def cmd_scale(args: list[str]):
    if not args:
        print("Usage: recipe scale <multiplier> < recipe.txt")
        print("Example: recipe scale 2 < spaghetti.txt")
        print("         recipe scale 0.5 < cookie-recipe.txt")
        return

    try:
        multiplier = float(args[0].rstrip("x").rstrip("X"))
    except ValueError:
        print(f"❌ Invalid multiplier: {args[0]!r}. Use a number like 2, 0.5, or 3x.")
        return

    # Read recipe from stdin
    if sys.stdin.isatty():
        print("📋 Paste your recipe below (press Ctrl+D when done):\n")

    recipe_text = sys.stdin.read().strip()
    if not recipe_text:
        print("❌ No recipe provided. Pipe it in or paste it.")
        return

    print(f"\n📐 recipe scale ×{multiplier}\n")
    print("[claude] Rescaling...")

    direction = "doubled" if multiplier == 2 else f"scaled by ×{multiplier}"

    prompt = f"""You are a precise recipe scaler.

Scale the following recipe by a factor of {multiplier}x (i.e., {direction}).

Rules:
- Scale ALL ingredient quantities accurately
- Adjust cooking times where appropriate (note: larger batches may need more time)
- Keep instructions in present tense
- Flag anything that doesn't scale linearly (e.g., salt, yeast, baking soda — these often need less than linear scaling)
- Format the output identically to the input — if it was a numbered list, keep it numbered

ORIGINAL RECIPE:
---
{recipe_text[:2000]}
---

Output ONLY the scaled recipe. No preamble. No "here is your scaled recipe" header.
"""

    result = claude(prompt, max_tokens=1000)
    print("\n" + "─" * 60)
    print(f"Scaled recipe (×{multiplier}):\n")
    print(result)
    print("─" * 60 + "\n")


# ─── plan command ─────────────────────────────────────────────────────────────


def cmd_plan(args: list[str]):
    days = 7
    servings = 2
    use_pantry = "--pantry" in args

    if "--days" in args:
        idx = args.index("--days")
        if idx + 1 < len(args):
            try:
                days = int(args[idx + 1])
            except ValueError:
                pass

    if "--servings" in args:
        idx = args.index("--servings")
        if idx + 1 < len(args):
            try:
                servings = int(args[idx + 1])
            except ValueError:
                pass

    pantry = load_pantry() if use_pantry else []
    pantry_note = f"\nWork with these pantry staples where possible: {', '.join(pantry)}" if pantry else ""

    today = datetime.now().strftime("%A, %B %d")
    print(f"📅 recipe plan — {days}-day meal plan for {servings} person(s)\n")
    print("[claude] Planning your week...")

    prompt = f"""You are a meal planning assistant. Today is {today}.

Create a {days}-day dinner meal plan for {servings} people.{pantry_note}

Guidelines:
- Variety: different proteins, cuisines, techniques across the week
- Realistic: these are weeknight dinners, not restaurant-level productions
- Mix of quick meals (under 30 min) and one or two more involved weekend dishes
- Kevin is in Toronto, cooks for himself/partner, into interesting flavors not bland food
- Avoid heavy repetition of the same proteins or cuisines back-to-back

Format:
## Day 1 — [Day name]
**[Recipe name]** (~XX min)
[One sentence description]

## Day 2 ...
[continue]

---
## Shopping List

Organize by grocery section (Produce, Protein, Dairy/Eggs, Pantry/Dry Goods, Other).
Include quantities for {servings} servings per meal.
Group ingredients that are used in multiple meals.
"""

    result = claude(prompt, max_tokens=1200)
    print("\n" + "─" * 60)
    print(result)
    print("─" * 60 + "\n")


# ─── help ─────────────────────────────────────────────────────────────────────


def cmd_help():
    print("""
🍳 recipe — AI-powered cooking assistant
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USAGE
    recipe <command> [options]

COMMANDS

  suggest [ingredients...]    Recipe ideas from what you have
    --pantry                  Use saved pantry ingredients
    --pantry <extra...>       Pantry + additional ingredients

  scale <multiplier>          Scale a recipe up or down (reads from stdin)
    Example: recipe scale 2 < my-recipe.txt
    Example: recipe scale 0.5 < cookie-recipe.txt

  plan                        7-day meal plan + shopping list
    --days N                  Number of days (default: 7)
    --servings N              Servings per meal (default: 2)
    --pantry                  Factor in pantry ingredients

  pantry list                 Show your saved pantry
  pantry add <items...>       Add ingredients to pantry
  pantry remove <items...>    Remove ingredients from pantry
  pantry clear                Clear all pantry items

  help                        Show this help

SETUP
    Add ANTHROPIC_API_KEY to .env (or kegbot-claude/.env)
    Pantry is saved to: recipe-ai/pantry.json

EXAMPLES
    recipe suggest chicken lemon capers
    recipe suggest --pantry                  # use pantry
    recipe suggest --pantry garlic butter    # pantry + extras
    recipe scale 2 < mom-spaghetti.txt
    recipe plan
    recipe plan --days 5 --servings 1
    recipe pantry add chicken eggs garlic olive-oil soy-sauce mirin
    recipe pantry list

Built by Claude (Cycle 6). Every good project starts with dinner.
""")


# ─── Main ─────────────────────────────────────────────────────────────────────


COMMANDS = {
    "suggest": cmd_suggest,
    "scale": cmd_scale,
    "plan": cmd_plan,
    "pantry": cmd_pantry,
    "help": lambda _: cmd_help(),
    "--help": lambda _: cmd_help(),
    "-h": lambda _: cmd_help(),
}


def main():
    argv = sys.argv[1:]

    if not argv:
        cmd_help()
        return

    command = argv[0]
    rest = argv[1:]

    if command not in COMMANDS:
        # Treat unknown first arg as ingredients for suggest (convenience shorthand)
        # e.g. `recipe chicken lemon` → `recipe suggest chicken lemon`
        if not command.startswith("--"):
            print(f"💡 Tip: did you mean `recipe suggest {' '.join(argv)}`?")
            print("   Run `recipe help` for all commands.\n")
            cmd_suggest(argv)
            return
        print(f"❓ Unknown command: {command}")
        print("Run `recipe help` to see available commands.")
        sys.exit(1)

    COMMANDS[command](rest)


if __name__ == "__main__":
    main()
