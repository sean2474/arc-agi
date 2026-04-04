# Design Patterns & SOLID

## Applicable Patterns

이 프로젝트에서 유용할 수 있는 패턴들. 상황에 맞게 적용.

- **Strategy**: 게임마다 다른 전략 알고리즘을 교체 가능하게
- **Observer**: 프레임 변화 감지 → 이벤트 발행 → 구독자 처리
- **State**: 에이전트 상태(탐색/실험/실행)에 따라 다른 행동
- **Repository**: 월드 모델/가설/기억을 저장소로 추상화
- **Pipeline**: 프레임 분석을 단계별 체인으로 구성

## SOLID Principles

Evaluator가 코드 리뷰 시 체크:

- **S** (Single Responsibility): 클래스/함수는 하나의 이유로만 변경되어야 한다
- **O** (Open/Closed): 확장에 열려있고 수정에 닫혀있게
- **L** (Liskov Substitution): 하위 타입은 상위 타입을 완전히 대체할 수 있어야 한다
- **I** (Interface Segregation): 클라이언트가 쓰지 않는 인터페이스에 의존하지 않기
- **D** (Dependency Inversion): 구체 클래스가 아닌 추상(Protocol/ABC)에 의존

## Anti-patterns to Avoid

- God Object: 하나의 클래스가 너무 많은 책임을 가짐
- Spaghetti Code: 함수 분리 없이 한 파일에 모든 로직
- Copy-Paste: 같은 코드 반복 대신 공통 모듈로 추출
- Premature Optimization: 먼저 작동하게, 그 다음 최적화
