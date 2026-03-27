"""LLMAgent — Phase별 사이클 에이전트.

Phase 1: SCAN → UPDATE
Phase 2+: DECIDE → EXECUTE → OBSERVE → EVALUATE → UPDATE
"""

import time
import functools

from arcengine import GameAction, GameState

from .grid_utils import frame_to_compact
from .models import StepRecord
from .world_model import WorldModel
from .prompts import SYSTEM_PROMPT, parse_llm_response
from .steps import do_scan, do_hypothesize, do_observe, do_decide, do_incident, do_evaluate, do_update


def timed(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = fn(*args, **kwargs)
        print(f"  [{fn.__name__}] {time.time() - start:.1f}s")
        return result
    return wrapper


class LLMAgent:
    """Phase 1: SCAN → UPDATE. Phase 2+: DECIDE → EXECUTE → OBSERVE → EVALUATE → UPDATE."""

    def __init__(
        self,
        model: str = "qwen3-8b",
        max_tokens: int | None = None,
        name: str = "qwen3_v0",
        api_base: str = "http://localhost:8080/v1",
        vlm_model: str = "qwen3-vl-30b",
        vlm_api_base: str = "http://localhost:8081/v1",
    ):
        import openai
        self.client = openai.OpenAI(base_url=api_base, api_key="local")
        self.vlm_client = openai.OpenAI(base_url=vlm_api_base, api_key="local")
        self.model = model
        self.vlm_model = vlm_model
        self.max_tokens = max_tokens
        self.name = name

        self.summary: dict = {}
        self.world_model = WorldModel()
        self.success_condition: str = ""
        self.failure_condition: str = ""
        self.prev_grid: list[str] | None = None
        self.prev_levels: int = 0
        self.last_action: str = ""
        self.last_goal: str = ""

        self.reports: list[dict] = []
        self.game_info: dict = {}
        self.available_values: set[int] = set()

        self.history: list[StepRecord] = []
        self.llm_call_count: int = 0
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self._step_prompts: dict = {}
        self._step_responses: dict = {}

    def setup(self, game_info: dict):
        self.game_info = game_info
        self.available_values = {a["value"] for a in game_info["available_actions"]}
        self.world_model.init_actions(game_info["available_actions"])

    # ── VLM 호출 래퍼 (이미지 입력) ──

    def _call_vlm(self, text: str, images_b64: list[str], retries: int = 3, label: str = "") -> dict | None:
        """VLM 호출. 이미지 + 텍스트 → JSON 응답."""
        if label:
            self._step_prompts[label] = text
        content = []
        for img in images_b64:
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}"}})
        content.append({"type": "text", "text": text})

        for attempt in range(retries):
            try:
                response = self.vlm_client.chat.completions.create(
                    model=self.vlm_model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": content},
                    ],
                )
                self.llm_call_count += 1
                usage = response.usage
                if usage:
                    self.total_input_tokens += usage.prompt_tokens or 0
                    self.total_output_tokens += usage.completion_tokens or 0
                raw_text = response.choices[0].message.content

                if label:
                    self._step_responses[label] = raw_text

                parsed = parse_llm_response(raw_text)
                if parsed is None:
                    print(f"  [PARSE_FAIL] VLM raw (first 500):")
                    print(f"  {repr(raw_text[:500])}")
                return parsed
            except KeyboardInterrupt:
                raise
            except Exception as e:
                wait = 2 ** attempt * 5
                print(f"  [VLM_ERR] {e}, retry in {wait}s ({attempt+1}/{retries})")
                time.sleep(wait)
        print(f"  [VLM_FAIL] after {retries} retries")
        return None

    # ── LLM 호출 래퍼 (텍스트만) ──

    def _call_llm(self, user_msg: str, retries: int = 3, label: str = "") -> dict | None:
        if label:
            self._step_prompts[label] = user_msg
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

                if label:
                    self._step_responses[label] = raw_text

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

    @timed
    def get_next_action(self, step: int, obs) -> tuple[GameAction | None, StepRecord]:
        curr_grid = frame_to_compact(obs.frame[-1])
        curr_state = obs.state
        curr_levels = obs.levels_completed
        self._step_prompts = {}
        self._step_responses = {}

        phase = self.world_model.phase

        # ── Phase 1: SCAN → HYPOTHESIZE → UPDATE ──
        if phase == "static_observation":
            print(f"  [{phase}]")
            print(f"  [SCAN]")
            scan_result = do_scan(self, step, curr_grid, curr_levels)

            # objects merge
            scan_objects = scan_result.get("objects", {})
            if scan_objects and isinstance(scan_objects, dict):
                self.world_model.merge_objects(scan_objects)

            # HYPOTHESIZE
            print(f"  [HYPOTHESIZE]")
            hyp_result = do_hypothesize(self, scan_result)

            # apply hypotheses to world model
            obj_hyps = hyp_result.get("object_hypotheses", {})
            for obj_id, hyp in obj_hyps.items():
                if obj_id in self.world_model.get_objects():
                    self.world_model.update_object(obj_id, type_hypothesis=hyp.get("type_hypothesis", "unknown"))

            game_type = hyp_result.get("game_type", {})
            if game_type:
                self.world_model.set_game_type(game_type.get("hypothesis", "unknown"), game_type.get("confidence", 0.3))

            goal_hyp = hyp_result.get("goal_hypothesis", {})
            if goal_hyp:
                self.world_model.set_goal(goal_hyp.get("description", "unknown"), goal_hyp.get("confidence", 0.3))

            self.world_model.update_phase()

            hypothesis = f"objects: {list(scan_objects.keys())}" if scan_objects else "no objects detected"
            reasoning = hyp_result.get("reasoning", "")

            record = StepRecord(
                step=step, action="scan_only", state=curr_state.value,
                levels_completed=curr_levels, grid=curr_grid,
                observation=str(scan_result.get("patterns", [])),
                hypothesis=hypothesis,
                reasoning=reasoning,
                goal="initial scan + hypothesize",
                llm_phase="scan+hypothesize",
                prompts=dict(self._step_prompts) if self._step_prompts else None,
                responses=dict(self._step_responses) if self._step_responses else None,
                world_model=self.world_model.to_dict(),
            )
            self.prev_grid = curr_grid
            self.prev_levels = curr_levels
            self.history.append(record)
            return None, record

        # ── Phase 2~4: OBSERVE → EVALUATE → UPDATE → DECIDE ──

        report = None
        incident_result = None
        observe_result = None

        # OBSERVE + EVALUATE + UPDATE (이전 액션이 있었으면)
        if self.prev_grid is not None and self.last_action:
            is_game_over = curr_state == GameState.GAME_OVER
            is_level_complete = curr_levels > self.prev_levels

            # INCIDENT
            if is_game_over or is_level_complete:
                label = "DEATH" if is_game_over else "WIN"
                print(f"  [INCIDENT] {label}")
                incident_result = do_incident(self, curr_grid, is_game_over, is_level_complete, self.prev_levels, curr_levels)

            if is_level_complete:
                self.world_model.reset_for_new_level()

            # OBSERVE (변화 관찰)
            print(f"  [OBSERVE]")
            observe_result = do_observe(self, self.last_action, self.last_goal, self.prev_grid, curr_grid)

            # observe 결과에서 objects merge
            for key in ("moved_objects", "new_objects"):
                objs = observe_result.get(key, {})
                if objs and isinstance(objs, dict):
                    self.world_model.merge_objects(objs)

            # EVALUATE
            print(f"  [EVALUATE]")
            report, discoveries = do_evaluate(self, curr_grid, incident_result)
            self.reports.append(report)

            # UPDATE
            print(f"  [UPDATE]")
            do_update(self, {"report": report, "goal_achieved": report.get("goal_achieved", False)}, discoveries, incident_result)
            self.world_model.update_phase()

        phase = self.world_model.phase
        print(f"  [{phase}]")

        # DECIDE (1개 액션)
        print(f"  [DECIDE]")
        action, action_name, reasoning, goal = do_decide(self, observe_result or {})

        # 다음 스텝을 위해 저장
        self.last_action = action_name
        self.last_goal = goal or ""

        hypothesis = ""
        challenge = ""
        if observe_result:
            hypothesis = str(observe_result.get("changes", ""))
            challenge = ", ".join(observe_result.get("contradictions", []))

        record = StepRecord(
            step=step, action=action_name, state=curr_state.value,
            levels_completed=curr_levels, grid=curr_grid,
            reasoning=reasoning,
            observation=hypothesis,
            hypothesis=f"phase: {phase}",
            challenge=challenge,
            goal=goal, llm_phase="decide",
            report=report,
            prompts=dict(self._step_prompts) if self._step_prompts else None,
            responses=dict(self._step_responses) if self._step_responses else None,
            world_model=self.world_model.to_dict(),
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
            "world_model": self.world_model.to_dict(),
            "reports": self.reports,
            "summary": self.summary,
        }
