# Anthropic Claude 프로토타입 에이전트 구조

## 핵심 아이디어

LLM을 매 스텝마다 호출하지 않는다. **시퀀스(액션 배열)**를 받아서 실행하고, **트리거 조건**이 발생할 때만 LLM을 다시 호출한다. 이렇게 하면 API 호출 수와 비용을 크게 줄일 수 있다.

---

## 파일 구조

```
arc-agi-3/
├── agent.py               ← ClaudeAgent (LLM 호출 + 시퀀스 관리)
├── run_agent.py            ← 게임 루프 (env ↔ agent)
├── play.py                 ← (기존) 수동 플레이어
└── .env                    ← ANTHROPIC_API_KEY, ARC_API_KEY
```

---

## 게임 루프 흐름 (4단계 사이클)

각 사이클은 4개의 분리된 LLM 호출로 구성:

```
━━━ 사이클 N ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[STEP 1: OBSERVE]  LLM 호출  ← 순수 관찰만
  입력: summary + current frame
  출력: 환경 분석 (values, patterns, player, goal hypothesis)
  CoT 강제: OBSERVE → DIFF → HYPOTHESIZE → CHALLENGE → CONCLUDE
        ↓
[STEP 2: DECIDE]  LLM 호출  ← 의도만 결정
  입력: OBSERVE 결과 + summary + reports
  출력: action sequence, sequence_goal, win_condition_hypothesis, confidence
        ↓
[EXECUTE]  코드가 시퀀스 실행 (LLM 호출 없음)
  반복: env.step(action) → diff 계산 → observation 기록
  종료: 시퀀스 소진 or 트리거 발생
        ↓
[STEP 2a: INCIDENT]  ← game_over/level_complete 시에만
        ↓
[STEP 3: EVALUATE]  LLM 호출  ← 결과 평가
  입력: goal + observations + before/after + incident_result
  출력: goal_achieved, report, discoveries
        ↓
[STEP 4: UPDATE]  LLM 호출  ← 지식 통합
  입력: prev summary + report + discoveries + incident
  출력: updated_summary + updated_world_model

━━━ 사이클 N+1 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[STEP 1: OBSERVE]  ← updated_summary + world_model + 새 프레임
  ...반복
```

### LLM 호출 4종류

| 단계 | 역할 | 핵심 원칙 |
|------|------|----------|
| **OBSERVE** | 뭐가 보이는지 | **관찰만**. 판단/의도 금지. CoT 강제 |
| **DECIDE** | 뭘 할지 | OBSERVE + world_model 기반. **낮은 confidence 우선 탐색** |
| **EVALUATE** | 어떻게 됐는지 | 정직한 평가. 합리화 금지 |
| **UPDATE** | 뭘 배웠는지 | summary + **world_model confidence 갱신** |

### 왜 OBSERVE와 DECIDE를 분리하는가

- 한 호출에서 관찰+결정 동시 → reasoning이 intent를 오염
- 분리 → OBSERVE는 사실만, DECIDE가 판단

### 흐름 요약

```
OBSERVE → DECIDE → 실행 → [INCIDENT] → EVALUATE → UPDATE(+world_model)
    → OBSERVE → DECIDE → ...
```

---

## World Model

게임 규칙에 대한 **구조화된 가설 + confidence**.
summary(자유 텍스트)와 달리, world model은 **코드가 직접 읽고 판단**할 수 있는 구조.

### 구조

```json
{
  "game_type": {"hypothesis": "navigation", "confidence": 0.0},
  "actions": {
    "up":    {"effect": "unknown", "confidence": 0.0},
    "down":  {"effect": "unknown", "confidence": 0.0},
    "left":  {"effect": "unknown", "confidence": 0.0},
    "right": {"effect": "unknown", "confidence": 0.0},
    "space": {"effect": "unknown", "confidence": 0.0},
    "click": {"effect": "unknown", "confidence": 0.0},
    "undo":  {"effect": "unknown", "confidence": 0.0}
  },
  "controllable": {"description": null, "confidence": 0.0},
  "goal": {"description": null, "confidence": 0.0},
  "objects": {},
  "dangers": [],
  "interactions": []
}
```

