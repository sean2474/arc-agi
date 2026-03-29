# 아이디어 메모

## 이동/회전 탐지 히스토리 기반 최적화

**현황**: 현재 move/rotation 탐지는 매 프레임 0부터 순차 탐색 (+1, +2, +3, ...).

**아이디어**: 같은 액션을 반복하면 같은 이동 거리를 반복할 가능성이 높다.
직전 애니메이션에서 +3으로 이동했다면, 다음 탐색은 +3 ± 소폭 범위 먼저 시도.

**예시**:
```
직전 delta = (0, -5)
다음 탐색 순서: (0,-5), (0,-4), (0,-6), (0,-3), (0,-7), ...  ← 우선 탐색
실패 시 전체 범위 fallback
```

**적용 대상**:
- `match_blobs`: center 거리 계산 시 예상 위치 중심으로 먼저 탐색
- `_detect_rotation_or_transform`: rotation 탐색 시 직전 angle에서 ±몇 도 먼저 탐색
- `detect_frame_shift` (camera): 직전 camera shift에서 시작

**구현 시 필요한 것**:
- `tracking["last_deltas"]`: obj_id → 마지막 (dr, dc) dict
- `tracking["last_camera_shift"]`: (dr, dc, angle)
- `tracking["last_rotation_angle"]`: obj_id → 마지막 angle

**우선순위**: low (기능 완성 후 최적화 단계)

---

## LLM 입력: 좌표/크기 대신 아웃라인+이름 태그 이미지 전달

**현황**: LLM에 오브젝트 정보를 전달할 때 bbox 좌표, 크기 등 숫자 데이터를 전달.

**아이디어**: play 화면처럼 그리드 이미지 위에 오브젝트 아웃라인을 그리고 태그를 달아서 이미지로 전달.

**핵심 원칙**:
- 좌표값, 크기(cell_count) 등 숫자는 LLM에 전달하지 않음
- 대신 그리드 이미지에 오브젝트 경계를 아웃라인으로 표시
- 태그는 `obj_001` 같은 ID가 아니라 **LLM이 직접 지은 이름** (e.g. "player", "wall", "bullet")
- LLM이 이전에 이름을 붙인 오브젝트면 그 이름을 태그로 재사용

**전달 내용 (이미지 + 텍스트)**:
```
이미지: 그리드 + 각 오브젝트 아웃라인 + LLM-이름 태그
텍스트: 이벤트 목록 (move/collide/appear/disappear/transform 등)
         오브젝트별: LLM이름, 색상 조합, 발생 이벤트
```

**전달하지 않는 것**:
- bbox 좌표 (row_min, col_min 등)
- cell_count (크기)
- instance_id (obj_001 등 내부 ID)

**장점**:
- LLM이 시각적으로 직접 오브젝트를 인식 가능
- 숫자 대신 자연스러운 시각 정보로 spatial reasoning 향상
- LLM이 붙인 이름으로 일관성 있는 오브젝트 추적 가능

**구현 시 필요한 것**:
- `Blob.name`: LLM이 지은 이름 (이미 있음)
- 그리드 이미지 렌더링 + 아웃라인 오버레이 함수
- LLM 응답에서 오브젝트 이름 파싱 → `blob.name` 업데이트

**우선순위**: medium (LLM 통합 단계에서 구현)
