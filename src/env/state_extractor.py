"""게임 프레임에서 구조화된 상태를 추출한다.

게임별로 다른 추출 로직이 필요하므로 Strategy 패턴 사용.
기본 추출기는 프레임 raw data만 반환하고,
게임별 추출기가 오브젝트/위치 등을 해석.
"""

from abc import ABC, abstractmethod

import numpy as np
import numpy.typing as npt

from src.agent.base import GameState


class StateExtractor(ABC):
    """게임 상태 추출기 인터페이스."""

    @abstractmethod
    def extract(self, state: GameState) -> dict:
        """GameState에서 구조화된 정보를 추출한다.

        Returns:
            dict: 추출된 정보. 게임별로 키가 다를 수 있음.
        """
        ...


class DefaultExtractor(StateExtractor):
    """기본 추출기 — 프레임의 색상 분포만 반환."""

    def extract(self, state: GameState) -> dict:
        if not state.frame_raw:
            return {}

        frame = state.frame_raw[0]
        unique, counts = np.unique(frame, return_counts=True)

        return {
            "frame_shape": frame.shape,
            "color_distribution": dict(zip(unique.tolist(), counts.tolist())),
        }


class Ls20Extractor(StateExtractor):
    """ls20 전용 추출기.

    ceiling test용: 게임 내부 클래스에 직접 접근하여
    플레이어 위치, 도구 상태, 슬롯 정보 등을 추출한다.
    """

    COLORS = {12: "red", 9: "orange", 14: "cyan", 8: "blue"}
    COLOR_ORDER = [12, 9, 14, 8]
    SHAPES = ["shape_0", "shape_1", "shape_2", "shape_3", "shape_4", "shape_5"]
    ROTATIONS = [0, 90, 180, 270]

    def __init__(self, game_instance: object) -> None:
        self._game = game_instance

    def extract(self, state: GameState) -> dict:
        g = self._game

        # 플레이어 위치
        player_x = g.mgu.x
        player_y = g.mgu.y

        # 도구 상태
        shape_idx = g.snw
        color_idx = g.tmx
        rotation_idx = g.tuv
        color_value = self.COLOR_ORDER[color_idx]

        # 슬롯 정보
        slots = []
        for i, slot_sprite in enumerate(g.qqv):
            if g.rzt[i]:
                continue  # 이미 클리어된 슬롯
            slots.append({
                "index": i,
                "x": slot_sprite.x,
                "y": slot_sprite.y,
                "required_shape": g.gfy[i],
                "required_color": self.COLOR_ORDER[g.vxy[i]],
                "required_rotation": self.ROTATIONS[g.cjl[i]],
            })

        # 에너지 & lives
        energy = g.ggk.snw
        max_energy = g.ggk.tmx
        lives = g.lbq

        # 매치 체크 — 현재 도구가 어떤 슬롯과 매치되는지
        current_tool = (shape_idx, color_value, self.ROTATIONS[rotation_idx])
        for slot in slots:
            required = (slot["required_shape"], slot["required_color"], slot["required_rotation"])
            slot["matches_current"] = current_tool == required

        # 간략 맵 생성 (13x13 타일)
        tile_map = self._build_tile_map(state, player_x, player_y, slots)

        return {
            "player": {"x": player_x, "y": player_y},
            "tool": {
                "shape": shape_idx,
                "shape_name": self.SHAPES[shape_idx] if shape_idx < len(self.SHAPES) else f"shape_{shape_idx}",
                "color": color_value,
                "color_name": self.COLORS.get(color_value, str(color_value)),
                "rotation": self.ROTATIONS[rotation_idx],
            },
            "slots": slots,
            "slots_remaining": len(slots),
            "energy": energy,
            "max_energy": max_energy,
            "lives": lives,
            "level": state.levels_completed + 1,
            "tile_map": tile_map,
        }

    def _build_tile_map(
        self,
        state: GameState,
        player_x: int,
        player_y: int,
        slots: list[dict],
    ) -> str:
        """64x64 프레임을 13x13 타일 맵으로 변환."""
        if not state.frame_raw:
            return ""

        raw = state.frame_raw[0]
        frame = np.array(raw) if not isinstance(raw, np.ndarray) else raw
        lines = []
        tile_size = 5

        for ty in range(0, 64, tile_size):
            row = ""
            for tx in range(0, 64, tile_size):
                # 이 타일의 주요 색상 확인
                tile = frame[ty:ty + tile_size, tx:tx + tile_size]

                if player_x == tx and player_y == ty:
                    row += " P "
                elif any(s["x"] == tx and s["y"] == ty for s in slots):
                    idx = next(s["index"] for s in slots if s["x"] == tx and s["y"] == ty)
                    row += f"T{idx} " if idx < 10 else f"T{idx}"
                elif np.all(tile == 5):
                    row += " # "  # 벽
                elif np.any(tile == 5) and np.sum(tile == 5) > tile.size * 0.5:
                    row += " # "  # 대부분 벽
                else:
                    row += " . "
            lines.append(row)

        return "\n".join(lines)
