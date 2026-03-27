"""LLMAgent — 사이클 기반 에이전트.

사이클: OBSERVE → DECIDE → EXECUTE → [INCIDENT] → EVALUATE → UPDATE → ...
Anthropic API 또는 OpenAI-compatible API (로컬 모델) 지원.
"""

import random
from dataclasses import dataclass

from arcengine import GameAction, GameState

from .const import ACTION_NAME_TO_NUM
from .grid_utils import frame_to_compact, detect_triggers
from .prompts import (
    SYSTEM_PROMPT,
    build_observe_message,
    build_decide_message,
    build_incident_gameover_message,
    build_incident_levelcomplete_message,
    build_evaluate_message,
    build_update_message,
    parse_llm_response,
)


# ── 시퀀스 항목 → GameAction 변환 ──

ACTION_NUM_MAP = {
    1: GameAction.ACTION1, 2: GameAction.ACTION2,
    3: GameAction.ACTION3, 4: GameAction.ACTION4,
    5: GameAction.ACTION5, 6: GameAction.ACTION6,
    7: GameAction.ACTION7,
}


def sequence_item_to_action(item, available_values: set[int]) -> tuple[GameAction, str] | None:
    """시퀀스 항목(이름 or 숫자) → (GameAction, display_name). 무효하면 None."""
    # click: ["click", x, y]
    if isinstance(item, list) and len(item) == 3:
        key = item[0]
        if key == "click" or key == 6:
            action = GameAction.ACTION6
            x, y = int(item[1]), int(item[2])
            action.set_data({"x": x, "y": y})
            return action, f"click({x},{y})"
        return None

    # 이름 → 숫자 변환
    if isinstance(item, str):
        val = ACTION_NAME_TO_NUM.get(item.lower())
        if val is None:
            return None
    else:
        val = int(item)

    if val not in available_values or val == 0:
        return None

    action = ACTION_NUM_MAP.get(val)
    if action is None:
        return None
    name = {v: k for k, v in ACTION_NAME_TO_NUM.items()}.get(val, f"action{val}")
    return action, name


# ── 스텝 기록 (replay용) ──

@dataclass
class StepRecord:
    step: int
    action: str
    state: str
    levels_completed: int
    grid: list[str]
    trigger: str | None = None
    reasoning: str | None = None
    observation: str | None = None
    hypothesis: str | None = None
    challenge: str | None = None
    sequence_goal: str | None = None
    llm_phase: str | None = None       # "observe+decide", "incident", "evaluate", "update", None(=seq exec)
    report: dict | None = None
    prompts: dict | None = None         # {"observe": "...", "decide": "...", ...}

    def to_dict(self) -> dict:
        d = {
            "step": self.step,
            "action": self.action,
            "state": self.state,
            "levels_completed": self.levels_completed,
            "grid": self.grid,
            "trigger": self.trigger,
            "reasoning": self.reasoning,
            "observation": self.observation,
            "hypothesis": self.hypothesis,
            "challenge": self.challenge,
            "sequence_goal": self.sequence_goal,
            "llm_phase": self.llm_phase,
        }
        if self.report:
            d["report"] = self.report
        if self.prompts:
            d["prompts"] = self.prompts
        return d


# ── 메인 에이전트 ──

