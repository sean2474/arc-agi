"""LLMAgent — 매 스텝 4단계 사이클 에이전트.

OBSERVE → DECIDE(1액션) → EXECUTE → EVALUATE → UPDATE
"""

from arcengine import GameAction, GameState

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
        self.world_model: dict = {
            "phase": "static_observation",
            "game_type": {"hypothesis": "unknown", "confidence": 0.0},
            "actions": {},
            "controllable": {"description": None, "confidence": 0.0},
            "goal": {"description": None, "confidence": 0.0},
            "objects": {},
            "dangers": [],
            "interactions": [],
            "immediate_plan": "analyze first frame to identify all objects",
            "strategic_plan": "identify all distinguishable objects on screen",
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
        self.world_model["actions"] = {
            ACTION_NUM_TO_NAME.get(a["value"], f"action{a['value']}"): {"effect": "unknown", "confidence": 0.0}
            for a in game_info["available_actions"]
        }

    # ── LLM 호출 래퍼 ──

    def _call_llm(self, user_msg: str, retries: int = 3) -> dict | None:
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
                    print(f"  🔍 parse fail — raw (first 500):")
                    print(f"  {repr(raw_text[:500])}")
                return parsed
            except KeyboardInterrupt:
                raise
            except Exception as e:
                wait = 2 ** attempt * 5
                print(f"  ⚠️ API error ({e}), retry in {wait}s ({attempt+1}/{retries})")
                time.sleep(wait)
        print(f"  ❌ API failed after {retries} retries")
        return None

    # ── 메인 인터페이스 ──

    def get_next_action(self, step: int, obs) -> tuple[GameAction, StepRecord]:
        """매 스텝: OBSERVE → DECIDE(1액션) 반환."""
        curr_grid = frame_to_compact(obs.frame[-1])
        curr_state = obs.state
        curr_levels = obs.levels_completed

        report = None
        incident_result = None

        # EVALUATE + UPDATE (첫 스텝 제외)
        if self.prev_grid is not None:
            is_game_over = curr_state == GameState.GAME_OVER
            is_level_complete = curr_levels > self.prev_levels

            if is_game_over or is_level_complete:
                label = "DEATH" if is_game_over else "WIN"
                print(f"  🚨 INCIDENT ({label})...")
                incident_result = do_incident(self, curr_grid, is_game_over, is_level_complete, self.prev_levels, curr_levels)

            print(f"  📊 EVALUATE...")
            report, discoveries = do_evaluate(self, curr_grid, incident_result)
            self.reports.append(report)

            print(f"  📝 UPDATE...")
            do_update(self, {"report": report, "goal_achieved": report.get("goal_achieved", False)}, discoveries, incident_result)

            # phase 갱신
            self.world_model["phase"] = get_current_phase(self.world_model)

        phase = self.world_model.get("phase", "static_observation")
        print(f"  [{phase}]")

        # OBSERVE
        print(f"  👁️ OBSERVE...")
        observe_result = do_observe(self, step, curr_grid, curr_levels)

        # OBSERVE 결과에서 objects를 world_model에 merge
        obs_objects = observe_result.get("objects", {})
        if obs_objects and isinstance(obs_objects, dict):
            for k, v in obs_objects.items():
                if k in self.world_model["objects"]:
                    self.world_model["objects"][k].update(v)
                else:
                    self.world_model["objects"][k] = v
            # phase 재계산 (objects가 추가됐을 수 있으므로)
            self.world_model["phase"] = get_current_phase(self.world_model)

        # DECIDE (1개 액션)
        print(f"  🧠 DECIDE...")
        action, action_name, reasoning, goal = do_decide(self, observe_result)

        # observe 결과에서 hypothesis/challenge 추출
        changes = observe_result.get("changes", "")
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
