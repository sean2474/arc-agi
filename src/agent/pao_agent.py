"""Planner-Actor-Observer 에이전트.

Planner: goal/subgoal 설정 (VLM, 드물게)
Actor: subgoal 방향으로 액션 선택 (VLM, 매 스텝)
Observer: 프레임 변화 감지 (코드, 매 스텝)
"""

import re
import json

import numpy as np
from arcengine import GameAction

from src.agent.base import Agent, AgentResponse, GameState
from src.env.observer import Observer, Observation
from src.llm.client import AnthropicClient
from src.llm.frame_renderer import frame_to_base64
from src.llm.pao_prompts import (
    PLANNER_SYSTEM,
    ACTOR_SYSTEM,
    build_planner_message,
    build_actor_message,
)


class PAOAgent(Agent):
    """Planner-Actor-Observer 에이전트."""

    def __init__(self, client: AnthropicClient, max_replan: int = 5) -> None:
        self._client = client
        self._observer = Observer()
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

        # 레벨 변경 감지 → 강제 replan
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
                        f">> Subgoal {subgoal.get('id','')} done! Next: {next_sg.get('description','')}"
                    )

        # Planner 호출 조건
        need_plan = (
            not self._subgoals  # 첫 번째
            or self._current_subgoal_idx >= len(self._subgoals)  # 모든 subgoal 완료
            or self._stuck_count >= 5  # stuck
            or obs.position_reset  # 리셋 발생
            or obs.slot_cleared  # 슬롯 클리어 (상황 변화)
        )

        if need_plan and self._plan_count < self._max_replan:
            self._replan(ext, state)

        # Actor: 현재 subgoal 방향으로 액션
        if self._subgoals and self._current_subgoal_idx < len(self._subgoals):
            subgoal = self._subgoals[self._current_subgoal_idx]
        else:
            subgoal = {"description": "explore the map", "target": [32, 32]}

        action_id, reasoning = self._act(state, ext, subgoal)

        return AgentResponse(
            action=GameAction.from_id(action_id),
            reasoning=f"[SG{self._current_subgoal_idx}] {reasoning}",
        )

    def _replan(self, ext: dict, state: GameState | None = None) -> None:
        """Planner를 호출하여 새 subgoal을 생성한다."""
        self._plan_count += 1
        self._stuck_count = 0

        msg = build_planner_message(ext, self._obs_history)

        # 이미지도 함께 전달
        frame_b64 = None
        if state and state.frame_raw:
            raw = state.frame_raw[0]
            frame = np.array(raw) if not isinstance(raw, np.ndarray) else raw
            frame_b64 = frame_to_base64(frame, scale=8)

        if frame_b64:
            content = [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": frame_b64}},
                {"type": "text", "text": msg},
            ]
        else:
            content = msg

        response = self._client.send(
            system=PLANNER_SYSTEM,
            messages=[{"role": "user", "content": content}],
        )

        subgoals = self._parse_planner(response.content)
        if subgoals:
            self._subgoals = subgoals
            self._current_subgoal_idx = 0
            descriptions = [sg.get("description", "") for sg in subgoals]
            self._obs_history.append(f">> REPLAN ({self._plan_count}): {descriptions}")

    def _act(self, state: GameState, ext: dict, subgoal: dict) -> tuple[int, str]:
        """Actor를 호출하여 단일 액션을 선택한다."""
        # 프레임 이미지
        frame_b64 = None
        if state.frame_raw:
            raw = state.frame_raw[0]
            frame = np.array(raw) if not isinstance(raw, np.ndarray) else raw
            frame_b64 = frame_to_base64(frame, scale=8)

        content = build_actor_message(ext, subgoal, self._obs_history[-5:], frame_b64)

        if isinstance(content, list):
            messages = [{"role": "user", "content": content}]
        else:
            messages = [{"role": "user", "content": content}]

        response = self._client.send(
            system=ACTOR_SYSTEM,
            messages=messages,
        )

        return self._parse_actor(response.content)

    def _check_subgoal_done(self, subgoal: dict, ext: dict, obs: Observation) -> bool:
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

    def _parse_planner(self, content: str) -> list[dict]:
        """Planner 응답에서 subgoals를 추출한다."""
        # "subgoals": [...] 패턴
        match = re.search(r'"subgoals"\s*:\s*\[', content)
        if not match:
            return []

        # JSON 전체 파싱 시도
        try:
            # content에서 JSON 부분 추출
            brace_start = content.find("{")
            if brace_start < 0:
                return []

            depth = 0
            end = brace_start
            for i in range(brace_start, len(content)):
                if content[i] == "{":
                    depth += 1
                elif content[i] == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break

            data = json.loads(content[brace_start:end])
            subgoals = data.get("subgoals", [])
            # target을 리스트로 보장
            for sg in subgoals:
                if "target" not in sg:
                    sg["target"] = [32, 32]
                elif isinstance(sg["target"], dict):
                    sg["target"] = [sg["target"].get("x", 32), sg["target"].get("y", 32)]
            return subgoals
        except (json.JSONDecodeError, ValueError):
            return []

    def _parse_actor(self, content: str) -> tuple[int, str]:
        """Actor 응답에서 액션과 reasoning을 추출한다."""
        action_match = re.search(r'"action"\s*:\s*(\d+)', content)
        action_id = int(action_match.group(1)) if action_match else 1
        if action_id < 1 or action_id > 4:
            action_id = 1

        thinking_match = re.search(r'"thinking"\s*:\s*"(.*?)"', content, re.DOTALL)
        reasoning = thinking_match.group(1)[:300] if thinking_match else content[:200]

        return action_id, reasoning

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

    def get_usage(self) -> str:
        return self._client.get_usage_summary()
