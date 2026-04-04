"""Planner-Actor-Observer 에이전트.

SRP에 따라 3개의 클래스로 분리:
- PlannerService: goal/subgoal 설정 (VLM, 드물게)
- ActorService: subgoal 방향으로 액션 선택 (VLM, 매 스텝)
- PAOAgent: 조율자 — Planner, Actor, Observer를 연결
"""

import numpy as np
from arcengine import GameAction

from src.agent.base import AgentResponse, GameState
from src.env.observer import Observation, Observer
from src.llm.client import LLMClient
from src.llm.frame_renderer import frame_to_base64
from src.llm.pao_prompts import (
    ACTOR_SYSTEM,
    PLANNER_SYSTEM,
    build_actor_message,
    build_planner_message,
)
from src.llm.response_parser import PlannerResponseParser, ResponseParser


class PlannerService:
    """Planner — 게임 상태를 분석하여 subgoal을 생성한다."""

    def __init__(
        self,
        client: LLMClient,
        parser: PlannerResponseParser,
    ) -> None:
        self._client = client
        self._parser = parser

    def create_plan(
        self,
        ext: dict,
        obs_history: list[str],
        frame_b64: str | None,
    ) -> list[dict]:
        """현재 상태에서 subgoal 리스트를 생성한다."""
        msg = build_planner_message(ext, obs_history)

        if frame_b64:
            content: str | list = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": frame_b64,
                    },
                },
                {"type": "text", "text": msg},
            ]
        else:
            content = msg

        response = self._client.send(
            system=PLANNER_SYSTEM,
            messages=[{"role": "user", "content": content}],
        )

        return self._parser.parse_subgoals(response.content)


class ActorService:
    """Actor — 현재 subgoal 방향으로 단일 액션을 선택한다."""

    def __init__(
        self,
        client: LLMClient,
        parser: ResponseParser,
    ) -> None:
        self._client = client
        self._parser = parser

    def select_action(
        self,
        ext: dict,
        subgoal: dict,
        obs_history: list[str],
        frame_b64: str | None,
    ) -> tuple[int, str]:
        """subgoal을 향한 단일 액션과 reasoning을 반환한다."""
        content = build_actor_message(ext, subgoal, obs_history[-5:], frame_b64)

        if isinstance(content, list):
            messages = [{"role": "user", "content": content}]
        else:
            messages = [{"role": "user", "content": content}]

        response = self._client.send(
            system=ACTOR_SYSTEM,
            messages=messages,
        )

        return self._parser.parse(response.content)


