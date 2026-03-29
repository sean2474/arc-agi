# 오브젝트 시스템 ↔ LLM 에이전트 통합 설계

코드가 수학적으로 오브젝트를 추적하고, LLM은 **이름/역할 부여 + 고수준 해석**만 담당한다.

---

## 전체 아키텍처

```
BlobManager (코드)
  ├─ extract_blobs()         → 현재 프레임 blob 추출
  ├─ step()                  → animation_events, result_events
  └─ _archive                → color_sig → canonical obj_id (레벨 간 영속)
          ↓
  WorldModel (브리지)
  ├─ objects: {obj_id: {name, bbox, colors, type_hypothesis, is_present}}
  └─ to_prompt_dict()        → LLM 프롬프트용 직렬화
          ↓
  LLM Steps
  ├─ SCAN      → blob 목록 받고 name/type 부여
  ├─ OBSERVE   → events + 이미지 받고 해석 + world model 업데이트
  └─ DECIDE    → world model 보고 다음 액션 결정
```

---

## 단계별 변경사항

### SCAN (Phase 1 — 첫 프레임)

**기존**: LLM이 이미지에서 오브젝트를 직접 식별 (위치/크기 추정)

**변경**: 코드가 추출한 blob 목록을 LLM에 전달 → **이름/역할만 부여**

```
프롬프트 추가 섹션:

CODE-EXTRACTED OBJECTS (exact positions, do not re-estimate):
- obj_001: colors=[e], bbox=row10-14/col8-12, cells=15, shape=solid_rect, rare=false
- obj_002: colors=[9], bbox=row32/col20, cells=1, shape=single_pixel, rare=true
- obj_003: colors=[3,e], bbox=row0-2/col0-63, cells=128, shape=line_h, near_edge=top

For each object, assign ONLY:
- "name": game-role based (e.g. "player", "exit", "wall"). NOT color/shape.
- "type_hypothesis": "player"|"goal"|"obstacle"|"platform"|"hud"|"unknown"

Do NOT re-estimate positions. Use bbox as given.
```

**LLM 응답 형식**:
```json
{
  "object_roles": {
    "obj_001": {"name": "player", "type_hypothesis": "player"},
    "obj_002": {"name": "exit",   "type_hypothesis": "goal"},
    "obj_003": {"name": "floor",  "type_hypothesis": "platform"}
  }
}
```

**WorldModel 업데이트**:
`agent._blob_manager._blobs`의 각 blob에 LLM이 부여한 name/type을 덮어쓴다.
그 후 `WorldModel.sync_from_blobs(blobs)` 로 world model objects 갱신.

---

### OBSERVE (Phase 2+ — 액션 후)

**기존**: `summarize_diff` (셀 단위 변경 요약 문자열)

**변경**: `animation_events` + `result_events` (구조화 이벤트 목록)

```
프롬프트 섹션 교체:

CODE-DETECTED EVENTS (animation frames):
  move     player Δ(-1,0) f0-f2
  collide  player × wall f3
  disappear exit cause=collected f3

CODE-DETECTED EVENTS (final result):
  rotation obj_007 270°

(Images: BEFORE left, AFTER right)

STEP 1 - VERIFY events: Do the images confirm or contradict these events?
STEP 2 - MISSING: Any changes in images NOT captured in events?
STEP 3 - CLASSIFY: Update type_hypothesis for any object if new evidence.
STEP 4 - NAME REVIEW: Should any object be renamed based on what happened?
```

**이벤트 → 텍스트 변환** (`format_events_for_prompt(events)`):

| 이벤트 타입 | 출력 |
|---|---|
| `move` | `move  {obj} Δ({dr},{dc}) f{frame}` |
| `collide` | `collide  {obj_a} × {obj_b} f{frame}` |
| `disappear` | `disappear  {obj} cause={cause} f{frame}` |
| `appear` | `appear  {obj} at ({r},{c}) f{frame}` |
| `rotation` | `rotation  {obj} {angle}° f{frame}` |
| `transform` | `transform  {obj} color_diff={val} f{frame}` |
| `merge` | `merge  {obj_a} + {obj_b} f{frame}` |
| `camera_shift` | `camera_shift  Δ({dr},{dc}) f{frame}` |
| `game_over` | `game_over f{frame}` |

