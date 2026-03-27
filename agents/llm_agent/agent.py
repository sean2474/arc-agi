"""LLMAgent — 사이클 기반 에이전트.

사이클: OBSERVE → DECIDE → EXECUTE → [INCIDENT] → EVALUATE → UPDATE → ...
Anthropic API 또는 OpenAI-compatible API (로컬 모델) 지원.
"""

import random
from dataclasses import dataclass

from arcengine import GameAction, GameState

from .const import get_max_sequence_length, ACTION_NAME_TO_NUM
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
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 1024,
        name: str = "claude_v0",
        backend: str = "anthropic",       # "anthropic" or "openai"
        api_base: str = "http://localhost:8080/v1",  # OpenAI-compatible endpoint
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.name = name
        self.backend = backend

        if backend == "anthropic":
            import anthropic
            self.client = anthropic.Anthropic()
        else:
            import openai
            self.client = openai.OpenAI(base_url=api_base, api_key="local")

        # 상태
        self.summary: dict = {}
        self.world_model: dict = {
            "game_type": {"hypothesis": "unknown", "confidence": 0.0},
            "actions": {},  # setup()에서 available_actions 기반으로 초기화
            "controllable": {"description": None, "confidence": 0.0},
            "goal": {"description": None, "confidence": 0.0},
            "objects": {},
            "dangers": [],
            "interactions": [],
        }
        self.sequence: list = []
        self.planned_sequence: list = []
        self.sequence_goal: str = ""
        self.success_condition: str = ""
        self.failure_condition: str = ""
        self.replan_conditions: list[str] = []
        self.confidence: float = 0.0
        self.prev_grid: list[str] | None = None
        self.prev_levels: int = 0

        # 시퀀스 실행 중 수집
        self.frame_before: list[str] = []
        self.executed_actions: list[str] = []
        self.observations: list[dict] = []

        # 누적 reports
        self.reports: list[dict] = []
        self.sequence_id: int = 0

        # 게임 정보
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
                if self.backend == "anthropic":
                    response = self.client.messages.create(
                        model=self.model,
                        max_tokens=self.max_tokens,
                        system=SYSTEM_PROMPT,
                        messages=[{"role": "user", "content": user_msg}],
                    )
                    self.llm_call_count += 1
                    self.total_input_tokens += response.usage.input_tokens
                    self.total_output_tokens += response.usage.output_tokens
                    raw_text = response.content[0].text
                else:
                    # OpenAI-compatible (로컬 모델)
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

    # ── STEP 2: DECIDE ──

    def _do_decide(self, observe_result: dict, curr_grid: list[str]):
        """DECIDE LLM 호출 → 시퀀스 세팅."""
        max_len = get_max_sequence_length(self.world_model)

        # untested actions 힌트
        untested = [k for k, v in self.world_model.get("actions", {}).items() if v.get("confidence", 0) == 0.0]
        hint = f"UNTESTED ACTIONS: {untested}. Consider testing one of these first." if untested else ""

        msg = build_decide_message(
            observe_result=observe_result,
            summary=self.summary,
            world_model=self.world_model,
            reports=self.reports,
            available_actions=self.game_info.get("available_actions", []),
            max_len=max_len,
            hint=hint,
        )
        parsed = self._call_llm(msg)

        if parsed is None:
            print(f"  ⚠️ DECIDE 파싱 실패, 랜덤 폴백")
            val = random.choice(list(self.available_values))
            self._init_sequence([val], "random exploration (parse failed)", "", "", 0.1)
            return None, "random exploration", None, None

        self.confidence = parsed.get("confidence", 0.5)
        raw_seq = parsed.get("sequence", parsed.get("next_sequence", []))

        effective_len = max(1, int(max_len * self.confidence))
        goal = parsed.get("sequence_goal", "")
        success_cond = parsed.get("success_condition", "")
        failure_cond = parsed.get("failure_condition", "")

        self._init_sequence(raw_seq[:effective_len], goal, success_cond, failure_cond, self.confidence)
        self.replan_conditions = parsed.get("replan_conditions", [])

        reasoning = parsed.get("reasoning", "")
        win_hyp = parsed.get("win_condition_hypothesis", "")
        return reasoning, goal, win_hyp, success_cond

    def _init_sequence(self, seq: list, goal: str, success_cond: str, failure_cond: str, confidence: float):
        """시퀀스 실행 준비 (공통)."""
        self.sequence = list(seq)
        self.planned_sequence = list(seq)
        self.sequence_goal = goal
        self.success_condition = success_cond
        self.failure_condition = failure_cond
        self.confidence = confidence
        self.frame_before = []  # _run_cycle에서 설정
        self.executed_actions = []
        self.observations = []
        self.sequence_id += 1

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
        """매 스텝 호출. 시퀀스 실행 or 3단계 사이클."""
        curr_grid = frame_to_compact(obs.frame[-1])
        curr_state = obs.state
        curr_levels = obs.levels_completed

        # 트리거 체크
        triggers, diff = detect_triggers(
            self.prev_grid, curr_grid,
            self.prev_levels, curr_state, curr_levels,
            self.replan_conditions,
        )

        need_cycle = False
        abort_reason = None

        if len(self.sequence) == 0 and len(self.executed_actions) == 0:
            # 첫 시작 — PLAN만 필요
            need_cycle = True
        elif len(self.sequence) == 0:
            # 시퀀스 정상 소진 — EVALUATE → UPDATE → PLAN
            need_cycle = True
        elif triggers:
            # 트리거 발생 — 시퀀스 중단 → EVALUATE → UPDATE → PLAN
            need_cycle = True
            abort_reason = ", ".join(triggers)
            self.sequence = []

        if need_cycle:
            action, record = self._run_cycle(
                step, curr_grid, curr_state, curr_levels, abort_reason,
            )
        else:
            action, record = self._execute_sequence(step, curr_grid, curr_state, curr_levels, diff)

        self.prev_grid = curr_grid
        self.prev_levels = curr_levels
        self.history.append(record)
        return action, record

    def _run_cycle(self, step, curr_grid, curr_state, curr_levels, abort_reason):
        """[INCIDENT] → EVALUATE → UPDATE → OBSERVE → DECIDE → 첫 액션 반환."""
        report = None
        incident_result = None

        # INCIDENT + EVALUATE + UPDATE (첫 시작이 아닌 경우에만)
        if self.executed_actions:
            is_game_over = curr_state == GameState.GAME_OVER
            is_level_complete = curr_levels > self.prev_levels

            if is_game_over or is_level_complete:
                label = "💀 DEATH" if is_game_over else "🎉 WIN"
                print(f"  🚨 INCIDENT ({label})...")
                incident_result = self._do_incident(
                    curr_grid,
                    game_over=is_game_over,
                    level_complete=is_level_complete,
                    prev_level=self.prev_levels,
                    curr_level=curr_levels,
                )

            print(f"  📊 EVALUATE...")
            report, discoveries = self._do_evaluate(
                abort_reason, curr_grid,
                incident_result=incident_result,
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

        # DECIDE
        print(f"  🧠 DECIDE...")
        reasoning, seq_goal, win_hyp, success_cond = self._do_decide(observe_result, curr_grid)
        self.frame_before = list(curr_grid)

        # 시퀀스에서 첫 액션 꺼내기
        if self.sequence:
            item = self.sequence.pop(0)
            result = sequence_item_to_action(item, self.available_values)
            action, action_name = result if result else (GameAction.ACTION1, "up(fallback)")
        else:
            action, action_name = GameAction.ACTION1, "up(empty_seq)"

        self.executed_actions.append(action_name)

        if self.prev_grid and curr_grid:
            self.observations.append({
                "step": step,
                "action": action_name,
            })

        # observe_result에서 hypothesis/challenge 추출
        game_type = observe_result.get("game_type_hypothesis", {})
        ctrl = observe_result.get("controllable_element", {})
        goal = observe_result.get("goal_hypothesis", {})
        hypothesis = f"game={game_type.get('type','?')}, control={ctrl.get('description','?')}, goal={goal.get('description','?')}"
        challenge = ", ".join(observe_result.get("contradictions", []))

        return action, StepRecord(
            step=step, action=action_name, state=curr_state.value,
            levels_completed=curr_levels, grid=curr_grid,
            trigger=abort_reason,
            reasoning=reasoning,
            observation=str(observe_result.get("changes_from_summary", "")),
            hypothesis=hypothesis, challenge=challenge,
            sequence_goal=seq_goal, llm_phase="observe+decide",
            report=report,
        )

    def _execute_sequence(self, step, curr_grid, curr_state, curr_levels, diff):
        """시퀀스에서 다음 액션 꺼내서 실행."""
        item = self.sequence.pop(0)
        result = sequence_item_to_action(item, self.available_values)
        action, action_name = result if result else (GameAction.ACTION1, "ACTION1(invalid)")

        self.executed_actions.append(action_name)

        self.observations.append({
            "step": step,
            "action": action_name,
        })

        return action, StepRecord(
            step=step, action=action_name, state=curr_state.value,
            levels_completed=curr_levels, grid=curr_grid,
            trigger=None, reasoning=None, observation=None,
            sequence_goal=self.sequence_goal, llm_phase=None,
        )

    def get_stats(self) -> dict:
        return {
            "llm_calls": self.llm_call_count,
            "total_steps": len(self.history),
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "world_model": self.world_model,
            "total_cycles": self.sequence_id,
            "reports": self.reports,
            "summary": self.summary,
        }
