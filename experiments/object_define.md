# 알고리즘 기반 오브젝트 정의 설계

LLM에게 오브젝트 위치/크기 추정을 맡기지 않고, 코드가 수학적으로 먼저 추출한 뒤 LLM에게 역할/이름 부여만 시킨다.

---

## 1단계: 배경 색상 판별 (`detect_background_colors`)

### 기준
- **빈도수**: 색상별 셀 수를 정렬. 상위 2~3개 색이 전체의 X% 이상 → 배경 후보
- **크기 기준**: 해당 색의 bounding box가 화면 넓이/높이의 50% 이상 → 배경 or wall
- **빈도 유사도**: 1,2위 색 빈도가 비슷(예: 1위의 70% 이상)이면 둘 다 배경 후보
- **체크무늬 탐지**: 2개 색이 교대로 나타나면 → 체크무늬 배경 (둘 다 배경)
- **픽셀 분산도**: 배경 색은 그리드 전체에 고르게 분포. 오브젝트 색은 국소적으로 밀집.

### 출력
```python
{"bg_colors": {"2", "0"}, "wall_colors": {"c"}}
```

---

## 2단계: 카메라 이동/회전 감지 (`detect_frame_shift`)

### 구현 방식
**numpy 기반. pure Python 루프 없음.**

#### 평행 이동 감지 (SSE)
```python
# np.roll로 shift 적용 후 평균 제곱 오차
sse = np.mean((np.roll(arr_a, (-dr, -dc), axis=(0,1)) - arr_b) ** 2)
```
- 탐색 범위: 각 애니메이션 프레임당 ±4 셀 (애니메이션 1프레임 = 소이동)
- diff < threshold면 SSE 계산 생략 (성능 최적화)

#### 회전 감지 (1도 단위)
- scipy 없이 numpy로 nearest-neighbor 역방향 매핑:
```python
# 역회전 행렬로 src 좌표 계산 → 원본 픽셀 샘플링
src_r = cos(a)*yr + sin(a)*xc + cy
src_c = -sin(a)*yr + cos(a)*xc + cx
```
- **카메라**: 평행이동 먼저, SSE 개선 부족 시 ±10도 탐색 (1도 step)
- 회전 + 평행이동 combined: rotate 후 ±2 shift 추가 탐색

#### 회전 vs 평행이동 판정
- sse_translate 대비 sse_rotate가 15% 이상 개선 → 회전 감지

### 좌표 보정
카메라가 (dr, dc) 이동 시 → 모든 `bbox`에 (-dr, -dc) 적용
회전 감지 시 → 별도 `camera_rotation` 이벤트 기록 (bbox 보정 로직 미정)

---

## 3단계: 연결 컴포넌트 추출 (`extract_blobs`)

배경 제거 후 나머지 색상에 대해 4-connected flood fill 실행.

### 필터링
- **1픽셀 노이즈 제거**: 셀 수 1 (또는 threshold 이하) → 제거
- **HUD 탐지**: 화면 가장자리(row 0~2 or col 0~2 or 끝 2줄) 고정 위치 → `hud` 태깅
- **Hollow 탐지**: blob의 내부에 배경 색이 있으면 → 해당 blob이 frame(테두리)일 가능성

### Enclosure 기반 완전 합병 (`_merge_enclosed_blobs`)
추출 후 post-process: blob B의 bbox가 blob A의 bbox 안에 완전히 포함되면 B를 A에 흡수.

**가정**: 게임 시작 시 독립된 두 오브젝트는 서로의 bbox 안에 완전히 포함되지 않는다.

**합병 규칙**:
- `A.bbox_area > B.bbox_area` → B는 A의 내부 패턴
- 같은 bbox_area면 `cell_count` 큰 쪽이 컨테이너
- 합병 결과: `A.colors += B.colors` (deduplicated), `A.cell_count += B.cell_count`, B 제거
- 체인: C⊂B⊂A → C, B 모두 A에 흡수 (root까지 follow)

**이점**: downstream 코드 변경 없음. 이동/충돌 판정은 합병된 composite blob 기준으로 자동 적용.

