## Goal

VLM 에이전트를 Planner-Actor-Observer 3단계 구조로 재설계. Planner가 goal/subgoal을 설정하고, Actor가 subgoal을 실행하고, Observer가 프레임 변화를 감지하여 subgoal 달성 여부를 판단.

## Hypothesis

계층적 의사결정으로 일관된 방향성(planner)과 즉각적 반응(observer)을 동시에 달성할 수 있다. Planner는 비싸지만 드물게 호출하고, Observer는 코드 기반으로 무료, Actor는 subgoal 단위로 호출.

## Approach

1. Observer를 코드로 구현 (프레임 diff → 변화 감지, 위치 변화, 에너지 변화 등)
2. Planner 프롬프트 설계: 현재 상태 + 게임 규칙 → goal + subgoals 리스트 출력
3. Actor 프롬프트 설계: 현재 subgoal + 프레임 → 다음 액션 1개
4. 실행 루프: Planner → subgoal 순회 → Actor가 각 subgoal 실행 → Observer가 매 스텝 변화 감지 → subgoal 달성 시 다음으로 → 실패 시 Planner 재호출
5. ls20에서 테스트

## Constraints

- Planner 호출은 최소화 (subgoal 실패 또는 레벨 변경 시에만)
- Observer는 LLM 호출 없이 코드 기반으로
- Actor는 매 스텝 VLM 호출 (이미지 + subgoal 텍스트)
- 기존 src/ 모듈 구조 유지하면서 확장

## Success Criteria

- [ ] Observer가 프레임 diff로 이동 성공/실패, 패드 밟기, 슬롯 클리어를 감지할 수 있다
- [ ] Planner가 합리적인 subgoal 시퀀스를 생성한다 (예: rotation 패드로 이동 → 슬롯으로 이동)
- [ ] Actor가 subgoal 방향으로 일관되게 움직인다
- [ ] ls20 레벨 1을 이전보다 적은 스텝으로 클리어한다
