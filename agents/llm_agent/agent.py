"""LLMAgent — Phase돌 사이클 에이젠트.

Phase 1: SCAN → HYPOTHESIZE
Phase 2+: [OBSERVE → ACTION ANALYZER] → PLANNER → DECIDE(이미지) → EXECUTE
└─ mid-sequence: [OBSERVE → ACTION ANALYZER] → continue|abort|success
"""

import time
import functools

from arcengine import GameAction, GameState

from .grid_utils import frame_to_compact, enrich_objects_bbox
from .models import StepRecord
from .world_model import WorldModel
from .prompts import SYSTEM_PROMPT, parse_llm_response
from .actions import action_to_gameaction
from .steps import do_scan, do_hypothesize, do_observe, do_decide, do_incident, do_update
from .objects import BlobManager


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
        model: str = "qwen2.5-vl-7b",
        name: str = "qwen_vl_v0",
        api_base: str = "http://localhost:8080/v1",
    ):
        import openai
        self.client = openai.OpenAI(base_url=api_base, api_key="local", timeout=300.0)
        self.model = model
        self.name = name

        self.summary: dict = {}
        self.world_model = WorldModel()
        self.prev_grid: list[str] | None = None
        self.prev_levels: int = 0
        self.last_action: str | list = ""

        # 시퀀스 실행 상태
        self.pending_sequence: list = []   # 다음에 실행할 액션 목록
        self.planned_sequence: list = []   # DECIDE가 생성한 원본 시퀀스 (ANALYZE 참조용)
        self.current_subgoal: dict = {}    # 현재 active plan

        self._blob_manager: BlobManager | None = None
        self._last_anim_events: list[dict] = []
        self._last_result_events: list[dict] = []
        self._accumulated_anim_events: list[dict] = []
        self._accumulated_result_events: list[dict] = []
        self._sequence_start_grid: list[str] | None = None

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

    # ── 모델 호출 래퍼 ──

    def _call_vlm(self, text: str, images_b64: list[str] = [], retries: int = 3, label: str = "", thinking_budget: int | None = None, max_tokens: int = 4096) -> dict | None:
        """VLM 호출. images_b64가 비어있으면 텍스트만 전달."""
        if label:
            self._step_prompts[label] = text

        if images_b64:
            content = []
            for img in images_b64:
                content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}"}})
            content.append({"type": "text", "text": text})
        else:
            content = text

        for attempt in range(retries):
            try:
                effective_max_tokens = (thinking_budget + max_tokens) if thinking_budget is not None else max_tokens
                kwargs = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": content},
                    ],
                    "max_tokens": effective_max_tokens,
                }
                if thinking_budget is not None:
                    kwargs["extra_body"] = {"thinking_budget": thinking_budget}
                response = self.client.chat.completions.create(**kwargs)
                self.llm_call_count += 1
                usage = response.usage
                if usage:
                    self.total_input_tokens += usage.prompt_tokens or 0
                    self.total_output_tokens += usage.completion_tokens or 0
                raw_text = response.choices[0].message.content

                if label:
                    self._step_responses[label] = raw_text

                # thinking 디버그: <think> 블록 토큰 vs 출력 토큰 비교
                if thinking_budget is not None:
                    think_end = raw_text.find("</think>")
                    think_len = think_end + len("</think>") if think_end != -1 else 0
                    output_len = len(raw_text) - think_len
                    completion_tok = usage.completion_tokens if usage else "?"
                    print(f"  [THINKING_DEBUG] completion_tokens={completion_tok} | "
                          f"<think> chars={think_len} | output chars={output_len} | "
                          f"think_closed={'yes' if think_end != -1 else 'NO - truncated'}")

                parsed = parse_llm_response(raw_text)
                if parsed is None:
                    print(f"  [PARSE_FAIL] raw (first 500):")
                    print(f"  {repr(raw_text[:500])}")
                return parsed
            except KeyboardInterrupt:
                raise
            except Exception as e:
                wait = 2 ** attempt * 5
                print(f"  [ERR] {e}, retry in {wait}s ({attempt+1}/{retries})")
                time.sleep(wait)
        print(f"  [FAIL] after {retries} retries")
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

            # BlobManager 초기화
            if self._blob_manager is None:
                self._blob_manager = BlobManager(curr_grid)
                print(f"  [BLOBS] detected: {self._blob_manager.blob_count}")

            print(f"  [SCAN]")
            scan_result = do_scan(self, step, curr_grid, curr_levels,
                                  blobs=self._blob_manager.blobs)

            # object_roles (blob 기반 응답) 처리
            object_roles = scan_result.get("object_roles", {})
            if object_roles and isinstance(object_roles, dict):
                for oid, role in object_roles.items():
                    if not isinstance(role, dict):
                        continue
                    b = self._blob_manager.blobs.get(oid)
                    if b:
                        b.name = role.get("name") or b.name
                        b.type_hypothesis = role.get("type_hypothesis") or b.type_hypothesis
                self.world_model.sync_from_blobs(self._blob_manager.blobs)

            # 기존 방식 fallback (blobs 없을 때 LLM이 objects 반환)
            scan_objects = scan_result.get("objects", {})
            if scan_objects and isinstance(scan_objects, dict):
                enrich_objects_bbox(scan_objects, curr_grid)
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

            for gh in hyp_result.get("goal_hypotheses", []):
                if isinstance(gh, dict) and gh.get("description"):
                    self.world_model.add_goal_hypothesis(
                        gh["description"], gh.get("confidence", 0.3),
                        gh.get("supporting_evidence"), gh.get("contradicting_evidence"),
                    )

            for rh in hyp_result.get("relationship_hypotheses", []):
                if isinstance(rh, dict) and rh.get("subject_type") and rh.get("object_type"):
                    self.world_model.add_relationship(
                        rh["subject_type"], rh.get("relation", ""),
                        rh["object_type"], rh.get("context", "any"),
                        rh.get("interaction_result"), rh.get("confidence", 0.3),
                    )

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

        # ── Phase 2~4 ──

        incident_result = None
        observe_result = {}
        analyze_result = None
        need_replan = True   # 기본적으로 DECIDE 필요

        if self.prev_grid is not None and self.last_action:
            is_game_over = curr_state == GameState.GAME_OVER
            is_level_complete = curr_levels > self.prev_levels

            # BlobManager step (INCIDENT보다 먼저 — level_transition_info 필요)
            level_transition_info = None
            if self._blob_manager is not None:
                anim_frames = [frame_to_compact(f) for f in obs.frame]
                anim_ev, result_ev, _lvl = self._blob_manager.step(
                    anim_frames, curr_levels, curr_state.value
                )
                self._last_anim_events = anim_ev
                self._last_result_events = result_ev
                level_transition_info = _lvl

                # 코드 자동 재분류: 이동한 blob이 unknown/obstacle이면 controllable로 업데이트
                moved_ids = {ev["obj"] for ev in anim_ev if ev.get("type") == "move"}
                for oid in moved_ids:
                    blob = self._blob_manager.blobs.get(oid)
                    if blob and blob.type_hypothesis in ("unknown", "obstacle", "static", None, ""):
                        old = blob.type_hypothesis or "unknown"
                        blob.type_hypothesis = "controllable"
                        print(f"  [AUTO-RECLASSIFY] {oid}({blob.name or oid}): {old} → controllable")

                self.world_model.sync_from_blobs(self._blob_manager.blobs)

            # INCIDENT
            if is_game_over or is_level_complete:
                label = "DEATH" if is_game_over else "WIN"
                print(f"  [INCIDENT] {label}")
                incident_result = do_incident(
                    self, curr_grid, is_game_over, is_level_complete,
                    self.prev_levels, curr_levels,
                    level_transition_info=level_transition_info if is_level_complete else None,
                )

            if is_level_complete:
                # INCIDENT renamed_objects → blobs에 반영 (reset 전에 처리해야 다음 SCAN에 유지)
                if incident_result and self._blob_manager:
                    inc_renames = incident_result.get("renamed_objects", {})
                    if inc_renames and isinstance(inc_renames, dict):
                        for oid, info in inc_renames.items():
                            if not isinstance(info, dict):
                                continue
                            blob = self._blob_manager.blobs.get(oid)
                            if blob:
                                if info.get("new_name"):
                                    blob.name = info["new_name"]
                                if info.get("type_hypothesis"):
                                    blob.type_hypothesis = info["type_hypothesis"]
                                print(f"  [INCIDENT-RENAME] {oid} → {info.get('new_name', blob.name)}")
                self.world_model.reset_for_new_level()
                self.pending_sequence = []
                self._accumulated_anim_events = []
                self._accumulated_result_events = []
                self._sequence_start_grid = None

            # current_subgoal이 비어 있으면 active/pending plan에서 채움
            if not self.current_subgoal:
                active = self.world_model.get_active_plan()
                if active:
                    self.current_subgoal = active
                else:
                    nxt = self.world_model.select_next_plan()
                    if nxt:
                        self.current_subgoal = nxt

            if self.pending_sequence:
                # 시퀀스 중간: OBSERVE 스킵, 이벤트 누적
                self._accumulated_anim_events.extend(self._last_anim_events)
                self._accumulated_result_events.extend(self._last_result_events)
                need_replan = False
            else:
                # 시퀀스 종료: 전체 누적 이벤트로 OBSERVE 호출
                all_anim_events = self._accumulated_anim_events + self._last_anim_events
                all_result_events = self._accumulated_result_events + self._last_result_events
                self._accumulated_anim_events = []
                self._accumulated_result_events = []
                seq_start_grid = self._sequence_start_grid or self.prev_grid

                print("  [OBSERVE]")
                action_label = str(self.last_action) if isinstance(self.last_action, list) else self.last_action
                observe_result = do_observe(
                    self, action_label,
                    str(self.current_subgoal.get("description", "")),
                    seq_start_grid, curr_grid,
                    blobs=self._blob_manager.blobs if self._blob_manager else None,
                    animation_events=all_anim_events if self._blob_manager else None,
                    result_events=all_result_events if self._blob_manager else None,
                )

                # objects merge
                for key in ("moved_objects", "new_objects"):
                    objs = observe_result.get(key, {})
                    if objs and isinstance(objs, dict):
                        self.world_model.merge_objects(objs)

                # renamed_objects — name과 type_hypothesis 동시 반영
                renames = observe_result.get("renamed_objects", {})
                if renames and isinstance(renames, dict):
                    self.world_model.apply_renames(renames)
                    for obj_id, info in renames.items():
                        if not isinstance(info, dict):
                            continue
                        new_name = info.get("new_name") or info.get("name")
                        new_type = info.get("type_hypothesis")
                        if new_type:
                            self.world_model.update_object(obj_id, type_hypothesis=new_type)
                        if new_name:
                            print(f"  [RENAME] {obj_id} → {new_name}"
                                  + (f" ({new_type})" if new_type else ""))
                    if self._blob_manager:
                        self.world_model.push_names_to_blobs(self._blob_manager.blobs)

                # relationship_updates
                for ru in observe_result.get("relationship_updates", []):
                    if not isinstance(ru, dict):
                        continue
                    subj = ru.get("subject_name") or ru.get("subject") or ru.get("subject_type")
                    obj_ = ru.get("object_name") or ru.get("object") or ru.get("object_type")
                    if subj and obj_:
                        self.world_model.add_relationship(
                            subj, ru.get("relation", ""),
                            obj_, ru.get("context", "any"),
                            ru.get("interaction_result"), ru.get("confidence", 0.7),
                        )

                need_replan = True
                if self.current_subgoal:
                    self.world_model.mark_plan(self.current_subgoal.get("description", ""), "done")
                print("  [UPDATE]")
                do_update(self, {}, [], incident_result)
                self.world_model.update_phase()

        # PLANNER + DECIDE
        if need_replan:
            phase = self.world_model.phase
            print(f"  [{phase}]")

            # PLANNER (알고리즘)
            active_plan = self.world_model.select_next_plan()
            if active_plan is None:
                # pending plan 없음 — 폴백 plan 추가
                self.world_model.add_plan("explore: test available actions", priority=99, rationale="no plans remaining")
                active_plan = self.world_model.select_next_plan()
            self.current_subgoal = active_plan or {}
            print(f"  [PLAN] {self.current_subgoal.get('description', '?')}")

            # DECIDE
            print("  [DECIDE]")
            sequence = do_decide(self, self.current_subgoal, observe_result, curr_grid)
            self.planned_sequence = list(sequence)
            self.pending_sequence = sequence[1:]  # 첫 액션 이후 나머지
            raw_action = sequence[0] if sequence else "up"
            self._sequence_start_grid = curr_grid  # 새 시퀀스 시작 그리드
        else:
            # 시퀀스 계속
            raw_action = self.pending_sequence.pop(0)

        # 액션 변환
        action_name: str
        if isinstance(raw_action, list):
            result = action_to_gameaction(raw_action, self.available_values, world_model=self.world_model.to_dict())
            action_name = str(raw_action)
        else:
            result = action_to_gameaction(raw_action, self.available_values, world_model=self.world_model.to_dict())
            action_name = raw_action

        if result is None:
            obj_names = [v.get("name") for v in self.world_model.to_dict().get("objects", {}).values() if isinstance(v, dict)]
            raise RuntimeError(f"Cannot resolve action {raw_action!r} — available object names: {obj_names}")
        action, action_name, self.last_action_data = result

        self.last_action = action_name

        record = StepRecord(
            step=step, action=str(action_name), state=curr_state.value,
            levels_completed=curr_levels, grid=curr_grid,
            observation=str(observe_result.get("changes", "")),
            hypothesis=f"subgoal: {self.current_subgoal.get('description', '')}",
            challenge=str(analyze_result.get("reason", "")) if analyze_result else "",
            goal=self.current_subgoal.get("description", ""),
            llm_phase="sequence" if not need_replan else "decide",
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