### 추가 아이디어
- **Enclosing 관계**: blob A의 bbox 안에 blob B가 완전히 포함 → A가 배경/container일 확률 높음
- **Symmetry**: blob의 좌우/상하 대칭 → 벽/배경 구조물 가능성
- **Aspect ratio**: 가로가 훨씬 긴 flat 직사각형 → 플랫폼/floor. 세로가 훨씬 긴 → 기둥/wall
- **Color rarity**: 전체 그리드에서 희귀한 색(5셀 미만) → 특수 오브젝트 (player, goal 등)
- **Multi-frame stability**: 여러 프레임에서 같은 위치 → static. 움직이면 → dynamic
- **Relative size**: 전체 오브젝트 대비 크기. 가장 작은 단일 blob → player 후보

---

## Blob 매칭 (`match_blobs`) — 2-pass 전략

**Pass 1 (색상 우선)**: 동일 color set + manhattan ≤ max_dist → 매칭
**Pass 2 (위치 fallback)**: Pass 1에서 매칭 안 된 prev blob에 대해, 색상 무시하고 위치 + cell_count(±60%) 기준으로 매칭
- Pass 2 매칭 = 색상이 바뀐 transform 후보 → `_detect_rotation_or_transform`이 `color_diff >= 0.05` 감지해 `transform` 이벤트 emit

**Pass 2 없이는**: 색상이 바뀐 blob → unmatched_prev(disappear) + unmatched_curr(appear)로 처리돼 transform 이벤트 발생 불가.

---

## 4단계: 오브젝트 분류 태깅 (코드 자동)

```python
{
  "color": "e",
  "bbox": {"row_min": 10, "row_max": 14, "col_min": 10, "col_max": 12},
  "cell_count": 15,
  "shape_tags": ["rectangle", "solid"],  # hollow, L-shape, etc.
  "candidate_roles": ["static", "platform"],  # 코드 추정
  "aspect_ratio": 1.67,
  "is_rare_color": False,
  "near_edge": False
}
```

---

## 5단계: LLM에 역할 부여 요청

코드가 추출한 blob 목록을 LLM에 전달. LLM은 위치/크기 추정 불필요.

```
Detected objects (code-extracted, exact positions):
- blob_1: color=e, bbox=row10-14/col10-12, size=15 cells, rectangle, not rare
- blob_2: color=9, bbox=row32-32/col20-20, size=1 cell, rare color → likely player or goal

Assign: name, type_hypothesis for each blob.
```

---

## 구현 우선순위

1. `detect_background_colors(grid)` — 빈도+분포 기반
2. `extract_blobs(grid, bg_colors)` — flood fill
3. `detect_camera_shift(prev_grid, curr_grid, bg_colors)` — 배경 패턴 비교
4. SCAN 프롬프트 수정: 코드 추출 blob 목록 + 이름/역할만 요청

---

## 추가 아이디어

### Action-Response Correlation (강력)
액션 실행 후 어떤 blob이 이동했는지 diff로 확인 → 그게 controllable 오브젝트.
- `right` 실행 → blob_2가 col+1 이동 → blob_2 = player
- 여러 액션 축적하면 confidence 높아짐
- 코드가 자동으로 `type_hypothesis: "controllable"` 태깅 가능

### Temporal Change Density
여러 프레임에 걸쳐 셀별 변경 빈도 계산 → heatmap.
- 자주 바뀌는 셀 = player/dynamic 오브젝트 경로
- 한 번도 안 바뀐 셀 = 확실한 static background

### Contact/Touching Detection
두 blob이 edge를 공유하면 "touching" 관계.
- push 메카닉 추정에 중요 (player가 박스를 push)
- touching 오브젝트 쌍을 world model에 기록

### Coverage 기반 Collide + Disappear 처리

**문제**: 오브젝트가 빠르게 이동(5px/frame)할 때 adjacent 체크를 건너뛰어 collide 미감지.
오브젝트가 완전히 다른 오브젝트 위를 덮으면 curr_raw에서 사라짐(hidden).

**Collide 감지 방식 (두 가지 경로)**:

**경로 1 — 살아있는 blob 간 overlap** (`detect_frame_events` main loop):
```python
# _adjacent (1px buffer) → 제거
# _bbox_overlaps (실제 좌표 겹침) → collide 발생
if _bbox_overlaps(cb_a.bbox, cb_b.bbox):  # → collide event
```

**경로 2 — coverage 감지** (disappear loop):
```
for each disappeared blob B (unmatched_prev):
  1. collide_destroy: 이전 프레임 collide 상태면 → "collide_destroy"
  2. covered: 현재 프레임 어떤 blob A의 bbox가 B의 last bbox와 overlap →
     - cause = "covered"
     - collide(A, B) 이벤트 emit (disappear 앞에)
     - curr_collide_pairs에 추가
  3. else: "unknown"
```

