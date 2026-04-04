## Objects

### Player (tag: "caf", sprite: "pca")
- 9x9 사이즈, 색상 3 (초록)
- 이동 단위: 5픽셀씩 상하좌우

### Cursor/Tool (tag: "wex", sprite: "kdj")  
- 3x3 다이아몬드 모양, 색상 0
- 플레이어가 들고 다니는 도구
- **3가지 속성을 가짐**:
  - **Shape** (모양): 6가지 스프라이트 중 하나 (opw, lyd, tmx, nio, dcb, fij)
  - **Color** (색상): 4가지 중 하나 (12=빨강, 9=주황, 14=하늘, 8=파랑)
  - **Rotation** (회전): 4방향 (0, 90, 180, 270도)

### Target Slots (tag: "mae", sprite: "lhs")
- 5x5 사이즈, 색상 5 (회색) 배경
- 각 슬롯은 **정답 조합** (shape + color + rotation)을 가짐
- 커서 도구의 속성이 슬롯의 정답과 일치해야 슬롯을 클리어

### Target Indicators (tag: "axa")
- 슬롯 위에 표시되는 정답 힌트
- 어떤 shape+color+rotation이 필요한지 보여줌

### Walls (tag: "nfq", sprite: "hep")
- 10x10 사이즈, 색상 5 (회색)
- 충돌 가능, 이동 차단

### Maze Walls (sprite: "nlo")
- 5x5 사이즈, 색상 5 (회색)  
- 미로 구조를 형성

### Tool Modifiers (스테핑 패드)
- **Shape changer** (tag: "gsu"): 밟으면 커서 모양이 다음 것으로 순환
- **Color changer** (tag: "gic"): 밟으면 커서 색상이 다음 것으로 순환
- **Rotation changer** (tag: "bgt"): 밟으면 커서 회전이 90도씩 순환

### Collectible (tag: "iri")
- 밟으면 수집되고, 에너지(jvq) 보충

### Border Walls (tag: "jdd")
- 맵 경계, 이동 차단

### Goal Area (tag: "yar", sprite: "ggk")
- 7x7 사이즈, 색상 5
- 슬롯 주변의 프레임

### Match Indicator (tag: "qex")
- 슬롯 근처에 표시, 현재 커서 설정이 해당 슬롯과 매치되면 보임

### Goal Arrow (tag: "fng")
- 목표 방향을 가리키는 화살표, 매치되는 슬롯이 있을 때 보임

## Rules

### 이동
- ACTION1=위, ACTION2=아래, ACTION3=왼쪽, ACTION4=오른쪽
- 5픽셀씩 이동
- 벽(nfq), 미로벽(nlo), 경계(jdd)에 의해 차단

### 커서 도구 시스템
- 플레이어는 커서 도구를 들고 다님
- 도구에는 shape/color/rotation 3가지 속성이 있음
- 특수 패드를 밟으면 속성이 순환:
  - gsu 패드 → shape 변경 (6종류 순환)
  - gic 패드 → color 변경 (12→9→14→8→12...)
  - bgt 패드 → rotation 변경 (0→90→180→270→0...)

### 클리어 조건
1. 커서 도구의 (shape, color, rotation)을 타겟 슬롯의 정답 조합과 일치시킴
2. 해당 슬롯 위치로 이동하면 슬롯 클리어
3. **모든 슬롯을 클리어하면 레벨 클리어**

### 실패 조건  
- 에너지 시스템: 이동할 때마다 에너지 소모 (jvq 카운터)
- 에너지가 0이 되면 → 슬롯을 클리어하지 않은 채 이동하면 "miss" 카운트 증가
- lives(lbq) = 3, miss 3번이면 GAME_OVER
- miss 시 위치/커서/슬롯 상태 전부 리셋

### 레벨별 특수 효과
- 일부 레벨(kdy=True)은 시야 제한(radius 20 원형)

## Action Effects

| Action | Effect |
|--------|--------|
| ACTION1 (Up) | y -= 5 |
| ACTION2 (Down) | y += 5 |
| ACTION3 (Left) | x -= 5 |
| ACTION4 (Right) | x += 5 |

## Level Progression

- 7개 레벨
- 레벨 1: 슬롯 1개, 미로 간단
- 이후 레벨: 슬롯 증가, 미로 복잡, 시야 제한 추가

## Open Questions

- 에너지 시스템의 정확한 리필 메커니즘 (collectible 수집 시 리셋?)
- 후반 레벨의 시야 제한(kdy=True) 범위 정확성