### confidence 규칙

| 값 | 의미 |
|----|------|
| `0.0` | 전혀 모름 (테스트 안 함) |
| `0.3` | 가설만 있음 (관찰 기반 추측) |
| `0.7` | 1회 검증됨 (기대대로 변화 확인) |
| `1.0` | 반복 확인됨 |

### DECIDE는 항상 1개 액션만 반환

LLM이 한번에 여러 액션을 출력하지 않음. **항상 1개만**.
매 스텝마다 OBSERVE→DECIDE→EXECUTE→EVALUATE→UPDATE 사이클을 돌림.

이유:
- 여러 액션을 한번에 출력하면 중간 피드백 없이 실행 → 잘못된 방향으로 계속 감
- 작은 모델에서 시퀀스 출력이 불안정 (파싱 실패)
- 매 스텝 피드백 → 더 빠른 규칙 파악

### 방향키 배치 업데이트

방향키(up/down/left/right)는 **하나만 테스트해도 나머지를 추론** 가능:

```
up 테스트 → "값 c가 2칸 위로 이동"
→ actions.up    = {"effect": "moves up 2 cells",    "confidence": 0.7}  ← 검증됨
→ actions.down  = {"effect": "likely moves down",   "confidence": 0.5}  ← 추론
→ actions.left  = {"effect": "likely moves left",   "confidence": 0.5}  ← 추론
→ actions.right = {"effect": "likely moves right",  "confidence": 0.5}  ← 추론
```

나머지 액션(space, click, undo)은 **각각 개별 테스트** 필요.
LLM이 UPDATE에서 방향키 4개를 한꺼번에 업데이트하도록 프롬프트에 명시.

### 탐색 우선순위 (DECIDE에서 사용)

DECIDE 프롬프트에 world model을 전달하면, LLM이 자연스럽게:

```
1. confidence == 0.0인 액션 → 테스트 우선 (시퀀스 1개)
2. confidence < 0.5인 가설 → 검증 우선
3. 모든 기본 액션 검증 완료 → 목표 달성 전략으로 전환
```

코드에서도 강제:
```python
# DECIDE 전에 코드가 힌트를 생성
untested = [k for k, v in world_model["actions"].items() if v["confidence"] == 0.0]
if untested:
    hint = f"UNTESTED ACTIONS: {untested}. Consider testing one of these."
```

### 초반 흐름 예시

```
cycle 1: OBSERVE(첫 프레임) → DECIDE(up 1개) → EXECUTE(up) → EVALUATE → UPDATE
  → world_model.actions.up = 0.7, down/left/right = 0.5
  → avg confidence = 0.42 → 시퀀스 최대 3개

cycle 2: OBSERVE → DECIDE(space 테스트) → EXECUTE(space) → EVALUATE → UPDATE
  → world_model.actions.space = 0.7 (or 0.0 if no effect)
  → avg confidence = 0.48 → 시퀀스 최대 3개

cycle 3: OBSERVE → DECIDE(목표 방향 3스텝) → EXECUTE → EVALUATE → UPDATE
  → 점점 전략적 플레이로 전환
```

---

## 트리거 조건 (코드로 감지)

LLM을 다시 호출해야 하는 경우:

| 트리거 | 설명 |
|--------|------|
| `sequence_empty` | 시퀀스를 전부 소진 |
| `game_over` | state가 GAME_OVER로 변경 |
| `level_complete` | levels_completed 증가 |
| `new_value_appeared` | 그리드에 새로운 색상 값 등장 |
| `no_change` | 액션 실행했는데 그리드 변화 없음 (벽?) |
| `replan_condition_met` | LLM이 지정한 커스텀 조건 충족 |

→ 시퀀스 실행 중 트리거가 발생하면 **즉시 중단**하고 LLM 호출

---

## 시퀀스 길이 제한 (코드 강제)

LLM이 "불확실하면 짧게"를 잘 안 지키므로 코드로 강제한다.
`confirmed_mechanics` 수에 따라 최대 길이를 동적으로 결정.

**설정은 `const.py`에 정의:**

