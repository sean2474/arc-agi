#!/usr/bin/env python3
"""에이전트 실행 결과 리플레이어.

사용법:
    python visualizer/replay.py                                    # 최신 실험
    python visualizer/replay.py experiments/20260404_vlm_test/     # 특정 실험
    python visualizer/replay.py replay.json                        # 직접 JSON
"""

import sys
import json
import argparse
from pathlib import Path

from flask import Flask, jsonify, render_template_string

sys.path.insert(0, str(Path(__file__).parent.parent))
from visualizer.colors import ARC_COLORS
from visualizer.converter import convert_experiment


HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Replay: {{ title }} — {{ agent_name }}</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:#1a1a2e; color:#eee; font-family:'Courier New',monospace;
         display:flex; height:100vh; overflow:hidden; }
  #sidebar { width:480px; min-width:480px; background:#16213e; display:flex; flex-direction:column;
             border-right:2px solid #333; }
  #main { flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; padding:16px; }
  h1 { font-size:15px; color:#7fdbff; padding:12px 16px; border-bottom:1px solid #333; }
  #summary { padding:8px 16px; font-size:11px; color:#888; border-bottom:1px solid #333; }
  #controls { display:flex; gap:8px; padding:10px 16px; border-bottom:1px solid #333; align-items:center; }
  .btn { padding:5px 12px; border:1px solid #555; background:#0f3460; color:#eee;
         border-radius:4px; cursor:pointer; font-family:inherit; font-size:13px; }
  .btn:hover { background:#533483; }
  .btn:disabled { opacity:0.3; cursor:default; }
  #step-display { flex:1; text-align:center; font-size:13px; color:#aaa; }
  #timeline { padding:0 16px 8px; border-bottom:1px solid #333; }
  #timeline input { width:100%; }
  #info-panel { padding:12px 16px; font-size:12px; line-height:1.5; overflow-y:auto; max-height:240px;
                border-bottom:1px solid #333; }
  .info-label { color:#7fdbff; font-weight:bold; font-size:11px; text-transform:uppercase; margin-top:8px; }
  .info-content { color:#ccc; white-space:pre-wrap; word-break:break-word;
                   font-family:Arial,Helvetica,sans-serif; font-size:13px; line-height:1.6; }
  .badge { display:inline-block; padding:1px 6px; border-radius:8px; font-size:10px; margin-left:6px; }
  .badge-vlm { background:#2d6a4f; color:#fff; }
  .badge-queue { background:#333; color:#888; }
  .badge-blocked { background:#7f4f24; color:#fff; }
  .badge-ok { background:#0f3460; color:#7fdbff; }
  #step-list { flex:1; overflow-y:auto; }
  .step-item { padding:5px 16px; cursor:pointer; font-size:11px; border-bottom:1px solid #222;
               display:flex; align-items:center; gap:6px; }
  .step-item:hover { background:#0f3460; }
  .step-item.active { background:#533483; }
  .step-item.vlm { border-left:3px solid #7fdbff; }
  .step-item.blocked { color:#ff6b6b; }
  .step-num { color:#666; width:28px; text-align:right; }
  .step-action { width:70px; }
  .step-move { flex:1; font-size:10px; color:#888; }
  canvas { border:2px solid #333; image-rendering:pixelated; }
  #grid-status { margin-top:8px; font-size:12px; color:#888; }
</style>
</head>
<body>
  <div id="sidebar">
    <h1>{{ title }} — {{ agent_name }}</h1>
    <div id="summary">
      Result: {{ final_state }} | Levels: {{ levels }} | Steps: {{ total }} | {{ api_usage }}
    </div>
    <div id="controls">
      <button class="btn" id="btn-prev" onclick="go(-1)">◀</button>
      <div id="step-display">0 / {{ total }}</div>
      <button class="btn" id="btn-next" onclick="go(1)">▶</button>
      <button class="btn" id="btn-play" onclick="togglePlay()">▶ Play</button>
    </div>
    <div id="timeline">
      <input type="range" id="slider" min="0" max="{{ total }}" value="0" oninput="goTo(+this.value)">
    </div>
    <div id="info-panel"></div>
    <div id="step-list"></div>
  </div>
  <div id="main">
    <canvas id="grid" width="512" height="512"></canvas>
    <div id="grid-status"></div>
  </div>

<script>
const COLORS = {{ colors | tojson }};
const CELL = 8;
const canvas = document.getElementById('grid');
const ctx = canvas.getContext('2d');

let trajectory = {{ trajectory | tojson }};
let currentIdx = 0;
let playing = false;
let playInterval = null;

function drawGrid(grid) {
  if (!grid || !grid.length) return;
  for (let y = 0; y < grid.length; y++) {
    const row = grid[y];
    for (let x = 0; x < row.length; x++) {
      const val = parseInt(row[x], 16);
      ctx.fillStyle = COLORS[val] || '#000';
      ctx.fillRect(x*CELL, y*CELL, CELL, CELL);
    }
  }
}

function esc(s) { if (!s) return ''; const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }

function showStep(idx) {
  if (idx < 0 || idx >= trajectory.length) return;
  currentIdx = idx;
  const s = trajectory[idx];
  drawGrid(s.grid);

  document.getElementById('step-display').textContent = s.step + ' / ' + trajectory.length;
  document.getElementById('slider').value = idx;

  const moved = s.moved !== false;
  const isVlm = s.llm_called;

  let statusParts = ['state: ' + s.state];
  if (s.levels_completed !== undefined) statusParts.push('levels: ' + s.levels_completed);
  statusParts.push('action: ' + s.action);
  if (!moved && s.action !== 'RESET') statusParts.push('BLOCKED');
  document.getElementById('grid-status').textContent = statusParts.join('  |  ');

  // info panel
  let html = '';
  let badges = '';
  if (isVlm) badges += '<span class="badge badge-vlm">VLM</span>';
  else if (s.action !== 'RESET') badges += '<span class="badge badge-queue">queued</span>';
  if (!moved && s.action !== 'RESET') badges += '<span class="badge badge-blocked">blocked</span>';
  else if (s.action !== 'RESET') badges += '<span class="badge badge-ok">moved</span>';

  html += '<div class="info-label">Step ' + s.step + ' — ' + s.action + badges + '</div>';

  if (s.player_pos && s.new_pos) {
    html += '<div class="info-content">(' + s.player_pos[0] + ',' + s.player_pos[1] + ') → (' + s.new_pos[0] + ',' + s.new_pos[1] + ')</div>';
  }
  if (s.event) {
    html += '<div class="info-label">Event</div><div class="info-content">' + esc(s.event) + '</div>';
  }
  if (s.reasoning && s.reasoning.length > 5 && !s.reasoning.startsWith('(queued)')) {
    html += '<div class="info-label">Reasoning</div><div class="info-content">' + esc(s.reasoning) + '</div>';
  }

  document.getElementById('info-panel').innerHTML = html;

  // step list highlight
  document.querySelectorAll('.step-item').forEach((el, i) => el.classList.toggle('active', i === idx));
  const activeEl = document.querySelector('.step-item.active');
  if (activeEl) activeEl.scrollIntoView({ block: 'nearest' });

  document.getElementById('btn-prev').disabled = idx === 0;
  document.getElementById('btn-next').disabled = idx === trajectory.length - 1;
}

function go(d) { showStep(currentIdx + d); }
function goTo(i) { showStep(i); }

function togglePlay() {
  playing = !playing;
  document.getElementById('btn-play').textContent = playing ? '⏸' : '▶ Play';
  if (playing) {
    playInterval = setInterval(() => {
      if (currentIdx >= trajectory.length - 1) { togglePlay(); return; }
      go(1);
    }, 300);
  } else clearInterval(playInterval);
}

document.addEventListener('keydown', e => {
  if (e.key === 'ArrowLeft') go(-1);
  else if (e.key === 'ArrowRight') go(1);
  else if (e.key === ' ') { e.preventDefault(); togglePlay(); }
});

// build step list
const listEl = document.getElementById('step-list');
trajectory.forEach((s, i) => {
  const div = document.createElement('div');
  const isVlm = s.llm_called;
  const blocked = s.moved === false && s.action !== 'RESET';
  div.className = 'step-item' + (isVlm ? ' vlm' : '') + (blocked ? ' blocked' : '');

  let moveStr = '';
  if (s.player_pos && s.new_pos) {
    moveStr = '(' + s.player_pos[0] + ',' + s.player_pos[1] + ')→(' + s.new_pos[0] + ',' + s.new_pos[1] + ')';
  }
  if (blocked) moveStr += ' ✕';

  div.innerHTML = '<span class="step-num">' + s.step + '</span>' +
    '<span class="step-action">' + s.action + '</span>' +
    '<span class="step-move">' + moveStr + '</span>';
  div.onclick = () => goTo(i);
  listEl.appendChild(div);
});

showStep(0);
</script>
</body>
</html>"""


def find_experiment(path_str: str | None) -> Path:
    """실험 디렉토리 또는 replay.json을 찾는다."""
    exp_dir = Path("experiments")

    if path_str:
        p = Path(path_str)
        if p.is_file() and p.suffix == ".json":
            return p
        if p.is_dir():
            return p
        # 부분 매치
        if exp_dir.exists():
            for d in sorted(exp_dir.iterdir(), reverse=True):
                if path_str in d.name:
                    return d

    # 최신 실험
    if exp_dir.exists():
        dirs = sorted(exp_dir.iterdir(), reverse=True)
        if dirs:
            return dirs[0]

    print("No experiments found")
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="ARC-AGI-3 리플레이어")
    parser.add_argument("path", nargs="?", help="실험 디렉토리, replay.json, 또는 이름 부분매치")
    parser.add_argument("-p", "--port", type=int, default=5556, help="포트 (기본: 5556)")
    args = parser.parse_args()

    target = find_experiment(args.path)

    # replay.json 직접 지정
    if target.is_file() and target.suffix == ".json" and target.name == "replay.json":
        replay_path = target
    elif target.is_dir():
        # replay.json이 있으면 사용, 없으면 생성
        replay_path = target / "replay.json"
        if not replay_path.exists():
            print(f"Converting experiment to replay format...")
            replay_path = convert_experiment(target, replay_path)
    else:
        print(f"Unknown target: {target}")
        sys.exit(1)

    print(f"Loading {replay_path}")
    run_data = json.loads(replay_path.read_text())

    title = run_data.get("title", "?")
    agent_name = run_data.get("agent_name", "?")
    total = len(run_data.get("trajectory", []))
    final_state = run_data.get("final_state", "?")
    levels = run_data.get("levels_completed", 0)
    api_usage = run_data.get("api_usage", "")

    print(f"{title} — {agent_name} ({total} steps, {final_state})")

    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template_string(
            HTML,
            title=title,
            agent_name=agent_name,
            total=total,
            final_state=final_state,
            levels=levels,
            api_usage=api_usage,
            colors=ARC_COLORS,
            trajectory=run_data.get("trajectory", []),
        )

    print(f"\n  http://localhost:{args.port}")
    app.run(host="0.0.0.0", port=args.port, debug=False)


if __name__ == "__main__":
    main()
