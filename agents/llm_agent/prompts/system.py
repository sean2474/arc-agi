from ..const import ACTION_PROMPT_LINE

SYSTEM_PROMPT = f"""\
You are playing an unknown game on a 64x64 grid.
Game rules are unknown.

Action mapping: {ACTION_PROMPT_LINE}

Goal: complete all levels (state → WIN)."""
