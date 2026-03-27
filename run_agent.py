"""ARC-AGI-3 에이전트 실행기.

사용법:
    python run_agent.py
    python run_agent.py --game ls20
    python run_agent.py -c configs/default.yaml
"""

import sys
import json
import argparse
import subprocess
import time
import atexit
from pathlib import Path
from datetime import datetime

import yaml
import requests
from dotenv import load_dotenv

import arc_agi
from arcengine import GameAction, GameState

from agents.llm_agent import LLMAgent, StepRecord


load_dotenv()

_server_proc = None


def start_model_server(server_cfg: dict) -> None:
    """vLLM 서버가 안 돼있으면 자동 시작."""
    global _server_proc
    port = server_cfg.get("port", 8080)
    api_url = f"http://localhost:{port}/v1/models"

    # 이미 돌고 있는지 체크
    try:
        r = requests.get(api_url, timeout=3)
        if r.status_code == 200:
            print(f"✅ 모델 서버 이미 실행 중 (port {port})")
            return
    except Exception:
        pass

    model_path = server_cfg.get("model_path", "./qwen3-8b")
    extra_args = server_cfg.get("extra_args", "")

    cmd = f"vllm serve {model_path} --port {port} {extra_args}"
    print(f"🚀 모델 서버 시작: {cmd}")
    _server_proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    atexit.register(_stop_server)

    # 서버 준비 대기
    print("   서버 로딩 대기 중...", end="", flush=True)
    for i in range(120):  # 최대 2분
        time.sleep(2)
        try:
            r = requests.get(api_url, timeout=3)
            if r.status_code == 200:
                print(f" 준비 완료! ({(i+1)*2}초)")
                return
        except Exception:
            pass
        if i % 10 == 9:
            print(".", end="", flush=True)

    print(" ❌ 타임아웃 (2분)")
    _stop_server()
    sys.exit(1)


def _stop_server():
    global _server_proc
    if _server_proc and _server_proc.poll() is None:
        print("🛑 모델 서버 종료")
        _server_proc.terminate()
        _server_proc.wait(timeout=10)
        _server_proc = None


def load_config(config_path: str) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def save_run(records: list[StepRecord], game_info: dict, agent_name: str, stats: dict, output_dir: Path):
    """data/{game_id}/{agent_name}/ 에 결과 저장."""
    output_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = output_dir / f"run_{ts}.json"

    data = {
        "game_id": game_info["game_id"],
        "title": game_info["title"],
        "tags": game_info["tags"],
        "win_levels": game_info["win_levels"],
        "baseline_actions": game_info["baseline_actions"],
        "available_actions": game_info["available_actions"],
        "agent_name": agent_name,
        "stats": stats,
        "saved_at": datetime.now().isoformat(),
        "total_steps": len(records),
        "trajectory": [r.to_dict() for r in records],
    }

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"💾 저장: {filepath}")
    return filepath


