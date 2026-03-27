"""WorldModel — 게임 규칙에 대한 구조화된 가설 + confidence.

Facade 패턴: 내부 데이터는 메서드로만 접근.
Object identity: instance_id + bbox.
Action confidence: context-dependent.
"""

import copy
from .const import ACTION_NUM_TO_NAME, get_current_phase


class WorldModel:
    _obj_counter = 0

    def __init__(self):
        self._data = {
            "phase": "static_observation",
            "game_type": {"hypothesis": "unknown", "confidence": 0.0},
            "actions": {},
            "controllable": {"description": None, "confidence": 0.0},
            "goal": {"description": None, "confidence": 0.0},
            "objects": {},
            "dangers": [],
            "interactions": [],
            "immediate_plan": {"description": "scan first frame", "confidence": 0.5},
            "strategic_plan": {"description": "identify all objects on screen", "confidence": 0.5},
        }

    # ── Phase ──

    @property
    def phase(self) -> str:
        return self._data["phase"]

    def update_phase(self):
        self._data["phase"] = get_current_phase(self._data)

    # ── Actions (context-dependent) ──

    def init_actions(self, available_actions: list[dict]):
        actions = {}
        for a in available_actions:
            name = ACTION_NUM_TO_NAME.get(a["value"], f"action{a['value']}")
            entry = {
                "effects": [{"context": "default", "effect": "unknown", "confidence": 0.0}],
            }
            if name == "click":
                entry["target"] = None
            actions[name] = entry
        self._data["actions"] = actions

    def get_actions(self) -> dict:
        return self._data["actions"]

    def get_action_confidence(self, name: str) -> float:
        """action의 최대 confidence 반환."""
        action = self._data["actions"].get(name, {})
        effects = action.get("effects", [])
        if not effects:
            return 0.0
        return max(e.get("confidence", 0.0) for e in effects)

    def add_action_effect(self, name: str, context: str, effect: str, confidence: float):
        """action에 새 context+effect 추가. 기존 context면 업데이트."""
        if name not in self._data["actions"]:
            return
        effects = self._data["actions"][name]["effects"]
        for e in effects:
            if e["context"] == context:
                e["effect"] = effect
                e["confidence"] = confidence
                return
        effects.append({"context": context, "effect": effect, "confidence": confidence})

    # ── Objects (instance_id + bbox) ──

    def get_objects(self) -> dict:
        return self._data["objects"]

    def _next_obj_id(self) -> str:
        WorldModel._obj_counter += 1
        return f"obj_{WorldModel._obj_counter:03d}"

    def add_object(self, value: str, bbox: dict, type_hypothesis: str = "unknown") -> str:
        """새 오브젝트 추가. instance_id 반환."""
        obj_id = self._next_obj_id()
        self._data["objects"][obj_id] = {
            "instance_id": obj_id,
            "value": value,
            "type_hypothesis": type_hypothesis,
            "bbox": bbox,
            "clickable": False,
            "interaction_tested": False,
        }
        return obj_id

    def merge_objects(self, new_objects: dict):
        """LLM이 반환한 objects를 merge. 기존 키면 update, 새 키면 추가."""
        for k, v in new_objects.items():
            if k in self._data["objects"]:
                self._data["objects"][k].update(v)
            else:
                self._data["objects"][k] = v

    def update_object(self, obj_id: str, **kwargs):
        if obj_id in self._data["objects"]:
            self._data["objects"][obj_id].update(kwargs)

    def get_object_center(self, obj_id: str) -> tuple[int, int] | None:
        """bbox에서 center 좌표 계산. (x, y) 반환."""
        obj = self._data["objects"].get(obj_id)
        if not obj or "bbox" not in obj:
            return None
        bbox = obj["bbox"]
        x = (bbox.get("col_min", 0) + bbox.get("col_max", 0)) // 2
        y = (bbox.get("row_min", 0) + bbox.get("row_max", 0)) // 2
        return (x, y)

    # ── Controllable ──

    def get_controllable(self) -> dict:
        return self._data["controllable"]

    def set_controllable(self, description: str, confidence: float):
        self._data["controllable"] = {"description": description, "confidence": confidence}

    # ── Goal ──

    def get_goal(self) -> dict:
        return self._data["goal"]

    def set_goal(self, description: str, confidence: float):
        self._data["goal"] = {"description": description, "confidence": confidence}

    # ── Dangers ──

    def get_dangers(self) -> list:
        return self._data["dangers"]

    def add_danger(self, danger: dict):
        self._data["dangers"].append(danger)

    # ── Interactions ──

    def get_interactions(self) -> list:
        return self._data["interactions"]

    def add_interaction(self, interaction: dict):
        self._data["interactions"].append(interaction)

    # ── Plans ──

    def get_immediate_plan(self) -> dict:
        return self._data["immediate_plan"]

    def set_immediate_plan(self, description: str, confidence: float):
        self._data["immediate_plan"] = {"description": description, "confidence": confidence}

    def get_strategic_plan(self) -> dict:
        return self._data["strategic_plan"]

    def set_strategic_plan(self, description: str, confidence: float):
        self._data["strategic_plan"] = {"description": description, "confidence": confidence}

    # ── Game Type ──

    def get_game_type(self) -> dict:
        return self._data["game_type"]

    def set_game_type(self, hypothesis: str, confidence: float):
        self._data["game_type"] = {"hypothesis": hypothesis, "confidence": confidence}

    # ── Bulk update (LLM UPDATE 결과 반영) ──

    def apply_llm_update(self, updated_wm: dict):
        if not isinstance(updated_wm, dict):
            return

        if "actions" in updated_wm:
            for name, action_data in updated_wm["actions"].items():
                if name in self._data["actions"]:
                    # effects merge
                    if "effects" in action_data:
                        for new_effect in action_data["effects"]:
                            self.add_action_effect(
                                name,
                                new_effect.get("context", "default"),
                                new_effect.get("effect", "unknown"),
                                new_effect.get("confidence", 0.0),
                            )
                    else:
                        self._data["actions"][name].update(action_data)

        if "objects" in updated_wm:
            self.merge_objects(updated_wm["objects"])

        skip = {"actions", "objects"}
        for k, v in updated_wm.items():
            if k not in skip and k in self._data:
                self._data[k] = v

    # ── 레벨 전환 ──

    def reset_for_new_level(self):
        prev_goal = self._data.get("goal", {}).get("description", "unknown")
        prev_objects = copy.deepcopy(self._data.get("objects", {}))

        self._data["phase"] = "static_observation"
        self._data["objects"] = {}

        # 이전 레벨 objects 지식 보존용 (SCAN 후 매칭에 사용)
        self._prev_level_objects = prev_objects

        self._data["immediate_plan"] = {"description": "scan new level", "confidence": 0.5}
        self._data["strategic_plan"] = {
            "description": f"previous level cleared by: {prev_goal}. re-scan and apply similar strategy.",
            "confidence": 0.4,
        }

    def match_objects_from_prev_level(self, new_objects: dict) -> dict:
        """새 레벨 SCAN 결과와 이전 레벨 objects를 value로 매칭. 지식 carry-over."""
        prev = getattr(self, "_prev_level_objects", {})
        if not prev:
            return new_objects

        for new_id, new_obj in new_objects.items():
            for prev_id, prev_obj in prev.items():
                if prev_obj.get("value") == new_obj.get("value"):
                    new_obj["type_hypothesis"] = prev_obj.get("type_hypothesis", "unknown")
                    new_obj["clickable"] = prev_obj.get("clickable", False)
                    new_obj["interaction_tested"] = False
                    break
        return new_objects

    # ── 직렬화 ──

    def to_dict(self) -> dict:
        return copy.deepcopy(self._data)
