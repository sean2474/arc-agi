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

---

## Phase System (탐색 단계)

에이전트는 4단계를 순서대로 진행. 각 phase의 종료 조건이 충족되면 다음 phase로.
**"캐릭터"라는 가정 없이, "액션의 결과로 뭐가 변하는지"만 추적.**

### Phase 1: Static Observation (첫 프레임)

첫 프레임만 보고 화면의 모든 구분 가능한 요소를 추출.

#### 배경 자동 감지 (코드에서 처리)

LLM에게 프레임을 보내기 전에 **코드가 배경을 자동으로 감지**:

```python
from collections import Counter

def analyze_grid(grid: list[str]) -> dict:
    """그리드 통계 분석. 배경 후보 + 비배경 값 목록."""
    flat = [cell for row in grid for cell in row]
    total = len(flat)
    counts = Counter(flat)
    bg_value, bg_count = counts.most_common(1)[0]
    return {
        "background": {"value": bg_value, "count": bg_count, "pct": bg_count / total * 100},
        "non_background": {v: c for v, c in counts.items() if v != bg_value},
    }
```

OBSERVE 프롬프트에 힌트로 전달:
```
GRID ANALYSIS (auto-detected):
  background: value '4' (yellow, 72.3% of grid) — likely background, you can skip this
  non-background values: {'5': 1024, '3': 512, '9': 48, 'c': 20, 'b': 15}
  focus on non-background values for object detection
```

효과:
- LLM이 "값 4가 뭔지 분석" 같은 토큰 낭비를 안 함
- 비배경 값에만 집중 → 더 정확한 object 추출
- 인간이 게임을 볼 때 배경을 무시하고 오브젝트에 집중하는 것과 같은 효과

#### object 추출

- 비배경 값들에서 구분 가능한 오브젝트/영역 추출
- 각 오브젝트: 값, 위치, 크기, 모양, 패턴
- **아직 뭐가 뭔지 모름** — 움직이는지, 상호작용 가능한지 전부 unknown
- 결과를 `objects` 딕셔너리에 저장

```json
"objects": {
  "name": {"value": "...", "position": "...", "type": "unknown"}
}
```

**종료 조건**: 첫 OBSERVE 완료

### Phase 2: Action Effect Discovery

액션을 1개씩 실행하고 **뭐가 바뀌었는지** 관찰.

- 방향키 1개 테스트 → before/after 비교 → 어떤 오브젝트가 움직였는지 확인
  - 움직인 오브젝트 → `type: "controllable"` (캐릭터일 수도, 커서일 수도, 전체 보드일 수도)
  - 안 움직인 오브젝트 → `type: "static"` (벽, 배경 등)
- 방향키 1개 검증 → 나머지 3개 추론 (confidence 0.5)
- space, click, undo는 각각 개별 테스트

```
up 테스트 → "오브젝트 A가 2칸 위로 이동"
→ A.type = "controllable"
→ actions.up = {"effect": "moves A up 2", "confidence": 0.7}
→ actions.down/left/right = {"effect": "inferred", "confidence": 0.5}
```

**종료 조건**: available actions 평균 confidence ≥ 0.7

### Phase 3: Interaction Discovery

controllable을 써서 다른 오브젝트에 접근/작용 시도.

- objects에서 `type: "unknown"` 또는 `type: "static"`인 것들이 **interaction candidate**
- controllable을 candidate 근처로 이동시켜서 접촉/통과 시도
- 결과에 따라:
  - 성공 (뭔가 변화) → `interactions` 리스트에 추가, object type 갱신
  - 실패 (변화 없음) → candidate에서 제거, `type: "non-interactive"`
  - 위험 (game_over) → `dangers` 리스트에 추가

```json
"interactions": [
  {"subject": "...", "object": "...", "action": "...", "result": "...", "confidence": 0.0}
],
"dangers": [
  {"object": "...", "condition": "...", "result": "game_over"}
]
```

**종료 조건**: untested interaction candidate가 없음

### Phase 4: Goal Discovery + Execution