class LLMAgent:
    """4단계 사이클 기반 Claude 에이전트.

    OBSERVE → DECIDE → EXECUTE → [INCIDENT] → EVALUATE → UPDATE → ...
    """

    def __init__(
        self,
        model: str = "qwen3-8b",
        max_tokens: int = 1024,
        name: str = "qwen3_v0",
        api_base: str = "http://localhost:8080/v1",
    ):
        import openai
        self.client = openai.OpenAI(base_url=api_base, api_key="local")
        self.model = model
        self.max_tokens = max_tokens
        self.name = name

        # 상태
        self.summary: dict = {}
        self.world_model: dict = {
            "game_type": {"hypothesis": "unknown", "confidence": 0.0},
            "actions": {},
            "controllable": {"description": None, "confidence": 0.0},
            "goal": {"description": None, "confidence": 0.0},
            "objects": {},
            "dangers": [],
            "interactions": [],
        }
        self.success_condition: str = ""
        self.failure_condition: str = ""
        self.prev_grid: list[str] | None = None
        self.prev_levels: int = 0

        # 누적
        self.reports: list[dict] = []
        self.game_info: dict = {}
        self.available_values: set[int] = set()

        # 기록
        self.history: list[StepRecord] = []
        self.llm_call_count: int = 0
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0

    def setup(self, game_info: dict):
        self.game_info = game_info
        self.available_values = {a["value"] for a in game_info["available_actions"]}
        # world_model.actions를 available_actions 기반으로 초기화
        from .const import ACTION_NUM_TO_NAME
        self.world_model["actions"] = {
            ACTION_NUM_TO_NAME.get(a["value"], f"action{a['value']}"): {"effect": "unknown", "confidence": 0.0}
            for a in game_info["available_actions"]
        }

    # ── LLM 호출 래퍼 ──

    def _call_llm(self, user_msg: str, retries: int = 3) -> dict | None:
        import time
        for attempt in range(retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                )
                self.llm_call_count += 1
                usage = response.usage
                if usage:
                    self.total_input_tokens += usage.prompt_tokens or 0
                    self.total_output_tokens += usage.completion_tokens or 0
                raw_text = response.choices[0].message.content

                parsed = parse_llm_response(raw_text)
                if parsed is None:
                    print(f"  🔍 파싱 실패 — raw 출력 (처음 500자):")
                    print(f"  {repr(raw_text[:500])}")
                return parsed
            except KeyboardInterrupt:
                raise
            except Exception as e:
                wait = 2 ** attempt * 5
                print(f"  ⚠️ API 에러 ({e}), {wait}s 후 재시도 ({attempt+1}/{retries})")
                time.sleep(wait)
        print(f"  ❌ API 호출 {retries}회 실패")
        return None

    # ── STEP 1: OBSERVE ──

    def _do_observe(self, step: int, curr_grid: list[str], curr_levels: int) -> dict:
        """OBSERVE LLM 호출 → 순수 관찰 결과 반환."""
        msg = build_observe_message(
            game_id=self.game_info.get("game_id", "unknown"),
            available_actions=self.game_info.get("available_actions", []),
            levels_completed=curr_levels,
            win_levels=self.game_info.get("win_levels", 0),
            step=step,
            summary=self.summary,
            world_model=self.world_model,
            grid=curr_grid,
            prev_grid=self.frame_before if self.frame_before else self.prev_grid,
        )
        parsed = self._call_llm(msg)
        if parsed is None:
            print(f"  ⚠️ OBSERVE 파싱 실패")
            return {"values": {}, "patterns": [], "unknowns": ["observe failed"]}
        return parsed

    # ── STEP 2: DECIDE (1개 액션) ──

    def _do_decide(self, observe_result: dict):
        """DECIDE LLM 호출 → 1개 액션 반환."""
        untested = [k for k, v in self.world_model.get("actions", {}).items() if v.get("confidence", 0) == 0.0]
        hint = f"UNTESTED ACTIONS: {untested}. Test one of these." if untested else ""

        msg = build_decide_message(
            observe_result=observe_result,
            summary=self.summary,
            world_model=self.world_model,
            reports=self.reports,
            available_actions=self.game_info.get("available_actions", []),
            hint=hint,
        )
        parsed = self._call_llm(msg)

        if parsed is None:
            print(f"  ⚠️ DECIDE 파싱 실패, 랜덤 폴백")
            val = random.choice(list(self.available_values))
            result = sequence_item_to_action(val, self.available_values)
            action, name = result if result else (GameAction.ACTION1, "up")
            return action, name, None, "random (parse failed)"

        # 1개 액션 추출
        raw_action = parsed.get("action", "up")
        result = sequence_item_to_action(raw_action, self.available_values)
        if result is None:
            result = (GameAction.ACTION1, "up")
        action, action_name = result

        reasoning = parsed.get("reasoning", "")
        goal = parsed.get("goal", parsed.get("sequence_goal", ""))
        self.success_condition = parsed.get("success_condition", "")
        self.failure_condition = parsed.get("failure_condition", "")

        return action, action_name, reasoning, goal

    # ── STEP 2a: INCIDENT (game_over / level_complete 시에만) ──

    def _do_incident(
        self,
        curr_grid: list[str],
        game_over: bool = False,
        level_complete: bool = False,
        prev_level: int = 0,
        curr_level: int = 0,
    ) -> dict | None:
        """INCIDENT LLM 호출 → 사건 분석. 해당 없으면 None."""
        if game_over:
            msg = build_incident_gameover_message(
                last_observations=self.observations,
                frame_before_death=self.prev_grid or [],
                frame_at_death=curr_grid,
            )
        elif level_complete:
            msg = build_incident_levelcomplete_message(
                prev_level=prev_level,
                curr_level=curr_level,
                last_observations=self.observations,
                frame_before_win=self.prev_grid or [],
                frame_at_win=curr_grid,
            )
        else:
            return None

        parsed = self._call_llm(msg)
        if parsed is None:
            print(f"  ⚠️ INCIDENT 파싱 실패")
            return None
        return parsed

    # ── STEP 2b: EVALUATE ──

    def _do_evaluate(
        self,
        abort_reason: str | None,
        curr_grid: list[str],
        incident_result: dict | None = None,
    ):
        """EVALUATE LLM 호출 → report 생성."""
        msg = build_evaluate_message(
            sequence_goal=self.sequence_goal,
            success_condition=getattr(self, "success_condition", ""),
            failure_condition=getattr(self, "failure_condition", ""),
            planned_sequence=self.planned_sequence,
            executed_actions=self.executed_actions,
            abort_reason=abort_reason,
            observations=self.observations,
            frame_before=self.frame_before,
            frame_after=curr_grid,
            incident_result=incident_result,
        )
        parsed = self._call_llm(msg)

        if parsed is None:
            print(f"  ⚠️ EVALUATE 파싱 실패")
            return {
                "sequence_id": self.sequence_id,
                "sequence_goal": self.sequence_goal,
                "actions_taken": self.executed_actions,
                "goal_achieved": False,
                "reasoning": "evaluate parse failed",
                "key_learnings": [],
                "abort_reason": abort_reason,
            }, []

        report = parsed.get("report", {})
        report["sequence_id"] = self.sequence_id
        report["abort_reason"] = abort_reason

        discoveries = parsed.get("new_discoveries", [])
        return report, discoveries

    # ── STEP 3: UPDATE ──

    def _do_update(self, evaluation: dict, discoveries: list[str], incident_result: dict | None = None):
        """UPDATE LLM 호출 → summary + world_model 갱신."""
        msg = build_update_message(
            summary=self.summary,
            world_model=self.world_model,
            evaluation=evaluation,
            discoveries=discoveries,
            incident_result=incident_result,
        )
        parsed = self._call_llm(msg)

        if parsed is None:
            print(f"  ⚠️ UPDATE 파싱 실패, summary/world_model 유지")
            return

        updated = parsed.get("updated_summary")
        if updated and isinstance(updated, dict):
            self.summary = updated

        updated_wm = parsed.get("updated_world_model")
        if updated_wm and isinstance(updated_wm, dict):
            # actions는 merge (기존 키 유지)
            if "actions" in updated_wm:
                for k, v in updated_wm["actions"].items():
                    if k in self.world_model["actions"]:
                        self.world_model["actions"][k].update(v)
                    else:
                        self.world_model["actions"][k] = v
                del updated_wm["actions"]
            self.world_model.update(updated_wm)

    # ── 메인 인터페이스 ──

    def get_next_action(self, step: int, obs) -> tuple[GameAction, StepRecord]:
        """매 스텝 호출. 매번 OBSERVE → DECIDE(1액션)."""
        curr_grid = frame_to_compact(obs.frame[-1])
        curr_state = obs.state
        curr_levels = obs.levels_completed

        action, record = self._run_cycle(step, curr_grid, curr_state, curr_levels)

        self.prev_grid = curr_grid
        self.prev_levels = curr_levels
        self.history.append(record)
        return action, record

    def _run_cycle(self, step, curr_grid, curr_state, curr_levels):
        """[INCIDENT] → EVALUATE → UPDATE → OBSERVE → DECIDE(1액션) 반환."""
        report = None
        incident_result = None

        # INCIDENT + EVALUATE + UPDATE (첫 스텝 제외)
        if self.prev_grid is not None:
            is_game_over = curr_state == GameState.GAME_OVER
            is_level_complete = curr_levels > self.prev_levels

            if is_game_over or is_level_complete:
                label = "DEATH" if is_game_over else "WIN"
                print(f"  🚨 INCIDENT ({label})...")
                incident_result = self._do_incident(
                    curr_grid,
                    game_over=is_game_over,
                    level_complete=is_level_complete,
                    prev_level=self.prev_levels,
                    curr_level=curr_levels,
                )

            print(f"  📊 EVALUATE...")
            last_action = self.history[-1].action if self.history else "unknown"
            last_goal = self.history[-1].goal if self.history else ""
            report, discoveries = self._do_evaluate(
                None, curr_grid, incident_result=incident_result,
            )
            self.reports.append(report)

            print(f"  📝 UPDATE...")
            eval_result = {
                "report": report,
                "goal_achieved": report.get("goal_achieved", False),
            }
            self._do_update(eval_result, discoveries, incident_result=incident_result)

        # OBSERVE
        print(f"  👁️ OBSERVE...")
        observe_result = self._do_observe(step, curr_grid, curr_levels)

        # DECIDE (1개 액션)
        print(f"  🧠 DECIDE...")
        action, action_name, reasoning, goal = self._do_decide(observe_result)

        # observe_result에서 hypothesis/challenge 추출
        game_type = observe_result.get("game_type_hypothesis", {})
        ctrl = observe_result.get("controllable_element", {})
        goal_hyp = observe_result.get("goal_hypothesis", {})
        hypothesis = f"game={game_type.get('type','?')}, control={ctrl.get('description','?')}, goal={goal_hyp.get('description','?')}"
        challenge = ", ".join(observe_result.get("contradictions", []))

        record = StepRecord(
            step=step, action=action_name, state=curr_state.value,
            levels_completed=curr_levels, grid=curr_grid,
            reasoning=reasoning,
            observation=str(observe_result.get("changes_from_summary", "")),
            hypothesis=hypothesis, challenge=challenge,
            sequence_goal=goal, llm_phase="observe+decide",
            report=report,
        )

        return action, record

    def get_stats(self) -> dict:
        return {
            "llm_calls": self.llm_call_count,
            "total_steps": len(self.history),
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "world_model": self.world_model,
            "reports": self.reports,
            "summary": self.summary,
        }
