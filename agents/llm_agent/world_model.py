"""WorldModel — 게임 규칙에 대한 구조화된 가설 + confidence.

Facade 패턴: 내부 데이터는 메서드로만 접근.
Object identity: instance_id + bbox.
Action confidence: context-dependent.
"""

import copy
from collections import Counter
from .const import ACTION_NUM_TO_NAME, get_current_phase


class WorldModel:
    _obj_counter = 0

    def __init__(self):
        self._data = {
            "phase": "static_observation",
            "game_type": {"hypothesis": "unknown", "confidence": 0.0},
            "actions": {},
            "controllable": {"description": None, "confidence": 0.0},
            "goal_hypotheses": [],
            "objects": {},
            "dangers": [],
            "interactions": [],
            "relationships": [],
            "plans": [
                {"description": "scan first frame", "priority": 1, "status": "pending", "confidence": 0.5, "rationale": "initial scan"}
            ],
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
        if not isinstance(new_objects, dict):
            return
        for k, v in new_objects.items():
            if not isinstance(v, dict):
                continue  # skip non-dict values (LLM sometimes returns strings)
            if k in self._data["objects"] and isinstance(self._data["objects"][k], dict):
                self._data["objects"][k].update(v)
            else:
                self._data["objects"][k] = v

    def update_object(self, obj_id: str, **kwargs):
        if obj_id in self._data["objects"]:
            self._data["objects"][obj_id].update(kwargs)

    def rename_object(self, obj_id: str, new_name: str):
        """object의 name 필드만 변경. id는 유지."""
        if obj_id in self._data["objects"]:
            self._data["objects"][obj_id]["name"] = new_name

    def apply_renames(self, renamed_objects: dict):
        """OBSERVE 결과의 renamed_objects 일괄 적용.
        형식: {"obj_001": {"new_name": "exit", "reason": "..."}}
        """
        for obj_id, info in renamed_objects.items():
            if not isinstance(info, dict):
                continue
            new_name = info.get("new_name") or info.get("name")
            if new_name:
                self.rename_object(obj_id, new_name)

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

    # ── Goal Hypotheses ──

    def get_goal_hypotheses(self) -> list:
        return self._data["goal_hypotheses"]

    def get_top_goal_hypothesis(self) -> dict | None:
        """confidence 가장 높은 goal hypothesis 반환."""
        hyps = self._data["goal_hypotheses"]
        if not hyps:
            return None
        return max(hyps, key=lambda h: h.get("confidence", 0.0))

    def add_goal_hypothesis(self, description: str, confidence: float,
                            supporting_evidence: list | None = None,
                            contradicting_evidence: list | None = None):
        """새 goal hypothesis 추가. 동일 description이면 update."""
        for h in self._data["goal_hypotheses"]:
            if h.get("description") == description:
                h["confidence"] = confidence
                if supporting_evidence:
                    h.setdefault("supporting_evidence", []).extend(supporting_evidence)
                if contradicting_evidence:
                    h.setdefault("contradicting_evidence", []).extend(contradicting_evidence)
                return
        self._data["goal_hypotheses"].append({
            "description": description,
            "confidence": confidence,
            "supporting_evidence": supporting_evidence or [],
            "contradicting_evidence": contradicting_evidence or [],
        })

    def set_goal_hypotheses(self, hypotheses: list):
        """LLM UPDATE 결과로 전체 교체."""
        if isinstance(hypotheses, list):
            self._data["goal_hypotheses"] = hypotheses

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

    # ── Relationships ──

    def get_relationships(self) -> list:
        return self._data["relationships"]

    def add_relationship(self, subject_type: str, relation: str, object_type: str,
                         context: str = "any", interaction_result=None, confidence: float = 0.3):
        """새 relationship 추가. (subject_type, relation, object_type) 중복이면 update."""
        for r in self._data["relationships"]:
            if (r.get("subject_type") == subject_type
                    and r.get("relation") == relation
                    and r.get("object_type") == object_type):
                r["context"] = context
                r["confidence"] = confidence
                if interaction_result is not None:
                    r["interaction_result"] = interaction_result
                return
        self._data["relationships"].append({
            "subject_type": subject_type,
            "relation": relation,
            "object_type": object_type,
            "context": context,
            "interaction_result": interaction_result,
            "confidence": confidence,
        })

    # ── Plans ──

    def get_plans(self) -> list:
        return self._data["plans"]

    def add_plan(self, description: str, priority: int = 99, confidence: float = 0.5, rationale: str = ""):
        """새 plan 추가 (pending 상태). 동일 description 이미 있으면 스킵."""
        desc_norm = description.strip().lower()
        if any(p.get("description", "").strip().lower() == desc_norm for p in self._data["plans"]):
            return
        self._data["plans"].append({
            "description": description,
            "priority": priority,
            "status": "pending",
            "confidence": confidence,
            "rationale": rationale,
        })

    def get_active_plan(self) -> dict | None:
        """status=active 인 항목 반환."""
        for p in self._data["plans"]:
            if p.get("status") == "active":
                return p
        return None

    def select_next_plan(self) -> dict | None:
        """알고리즘 Planner: pending 중 priority 가장 낙은 것 선택 → active."""
        pending = [p for p in self._data["plans"] if p.get("status") == "pending"]
        if not pending:
            return None
        chosen = min(pending, key=lambda p: p.get("priority", 99))
        chosen["status"] = "active"
        return chosen

    def mark_plan(self, description: str, status: str):
        """description으로 plan 찾아 status(done/failed) 마킹."""
        for p in self._data["plans"]:
            if p.get("description") == description:
                p["status"] = status
                return

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
            raw_objs = updated_wm["objects"]
            if isinstance(raw_objs, dict):
                # obj_NNN 키 형식만 허용 — LLM이 name-keyed 오브젝트 삽입 차단
                filtered = {k: v for k, v in raw_objs.items() if k.startswith("obj_")}
                if filtered:
                    self.merge_objects(filtered)

        if "goal_hypotheses" in updated_wm:
            self.set_goal_hypotheses(updated_wm["goal_hypotheses"])

        if "relationships" in updated_wm and isinstance(updated_wm["relationships"], list):
            for r in updated_wm["relationships"]:
                if isinstance(r, dict) and "subject_type" in r and "object_type" in r:
                    self.add_relationship(
                        r["subject_type"], r.get("relation", ""),
                        r["object_type"], r.get("context", "any"),
                        r.get("interaction_result"), r.get("confidence", 0.3),
                    )

        if "plans" in updated_wm and isinstance(updated_wm["plans"], list):
            for p in updated_wm["plans"]:
                if not isinstance(p, dict) or not p.get("description"):
                    continue
                existing = next((x for x in self._data["plans"] if x.get("description") == p["description"]), None)
                if existing:
                    existing.update(p)
                else:
                    self._data["plans"].append(p)

        skip = {"actions", "objects", "goal_hypotheses", "relationships", "plans"}
        for k, v in updated_wm.items():
            if k not in skip and k in self._data:
                self._data[k] = v

    # ── 레벨 전환 ──

    def reset_for_new_level(self):
        prev_objects = copy.deepcopy(self._data.get("objects", {}))
        top_goal = self.get_top_goal_hypothesis()
        prev_goal_desc = top_goal.get("description", "unknown") if top_goal else "unknown"

        self._data["phase"] = "static_observation"
        self._data["objects"] = {}

        # 이전 레벨 objects 지식 보존용 (SCAN 후 매칭에 사용)
        self._prev_level_objects = prev_objects

        # goal_hypotheses: confidence 유지하되 evidence 초기화
        for h in self._data["goal_hypotheses"]:
            h["supporting_evidence"] = []
            h["contradicting_evidence"] = []

        # relationships: interaction_result 있는 것만 유지, 가설은 confidence 반감
        kept = []
        for r in self._data["relationships"]:
            if r.get("interaction_result") is not None:
                kept.append(r)
            else:
                r["confidence"] = r.get("confidence", 0.3) / 2
                if r["confidence"] >= 0.1:
                    kept.append(r)
        self._data["relationships"] = kept

        # plans: done/failed 제거, 초기 plan 1개 추가
        self._data["plans"] = [
            {
                "description": f"scan new level. previous goal: {prev_goal_desc}",
                "priority": 1,
                "status": "pending",
                "confidence": 0.5,
                "rationale": "new level started",
            }
        ]

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

    _PROMPT_FIELDS = {"name", "shape", "colors", "position", "size", "type_hypothesis", "bbox"}

    def to_prompt_dict(self) -> dict:
        """프롬프트용 직렬화. objects를 list로, 내부 필드(bbox/instance_id 등) 제거."""
        d = copy.deepcopy(self._data)
        objects = d.get("objects", {})
        d["objects"] = [
            {k: v for k, v in obj.items() if k in self._PROMPT_FIELDS}
            for obj in objects.values()
            if isinstance(obj, dict)
        ]
        return d
