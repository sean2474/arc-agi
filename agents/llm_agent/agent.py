"""LLMAgent — 매 스텝 4단계 사이클 에이전트.

OBSERVE → DECIDE(1액션) → EXECUTE → EVALUATE → UPDATE
"""

import time
import functools

from arcengine import GameAction, GameState


def timed(fn):
    """메서드 실행 시간을 출력하는 데코레이터."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = fn(*args, **kwargs)
        elapsed = time.time() - start
        print(f"  [{fn.__name__}] {elapsed:.1f}s")
        return result
    return wrapper

from .const import ACTION_NUM_TO_NAME, get_current_phase, get_phase_hint
from .grid_utils import frame_to_compact
from .models import StepRecord
from .prompts import SYSTEM_PROMPT, parse_llm_response
from .steps import do_observe, do_decide, do_incident, do_evaluate, do_update


class LLMAgent:
    """매 스텝 OBSERVE → DECIDE(1액션) → EXECUTE → EVALUATE → UPDATE."""

    def __init__(
        self,
        model: str = "qwen3-8b",
        max_tokens: int | None = None,
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
        self.world_model: dict = self._init_world_model()
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
        self._step_prompts: dict = {}  # 현재 스텝의 프롬프트 수집용

    @staticmethod
    def _init_world_model() -> dict:
        return {
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

    def setup(self, game_info: dict):
        self.game_info = game_info
        self.available_values = {a["value"] for a in game_info["available_actions"]}
        actions = {}
        for a in game_info["available_actions"]:
            name = ACTION_NUM_TO_NAME.get(a["value"], f"action{a['value']}")
            entry = {"effect": "unknown", "confidence": 0.0}
            if name == "click":
                entry["target"] = None
            actions[name] = entry
        self.world_model["actions"] = actions

    def reset_for_new_level(self):
        """레벨 클리어 후 호출. phase 리셋, 지식은 carry-over."""
        prev_goal = self.world_model.get("goal", {}).get("description", "unknown")

        self.world_model["phase"] = "static_observation"

        # objects: position만 리셋, type/속성은 유지
        for obj in self.world_model.get("objects", {}).values():
            obj["position"] = "unknown (new level)"
            obj["interaction_tested"] = False

        # interactions, dangers는 유지 (전 레벨 지식 carry-over)
        # actions는 유지 (LLM이 OBSERVE에서 조절)

        self.world_model["immediate_plan"] = {"description": "observe new level", "confidence": 0.5}
        self.world_model["strategic_plan"] = {
            "description": f"previous level cleared by: {prev_goal}. re-observe and apply similar strategy.",
            "confidence": 0.4,
        }
        self.prev_grid = None

    # ── LLM 호출 래퍼 ──

    def _call_llm(self, user_msg: str, retries: int = 3, label: str = "") -> dict | None:
        if label:
            self._step_prompts[label] = user_msg
        import time
        for attempt in range(retries):
            try:
                kwargs = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                }
                if self.max_tokens is not None:
                    kwargs["max_tokens"] = self.max_tokens
                response = self.client.chat.completions.create(**kwargs)
                self.llm_call_count += 1
                usage = response.usage
                if usage:
                    self.total_input_tokens += usage.prompt_tokens or 0
                    self.total_output_tokens += usage.completion_tokens or 0
                raw_text = response.choices[0].message.content

                parsed = parse_llm_response(raw_text)
                if parsed is None:
                    print(f"  [PARSE_FAIL] raw (first 500):")
                    print(f"  {repr(raw_text[:500])}")
                return parsed
            except KeyboardInterrupt:
                raise
            except Exception as e:
                wait = 2 ** attempt * 5
                print(f"  [API_ERR] {e}, retry in {wait}s ({attempt+1}/{retries})")
                time.sleep(wait)
        print(f"  [API_FAIL] after {retries} retries")
        return None

    # ── 메인 인터페이스 ──

    def _merge_observe_objects(self, observe_result: dict):
        """OBSERVE 결과의 objects를 world_model에 merge."""
        obs_objects = observe_result.get("objects", {})
        if obs_objects and isinstance(obs_objects, dict):
            for k, v in obs_objects.items():
                if k in self.world_model["objects"]:
                    self.world_model["objects"][k].update(v)
                else:
                    self.world_model["objects"][k] = v
            self.world_model["phase"] = get_current_phase(self.world_model)
        return obs_objects

    @timed
    def get_next_action(self, step: int, obs) -> tuple[GameAction, StepRecord]:
        """매 스텝 호출. Phase에 따라 다른 사이클."""
        curr_grid = frame_to_compact(obs.frame[-1])
        curr_state = obs.state
        curr_levels = obs.levels_completed

        self._step_prompts = {}  # 새 스텝 시작 시 리셋
        report = None
        incident_result = None

        # EVALUATE + UPDATE (첫 스텝 제외)
        if self.prev_grid is not None:
            is_game_over = curr_state == GameState.GAME_OVER
            is_level_complete = curr_levels > self.prev_levels

            if is_game_over or is_level_complete:
                label = "DEATH" if is_game_over else "WIN"
                print(f"  [INCIDENT] {label}")
                incident_result = do_incident(self, curr_grid, is_game_over, is_level_complete, self.prev_levels, curr_levels)

            if is_level_complete:
                self.reset_for_new_level()

            print(f"  [EVALUATE]")
            report, discoveries = do_evaluate(self, curr_grid, incident_result)
            self.reports.append(report)

            print(f"  [UPDATE]")
            do_update(self, {"report": report, "goal_achieved": report.get("goal_achieved", False)}, discoveries, incident_result)
            self.world_model["phase"] = get_current_phase(self.world_model)

        phase = self.world_model.get("phase", "static_observation")
        print(f"  [{phase}]")

        # OBSERVE
        print(f"  [OBSERVE]")
        observe_result = do_observe(self, step, curr_grid, curr_levels)
        obs_objects = self._merge_observe_objects(observe_result)

        # Phase 1: OBSERVE만 하고 끝 (DECIDE/EXECUTE 없음)
        if phase == "static_observation":
            hypothesis = f"objects: {list(obs_objects.keys())}" if obs_objects else "no objects detected"
            challenge = ", ".join(observe_result.get("contradictions", []))
            record = StepRecord(
                step=step, action="observe_only", state=curr_state.value,
                levels_completed=curr_levels, grid=curr_grid,
                observation=str(observe_result.get("changes", "")),
                hypothesis=hypothesis, challenge=challenge,
                goal="static observation — no action taken",
                llm_phase="observe",
                prompts=dict(self._step_prompts) if self._step_prompts else None,
            )
            self.prev_grid = curr_grid
            self.prev_levels = curr_levels
            self.history.append(record)
            return None, record  # no action to execute

        # Phase 2~4: DECIDE(1액션) → EXECUTE
        print(f"  [DECIDE]")
        action, action_name, reasoning, goal = do_decide(self, observe_result)

        hypothesis = f"objects: {list(obs_objects.keys())}" if obs_objects else "no objects detected"
        challenge = ", ".join(observe_result.get("contradictions", []))

        record = StepRecord(
            step=step, action=action_name, state=curr_state.value,
            levels_completed=curr_levels, grid=curr_grid,
            reasoning=reasoning,
            observation=str(observe_result.get("changes", "")),
            hypothesis=hypothesis, challenge=challenge,
            goal=goal, llm_phase="observe+decide",
            report=report,
            prompts=dict(self._step_prompts) if self._step_prompts else None,
        )

        self.prev_grid = curr_grid
        self.prev_levels = curr_levels
        self.history.append(record)
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