**설계 이유**: adjacent(인접) 체크는 5px/frame 이동 시 건너뜀. overlap(겹침)은 완전 커버 및 좌표 공유를 모두 감지.

**출력 이벤트 순서** (같은 프레임):
```json
{"type": "collide", "obj_a": "obj_006", "obj_b": "obj_004", "frame": 2}
// disappear는 즉시 emit하지 않음 → 아래 Deferred Disappear 참조
```

### Deferred Disappear (coverage 기반)
`cause="covered"` disappear는 **즉시 emit하지 않는다**. collision 이벤트로 coverage가 전달됐으므로.
대신 `BlobManager._covered_by: dict[str, str]` 로 추적 (`covered_pid → covering_pid`).

```
매 프레임 체크:
  1. covered blob이 재등장(reappear) → _covered_by에서 제거, 이벤트 없음
  2. covering blob이 이동해서 더 이상 covered blob 위치를 덮지 않음
     → disappear(cause="collide_destroy") emit, _covered_by에서 제거
  3. 여전히 덮여있음 → 계속 추적
```

이 방식으로 collision 후 분리 시점에 disappear가 결정되므로 LLM이 인과관계를 올바르게 파악.

**재등장(reappear) ID 지속** (`_remap_blobs`):
`unmatched_curr` 처리 시 `is_present=False` absent blob 중 동일 색상 + 8셀 이내 위치 → 기존 ID 재사용.

```
재등장 매칭 조건:
  - set(ob.colors) == set(cb.colors)
  - manhattan(ob.last_seen_bbox.center, cb.center) <= 8
→ 기존 ID/name/type_hypothesis 재사용
```

**Absent blob carry-forward** (`_remap_blobs` 마지막):
`match_blobs`의 `unmatched_prev`는 present→absent 블롭만 포함. 이미 absent인 블롭은 포함되지 않아
`_remap_blobs` 이후 `new_blobs`에서 누락됨 → 2프레임 이상 absent 시 완전 삭제.

Fix: 루프 끝에 `corrected_prev` absent 블롭 중 `new_blobs`에 없는 것을 그대로 carry-forward.
```python
for oid, ob in corrected_prev.items():
    if not ob.is_present and oid not in new_blobs:
        new_blobs[oid] = ob  # camera-corrected; last_seen_bbox 누적 보정됨
```

### Texture vs Solid
blob 내부에 2색 이상이 규칙적으로 반복 → texture = background.
모든 셀이 단색 → solid = 오브젝트.

### Occlusion Tracking
이전 프레임에 있던 blob이 사라지고 같은 위치에 다른 blob → 뒤에 숨겨진 것.
오브젝트가 "disappeared"가 아니라 "hidden" 상태로 처리.

### is_present — 오브젝트 생존 상태 추적
오브젝트를 world model에서 **삭제하지 않는다**. 대신 `is_present` 필드로 관리.

```json
"obj_003": {
  "name": "key",
  "is_present": false,
  "last_seen_step": 7,
  "last_seen_bbox": {"row_min": 20, "row_max": 20, "col_min": 15, "col_max": 15},
  "disappear_reason": "collected"  // "collected", "hidden", "destroyed", "unknown"
}
```

- `is_present: true` → 현재 그리드에 존재
- `is_present: false` → 사라졌으나 기록 유지 (수집됐거나, 가려졌거나, 소멸됐거나)
- 코드가 매 프레임 blob list와 기존 오브젝트를 비교해서 자동 업데이트
- 다시 나타나면 → `is_present: true`로 복원, `reappear_step` 기록
- `disappear_reason` 추론: 같은 위치에 다른 오브젝트 → `hidden`. 없어졌을 때 score 증가 → `collected`. 그냥 사라짐 → `unknown`

---

### 이동 코히어런스 기반 오브젝트 그룹핑 (`apply_color_merge_groups`)

**merge 조건 (둘 다 충족해야)**:
1. **첫 이동 타이밍**: 두 blob 모두 이 프레임이 첫 이동 (이전에 한 번도 이동 안 함)
2. **이동 동일**: 같은 `(dr, dc)`로 이동

**가정**: 게임 시작 시 독립된 두 오브젝트가 항상 같은 delta로 이동하지 않는다.

