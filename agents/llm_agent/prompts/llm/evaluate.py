import json


def build_evaluate_message(
    sequence_goal: str,
    success_condition: str,
    failure_condition: str,
    planned_sequence: list,
    executed_actions: list[str],
    abort_reason: str | None,
    observations: list[dict],
    frame_before: list[str],
    frame_after: list[str],
    incident_result: dict | None = None,
) -> str:
    obs_str = json.dumps(observations, indent=2, ensure_ascii=False) if observations else "[]"

    incident_section = ""
    if incident_result:
        incident_section = f"""
INCIDENT ANALYSIS RESULT
{json.dumps(incident_result, indent=2, ensure_ascii=False)}
"""

    return f"""\
SEQUENCE RESULT
  goal: "{sequence_goal}"
  success_condition: "{success_condition}"
  failure_condition: "{failure_condition}"
  planned: {json.dumps(planned_sequence)}
  executed: {json.dumps(executed_actions)}
  abort_reason: {abort_reason or "null (completed normally)"}

OBSERVATIONS DURING SEQUENCE
{obs_str}

FRAME BEFORE
{chr(10).join(frame_before)}

FRAME AFTER
{chr(10).join(frame_after)}
{incident_section}
Before evaluating, work through these steps:

STEP 1 - COMPARE: Compare FRAME BEFORE and FRAME AFTER.
  What moved? What appeared? What disappeared?

STEP 2 - GOAL CHECK: Did the sequence achieve its stated goal?
  Check against success_condition and failure_condition.

STEP 3 - SURPRISES: Did anything unexpected happen?
  Anything that contradicts current knowledge?

STEP 4 - LESSONS: What should be remembered for future sequences?
  What worked? What didn't? What should never be tried again?

Then respond in JSON:
{{
  "goal_achieved": true,
  "goal_evaluation": "why succeeded or failed",
  "confidence": 0.6,
  "new_discoveries": ["discovery1", "discovery2"],
  "report": {{
    "sequence_goal": "the goal",
    "actions_taken": ["down", "down", "right"],
    "goal_achieved": true,
    "reasoning": "what happened and why",
    "key_learnings": ["learning1"]
  }}
}}

Rules:
- Focus ONLY on evaluating. Don't plan next actions.
- Be honest about failure. Don't rationalize bad results.
- STEP 4 (LESSONS) feeds into REPORTS that prevent repeating mistakes."""