def run_game(game_id: str, agent: LLMAgent, max_steps: int, data_dir: str, save_every: int, stop_after_level: int = 0):
    """단일 게임 실행."""
    print(f"\n{'='*60}")
    print(f"🎮 게임 시작: {game_id}")
    print(f"   에이전트: {agent.name} ({agent.model})")
    print(f"   최대 스텝: {max_steps}")
    print(f"{'='*60}\n")

    arc_client = arc_agi.Arcade()
    env = arc_client.make(game_id)
    if env is None:
        print(f"❌ 게임 '{game_id}' 생성 실패")
        return

    info = env.info
    game_info = {
        "game_id": info.game_id,
        "title": info.title,
        "tags": info.tags,
        "win_levels": None,
        "baseline_actions": info.baseline_actions,
        "available_actions": [
            {"name": a.name, "value": a.value, "type": "simple" if a.is_simple() else "complex"}
            for a in env.action_space
        ],
    }

    agent.setup(game_info)

    # RESET
    obs = env.step(GameAction.RESET)
    game_info["win_levels"] = obs.win_levels
    print(f"   레벨: {obs.win_levels}개, 베이스라인: {info.baseline_actions}")
    print()

    output_dir = Path(data_dir) / game_id / agent.name

    for step in range(1, max_steps + 1):
        action, record = agent.get_next_action(step, obs)

        # 로그
        phase_mark = {"observe+decide": "👁️🧠", "evaluate": "📊", "update": "📝"}.get(record.llm_phase or "", "  ")
        trigger_info = f" [{record.trigger}]" if record.trigger else ""
        print(f"  {phase_mark} step {step:3d} | {record.action:<20s} | state={record.state} lvl={record.levels_completed}{trigger_info}")

        if record.llm_phase == "observe+decide" and record.reasoning:
            if record.observation:
                print(f"           💬 {str(record.observation)[:100]}")
            if record.hypothesis:
                print(f"           💡 {record.hypothesis[:120]}")
            if record.challenge:
                print(f"           ⚡ {record.challenge[:120]}")
            print(f"           🎯 {record.sequence_goal}")
        if record.report:
            achieved = "✅" if record.report.get("goal_achieved") else "❌"
            print(f"           {achieved} {record.report.get('reasoning', '')[:80]}")

        # 액션 실행
        obs = env.step(action)

        # game_over → 자동 리셋
        if obs.state == GameState.GAME_OVER:
            print(f"  💀 GAME OVER → 자동 리셋")
            obs = env.step(GameAction.RESET)
            agent.prev_grid = None
            agent.prev_levels = obs.levels_completed
            agent.sequence = []

        # 레벨 클리어 체크
        if stop_after_level > 0 and obs.levels_completed >= stop_after_level:
            print(f"\n  ✅ 레벨 {stop_after_level} 클리어! (step {step})")
            break

        # WIN
        if obs.state == GameState.WIN:
            print(f"\n  🎉 게임 클리어! (step {step})")
            break

        # 중간 저장
        if save_every > 0 and step % save_every == 0:
            save_run(agent.history, game_info, agent.name, agent.get_stats(), output_dir)

    # 최종 저장
    save_run(agent.history, game_info, agent.name, agent.get_stats(), output_dir)

    # 스코어카드
    scorecard = arc_client.get_scorecard()
    if scorecard:
        print(f"\n📊 스코어카드:\n{scorecard}")

    # 통계
    stats = agent.get_stats()
    print(f"\n📈 통계:")
    print(f"   총 스텝: {stats['total_steps']}")
    print(f"   사이클: {stats['total_cycles']}회 (PLAN→EXECUTE→EVALUATE→UPDATE)")
    print(f"   LLM 호출: {stats['llm_calls']}회")
    print(f"   입력 토큰: {stats['input_tokens']:,}")
    print(f"   출력 토큰: {stats['output_tokens']:,}")


def main():
    parser = argparse.ArgumentParser(description="ARC-AGI-3 에이전트 실행기")
    parser.add_argument("--game", help="게임 ID (config의 game.ids 오버라이드)")
    parser.add_argument("-c", "--config", default="configs/default.yaml", help="설정 파일")
    args = parser.parse_args()

    cfg = load_config(args.config)

    # 모델 서버 자동 시작
    if "server" in cfg:
        start_model_server(cfg["server"])

    agent_cfg = cfg["agent"]
    game_cfg = cfg["game"]
    output_cfg = cfg["output"]

    game_ids = [args.game] if args.game else game_cfg["ids"]
    if not game_ids:
        arc_client = arc_agi.Arcade()
        games = arc_client.get_environments()
        game_ids = [g.game_id.split("-")[0] for g in games]
        print(f"🎮 전체 게임 {len(game_ids)}개 실행")

    agent = LLMAgent(
        model=agent_cfg["model"],
        max_tokens=agent_cfg.get("max_tokens", 1024),
        name=agent_cfg["name"],
        api_base=agent_cfg.get("api_base", "http://localhost:8080/v1"),
    )

    for gid in game_ids:
        run_game(
            game_id=gid,
            agent=agent,
            max_steps=game_cfg["max_steps"],
            data_dir=output_cfg["data_dir"],
            save_every=output_cfg.get("save_every", 0),
            stop_after_level=game_cfg.get("stop_level", 0),
        )


if __name__ == "__main__":
    main()