**구현 방식** (`run_animation_analysis`):
```
- tracking["ever_moved_sigs"]: 한 번이라도 이동한 color sig (frozenset) 집합
- tracking["color_merge_groups"]: 학습된 merge group 목록 (frozenset of color chars)
- 매 프레임: 첫 이동 blob 쌍이 동일 delta → color_merge_groups 추가
- 이후 모든 프레임: apply_color_merge_groups(curr_raw, groups) 로 자동 합병
- current_blobs에도 즉시 적용 → 다음 프레임 corrected가 이미 merged 상태로 시작
```

**일회성 지연**: 최초 감지 프레임에서는 separate 상태로 이벤트 처리. 다음 프레임부터 merged.

**출력 이벤트**:
```json
{"type": "merge", "obj_a": "obj_003", "obj_b": "obj_004", "frame": 0}
```

**포메이션 움직임** (적 여러 개가 같은 방향으로 이동):
- 처음 이동 시 같은 delta면 merge됨 → 같은 오브젝트로 처리
- 이후에 분리되는 경우는 미처리 (현재 split 로직 없음)

---

## 이벤트 출력 구조: animation vs result

액션 결과를 두 레이어로 LLM에 전달:

```json
{
  "animation": [ ... ],
  "result": [ ... ]
}
```

### `animation` (per-frame 연속 비교)
- 애니메이션 각 프레임 쌍 (frame[i-1] → frame[i]) 비교
- 포함 이벤트: `move`, `collide`, `disappear`, `camera_shift`, 중간 `transform`/`rotation`
- **`appear`는 마지막 프레임에서만** emit (`emit_appear=True` 플래그)
  - 이유: 카메라 이동 중 화면 가장자리에서 오브젝트가 잘려 보임 → 중간 프레임 appear는 partial blob
  - 마지막 프레임에서 완전히 보이는 오브젝트만 새 오브젝트로 정의
- 목적: 게임이 어떻게 진행됐는지 단계별 이해

### `result` (시작 vs 끝 1회 비교)
- `prev_grid` → `anim_frames[-1]` 단순 비교
- 포함 이벤트: `rotation`, `transform`, `move` (net 이동)
- 목적: 액션의 최종 결과만 요약
- `detect_transform_rotation(prev_blobs, curr_blobs, arr_prev, arr_final)` 로 생성
  - 블롭은 **ID로 매칭** (동일 ID = 동일 오브젝트)
  - camera 보정 불필요 (원본 arr 그대로)

### 한 오브젝트에 여러 이벤트 허용
flat list이므로 동일 obj가 여러 번 등장 가능:
```json
"result": [
  {"type": "move",     "obj": "obj_007", "delta": [-1, 0]},
  {"type": "rotation", "obj": "obj_007", "angle_deg": 90}
]
```

---

## 오브젝트 Rotation / Transform 감지

### `detect_transform_rotation` (public)
`object_event_detector.py`에 추가된 공개 함수.
- 입력: `prev_blobs`, `curr_blobs`, `arr_a` (prev_grid), `arr_b` (last anim frame)
- ID 매칭으로 각 쌍에 `_detect_rotation_or_transform` 호출
- camera 보정 없음 → 원본 bbox 그대로 사용

### `_detect_rotation_or_transform` 감지 순서
```
1. 색상 마스킹 (NEW)
   crop_a, crop_b에서 blob 자체 색상 픽셀만 유지, 나머지 0으로 마스킹
   colors_a/colors_b: set of hex chars (blob.colors, int(c,16) 비교)
   → 이동 시 배경/인접 blob 픽셀 차이로 인한 false rotation/transform 방지
2. covering_bboxes 마스킹
   다른 blob이 덮은 영역을 crop_a, crop_b 양쪽 모두 0으로 설정
   → 오버랩 영역의 색 변화가 rotation/transform으로 오판되는 것 방지
3. 90°/180°/270° SSE 체크
   → SSE 12% 이상 개선 시 rotation 반환 (ROT_THRESHOLD=0.88)
4. color_diff (pixel-level MAD)
   nonzero_mask = (pa != 0) & (pb_pad != 0)  ← intersection (AND)
   두 crop 모두 blob 픽셀이 있는 위치만 비교
   → pa=0(coverage 후) but pb_pad≠0(노출) 케이스 제외 → false transform 방지
   color_diff = mean(|pa - pb_pad|[intersection]) / 9.0
   color_diff >= 0.05 → transform 반환
5. 세부 각도 1° 탐색 (90° 배수 제외)
   → SSE 12% 이상 개선 시 rotation 반환
```

