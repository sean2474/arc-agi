---
name: play
description: 현재 에이전트로 게임을 실행하고 결과를 기록한다
argument-hint: "<game_id> [max_steps]"
---

# Play: 게임 실행

현재 에이전트 코드로 게임을 실행하고 결과를 experiments/에 기록한다.

## Task

1. `$ARGUMENTS` 게임을 실행한다
2. 실행 결과를 출력한다:
   - 게임 상태 (WIN/GAME_OVER)
   - 완료 레벨 수
   - 총 스텝 수
   - 점수
3. experiments/ 하위의 현재 실험 디렉토리에 결과를 기록한다
4. 이전 실험 결과와 비교하여 개선/퇴보를 표시한다
5. 스코어카드가 있으면 표시한다