- 확인된 interaction들을 조합해서 win condition 가설 수립
- 가설 검증 시도
- 레벨 클리어 → 다음 레벨에 carry-over

**종료 조건**: goal confidence ≥ 0.7 또는 레벨 클리어

### Phase 전환 (코드에서 관리)

```python
def get_current_phase(world_model: dict) -> str:
    objects = world_model.get("objects", {})
    actions = world_model.get("actions", {})
    interactions = world_model.get("interactions", [])
    goal = world_model.get("goal", {})

    if not objects:
        return "static_observation"

    action_avg = sum(a.get("confidence", 0) for a in actions.values()) / max(len(actions), 1)
    if action_avg < 0.7:
        return "action_discovery"

    untested_candidates = [o for o in objects.values() if o.get("type") in ("unknown", "static") and o.get("interaction_tested") != True]
    if untested_candidates:
        return "interaction_discovery"

    return "goal_execution"
```

### 단기 플랜 vs 장기 플랜

| | immediate_plan (이번 액션) | strategic_plan (현재 phase 목표) |
|---|---|---|
| **Phase 1** | "analyze first frame" | "identify all objects" |
| **Phase 2** | "test up action" | "discover all action effects" |
| **Phase 3** | "approach lime block" | "test all interaction candidates" |
| **Phase 4** | "push block to target" | "clear level 1" |

DECIDE 프롬프트에 `phase`, `immediate_plan`, `strategic_plan`을 전달.

### World Model 전체 구조 (업데이트)

```json
{
  "phase": "static_observation",
  "game_type": {"hypothesis": "unknown", "confidence": 0.0},
  "actions": {
    "up": {"effect": "unknown", "confidence": 0.0},
    "down": {"effect": "unknown", "confidence": 0.0}
  },
  "objects": {
    "lime_block": {"value": "c", "position": "row 46-47", "type": "unknown", "interaction_tested": false}
  },
  "controllable": {"description": null, "confidence": 0.0},
  "goal": {"description": null, "confidence": 0.0},
  "interactions": [],
  "dangers": [],
  "immediate_plan": "analyze first frame to identify all objects",
  "strategic_plan": "identify all distinguishable objects on screen"
}
```

### 코드 힌트 (DECIDE에 전달)

```python
phase = get_current_phase(world_model)
if phase == "action_discovery":
    untested = [k for k, v in world_model["actions"].items() if v["confidence"] == 0.0]
    hint = f"Phase: ACTION_DISCOVERY. Untested: {untested}. Test one."
elif phase == "interaction_discovery":
    candidates = [k for k, v in world_model["objects"].items() if v.get("type") in ("unknown", "static")]
    hint = f"Phase: INTERACTION_DISCOVERY. Candidates: {candidates}. Approach one."
elif phase == "goal_execution":
    hint = f"Phase: GOAL_EXECUTION. Win condition: {world_model['goal']}. Execute strategy."
```

### 흐름 예시

```
[Phase 1: Static Observation]
step 1: OBSERVE(첫 프레임) → objects: lime_block, maroon_block, green_corridors, teal_stripe
  → 모두 type: "unknown"

[Phase 2: Action Discovery]
step 1: DECIDE(up) → EXECUTE → EVALUATE: "lime_block moved up 2 rows"
  → lime_block.type = "controllable", actions.up = 0.7, down/left/right = 0.5
step 2: DECIDE(space) → EXECUTE → EVALUATE: "no change"
  → actions.space = 0.0 (no effect)
  → phase 종료 (avg confidence ≥ 0.7)

[Phase 3: Interaction Discovery]
step 3: DECIDE(move toward maroon_block) → EXECUTE → EVALUATE: "game_over"
  → dangers: [{object: maroon_block, result: game_over}]
step 4: DECIDE(move toward teal_stripe) → EXECUTE → EVALUATE: "level_complete"
  → interactions: [{controllable→teal_stripe, result: level_complete}]

[Phase 4: Goal Execution]
step 5+: 목표를 향해 전략적 플레이
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