class PAOAgent:
    """Planner-Actor-Observer 조율자. Agent Protocol을 구조적으로 만족.

    PlannerService, ActorService, Observer를 조합하여
    게임 루프를 관리한다. (DIP: 모두 주입받음)
    """

    def __init__(
        self,
        planner: PlannerService,
        actor: ActorService,
        observer: Observer,
        max_replan: int = 5,
    ) -> None:
        self._planner = planner
        self._actor = actor
        self._observer = observer
        self._max_replan = max_replan

        # Planner 상태
        self._subgoals: list[dict] = []
        self._current_subgoal_idx: int = 0
        self._plan_count: int = 0

        # Observer 히스토리
        self._obs_history: list[str] = []

        # stuck 감지
        self._stuck_count: int = 0
        self._last_pos: tuple[int, int] = (0, 0)

    def choose_action(self, state: GameState) -> AgentResponse:
        ext = state.extracted
        if not ext:
            return AgentResponse(action=GameAction.ACTION1, reasoning="no state")

        # Observer: 변화 감지
        obs = self._observer.observe(ext)
        self._obs_history.append(obs.summary)

        # 레벨 변경 감지 -> 강제 replan
        if obs.slot_cleared and ext["slots_remaining"] == 0:
            self._subgoals = []
            self._current_subgoal_idx = 0
            self._observer.reset()
            self._obs_history.append(">> ALL SLOTS CLEARED — new level!")

        # stuck 감지: 같은 위치에 3번 이상이면 replan
        current_pos = (ext["player"]["x"], ext["player"]["y"])
        if current_pos == self._last_pos:
            self._stuck_count += 1
        else:
            self._stuck_count = 0
        self._last_pos = current_pos

        # subgoal 달성 체크
        if self._subgoals and self._current_subgoal_idx < len(self._subgoals):
            subgoal = self._subgoals[self._current_subgoal_idx]
            if self._check_subgoal_done(subgoal, ext, obs):
                self._current_subgoal_idx += 1
                self._stuck_count = 0
                if self._current_subgoal_idx < len(self._subgoals):
                    next_sg = self._subgoals[self._current_subgoal_idx]
                    self._obs_history.append(
                        f">> Subgoal {subgoal.get('id', '')} done! "
                        f"Next: {next_sg.get('description', '')}"
                    )

        # Planner 호출 조건
        need_plan = (
            not self._subgoals
            or self._current_subgoal_idx >= len(self._subgoals)
            or self._stuck_count >= 5
            or obs.position_reset
            or obs.slot_cleared
        )

        if need_plan and self._plan_count < self._max_replan:
            self._replan(ext, state)

        # Actor: 현재 subgoal 방향으로 액션
        if self._subgoals and self._current_subgoal_idx < len(self._subgoals):
            subgoal = self._subgoals[self._current_subgoal_idx]
        else:
            subgoal = {"description": "explore the map", "target": [32, 32]}

        frame_b64 = self._get_frame_b64(state)
        action_id, reasoning = self._actor.select_action(
            ext, subgoal, self._obs_history, frame_b64
        )

        return AgentResponse(
            action=GameAction.from_id(action_id),
            reasoning=f"[SG{self._current_subgoal_idx}] {reasoning}",
        )

    def _replan(self, ext: dict, state: GameState) -> None:
        """Planner를 호출하여 새 subgoal을 생성한다."""
        self._plan_count += 1
        self._stuck_count = 0

        frame_b64 = self._get_frame_b64(state)
        subgoals = self._planner.create_plan(ext, self._obs_history, frame_b64)

        if subgoals:
            self._subgoals = subgoals
            self._current_subgoal_idx = 0
            descriptions = [sg.get("description", "") for sg in subgoals]
            self._obs_history.append(f">> REPLAN ({self._plan_count}): {descriptions}")

    @staticmethod
    def _get_frame_b64(state: GameState) -> str | None:
        """프레임 데이터를 base64 이미지로 변환한다."""
        if not state.frame_raw:
            return None
        raw = state.frame_raw[0]
        frame = np.array(raw) if not isinstance(raw, np.ndarray) else raw
        return frame_to_base64(frame, scale=8)

    @staticmethod
    def _check_subgoal_done(
        subgoal: dict, ext: dict, obs: Observation
    ) -> bool:
        """subgoal 달성 여부를 체크한다."""
        # 타겟 위치 도달
        target = subgoal.get("target")
        if target:
            pos = (ext["player"]["x"], ext["player"]["y"])
            if pos == (target[0], target[1]):
                return True

        # 도구 변경 감지
        done_when = subgoal.get("done_when", "")
        if "rotation" in done_when.lower() and obs.tool_changed and "rotation" in obs.tool_change_detail:
            return True
        if "color" in done_when.lower() and obs.tool_changed and "color" in obs.tool_change_detail:
            return True
        if "shape" in done_when.lower() and obs.tool_changed and "shape" in obs.tool_change_detail:
            return True
        if "slot" in done_when.lower() and obs.slot_cleared:
            return True

        return False

    def on_episode_start(self, game_id: str) -> None:
        self._subgoals = []
        self._current_subgoal_idx = 0
        self._plan_count = 0
        self._obs_history = []
        self._stuck_count = 0
        self._last_pos = (0, 0)
        self._observer.reset()

    def on_episode_end(self, result: str, total_steps: int) -> None:
        pass
