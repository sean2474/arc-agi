# ARC-AGI-3 게임별 Observation Space 정리

총 **25개** 게임. 태그별 4개 대표 게임 조사.

---

## 전체 게임 목록

| game_id | title | tags | win_levels |
|---------|-------|------|------------|
| ls20 | LS20 | `keyboard` | 7 |
| sc25 | SC25 | `keyboard_click` | 6 |
| lf52 | LF52 | `click` | 10 |
| vc33 | VC33 | `click` | - |
| tu93 | TU93 | `keyboard_click` | - |
| sk48 | SK48 | `keyboard_click` | - |
| bp35 | BP35 | `keyboard_click` | - |
| lp85 | LP85 | `click` | - |
| ar25 | AR25 | `keyboard_click` | - |
| m0r0 | M0R0 | `keyboard_click` | - |
| cd82 | CD82 | `keyboard_click` | - |
| dc22 | DC22 | `keyboard_click` | - |
| r11l | R11L | `click` | - |
| ka59 | KA59 | `keyboard_click` | - |
| su15 | SU15 | `click` | - |
| wa30 | WA30 | `keyboard` | - |
| re86 | RE86 | `keyboard_click` | - |
| tr87 | TR87 | `keyboard` | - |
| s5i5 | S5I5 | `click` | - |
| sp80 | SP80 | `keyboard_click` | - |
| ft09 | FT09 | *(없음)* | 6 |
| g50t | G50T | `keyboard` | - |
| cn04 | CN04 | `keyboard_click` | - |
| tn36 | TN36 | `click` | - |
| sb26 | SB26 | `keyboard_click` | - |

### 태그 분포
- **keyboard** (4개): ls20, wa30, tr87, g50t — simple action만
- **keyboard_click** (12개): sc25, tu93, sk48, bp35, ar25, m0r0, cd82, dc22, ka59, re86, sp80, sb26, cn04 — simple + complex 혼합
- **click** (7개): lf52, vc33, lp85, r11l, su15, s5i5, tn36 — complex 포함
- **없음** (1개): ft09 — complex만

---

## 1. LS20 — `keyboard` (simple only)

```
tags:             ['keyboard']
win_levels:       7
baseline_actions: [21, 123, 39, 92, 54, 108, 109]  ← 레벨별 기준 스텝 수
```

### Action Space
```
ACTION1 (1) simple   ← 4방향 이동 추정
ACTION2 (2) simple
ACTION3 (3) simple
ACTION4 (4) simple
```

### Observation (RESET 직후)
```
state:             NOT_FINISHED
levels_completed:  0
win_levels:        7
available_actions: [1, 2, 3, 4]
frame count:       1
frame[0]:          shape=(64, 64) dtype=int8
                   unique=[0, 1, 3, 4, 5, 8, 9, 11, 12]
```

### ACTION1 후
```
frame count: 1     ← 프레임 수 변화 없음 (정적 응답)
frame[0]:    unique=[0, 1, 3, 4, 5, 8, 9, 11, 12]
```

> **특징**: 1 step = 1 frame. 단순한 그리드 이동 게임.

---

## 2. SC25 — `keyboard_click` (simple + complex)

```
tags:             ['keyboard_click']
win_levels:       6
baseline_actions: [39, 5, 32, 33, 66, 41]
```

### Action Space
```
ACTION1 (1) simple
ACTION2 (2) simple
ACTION3 (3) simple
ACTION4 (4) simple
ACTION6 (6) complex   ← x, y 좌표 필요
```

### Observation (RESET 직후)
```
state:             NOT_FINISHED
levels_completed:  0
win_levels:        6
available_actions: [1, 2, 3, 4, 6]
frame count:       1
frame[0]:          shape=(64, 64) dtype=int8
                   unique=[0, 2, 3, 5, 9, 10, 14, 15]
```

### ACTION1 후
```
frame count: 22    ← 대량의 프레임! (애니메이션)
frame[0~15]:  unique=[0, 2, 3, 5, 9, 10, 14, 15]
frame[16~20]: unique=[2, 3, 5, 9, 10, 14, 15]    ← 0이 사라짐 (변화 발생)
frame[21]:    unique=[0, 2, 3, 5, 9, 10, 14, 15]
```

> **특징**: 1 step에 여러 프레임 반환 (애니메이션 시퀀스). 중간 프레임에서 상태 변화 관찰됨.

---

## 3. LF52 — `click` (complex 포함)

```
tags:             ['click']
win_levels:       10
baseline_actions: [24, 81, 74, 86, 118, 148, 189, 116, 150, 225]
```

### Action Space
```
ACTION1 (1) simple
ACTION2 (2) simple
ACTION3 (3) simple
ACTION4 (4) simple
ACTION6 (6) complex   ← x, y 좌표 필요
ACTION7 (7) simple
```

### Observation (RESET 직후)
```
state:             NOT_FINISHED
levels_completed:  0
win_levels:        10
available_actions: [1, 2, 3, 4, 6, 7]
frame count:       2           ← RESET부터 2프레임
frame[0]:          shape=(64, 64) dtype=int8 unique=[0, 1, 5, 9, 10, 14]
frame[1]:          shape=(64, 64) dtype=int8 unique=[0, 1, 5, 9, 10, 14]
```

### ACTION1 후
```
frame count: 2
frame[0]: unique=[0, 1, 5, 9, 10, 14]
frame[1]: unique=[0, 1, 5, 9, 10, 14]
```

> **특징**: 레벨 10개로 가장 많음. baseline_actions도 큼 (최대 225). RESET 시부터 2프레임.

---

## 4. FT09 — 태그 없음 (complex only)

```
tags:             []
win_levels:       6
baseline_actions: [17, 19, 15, 21, 65, 26]
```

### Action Space
```
ACTION6 (6) complex   ← x, y 좌표만으로 플레이
```
> **simple action이 아예 없음** — 클릭 좌표만으로 게임 진행

### Observation (RESET 직후)
```
state:             NOT_FINISHED
levels_completed:  0
win_levels:        6
available_actions: [6]
frame count:       1
frame[0]:          shape=(64, 64) dtype=int8
                   unique=[0, 2, 4, 5, 8, 9, 12]
```

### ACTION6 후 (x=0, y=0 클릭)
```
frame count: 5     ← 클릭 한 번에 5프레임 애니메이션
frame[0~4]: unique=[0, 2, 4, 5, 8, 9, 12]
```

> **특징**: 순수 클릭 게임. baseline 스텝 수가 적어서(15~65) 상대적으로 단순할 수 있음.

---

## 핵심 발견

### frame 반환 패턴
| 게임 | RESET 후 frames | ACTION 후 frames | 패턴 |
|------|-----------------|------------------|------|
| LS20 | 1 | 1 | 1:1 정적 |
| SC25 | 1 | **22** | 애니메이션 시퀀스 |
| LF52 | 2 | 2 | 고정 멀티프레임 |
| FT09 | 1 | **5** | 애니메이션 시퀀스 |

### 공통 구조
- 모든 frame: **shape=(64, 64), dtype=int8**
- 값 범위: **0~15** (게임마다 사용하는 값이 다름)
- `available_actions`는 게임 내내 고정 (동적으로 변하지 않음)

### baseline_actions 의미
- 각 레벨을 클리어하는 데 필요한 **기준 액션 수**
- 예: ls20 레벨1=21스텝, 레벨2=123스텝
- 에이전트 성능 평가 기준으로 활용 가능