```python
# const.py
MAX_SEQUENCE_LENGTH = 10
SEQUENCE_LENGTH_BY_CONFIDENCE = {
    0: 2,   # 아무것도 모름 → 탐색
    1: 4,   # 조금 앎
    3: 7,   # 꽤 앎
    5: MAX_SEQUENCE_LENGTH,  # 충분히 앎
}
```

- LLM 응답의 `next_sequence`가 이 길이를 초과하면 **코드가 잘라버림**
- 프롬프트에도 현재 제한을 동적으로 삽입 → LLM이 헛수고 안 함
- 액션 매핑(`ACTION_LABELS`), ARC 팔레트(`ARC_COLORS`)도 `const.py`에 있음

---

## LLM 프롬프트

### System Prompt (공통)
```
You are playing an unknown game. Analyze the situation and decide what to do next.

The grid is 64x64, each cell is a hex digit (0-f = 16 colors).
Game rules are unknown — you must figure them out by observing changes.

Color mapping:
  0=black  1=blue  2=red  3=green  4=yellow  5=gray  6=magenta  7=orange
  8=sky  9=maroon  a=purple  b=teal  c=lime  d=burgundy  e=olive  f=white

Action mapping:
  1: UP        2: DOWN      3: LEFT      4: RIGHT
  5: SPACEBAR  6: CLICK(x,y)  7: UNDO

Goal: complete all levels (state → WIN).
```

---

### STEP 1: OBSERVE (순수 관찰 — CoT 강제)

시점: 사이클 시작 시. **판단/의도 금지. 사실만 기록.**

**PREVIOUS FRAME = 시퀀스 시작 전 프레임** (직전 프레임 아님).
시퀀스가 여러 스텝이었으면, 시퀀스 전체의 효과를 한눈에 비교할 수 있음.

```
GAME INFO
  game_id: {game_id}
  available_actions: [up, down, left, right]
  levels_completed: {n} / {total}
  step: {step}

SUMMARY (accumulated knowledge)
{summary_json}

PREVIOUS FRAME (before sequence)
{frame_before_sequence}   ← 시퀀스 시작 전 상태. 없으면 생략.

CURRENT FRAME
{grid}

You are ONLY observing. Do NOT decide what to do. Just analyze.

Work through these steps:

STEP 1 - VALUES: List every unique hex value in the frame.
  For each: what color is it, roughly where does it appear, how much area does it cover?

STEP 2 - PATTERNS: What structures do you see?
  Rectangles, corridors, borders, isolated pixels, repeating patterns?

STEP 3 - DIFF: What changed from what you know (check SUMMARY)?
  What moved? What appeared? What disappeared? What stayed the same?

STEP 4 - HYPOTHESIZE:
  - What is the player? (which value, approximate position)
  - What are static elements? (walls, floors, borders)
  - What might be the goal/win condition?

STEP 5 - CHALLENGE: What evidence CONTRADICTS your hypotheses?
  - Could the "player" be something else?
  - What assumptions are unproven?
  - What don't you know that could change everything?

STEP 6 - CONCLUDE: Summarize your observations as facts only.

Respond in JSON:
{
  "values": {"0": "black, isolated pixels at (20,31)-(21,33)", ...},
  "patterns": ["green(3) forms corridors", "gray(5) rectangular blocks", ...],
  "changes_from_summary": "lime block moved up 2 rows",
  "player_hypothesis": {"value": "c", "position": "row 40-41, col 36-40", "confidence": 0.7},
  "goal_hypothesis": {"description": "navigate to teal(b) region", "confidence": 0.3},
  "contradictions": ["haven't verified if c moves or is pushed", ...],
  "unknowns": ["what triggers level complete", "role of maroon(9) blocks"]
}

Rules:
- Do NOT suggest actions. Do NOT plan. Observe ONLY.
- STEP 5 (CHALLENGE) is critical. Bad assumptions kill runs.
- Be specific about positions: use row/column ranges, not vague descriptions.
```

---

### STEP 2: DECIDE (의도 결정)

시점: OBSERVE 직후. OBSERVE 결과를 받아 액션을 결정.

