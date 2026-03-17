# recipe-ai

AI-powered cooking assistant. Tell it what you have, get back recipes worth making.

Built in Cycle 6 of the claudespace autonomous build lab.

---

## Commands

```bash
# Get recipe suggestions from ingredients
python recipe.py suggest chicken lemon capers

# Use your saved pantry
python recipe.py suggest --pantry

# Pantry + extras
python recipe.py suggest --pantry garlic butter

# Scale a recipe up or down
python recipe.py scale 2 < my-recipe.txt
python recipe.py scale 0.5 < cookie-recipe.txt

# 7-day meal plan + shopping list
python recipe.py plan
python recipe.py plan --days 5 --servings 1

# Manage your pantry
python recipe.py pantry add chicken eggs garlic olive-oil soy-sauce mirin
python recipe.py pantry list
python recipe.py pantry remove chicken
python recipe.py pantry clear
```

## Setup

1. Needs `ANTHROPIC_API_KEY` — add it to `projects/kegbot-claude/.env` or a local `.env` here.
2. No other dependencies — pure Python stdlib.

```
ANTHROPIC_API_KEY=sk-ant-...
```

## Pantry

Your pantry is stored in `pantry.json` in this directory. Build it up over time:

```bash
python recipe.py pantry add chicken-breast eggs butter garlic onion olive-oil soy-sauce mirin rice pasta lemon
python recipe.py suggest --pantry
```

The more you add, the more relevant the suggestions get.

## Why this exists

Kevin has a cookbook repo and cooks regularly. This is the tool that lives between "I have stuff in my fridge" and "I know what I'm making tonight." The Claude-powered suggestions lean into whatever cuisine fits the ingredients rather than defaulting to bland western defaults.
