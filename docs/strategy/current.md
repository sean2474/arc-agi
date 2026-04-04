## Goal

로컬 VLM (Qwen2.5-VL-7B)을 DPO로 파인튜닝하여 ls20 게임의 액션 선택 정확도를 높인다. 화면 변화 reward + Opus 기반 goal 접근도 평가를 결합.

## Hypothesis

DPO로 화면 변화가 있는 액션과 goal에 가까워지는 액션을 선호하도록 학습하면 벽 충돌 감소 + 목표 지향 이동이 가능해진다.

## Approach

1. training/train_local.py SRP 분리: model_loader.py, trajectory_collector.py, dpo_trainer.py로 분리
2. training/evaluator.py를 LLMClient Protocol 사용으로 변경, Opus 모델 지원
3. Observer 기반 세밀한 reward 함수 구현 (moved/blocked/tool_changed/slot_cleared/position_reset)
4. Opus evaluator 통합하여 N스텝마다 goal 접근도 평가
5. DPO preference 쌍 품질 향상: Observer 시뮬레이션으로 best/worst 액션 쌍 생성
6. train_local.py를 오케스트레이터로 리팩토링

## Constraints

- 기존 src/ 모듈 수정 최소화 (SOLID 리팩토링 결과 유지)
- training/ 디렉토리에서 작업
- GPU 서버 없이 로컬에서도 테스트 가능한 구조
- 새 라이브러리 도입 금지 (torch, transformers, peft는 이미 사용 중)

## Success Criteria

- [ ] training/train_local.py가 SRP에 따라 분리됨
- [ ] training/evaluator.py가 LLMClient Protocol 사용
- [ ] Observer 기반 세밀한 reward 함수 구현
- [ ] Opus evaluator 통합 (goal 접근도 평가)
- [ ] DPO preference 쌍 품질 향상
- [ ] 기존 테스트 깨지지 않음
