"""STEP 4: UPDATE — summary + world_model 갱신."""

from ..prompts import build_update_message


def _merge_dict_field(existing: dict, new: dict) -> dict:
    """기존 dict에 새 dict를 merge. 기존 키는 update, 새 키는 추가."""
    for k, v in new.items():
        if k in existing and isinstance(existing[k], dict) and isinstance(v, dict):
            existing[k].update(v)
        else:
            existing[k] = v
    return existing


def do_update(agent, evaluation: dict, discoveries: list[str], incident_result: dict | None = None):
    msg = build_update_message(
        summary=agent.summary,
        world_model=agent.world_model,
        evaluation=evaluation,
        discoveries=discoveries,
        incident_result=incident_result,
    )
    parsed = agent._call_llm(msg)

    if parsed is None:
        print(f"  [PARSE_FAIL] UPDATE, keeping current state")
        return

    updated = parsed.get("updated_summary")
    if updated and isinstance(updated, dict):
        agent.summary = updated

    updated_wm = parsed.get("updated_world_model")
    if updated_wm and isinstance(updated_wm, dict):
        # actions merge
        if "actions" in updated_wm:
            _merge_dict_field(agent.world_model.setdefault("actions", {}), updated_wm.pop("actions"))

        # objects merge
        if "objects" in updated_wm:
            _merge_dict_field(agent.world_model.setdefault("objects", {}), updated_wm.pop("objects"))

        # 나머지 필드는 덮어쓰기
        agent.world_model.update(updated_wm)