**LLM 응답 형식** (OBSERVE):
```json
{
  "event_verification": "confirmed|partial|contradicted",
  "missing_events": "...",
  "object_updates": {
    "obj_001": {"type_hypothesis": "player", "name": "player"}
  },
  "new_objects": {},
  "renamed_objects": {},
  "relationship_updates": []
}
```

---

### WorldModel ↔ BlobManager 동기화

`agent._blob_manager: BlobManager` 를 `LLMAgent`에 추가.

**sync 방향**:
```
BlobManager → WorldModel  (매 step 후 자동)
  blobs의 is_present, bbox, colors → objects 갱신
  LLM이 부여한 name/type은 blob.name / blob.type_hypothesis에 저장됨 → 그대로 반영

WorldModel → BlobManager  (LLM 응답 처리 후)
  LLM이 name/type을 수정 → blob.name / blob.type_hypothesis 업데이트
```

`WorldModel.sync_from_blobs(blobs: dict[str, Blob])` 메서드:
```python
def sync_from_blobs(self, blobs: dict):
    for oid, b in blobs.items():
        if oid not in self._data["objects"]:
            self._data["objects"][oid] = {}
        obj = self._data["objects"][oid]
        obj["bbox"]            = b.bbox
        obj["colors"]          = list(b.colors)
        obj["cell_count"]      = b.cell_count
        obj["shape_tags"]      = b.shape_tags
        obj["is_present"]      = b.is_present
        if b.name:
            obj.setdefault("name", b.name)
        if b.type_hypothesis:
            obj.setdefault("type_hypothesis", b.type_hypothesis)
    # Remove objects no longer tracked
    tracked = set(blobs.keys())
    for oid in list(self._data["objects"].keys()):
        if oid not in tracked:
            del self._data["objects"][oid]
```

`WorldModel.push_names_to_blobs(blobs: dict[str, Blob])` 메서드:
```python
def push_names_to_blobs(self, blobs: dict):
    for oid, obj in self._data["objects"].items():
        if oid in blobs:
            if "name" in obj:
                blobs[oid].name = obj["name"]
            if "type_hypothesis" in obj:
                blobs[oid].type_hypothesis = obj["type_hypothesis"]
```

---

## 이미지 어노테이션

`grid_to_image_base64_annotated(grid, objects)` — blob bbox 기반 오버레이.

OBSERVE의 before/after 이미지에는 obj_id 라벨을 bbox 위에 표시.
이렇게 하면 LLM이 이미지와 이벤트 텍스트를 obj_id로 연결 가능.

---

## 레벨 전환 처리 변경

기존: `_handle_level_transition` 반환값에 `cross_matches`만 있음.

변경:
1. `_remap_with_archive()` 로 canonical ID 복원 (이미 구현)
2. OBSERVE 대신 별도 **INCIDENT** 프롬프트 트리거:
   ```
   LEVEL TRANSITION DETECTED (level {n})
   
   Known objects (restored from archive):
   - obj_001: "player", colors=[e] → present at row12/col5
   - obj_003: "exit",   colors=[9] → NOT PRESENT this level
   
   New objects (unseen color types):
   - obj_025: colors=[4], bbox=row20/col8, cells=3
   
   Update world model for new level.
   ```

---

## 구현 순서

1. `LLMAgent.__init__`에 `self._blob_manager: BlobManager` 추가
2. `WorldModel.sync_from_blobs()` / `push_names_to_blobs()` 메서드 추가
3. SCAN 프롬프트: blob 목록 섹션 추가 (`build_scan_message` 파라미터 추가)
4. SCAN 응답 처리: `object_roles` → blob에 name/type 주입 → WorldModel sync
5. `format_events_for_prompt(events)` 유틸 함수 작성
6. OBSERVE 프롬프트: `diff_summary` 대신 formatted events 사용
7. OBSERVE 응답 처리: `object_updates` → WorldModel push → BlobManager sync
8. 레벨 전환: INCIDENT 프롬프트에 archive 기반 known/new 오브젝트 목록 전달

---

## 미결 설계 이슈

- **SCAN에서 blob이 너무 많을 때** (20개+): 코드가 major blob만 추려서 전달 (cell_count 상위 N개 또는 near_edge 제외)
- **LLM이 이벤트와 다른 해석을 할 때**: LLM 해석을 우선하되, 코드 이벤트를 근거로 재질문 가능
- **archive가 틀렸을 때** (다른 게임에서 같은 색 = 다른 역할): 레벨 전환 INCIDENT에서 LLM이 재명명 가능
