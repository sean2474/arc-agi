from ..const import ACTION_PROMPT_LINE, COLOR_PROMPT_LINE

SYSTEM_PROMPT = f"""\
You are playing an unknown game on a 64x64 grid.
Each cell is a hex digit (0-f = 16 colors). Game rules are unknown.

Color mapping: {COLOR_PROMPT_LINE}
Action mapping: {ACTION_PROMPT_LINE}

Goal: complete all levels (state → WIN)."""
