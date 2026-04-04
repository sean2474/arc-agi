---
name: experiment
description: 새 실험을 시작하거나 현재 실험을 종료한다
argument-hint: "<start|end> <experiment_name>"
---

# Experiment: 실험 관리

## start
```
/experiment start baseline_random_agent
```
1. `experiments/{YYYYMMDD_HHMMSS}_{name}/` 디렉토리 생성
2. `config.json` 작성: 이번 실험에서 뭘 바꿨는지 기록
   ```json
   {
     "name": "experiment_name",
     "timestamp": "ISO 8601",
     "description": "이 실험에서 변경한 내용",
     "changes": ["변경 1", "변경 2"],
     "hypothesis": "왜 이 변경이 효과가 있을 것이라 생각하는지"
   }
   ```
3. 현재 실험 경로를 사용자에게 알려준다

## end
```
/experiment end
```
1. 현재 실험의 results.json을 생성한다
   ```json
   {
     "name": "experiment_name",
     "timestamp_start": "ISO 8601",
     "timestamp_end": "ISO 8601",
     "games_played": [
       {"game_id": "ls20", "score": 0.15, "levels": 2, "steps": 45}
     ],
     "overall_score": 0.15,
     "conclusion": "실험 결과 요약"
   }
   ```
2. 이전 실험과 비교 표를 출력한다

$ARGUMENTS
