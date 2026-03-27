"""ARC-AGI-3 브라우저 비주얼 플레이어 — 게임 화면을 보면서 플레이하고 액션을 JSON으로 저장.

사용법:
    python play.py ls20
    python play.py ft09
    python play.py sc25 -o my_run.json

브라우저에서 http://localhost:5555 접속.

조작:
    ← ↑ → ↓ (또는 1~4)  → ACTION1~ACTION4
    5, 6, 7              → ACTION5~ACTION7
    마우스 클릭           → complex action (ACTION6 등)
    r                    → RESET
    s                    → 저장
"""

import sys
import json
import argparse
from datetime import datetime

import arc_agi
from arcengine import GameAction, GameState
from flask import Flask, jsonify, request, render_template_string


# ARC 공식 16색 팔레트
ARC_COLORS = [
    "#000000",  #  0: 검정
    "#0074D9",  #  1: 파랑
    "#FF4136",  #  2: 빨강
    "#2ECC40",  #  3: 초록
    "#FFDC00",  #  4: 노랑
    "#AAAAAA",  #  5: 회색
    "#F012BE",  #  6: 마젠타
    "#FF851B",  #  7: 주황
    "#7FDBFF",  #  8: 하늘
    "#870C25",  #  9: 적갈색
    "#B10DC9",  # 10: 보라
    "#39CCCC",  # 11: 청록
    "#01FF70",  # 12: 연두
    "#85144b",  # 13: 자주
    "#3D9970",  # 14: 올리브
    "#FFFFFF",  # 15: 흰색
]


HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>ARC-AGI-3: {{ title }}</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #1a1a2e; color: #eee; font-family: 'Courier New', monospace;
         display: flex; flex-direction: column; align-items: center; min-height: 100vh; padding: 16px; }
  h1 { font-size: 20px; margin-bottom: 8px; color: #7fdbff; }
  #status { font-size: 14px; margin-bottom: 12px; color: #aaa; }
  #grid-container { position: relative; }
  canvas { border: 2px solid #333; cursor: crosshair; image-rendering: pixelated; }
  #controls { margin-top: 16px; display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; }
  .btn { padding: 8px 16px; border: 1px solid #555; background: #16213e; color: #eee;
         border-radius: 6px; cursor: pointer; font-family: inherit; font-size: 13px; }
  .btn:hover { background: #0f3460; }
  .btn:active { background: #533483; }
  .btn.active { background: #533483; border-color: #7fdbff; }
  #info { margin-top: 12px; font-size: 12px; color: #666; text-align: center; line-height: 1.6; }
  #log { margin-top: 12px; max-height: 150px; overflow-y: auto; font-size: 11px; color: #888;
         width: 100%; max-width: 520px; background: #111; border-radius: 6px; padding: 8px; }
  .log-entry { margin: 2px 0; }
  .win { color: #2ecc40; font-weight: bold; }
  .gameover { color: #ff4136; font-weight: bold; }
</style>
</head>
<body>
  <h1>🎮 ARC-AGI-3: {{ title }}</h1>
  <div id="status">loading...</div>
  <div id="grid-container">
    <canvas id="grid" width="512" height="512"></canvas>
  </div>
  <div id="controls">
    {% for a in actions %}
    <button class="btn" onclick="doAction({{a.value}})"
      title="{{a.type}}">{{a.name}}</button>
    {% endfor %}
    <button class="btn" onclick="doReset()" style="border-color:#ff851b;">⟲ RESET</button>
    <button class="btn" onclick="doSave()" style="border-color:#2ecc40;">💾 SAVE</button>
  </div>
  <div id="info">
    ← ↑ → ↓ or 1~7: action &nbsp;|&nbsp; R: reset &nbsp;|&nbsp; S: save<br>
    클릭: complex action (좌표 전송) &nbsp;|&nbsp; 저장: {{ output }}
  </div>
  <div id="log"></div>

<script>
const COLORS = {{ colors | tojson }};
const CELL = 8; // 512 / 64
const canvas = document.getElementById('grid');
const ctx = canvas.getContext('2d');
const statusEl = document.getElementById('status');
const logEl = document.getElementById('log');

// 액션 value → key 매핑
const KEY_MAP = {
  'ArrowUp': 1, 'ArrowDown': 2, 'ArrowLeft': 3, 'ArrowRight': 4,
  '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7,
};
const VALID_ACTIONS = new Set({{ action_values | tojson }});
const COMPLEX_ACTION = {{ complex_action }};

function drawGrid(grid) {
  for (let y = 0; y < 64; y++) {
    const row = grid[y];
    for (let x = 0; x < 64; x++) {
      const val = parseInt(row[x], 16);
      ctx.fillStyle = COLORS[val] || '#000';
      ctx.fillRect(x * CELL, y * CELL, CELL, CELL);
    }
  }
}

function addLog(msg, cls) {
  const d = document.createElement('div');
  d.className = 'log-entry' + (cls ? ' ' + cls : '');
  d.textContent = msg;
  logEl.prepend(d);
}

async function sendAction(actionValue, data) {
  const body = { action: actionValue };
  if (data) body.data = data;
  const resp = await fetch('/action', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  });
  const result = await resp.json();
  drawGrid(result.grid);
  const state = result.state;
  const lvl = result.levels_completed + '/' + result.win_levels;
  statusEl.textContent = 'step ' + result.step + '  |  state: ' + state + '  |  levels: ' + lvl;

  const cls = state === 'WIN' ? 'win' : state === 'GAME_OVER' ? 'gameover' : '';
  addLog('[step ' + result.step + '] ' + result.action_name + ' → ' + state + ' levels=' + lvl, cls);

  if (state === 'WIN') statusEl.style.color = '#2ecc40';
  else if (state === 'GAME_OVER') statusEl.style.color = '#ff4136';
  else statusEl.style.color = '#aaa';
}

function doAction(val) { sendAction(val); }
function doReset() { sendAction(0); }
async function doSave() {
  const resp = await fetch('/save', { method: 'POST' });
  const result = await resp.json();
  addLog('💾 ' + result.message);
}

// 키보드
document.addEventListener('keydown', (e) => {
  if (e.key === 'r' || e.key === 'R') { doReset(); return; }
  if (e.key === 's' || e.key === 'S') { doSave(); return; }
  const val = KEY_MAP[e.key];
  if (val !== undefined && VALID_ACTIONS.has(val)) {
    sendAction(val);
    e.preventDefault();
  }
});

// 클릭 (complex action)
canvas.addEventListener('click', (e) => {
  if (COMPLEX_ACTION === null) return;
  const rect = canvas.getBoundingClientRect();
  const x = Math.floor((e.clientX - rect.left) / CELL);
  const y = Math.floor((e.clientY - rect.top) / CELL);
  sendAction(COMPLEX_ACTION, { x: Math.max(0, Math.min(63, x)), y: Math.max(0, Math.min(63, y)) });
});

// 초기 로드
fetch('/state').then(r => r.json()).then(result => {
  drawGrid(result.grid);
  statusEl.textContent = 'step ' + result.step + '  |  state: ' + result.state + '  |  levels: ' + result.levels_completed + '/' + result.win_levels;
  addLog('[step 0] RESET → ' + result.state);
});
</script>
</body>
</html>"""


def frame_to_compact(frame):
    return ["".join(format(v, "x") for v in row) for row in frame]


def build_step_record(step_num, action_name, obs):
    return {
        "step": step_num,
        "action": action_name,
        "state": obs.state.value,
        "levels_completed": obs.levels_completed,
        "grid": frame_to_compact(obs.frame[-1]),
    }


def save_trajectory(trajectory, game_info, filepath):
    data = {
        "game_id": game_info["game_id"],
        "title": game_info["title"],
        "tags": game_info["tags"],
        "win_levels": game_info["win_levels"],
        "baseline_actions": game_info["baseline_actions"],
        "available_actions": game_info["available_actions"],
        "total_steps": len(trajectory),
        "saved_at": datetime.now().isoformat(),
        "trajectory": trajectory,
    }
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return f"{filepath} ({len(trajectory)} steps)"


def main():
    parser = argparse.ArgumentParser(description="ARC-AGI-3 브라우저 비주얼 플레이어")
    parser.add_argument("game", nargs="?", default="ls20", help="게임 ID (기본: ls20)")
    parser.add_argument("-o", "--output", help="저장 파일명 (기본: {game}_play.json)")
    parser.add_argument("-p", "--port", type=int, default=5555, help="포트 (기본: 5555)")
    args = parser.parse_args()

    output = args.output or f"{args.game}_play.json"

    # 게임 초기화
    arc_client = arc_agi.Arcade()
    env = arc_client.make(args.game)
    if env is None:
        print(f"❌ 게임 '{args.game}' 생성 실패")
        sys.exit(1)

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

    action_map = {}
    complex_action_value = None
    for a in env.action_space:
        action_map[a.value] = a
        if a.is_complex():
            complex_action_value = a.value

    # RESET으로 시작
    trajectory = []
    state = {"step_num": 0}

    obs = env.step(GameAction.RESET)
    game_info["win_levels"] = obs.win_levels
    trajectory.append(build_step_record(0, "RESET", obs))
    last_grid = frame_to_compact(obs.frame[-1])
    print(f"[step 0] RESET → state={obs.state.value}, levels=0/{obs.win_levels}")

    # Flask app
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template_string(
            HTML_TEMPLATE,
            title=info.title,
            actions=game_info["available_actions"],
            colors=ARC_COLORS,
            action_values=[a.value for a in env.action_space],
            complex_action=complex_action_value if complex_action_value else "null",
            output=output,
        )

    @app.route("/state")
    def get_state():
        return jsonify({
            "grid": last_grid,
            "step": state["step_num"],
            "state": trajectory[-1]["state"],
            "levels_completed": trajectory[-1]["levels_completed"],
            "win_levels": game_info["win_levels"],
        })

    @app.route("/action", methods=["POST"])
    def do_action():
        nonlocal last_grid
        body = request.get_json()
        action_value = body.get("action", 0)
        action_data = body.get("data")

        if action_value == 0:
            state["step_num"] += 1
            obs_result = env.step(GameAction.RESET)
            action_name = "RESET"
        elif action_value in action_map:
            action = action_map[action_value]
            if action.is_complex() and action_data:
                action.set_data({"x": action_data["x"], "y": action_data["y"]})
                action_name = f"{action.name}({action_data['x']},{action_data['y']})"
            else:
                action_name = action.name
            state["step_num"] += 1
            obs_result = env.step(action)
        else:
            return jsonify({"error": "invalid action"}), 400

        last_grid = frame_to_compact(obs_result.frame[-1])
        record = build_step_record(state["step_num"], action_name, obs_result)
        trajectory.append(record)

        print(f"[step {state['step_num']}] {action_name} → state={obs_result.state.value}, levels={obs_result.levels_completed}/{game_info['win_levels']}")

        return jsonify({
            "grid": last_grid,
            "step": state["step_num"],
            "state": obs_result.state.value,
            "levels_completed": obs_result.levels_completed,
            "win_levels": game_info["win_levels"],
            "action_name": action_name,
        })

    @app.route("/save", methods=["POST"])
    def do_save():
        msg = save_trajectory(trajectory, game_info, output)
        print(f"💾 {msg}")
        return jsonify({"message": msg})

    print(f"\n🎮 {info.title} ({info.game_id})")
    print(f"   태그: {info.tags}")
    print(f"   베이스라인: {info.baseline_actions}")
    print(f"\n🌐 브라우저에서 접속: http://localhost:{args.port}")
    print(f"   저장 파일: {output}\n")

    app.run(host="0.0.0.0", port=args.port, debug=False)


if __name__ == "__main__":
    main()
