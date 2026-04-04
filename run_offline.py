#!/usr/bin/env python3
"""오프라인 러너 — 공식 main.py 파이프라인으로 에이전트 실행.

Usage:
    .venv/bin/python run_offline.py --agent ouragent --game ls20
    .venv/bin/python run_offline.py --agent ouragent                # 전체 게임
    .venv/bin/python run_offline.py --agent random --game ls20      # 랜덤 기준선
"""

import argparse
import json
import os
import re
import signal
import socket
import subprocess
import sys
import textwrap
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
ENV_DIR = PROJECT_ROOT / "environment_files"
RECORDINGS_DIR = PROJECT_ROOT / "recordings"
EXPERIMENTS_DIR = PROJECT_ROOT / "experiments"


def find_free_port(start: int = 8765) -> int:
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free port found")


def write_fake_api(path: Path, env_dir: Path, host: str, port: int) -> None:
    """main.py가 기대하는 /api/games 엔드포인트를 제공하는 스텁 서버."""
    code = textwrap.dedent(f"""
    import json
    from pathlib import Path
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    ENV_DIR = Path(r"{env_dir}")

    def list_games():
        if not ENV_DIR.exists():
            return []
        return [{{"game_id": p.name}} for p in sorted(ENV_DIR.iterdir()) if p.is_dir()]

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/api/games":
                payload = json.dumps(list_games()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, fmt, *args):
            return

    if __name__ == "__main__":
        ThreadingHTTPServer(("{host}", {port}), Handler).serve_forever()
    """).strip() + "\n"
    path.write_text(code, encoding="utf-8")


def write_env_file(path: Path, env_dir: Path, recordings_dir: Path, host: str, port: int) -> None:
    """main.py가 읽을 .env 파일."""
    text = textwrap.dedent(f"""
    OPERATION_MODE=OFFLINE
    ENVIRONMENTS_DIR={env_dir}
    RECORDINGS_DIR={recordings_dir}
    SCHEME=http
    HOST={host}
    PORT={port}
    ARC_BASE_URL=http://{host}:{port}
    ARC_API_KEY=offline
    """).strip() + "\n"
    path.write_text(text, encoding="utf-8")


def run(agent: str, game: str | None, description: str | None) -> None:
    host = "127.0.0.1"
    port = find_free_port()

    # 실험 디렉토리
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    desc = description or f"{agent}-{game or 'all'}"
    run_dir = EXPERIMENTS_DIR / f"{ts}_{desc}"
    run_dir.mkdir(parents=True, exist_ok=True)

    rec_dir = run_dir / "recordings"
    rec_dir.mkdir(exist_ok=True)

    # .env와 fake API 서버 파일
    env_file = PROJECT_ROOT / ".env.offline"
    write_env_file(env_file, ENV_DIR, rec_dir, host, port)

    fake_api_file = PROJECT_ROOT / "_fake_api.py"
    write_fake_api(fake_api_file, ENV_DIR, host, port)

    # main.py 명령어
    cmd = [sys.executable, "main.py", "--agent", agent]
    if game:
        cmd += ["--game", game]

    print("=" * 60)
    print(f"ARC-AGI-3 Offline Runner")
    print(f"Agent: {agent}, Game: {game or 'all'}")
    print(f"Run dir: {run_dir}")
    print(f"API stub: http://{host}:{port}/api/games")
    print("=" * 60)

    # fake API 서버 시작
    server_proc = subprocess.Popen(
        [sys.executable, str(fake_api_file)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # 서버 준비 대기
    import requests
    for _ in range(30):
        try:
            r = requests.get(f"http://{host}:{port}/api/games", timeout=0.5)
            if r.ok:
                break
        except Exception:
            time.sleep(0.1)

    # 환경 변수 설정
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["MPLBACKEND"] = "agg"
    # .env.offline 내용을 환경변수로
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()

    # main.py 실행
    log_path = run_dir / "run.log"
    proc = None

    # 로그 파싱용 정규식
    re_action = re.compile(
        r"(\w+)\s*-\s*(ACTION\d+|RESET):\s*count\s*(\d+),\s*levels completed\s*(\d+),\s*avg fps\s*([0-9.]+)"
    )
    re_done = re.compile(r"recording for (\w+)\.")
    re_scorecard = re.compile(r"--- FINAL SCORECARD REPORT ---")

    games_done = 0
    final_lines = []
    in_final = False

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=PROJECT_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        with log_path.open("w") as log_file:
            for line in proc.stdout:
                log_file.write(line)
                log_file.flush()

                line_s = line.rstrip("\n")

                if in_final:
                    final_lines.append(line_s)
                    continue

                if re_scorecard.search(line_s):
                    in_final = True
                    final_lines.append(line_s)
                    continue

                # 진행 표시
                m = re_action.search(line_s)
                if m:
                    gid, action, count, levels, fps = m.groups()
                    print(f"\r  {gid}: {action} #{count}, levels={levels}, fps={fps}    ", end="", flush=True)
                    continue

                m = re_done.search(line_s)
                if m:
                    games_done += 1
                    print(f"\n  ✓ {m.group(1)} done ({games_done} total)")
                    continue

        exit_code = proc.wait()

    except KeyboardInterrupt:
        print("\nInterrupted.")
        if proc:
            proc.terminate()
        exit_code = 1
    finally:
        server_proc.terminate()
        server_proc.wait(timeout=3)
        env_file.unlink(missing_ok=True)
        fake_api_file.unlink(missing_ok=True)

    # 스코어카드 파싱
    scorecard = None
    if final_lines:
        json_lines = []
        started = False
        depth = 0
        for l in final_lines:
            cleaned = re.sub(r"^\d{4}-\d{2}-\d{2}.*?\|\s*INFO\s*\|\s*", "", l)
            if not started:
                if "{" in cleaned:
                    started = True
                    idx = cleaned.find("{")
                    piece = cleaned[idx:]
                    json_lines.append(piece)
                    depth += piece.count("{") - piece.count("}")
                    if depth == 0:
                        break
            else:
                json_lines.append(cleaned)
                depth += cleaned.count("{") - cleaned.count("}")
                if depth == 0:
                    break

        if json_lines:
            try:
                scorecard = json.loads("\n".join(json_lines))
                (run_dir / "scorecard.json").write_text(
                    json.dumps(scorecard, indent=2, ensure_ascii=False)
                )
            except json.JSONDecodeError:
                pass

    # 결과 표시
    overall = None
    if scorecard and "environments" in scorecard:
        scores = [e.get("score", 0) for e in scorecard["environments"]]
        overall = sum(scores) / len(scores) if scores else None

    print("\n" + "=" * 60)
    print(f"Exit code: {exit_code}")
    print(f"Games done: {games_done}")
    if overall is not None:
        print(f"Overall score: {overall:.6f}")
    print(f"Run dir: {run_dir}")
    print(f"Recordings: {rec_dir}")
    print(f"Log: {log_path}")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="ARC-AGI-3 Offline Runner")
    parser.add_argument("-a", "--agent", required=True, help="에이전트 이름 (예: ouragent, random)")
    parser.add_argument("-g", "--game", help="특정 게임 (예: ls20). 없으면 전체.")
    parser.add_argument("-d", "--description", help="실험 설명")
    args = parser.parse_args()

    run(args.agent, args.game, args.description)


if __name__ == "__main__":
    main()
