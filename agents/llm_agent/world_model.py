"""WorldModel — 게임 규칙에 대한 구조화된 가설 + confidence.

Facade 패턴: 내부 데이터는 메서드로만 접근.
"""

from .const import ACTION_NUM_TO_NAME, get_current_phase


class WorldModel:
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
            "immediate_plan": {"description": "analyze first frame to identify all objects", "confidence": 0.5},
            "strategic_plan": {"description": "identify all distinguishable objects on screen", "confidence": 0.5},
        }

    # ── Phase ──

    @property
    def phase(self) -> str:
        return self._data["phase"]

    def update_phase(self):
        self._data["phase"] = get_current_phase(self._data)

    # ── Actions ──

    def init_actions(self, available_actions: list[dict]):
        actions = {}
        for a in available_actions:
            name = ACTION_NUM_TO_NAME.get(a["value"], f"action{a['value']}")
            entry = {"effect": "unknown", "confidence": 0.0}
            if name == "click":
                entry["target"] = None
            actions[name] = entry
        self._data["actions"] = actions

    def get_actions(self) -> dict:
        return self._data["actions"]

    def update_action(self, name: str, effect: str, confidence: float):
        if name in self._data["actions"]:
            self._data["actions"][name]["effect"] = effect
            self._data["actions"][name]["confidence"] = confidence

    # ── Objects ──

    def get_objects(self) -> dict:
        return self._data["objects"]

    def merge_objects(self, new_objects: dict):
        for k, v in new_objects.items():
            if k in self._data["objects"]:
                self._data["objects"][k].update(v)
            else:
                self._data["objects"][k] = v

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
        """LLM이 반환한 updated_world_model을 안전하게 merge."""
        if not isinstance(updated_wm, dict):
            return

        # actions merge
        if "actions" in updated_wm:
            for k, v in updated_wm["actions"].items():
                if k in self._data["actions"] and isinstance(v, dict):
                    self._data["actions"][k].update(v)
                else:
                    self._data["actions"][k] = v

        # objects merge
        if "objects" in updated_wm:
            self.merge_objects(updated_wm["objects"])

        # 나머지 필드 덮어쓰기 (actions, objects 제외)
        skip = {"actions", "objects"}
        for k, v in updated_wm.items():
            if k not in skip and k in self._data:
                self._data[k] = v

    # ── 레벨 전환 ──

    def reset_for_new_level(self):
        prev_goal = self._data.get("goal", {}).get("description", "unknown")

        self._data["phase"] = "static_observation"

        for obj in self._data.get("objects", {}).values():
            obj["position"] = "unknown (new level)"
            obj["interaction_tested"] = False

        self._data["immediate_plan"] = {"description": "observe new level", "confidence": 0.5}
        self._data["strategic_plan"] = {
            "description": f"previous level cleared by: {prev_goal}. re-observe and apply similar strategy.",
            "confidence": 0.4,
        }

    # ── 직렬화 ──

    def to_dict(self) -> dict:
        """프롬프트/JSON 저장용. 읽기 전용 복사본."""
        import copy
        return copy.deepcopy(self._data)
