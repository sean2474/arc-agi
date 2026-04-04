# ls20 Prompt Structure Design

## 설계 원칙

1. **규칙은 시스템 프롬프트에** — 매 턴 반복하지 않음 (prompt caching 활용)
2. **프레임 상태는 구조화된 텍스트로** — 64x64 raw grid가 아니라 해석된 상태
3. **액션 히스토리는 간결하게** — 최근 N스텝만
4. **출력 포맷 고정** — JSON으로 파싱 가능하게
5. **생각하는 과정 포함** — 전략적 추론을 유도

## 프롬프트 구조

### System Prompt (캐싱, 매 턴 동일)

```
You are playing an ARC-AGI-3 puzzle game called "ls20".

## Game Rules

### Movement
- ACTION1: Move up (y -= 5)
- ACTION2: Move down (y += 5)  
- ACTION3: Move left (x -= 5)
- ACTION4: Move right (x += 5)
- You move 5 pixels per step on a 64x64 grid
- Walls block movement

### Your Tool
You carry a cursor tool with 3 properties:
- Shape: one of [shape_0, shape_1, shape_2, shape_3, shape_4, shape_5]
- Color: one of [red(12), orange(9), cyan(14), blue(8)]
- Rotation: one of [0, 90, 180, 270] degrees

### Modifier Pads
Stepping on special pads changes your tool:
- Shape pad: cycles to next shape
- Color pad: cycles to next color (12→9→14→8→12...)
- Rotation pad: rotates 90° (0→90→180→270→0...)

### Win Condition
- Each level has target slots requiring a specific (shape, color, rotation) combination
- Match your tool to a slot's requirement, then move onto the slot to clear it
- Clear ALL slots to complete the level

### Lose Condition
- You have 3 lives
- Moving without clearing a slot costs energy
- When energy runs out, you lose a life and reset position
- 0 lives = game over

## Response Format
Always respond with exactly this JSON:
{
  "thinking": "your reasoning about current state and what to do next",
  "action": 1|2|3|4
}
```

### User Message (매 턴 변경)

```
## Current State
- Position: (x, y)
- Tool: shape={shape_idx}, color={color_name}, rotation={rotation}°
- Lives: {lives}/3
- Energy: {energy}/{max_energy}
- Slots remaining: {remaining}/{total}
- Level: {level}/7

## Slot Requirements
{for each uncompleted slot:}
- Slot at (x, y): needs shape={s}, color={c}, rotation={r}° {MATCH/MISMATCH markers}

## Visible Map (simplified)
{grid representation showing: P=player, W=wall, S=slot, [Sh]=shape_pad, [Co]=color_pad, [Ro]=rotation_pad, .=empty}

## Recent Actions (last 5)
- Step N: ACTION{x} → moved to (x,y), {event if any}

## Your Turn
Choose your next action.
```

## 핵심 설계 결정

### 1. 프레임을 raw grid로 주지 않는다
64x64 = 4096 셀을 텍스트로 주면 토큰 낭비 + LLM이 해석 못함.
대신 **해석된 상태**를 준다:
- 플레이어 위치, 도구 상태, 남은 슬롯
- 간략화한 맵 (주요 오브젝트만 표시)

### 2. 맵을 어떻게 간략화할 것인가
64x64를 5로 나누면 ~13x13 격자. 각 5x5 셀을 하나의 타일로:
- `.` = 빈 공간
- `#` = 벽
- `P` = 플레이어
- `T1`~`Tn` = 타겟 슬롯
- `Sh` = Shape 패드
- `Co` = Color 패드
- `Ro` = Rotation 패드
- `*` = Collectible
- `|` = 경계

→ 이러면 ~13x13 = 169 문자로 맵 전달 가능

### 3. 코드에서 상태를 추출해야 할 것들
게임 소스에서 직접 추출 (프레임 파싱이 아님):
- `self.mgu.x, self.mgu.y` → 플레이어 위치
- `self.snw, self.tmx, self.tuv` → shape/color/rotation index
- `self.rzt[i]` → 각 슬롯 클리어 여부
- `self.lbq` → 남은 lives
- `self.ggk.snw` → 에너지

### 4. 문제: 게임 내부 상태에 직접 접근 가능한가?
EnvironmentWrapper는 FrameDataRaw만 반환 — 내부 state 접근 불가.
**두 가지 옵션:**
a) 프레임에서 코드로 상태 추출 (색상/좌표 분석)
b) 게임 클래스를 직접 import해서 내부 접근

**실험 목적이므로 (b)를 사용** — 규칙 아는 ceiling test니까
게임 소스를 직접 로드하여 내부 상태를 읽는다.

### 5. 왜 이 구조가 좋은가
- LLM은 격자 퍼즐 형태에 익숙 (텍스트 게임 경험)
- 상태가 완전히 해석되어 있으므로 perception 문제 제거
- thinking 필드로 추론 과정 추적 가능
- JSON 출력으로 파싱 안정적
