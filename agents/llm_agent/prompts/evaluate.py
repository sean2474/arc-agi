import json


def build_evaluate_message(
    sequence_goal: str,
    success_condition: str,
    failure_condition: str,
    planned_sequence: list,
    executed_actions: list[str],
    abort_reason: str | None,
    observe_result: dict,
    incident_result: dict | None = None,
) -> str:
    observe_str = json.dumps(observe_result, indent=2, ensure_ascii=False)

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

OBSERVATION (from visual analysis of before/after frames)
{observe_str}
{incident_section}Evaluate the sequence using the OBSERVATION above. Work through:

STEP 1 - GOAL CHECK: Did the executed actions achieve the stated goal?
  Use the observation — do NOT re-analyze frames independently.

STEP 2 - SURPRISES: Did anything unexpected happen?
  Anything that contradicts current knowledge?

STEP 3 - LESSONS: What should be remembered for future sequences?
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
- Base your evaluation ONLY on the OBSERVATION provided above.
- Focus ONLY on evaluating. Don't plan next actions.
- Be honest about failure. Don't rationalize bad results."""
