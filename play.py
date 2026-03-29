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
from agents.llm_agent.const import ARC_COLORS
from arcengine import GameAction
from flask import Flask, jsonify, request, render_template_string
from agents.llm_agent.objects.manager import BlobManager, frame_to_compact

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
  #log { margin-top: 12px; max-height: 120px; overflow-y: auto; font-size: 11px; color: #888;
         width: 100%; max-width: 520px; background: #111; border-radius: 6px; padding: 8px; }
  .log-entry { margin: 2px 0; }
  .win { color: #2ecc40; font-weight: bold; }
  .gameover { color: #ff4136; font-weight: bold; }
  #events-panel { margin-top: 8px; max-height: 160px; overflow-y: auto; font-size: 11px;
                  width: 100%; max-width: 520px; background: #0a0a1a; border-radius: 6px;
                  padding: 8px; border: 1px solid #2a2a5a; }
  .ev-title { color: #7fdbff; font-size: 10px; margin-bottom: 4px; letter-spacing: 1px; }
  .ev-move { color: #01ff70; } .ev-appear { color: #ffdc00; }
  .ev-disappear { color: #ff4136; } .ev-collide { color: #ff851b; }
  .ev-camera { color: #7fdbff; } .ev-blob { color: #aaaaaa; font-size: 10px; }
  .ev-merged { color: #7fdbff; font-weight: bold; }
  .ev-merge { color: #cc5de8; font-weight: bold; }
  .ev-section { color: #555; font-size: 9px; letter-spacing: 1px; padding-top: 2px; }
  .btn-blobs { border-color: #01ff70; }
  .btn-blobs.off { border-color: #555; color: #555; }
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
    <button id="blobToggle" class="btn btn-blobs" onclick="toggleBlobs()">🔍 Blobs</button>
  </div>
  <div id="info">
    ← ↑ → ↓ or 1~7: action &nbsp;|&nbsp; R: reset &nbsp;|&nbsp; S: save<br>
    클릭: complex action (좌표 전송) &nbsp;|&nbsp; 저장: {{ output }}
  </div>
  <div id="log"></div>
  <div id="events-panel">
    <div class="ev-title">⚡ EVENTS &nbsp; <span id="blob-count" style="color:#555;"></span></div>
    <div id="events-log"></div>
  </div>

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

let currentGrid = null;
let currentBlobs = [];
let showBlobOverlay = true;

const BLOB_PALETTE = [
  '#ff6b6b','#ffd93d','#6bcb77','#4d96ff','#ff922b',
  '#cc5de8','#22b8cf','#f06595','#74c0fc','#a9e34b'
];
function blobColor(id) {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return BLOB_PALETTE[h % BLOB_PALETTE.length];
}

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

function drawBlobs(blobs) {
  if (!blobs || !showBlobOverlay) return;
  ctx.save();
  ctx.font = 'bold 7px monospace';
  for (const b of blobs) {
    const {row_min, row_max, col_min, col_max} = b.bbox;
    const x = col_min * CELL, y = row_min * CELL;
    const w = (col_max - col_min + 1) * CELL;
    const h = (row_max - row_min + 1) * CELL;
    const col = blobColor(b.id);
    ctx.strokeStyle = col;
    ctx.lineWidth = 1.5;
    ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
    const label = (b.name && b.name !== b.id) ? b.name : b.id.replace('obj_', '#');
    const tw = ctx.measureText(label).width;
    ctx.fillStyle = 'rgba(0,0,0,0.75)';
    ctx.fillRect(x, y, tw + 4, 9);
    ctx.fillStyle = col;
    ctx.fillText(label, x + 2, y + 8);
  }
  ctx.restore();
}

function render(grid, blobs) {
  if (grid !== undefined) currentGrid = grid;
  if (blobs !== undefined) currentBlobs = blobs || [];
  drawGrid(currentGrid);
  drawBlobs(currentBlobs);
}

function toggleBlobs() {
  showBlobOverlay = !showBlobOverlay;
  const btn = document.getElementById('blobToggle');
  btn.textContent = showBlobOverlay ? '🔍 Blobs' : '🔍 OFF';
  btn.classList.toggle('off', !showBlobOverlay);
  if (currentGrid) render();
}

function addLog(msg, cls) {
  const d = document.createElement('div');
  d.className = 'log-entry' + (cls ? ' ' + cls : '');
  d.textContent = msg;
  logEl.prepend(d);
}

const evLogEl = document.getElementById('events-log');
const blobCountEl = document.getElementById('blob-count');
const EV_CLASS = {
  'move': 'ev-move', 'appear': 'ev-appear', 'disappear': 'ev-disappear',
  'collide': 'ev-collide', 'camera_shift': 'ev-camera', 'camera_rotation': 'ev-camera',
  'rotation': 'ev-move', 'transform': 'ev-appear', 'merge': 'ev-merge'
};
function isMerged(ev) {
  return ev.frames && ev.frames[1] > ev.frames[0];
}
function fmtEvent(ev) {
  if (ev.type === 'move') {
    const d = ev.delta ? `Δ(${ev.delta[0]},${ev.delta[1]})` : '';
    const nf = ev.frames ? (ev.frames[1] - ev.frames[0] + 1) : 1;
    const f = ev.frames ? (isMerged(ev) ? ` ×${nf}f` : ` f${ev.frames[0]}`) : '';
    return `↕ ${ev.obj} ${d}${f}`;
  } else if (ev.type === 'appear') {
    return `✦ appear ${ev.obj} @[${ev.pos}]`;
  } else if (ev.type === 'disappear') {
    return `✗ disappear ${ev.obj} [${ev.cause}]`;
  } else if (ev.type === 'collide') {
    return `⚡ ${ev.obj_a} × ${ev.obj_b}`;
  } else if (ev.type === 'camera_shift') {
    return `📷 camera Δ(${ev.delta[0]},${ev.delta[1]})`;
  } else if (ev.type === 'camera_rotation') {
    return `📷 cam rot ${ev.angle_deg}°`;
  } else if (ev.type === 'rotation') {
    return `↻ ${ev.obj} ${ev.angle_deg}°`;
  } else if (ev.type === 'transform') {
    return `✨ transform ${ev.obj} Δcol=${ev.color_diff}`;
  } else if (ev.type === 'merge') {
    return `🔗 merge ${ev.obj_a} + ${ev.obj_b}`;
  }
  return JSON.stringify(ev);
}
function showEvents(animEvents, resultEvents, blobCount) {
  if (blobCount !== undefined) blobCountEl.textContent = `[${blobCount} blobs]`;
  const allEmpty = (!animEvents || animEvents.length === 0) && (!resultEvents || resultEvents.length === 0);
  if (allEmpty) return;

  // result events (bottom of this step block, shown first since we prepend)
  if (resultEvents && resultEvents.length > 0) {
    const header = document.createElement('div');
    header.className = 'log-entry ev-section';
    header.textContent = '▸ result';
    evLogEl.prepend(header);
    [...resultEvents].reverse().forEach(ev => {
      const d = document.createElement('div');
      const mergedCls = (ev.type === 'move' && isMerged(ev)) ? ' ev-merged' : '';
      d.className = 'log-entry ' + (EV_CLASS[ev.type] || '') + mergedCls;
      d.textContent = '  ' + fmtEvent(ev);
      evLogEl.prepend(d);
    });
  }

  // animation events
  if (animEvents && animEvents.length > 0) {
    const header = document.createElement('div');
    header.className = 'log-entry ev-section';
    header.textContent = '▸ animation';
    evLogEl.prepend(header);
    [...animEvents].reverse().forEach(ev => {
      const d = document.createElement('div');
      const mergedCls = (ev.type === 'move' && isMerged(ev)) ? ' ev-merged' : '';
      d.className = 'log-entry ' + (EV_CLASS[ev.type] || '') + mergedCls;
      d.textContent = '  ' + fmtEvent(ev);
      evLogEl.prepend(d);
    });
  }
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function sendAction(actionValue, data) {
  const body = { action: actionValue };
  if (data) body.data = data;
  const resp = await fetch('/action', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  });
  const result = await resp.json();

  // Play animation frames sequentially, then show final state with blobs
  const frames = result.anim_frames || [];
  for (const frame of frames) {
    render(frame, null);
    await sleep(60);
  }
  render(result.grid, result.blobs);

  const state = result.state;
  const lvl = result.levels_completed + '/' + result.win_levels;
  statusEl.textContent = 'step ' + result.step + '  |  state: ' + state + '  |  levels: ' + lvl;

  const cls = state === 'WIN' ? 'win' : state === 'GAME_OVER' ? 'gameover' : '';
  addLog('[step ' + result.step + '] ' + result.action_name + ' → ' + state + ' levels=' + lvl, cls);
  showEvents(result.animation_events, result.result_events, result.blob_count);

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
  render(result.grid, result.blobs);
  statusEl.textContent = 'step ' + result.step + '  |  state: ' + result.state + '  |  levels: ' + result.levels_completed + '/' + result.win_levels;
  addLog('[step 0] RESET → ' + result.state);
  if (result.blob_count !== undefined) blobCountEl.textContent = `[${result.blob_count} blobs]`;
});
</script>
</body>
</html>"""



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

    # Blob tracking state
    manager = BlobManager(last_grid)
    print(f"[step 0] blobs detected: {manager.blob_count}")

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
        blob_list = manager.serialize_blobs()
        return jsonify({
            "grid": last_grid,
            "step": state["step_num"],
            "state": trajectory[-1]["state"],
            "levels_completed": trajectory[-1]["levels_completed"],
            "win_levels": game_info["win_levels"],
            "blobs": blob_list,
            "blob_count": len(blob_list),
        })

    @app.route("/action", methods=["POST"])
    def do_action():
        nonlocal last_grid
        body = request.get_json()
        action_value = body.get("action", 0)
        action_data = body.get("data")

        prev_grid_snapshot = last_grid

        if action_value == 0:
            state["step_num"] += 1
            obs_result = env.step(GameAction.RESET)
            action_name = "RESET"
        elif action_value in action_map:
            action = action_map[action_value]
            if action.is_complex() and action_data:
                action_name = f"{action.name}({action_data['x']},{action_data['y']})"
            else:
                action_data = None
                action_name = action.name
            state["step_num"] += 1
            obs_result = env.step(action, data=action_data if action_data else None)
        else:
            return jsonify({"error": "invalid action"}), 400

        raw_frames = obs_result.frame
        last_grid = frame_to_compact(raw_frames[-1]) if raw_frames else prev_grid_snapshot
        record = build_step_record(state["step_num"], action_name, obs_result)
        trajectory.append(record)

        # --- Blob + event analysis ---
        anim_frames = [frame_to_compact(f) for f in raw_frames]
        if not anim_frames:
            anim_frames = [last_grid]  # no animation: compare prev → final in one step
        if action_value == 0:
            manager.reset(last_grid)
            events = []
            result_events = []
            level_transition_info = None
        else:
            events, result_events, level_transition_info = manager.step(
                anim_frames, obs_result.levels_completed, obs_result.state.value
            )

        blob_count = manager.blob_count
        print(f"[step {state['step_num']}] {action_name} → state={obs_result.state.value}, "
              f"levels={obs_result.levels_completed}/{game_info['win_levels']}, "
              f"blobs={blob_count}, anim={[e['type'] for e in events]}, result={[e['type'] for e in result_events]}")

        return jsonify({
            "grid": last_grid,
            "anim_frames": anim_frames,
            "step": state["step_num"],
            "state": obs_result.state.value,
            "levels_completed": obs_result.levels_completed,
            "win_levels": game_info["win_levels"],
            "action_name": action_name,
            "animation_events": events,
            "result_events": result_events,
            "events": events + result_events,
            "level_transition": level_transition_info,
            "blob_count": blob_count,
            "blobs": manager.serialize_blobs(),
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