```
OBSERVATION RESULT
{observe_json}

SUMMARY (accumulated knowledge)
{summary_json}

RECENT REPORTS (last 3)
{reports_json}

CONSTRAINT: max sequence length = {max_len}

Available actions: [up, down, left, right]

Based on the observation, decide what to do next.

You MUST answer these questions:
1. What is your current win condition hypothesis?
2. What specific thing will this sequence test or accomplish?
3. How will you know if it succeeded or failed?

Respond in JSON:
{
  "win_condition_hypothesis": "reach the teal(b) region at row 61",
  "reasoning": "the teal blocks at the bottom are the only unexplored interactive area",
  "sequence": ["down", "down", "right", "right"],
  "sequence_goal": "move player from (40,38) to (42,40) to test if maroon(9) blocks at (42-44) are passable",
  "success_condition": "player position changes to row 42+ after sequence",
  "failure_condition": "player stops at row 41 (blocked by maroon)",
  "confidence": 0.4,
  "replan_conditions": ["no_change", "game_over", "new_value"]
}

Rules:
- win_condition_hypothesis: REQUIRED. Must have a guess, even if uncertain.
- sequence: use action NAMES ["up","down","left","right","space","undo"]. Click: ["click", x, y].
- sequence_goal: MUST be specific with coordinates or verifiable conditions.
  BAD: "explore the area"  GOOD: "move to row 45 col 30 to reach green corridor"
- success_condition / failure_condition: EVALUATE uses these to judge. Be precise.
- max {max_len} actions. Low confidence → system may truncate further.
- Check REPORTS to avoid repeating failed strategies.
```

#### 왜 OBSERVE와 DECIDE를 분리하는가

- **한 호출에서 관찰+결정을 동시에 시키면**: intent가 observation을 오염
  - "이동하려면 이게 플레이어여야 하니까 → 이게 플레이어다" (순환논리)
- **분리하면**: OBSERVE가 순수 사실만 기록, DECIDE가 그 사실을 기반으로 판단
- OBSERVE의 CoT(특히 CHALLENGE)가 thinking 토큰의 역할을 대체

---

### STEP 2a: INCIDENT (game_over / level_complete 시에만)

시점: 시퀀스 실행 중 game_over 또는 level_complete가 발생했을 때.
EVALUATE 전에 별도 호출하여 **사건 분석에만 집중**.

#### game_over 시
```
GAME OVER — DEATH ANALYSIS

The player died. Analyze what happened:

LAST 3 OBSERVATIONS BEFORE DEATH
{last_observations}

FRAME RIGHT BEFORE DEATH
{frame_before_death}

FRAME AT DEATH
{frame_at_death}

Work through these steps:
1. What did the player touch/encounter right before dying?
2. Which grid value at which position caused it?
3. Was there a warning sign? (color change, new value appeared, etc.)
4. How can this be avoided in the future?

Respond in JSON:
{
  "death_cause": "what killed the player",
  "death_position": {"x": 0, "y": 0},
  "death_value": "the grid value that caused death",
  "warning_signs": ["any observable signs before death"],
  "avoidance_rule": "how to avoid this in the future"
}
```

#### level_complete 시
```
LEVEL COMPLETED ({prev_level} → {curr_level}) — WIN ANALYSIS

The level was cleared. Analyze what happened:

LAST 3 OBSERVATIONS BEFORE WIN
{last_observations}

FRAME RIGHT BEFORE WIN
{frame_before_win}

FRAME AT WIN
{frame_at_win}

Work through these steps:
1. What was the final action/position that triggered completion?
2. What is the confirmed win condition?
3. Is there a pattern across levels? Will this strategy generalize?

Respond in JSON:
{
  "win_trigger": "the action/position that triggered win",
  "win_condition": "confirmed rule for winning",
  "strategy_generalizes": true/false,
  "reasoning": "why this strategy will/won't work for next level"
}
```

→ INCIDENT 결과는 EVALUATE에 `incident_result`로 전달

---

### STEP 2b: EVALUATE (결과 평가)

시점: 시퀀스 실행 완료 후 (INCIDENT 직후 또는 정상 완료 시)

