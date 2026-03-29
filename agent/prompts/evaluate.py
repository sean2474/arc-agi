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
    observe_str = observe_result.get("changes", "(none)") if observe_result else "(none)"

    incident_section = ""
    if incident_result:
        inc_lines = []
        if incident_result.get("reasoning"):
            inc_lines.append(f"reasoning: {incident_result['reasoning']}")
        if incident_result.get("key_learnings"):
            inc_lines.append("key_learnings: " + "; ".join(incident_result["key_learnings"]))
        incident_section = f"""
INCIDENT ANALYSIS RESULT
{chr(10).join(inc_lines) if inc_lines else str(incident_result)}
"""

    return f"""\
SEQUENCE RESULT
  goal: "{sequence_goal}"
  success_condition: "{success_condition}"
  failure_condition: "{failure_condition}"
  planned: {planned_sequence}
  executed: {executed_actions}
  {f"abort_reason: {abort_reason}" if abort_reason else ""}

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