**핵심 설계 이유 (intersection vs union)**:
- collision 후 blob A가 blob B 위를 지나갔다 떠날 때:
  - frame_A(이전): B의 bbox에 A 픽셀 → color mask로 0
  - frame_B(이후): B 노출 → B 픽셀 non-zero
  - union `|`: 해당 셀 포함 → MAD > 0 → false transform
  - intersection `&`: pa=0이므로 제외 → MAD = 0 ✓

### 출력 이벤트
```json
{"type": "rotation",  "obj": "obj_007", "angle_deg": 90,  "frame": 5}
{"type": "transform", "obj": "obj_010", "color_diff": 0.35, "frame": 5}
```

---

## 레벨 전환 처리

### 감지 조건
`obs_result.levels_completed` 값이 이전 스텝 대비 증가 → 레벨 전환

### 처리 순서

**1. tracking 완전 리셋**
- ID, 위치, collide_pairs, color_merge_groups, ever_moved_sigs 모두 초기화
- 새 레벨에서 blob 전부 새로 감지 (`extract_blobs`)

**2. color ratio 기반 name/type 이어받기**
- `Blob`에 `color_ratios: dict[str, float]` 추가 (각 색의 셀 비율, `extract_blobs` 시 계산)
- 새 레벨 blob vs 이전 레벨 blob: color histogram L1 거리 비교
- 가장 가까운 매칭 (threshold ≤ 0.25) 존재 시 → `name`, `type_hypothesis` 이어받기
- **위치 무관**, 색상 비율만으로 매칭 (레벨마다 위치 다름)

```python
def color_hist_dist(h1: dict, h2: dict) -> float:
    all_colors = set(h1) | set(h2)
    return sum(abs(h1.get(c, 0.0) - h2.get(c, 0.0)) for c in all_colors)
# ≤ 0.25 → 같은 오브젝트 타입 추정
```

**3. LLM 검증 트리거**
레벨 전환 직후 LLM에 아래 정보를 전달하여 "이전 레벨과 동일 오브젝트인지" 판단 요청:
```json
{
  "event": "level_transition",
  "new_level": 2,
  "objects": [
    {
      "name": "obj_001",
      "inherited_from": "obj_003",
      "color_match_ratio": 0.92,
      "color_ratios": {"3": 0.6, "0": 0.4},
      "prev_type_hypothesis": "player",
      "bbox": {"row_min": 10, "row_max": 15, "col_min": 8, "col_max": 12}
    }
  ]
}
```
- `color_match_ratio`: `1 - color_hist_dist(new, old)` (1.0 = 완전 일치)
- `inherited_from`: 매칭된 이전 레벨 오브젝트 ID
- LLM이 `is_same_object: true/false` + 최종 name/type 확정

### `Blob` 필드 추가
```python
color_ratios: dict = field(default_factory=dict)  # {"3": 0.6, "0": 0.4}
```

---

## move 이벤트 합산 (`merge_events`)

같은 오브젝트의 연속 move 이벤트를 방향이 유지되는 동안 delta를 합산.

```python
def _same_direction(d1, d2):
    return d1[0] * d2[0] >= 0 and d1[1] * d2[1] >= 0
```

- `(-5,0) + (-5,0)` → `Δ(-10,0)` (합산) ✓
- `(-5,0) + (5,0)` → 별도 항목 2개 (부호 반전, 정보 손실 방지) ✓
- 합산 시 `delta` 누적, `frames[1]` 확장, `to` 갱신

---

## GAME_OVER 처리

`game_state == "GAME_OVER"` 시 `_run_animation_analysis` 스킵.

**이유**: game over 애니메이션(전체 화면 번쩍임 등)은 시각 효과이고 게임 정보가 없음.
Game over의 원인은 직전 스텝의 collide/disappear 이벤트에서 이미 기록됨.

```python
if game_state == "GAME_OVER":
    self.current_frame = anim_frames[-1]
    return [{"type": "game_over"}], [], None
```

- tracking 상태(`_blobs`, `_covered_by` 등) 유지
- `current_frame`만 마지막 프레임으로 업데이트
- `game_over` 이벤트 1개만 emit

---

## 미해결 문제

- 체크무늬 배경 위의 동일 색 오브젝트 → 배경과 구분 어려움
- 카메라 이동 vs 오브젝트 이동 → 모든 blob이 같은 방향 이동 시 카메라로 판단
- T=0 멀티컬러 오브젝트 → 1스텝 이상 관찰 전까지는 blob 단위로 처리, LLM이 임시 이름 부여