```
SEQUENCE RESULT
  goal: "{sequence_goal}"
  planned: {planned_sequence}
  executed: {executed_actions}
  abort_reason: {abort_reason}   ← null이면 정상 완료

OBSERVATIONS DURING SEQUENCE
{observations_json}

FRAME BEFORE
{frame_before}

FRAME AFTER
{frame_after}

{incident_section}  ← INCIDENT 결과가 있으면 삽입

Before evaluating, work through these steps:

STEP 1 - COMPARE: Compare FRAME BEFORE and FRAME AFTER.
  What moved? What appeared? What disappeared?

STEP 2 - GOAL CHECK: Did the sequence achieve its stated goal?
  Be specific — what was the goal, what actually happened?

STEP 3 - SURPRISES: Did anything unexpected happen?
  Anything that contradicts the current SUMMARY?

STEP 4 - LESSONS: What should be remembered for future sequences?
  What worked? What didn't? What should never be tried again?

Then respond in JSON:
{
  "goal_achieved": true/false,
  "goal_evaluation": "why succeeded or failed",
  "confidence": 0.6,
  "new_discoveries": ["discovery1", "discovery2"],
  "report": {
    "sequence_goal": "the goal",
    "actions_taken": [1, 1, 3],
    "goal_achieved": true/false,
    "reasoning": "what happened and why",
    "key_learnings": ["learning1"]
  }
}

Rules:
- Focus ONLY on evaluating what happened. Don't plan next actions.
- Be honest about failure. Don't rationalize bad results.
- STEP 4 (LESSONS) is critical — this feeds into REPORTS that prevent repeating mistakes.
```

→ UPDATE가 이 결과 + INCIDENT 결과를 받아서:
  - game_over → `dangers` 리스트에 추가
  - level_complete → `win_condition` 확정, 다음 레벨 전략에 carry-over

---

### STEP 3: UPDATE (지식 통합)

시점: EVALUATE 직후

```
PREVIOUS SUMMARY
{summary_json}

EVALUATION RESULT
{evaluation_json}

NEW DISCOVERIES
{discoveries_json}

Update the accumulated knowledge. Respond in JSON:
{
  "updated_summary": {
    "game_type": "...",
    "objects": { ... },
    "confirmed_actions": { ... },
    "confirmed_mechanics": [ ... ],
    "dangers": [ ... ],
    "win_condition": "...",
    "current_position": "...",
    "known_map": "..."
  }
}

Rules:
- Return the FULL updated summary, not a diff.
- Merge new discoveries into existing knowledge.
- Remove disproven hypotheses.
- If death_cause was reported, add it to dangers.
- If win_condition was reported, confirm it in summary.
- Keep it concise but complete. This is the only context PLAN will see.
```

---

### Report 구조

시퀀스마다 EVALUATE에서 1개씩 생성 → `reports` 리스트에 누적.
PLAN에 최근 3개를 전달해서 실패 전략 반복 방지.

```json
{
  "sequence_id": 3,
  "sequence_goal": "move right to reach teal region",
  "actions_taken": [4, 4, 4, 4, 2, 2],
  "goal_achieved": false,
  "reasoning": "hit a wall at column 45, couldn't proceed right",
  "key_learnings": ["wall exists at col 45", "need to go down first"],
  "abort_reason": "no_change",
  "steps": [15, 20]
}
```

→ replay.py에서 report 표시 → 시퀀스별 성공/실패를 한눈에 확인 가능

---

## 상태 관리

```python
state = {
    "summary": {},              # 누적 지식 (LLM이 업데이트)
    "current_reasoning": {},    # 현재 추론 상태
    "sequence": [],             # 남은 액션 시퀀스
    "sequence_goal": "",        # 현재 시퀀스의 목표
    "replan_conditions": [],    # LLM이 지정한 중단 조건
    "prev_grid": None,          # 이전 프레임 (diff 계산용)
    "prev_values": set(),       # 이전 프레임의 unique values
}
```

### summary 예시 (누적)
```json
{
  "game_type": "maze navigation",
  "player": {"value": 1, "position": [31, 32]},
  "goal": {"value": 9, "description": "reach the target"},
  "walls": {"value": 4},
  "confirmed_actions": {
    "1": "moves player up",
    "2": "moves player down"
  },
  "level_pattern": "maze gets larger each level"
}
```

### current_reasoning 예시
```json
{
  "current_objective": "reach value 9 at bottom-right",
  "plan": "go down then right",
  "obstacles_noted": "wall at row 30",
  "attempts": 1
}
```

---

## diff 계산 (코드)

```python
def compute_diff(prev_grid, curr_grid):
    """두 64x64 그리드 비교 → 변경 셀 목록"""
    changes = []
    for y in range(64):
        for x in range(64):
            if prev_grid[y][x] != curr_grid[y][x]:
                changes.append({
                    "x": x, "y": y,
                    "from": prev_grid[y][x],
                    "to": curr_grid[y][x]
                })
    return changes

def diff_to_compact(changes):
    """변경 셀을 간결한 문자열로"""
    if not changes:
        return "no changes"
    lines = [f"({c['x']},{c['y']}): {c['from']}→{c['to']}" for c in changes[:50]]
    if len(changes) > 50:
        lines.append(f"... and {len(changes)-50} more")
    return "\n".join(lines)
```

---

## 트리거 감지 (코드)

```python
def detect_triggers(prev_grid, curr_grid, prev_obs, curr_obs, replan_conditions):
    triggers = []

    # 1. game_over
    if curr_obs.state == GameState.GAME_OVER:
        triggers.append("game_over")

    # 2. level_complete
    if curr_obs.levels_completed > prev_obs.levels_completed:
        triggers.append(f"level_complete: {prev_obs.levels_completed}→{curr_obs.levels_completed}")

    # 3. no_change
    diff = compute_diff(prev_grid, curr_grid)
    if len(diff) == 0:
        triggers.append("no_change")

    # 4. new_value_appeared
    prev_vals = set(np.unique(prev_grid))
    curr_vals = set(np.unique(curr_grid))
    new_vals = curr_vals - prev_vals
    if new_vals:
        triggers.append(f"new_value_appeared: {sorted(new_vals)}")

    # 5. replan_condition_met
    for cond in replan_conditions:
        if cond == "new_value" and new_vals:
            triggers.append(f"replan:{cond}")
        elif cond == "game_over" and curr_obs.state == GameState.GAME_OVER:
            triggers.append(f"replan:{cond}")
        elif cond == "no_change" and len(diff) == 0:
            triggers.append(f"replan:{cond}")

    return triggers
```

---

## 토큰 효율

| 항목 | 호출당 토큰 |
|------|-----------|
| system prompt | ~200 |
| game info + summary + reasoning | ~300 |
| grid (64x64 hex) | ~1,500 |
| diff (보통 10~30 changes) | ~100 |
| 응답 | ~300 |
| **총** | **~2,400** |

핵심: **매 스텝이 아니라 트리거 시에만 호출** → 시퀀스 길이 10이면 LLM 호출 10배 감소

---

## 실행 예시

```bash
# .env 설정
echo 'ANTHROPIC_API_KEY=sk-ant-...' >> .env
echo 'ARC_API_KEY=...' >> .env

# 에이전트 실행
python run_agent.py --game ls20 --max-steps 200 --model claude-sonnet-4-20250514
```

---

## 첫 테스트 목표

1. ls20에서 Claude가 **레벨 1이라도 클리어**하는지 확인
2. 시퀀스 기반이 매 스텝 호출 대비 **API 호출 몇 배 줄어드는지** 측정
3. summary가 레벨 간에 **규칙 지식을 전달**하는지 관찰
4. 트리거가 적절하게 발동하는지 확인

---

## 나중에 확장

- **비전**: 그리드를 이미지로 변환해서 vision API 사용
- **그리드 압축**: RLE, diff-only, crop, downsample
- **메모리**: 게임별 summary 캐시 → 재시작 시 바로 로드
- **탐색**: 시퀀스 후보 여러 개 생성 후 시뮬레이션 비교
- **멀티 게임**: 25개 게임 순회 벤치마크