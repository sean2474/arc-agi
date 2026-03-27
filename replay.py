"""에이전트 실행 결과 리플레이어.

사용법:
    python replay.py data/ls20/claude_v0/run_20260327_091408.json
    python replay.py data/ls20/claude_v0/   # 디렉토리 → 최신 파일
"""

import sys
import json
import argparse
from pathlib import Path

from flask import Flask, jsonify, render_template_string
from agents.llm_agent.const import ARC_COLORS


HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Replay: {{ title }} — {{ agent_name }}</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:#1a1a2e; color:#eee; font-family:'Courier New',monospace;
         display:flex; height:100vh; overflow:hidden; }
  #sidebar { width:440px; min-width:440px; background:#16213e; display:flex; flex-direction:column;
             border-right:2px solid #333; }
  #main { flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; padding:16px; }
  h1 { font-size:16px; color:#7fdbff; padding:12px 16px; border-bottom:1px solid #333; }
  #controls { display:flex; gap:8px; padding:12px 16px; border-bottom:1px solid #333; align-items:center; }
  .btn { padding:6px 14px; border:1px solid #555; background:#0f3460; color:#eee;
         border-radius:4px; cursor:pointer; font-family:inherit; font-size:13px; }
  .btn:hover { background:#533483; }
  .btn:disabled { opacity:0.3; cursor:default; }
  #step-display { flex:1; text-align:center; font-size:14px; color:#aaa; }
  #info-panel { flex:1; overflow-y:auto; padding:12px 16px; font-size:12px; line-height:1.6; }
  .info-section { margin-bottom:14px; }
  .info-label { color:#7fdbff; font-weight:bold; margin-bottom:4px; font-size:11px; text-transform:uppercase; }
  .info-content { color:#ccc; white-space:pre-wrap; word-break:break-word;
                   font-family:Arial,Helvetica,sans-serif; font-size:14px; line-height:1.7; }
  .phase-badge { display:inline-block; padding:2px 8px; border-radius:10px; font-size:10px; margin-left:8px; }
  .phase-observe { background:#2d6a4f; color:#fff; }
  .phase-seq { background:#0f3460; color:#aaa; }
  .phase-report { background:#7f4f24; color:#fff; }
  canvas { border:2px solid #333; image-rendering:pixelated; }
  #grid-status { margin-top:8px; font-size:12px; color:#888; }
  #timeline { padding:0 16px 12px; border-bottom:1px solid #333; }
  #timeline input { width:100%; }
  #step-list { flex:1; overflow-y:auto; }
  .step-item { padding:6px 16px; cursor:pointer; font-size:11px; border-bottom:1px solid #222;
               display:flex; align-items:center; gap:8px; }
  .step-item:hover { background:#0f3460; }
  .step-item.active { background:#533483; }
  .step-item.llm { border-left:3px solid #7fdbff; }
  .step-num { color:#666; width:30px; }
  .step-action { flex:1; }
  .step-phase { font-size:9px; color:#7fdbff; }
  /* prompt popup */
  #prompt-overlay { display:none; position:fixed; top:0; left:0; width:100%; height:100%;
                    background:rgba(0,0,0,0.7); z-index:100; justify-content:center; align-items:center; }
  #prompt-overlay.show { display:flex; }
  #prompt-box { background:#16213e; border:2px solid #7fdbff; border-radius:8px; width:80%; max-width:900px;
                max-height:80vh; overflow-y:auto; padding:20px; position:relative; }
  #prompt-box pre { color:#ccc; font-size:12px; line-height:1.5; white-space:pre-wrap; word-break:break-word; }
  #prompt-close { position:absolute; top:10px; right:14px; cursor:pointer; color:#7fdbff; font-size:20px; }
  .prompt-tab { display:inline-block; padding:4px 12px; margin:0 4px 8px 0; border:1px solid #555;
                border-radius:4px; cursor:pointer; font-size:11px; color:#aaa; }
  .prompt-tab.active { background:#533483; color:#fff; border-color:#7fdbff; }
</style>
</head>
<body>
  <div id="sidebar">
    <h1> {{ title }} — {{ agent_name }}</h1>
    <div id="controls">
      <button class="btn" id="btn-prev" onclick="go(-1)">◀</button>
      <div id="step-display">0 / {{ total }}</div>
      <button class="btn" id="btn-next" onclick="go(1)">▶</button>
      <button class="btn" id="btn-play" onclick="togglePlay()">▶ Play</button>
    </div>
    <div id="timeline">
      <input type="range" id="slider" min="0" max="{{ total - 1 }}" value="0" oninput="goTo(+this.value)">
    </div>
    <div id="info-panel"></div>
    <div id="step-list"></div>
  </div>
  <div id="main">
    <canvas id="grid" width="512" height="512"></canvas>
    <div id="grid-status"></div>
  </div>
  <div id="prompt-overlay" onclick="if(event.target===this)closePrompt()">
    <div id="prompt-box">
      <span id="prompt-close" onclick="closePrompt()">✕</span>
      <div id="prompt-tabs"></div>
      <pre id="prompt-content"></pre>
    </div>
  </div>

<script>
const COLORS = {{ colors | tojson }};
const CELL = 8;
const canvas = document.getElementById('grid');
const ctx = canvas.getContext('2d');

let trajectory = [];
let currentIdx = 0;
let playing = false;
let playInterval = null;

function drawGrid(grid, worldModel) {
  for (let y = 0; y < 64; y++) {
    const row = grid[y];
    for (let x = 0; x < 64; x++) {
      ctx.fillStyle = COLORS[parseInt(row[x], 16)] || '#000';
      ctx.fillRect(x*CELL, y*CELL, CELL, CELL);
    }
  }
  // draw object bbox outlines
  if (worldModel && worldModel.objects) {
    ctx.font = '9px Arial';
    const typeColors = {
      'unknown': '#ffffff80', 'static': '#888888', 'dynamic': '#00ff00',
      'controllable': '#00ffff', 'dangerous': '#ff0000', 'goal': '#ffff00',
      'background': '#444444', 'non-interactive': '#666666',
    };
    for (const [id, obj] of Object.entries(worldModel.objects)) {
      const b = obj.bbox;
      if (!b) continue;
      const x = (b.col_min || 0) * CELL;
      const y = (b.row_min || 0) * CELL;
      const w = ((b.col_max || 0) - (b.col_min || 0) + 1) * CELL;
      const h = ((b.row_max || 0) - (b.row_min || 0) + 1) * CELL;
      const color = typeColors[obj.type_hypothesis] || '#ffffff80';
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;
      ctx.strokeRect(x, y, w, h);
      ctx.fillStyle = '#000000aa';
      const label = `${id}`;
      const tw = ctx.measureText(label).width + 4;
      ctx.fillRect(x, y - 11, tw, 11);
      ctx.fillStyle = color;
      ctx.fillText(label, x + 2, y - 2);
    }
  }
}

function esc(s) { if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

function showStep(idx) {
  if (idx < 0 || idx >= trajectory.length) return;
  currentIdx = idx;
  const s = trajectory[idx];
  drawGrid(s.grid, s.world_model);

  document.getElementById('step-display').textContent = `${s.step} / ${trajectory.length}`;
  document.getElementById('slider').value = idx;
  document.getElementById('grid-status').textContent =
    `state: ${s.state}  |  levels: ${s.levels_completed}  |  action: ${s.action}`;

  let html = '';
  // header
  const phase = s.llm_phase || (s.llm_called ? 'llm' : null);
  let badge = '<span class="phase-badge phase-seq">↻ seq</span>';
  if (phase === 'observe+decide') badge = '<span class="phase-badge phase-observe">observe+decide</span>';
  else if (phase) badge = `<span class="phase-badge phase-observe">${esc(phase)}</span>`;

  html += `<div class="info-section"><div class="info-label">Step ${s.step} — ${esc(s.action)} ${badge}</div></div>`;

  if (s.trigger) {
    html += `<div class="info-section"><div class="info-label">Trigger</div><div class="info-content">${esc(s.trigger)}</div></div>`;
  }
  if (s.hypothesis) {
    html += `<div class="info-section"><div class="info-label">Hypothesis</div><div class="info-content">${esc(s.hypothesis)}</div></div>`;
  }
  if (s.challenge) {
    html += `<div class="info-section"><div class="info-label">Challenge</div><div class="info-content">${esc(s.challenge)}</div></div>`;
  }
  if (s.observation) {
    html += `<div class="info-section"><div class="info-label">Observation</div><div class="info-content">${esc(s.observation)}</div></div>`;
  }
  if (s.reasoning) {
    html += `<div class="info-section"><div class="info-label">Reasoning</div><div class="info-content">${esc(s.reasoning)}</div></div>`;
  }
  if (s.sequence_goal) {
    html += `<div class="info-section"><div class="info-label">Goal</div><div class="info-content">${esc(s.goal || s.sequence_goal)}</div></div>`;
  }
  if (s.report) {
    const achieved = s.report.goal_achieved ? '[OK]' : '[FAIL]';
    html += `<div class="info-section"><div class="info-label">${achieved} Report</div>`;
    html += `<div class="info-content">${esc(s.report.reasoning || '')}</div>`;
    if (s.report.key_learnings && s.report.key_learnings.length) {
      html += `<div class="info-content" style="margin-top:6px;color:#aaa;">Learnings: ${esc(s.report.key_learnings.join(', '))}</div>`;
    }
    html += `</div>`;
  }
  // world model
  if (s.world_model) {
    html += `<div class="info-section"><div class="info-label">World Model</div>`;
    const wm = s.world_model;
    html += `<div class="info-content" style="font-size:12px;">`;
    html += `phase: ${esc(wm.phase || '?')}\n`;
    if (wm.objects && Object.keys(wm.objects).length) {
      html += `objects: ${Object.keys(wm.objects).join(', ')}\n`;
    }
    if (wm.controllable && wm.controllable.description) {
      html += `controllable: ${esc(wm.controllable.description)} (${wm.controllable.confidence})\n`;
    }
    if (wm.goal && wm.goal.description) {
      html += `goal: ${esc(wm.goal.description)} (${wm.goal.confidence})\n`;
    }
    if (wm.dangers && wm.dangers.length) {
      html += `dangers: ${wm.dangers.length}\n`;
    }
    if (wm.interactions && wm.interactions.length) {
      html += `interactions: ${wm.interactions.length}\n`;
    }
    if (wm.immediate_plan) {
      html += `plan: ${esc(typeof wm.immediate_plan === 'object' ? wm.immediate_plan.description : wm.immediate_plan)}\n`;
    }
    html += `</div>`;
    html += `<button class="btn" onclick="showWorldModel(${idx})" style="font-size:11px;margin-top:4px;">Full World Model</button>`;
    html += `</div>`;
  }
  // prompt button
  if (s.prompts) {
    html += `<div class="info-section"><button class="btn" onclick="showPrompts(${idx})" style="font-size:11px;">View Prompts</button></div>`;
  }

  document.getElementById('info-panel').innerHTML = html;

  // step list highlight
  document.querySelectorAll('.step-item').forEach((el, i) => el.classList.toggle('active', i === idx));
  const activeEl = document.querySelector('.step-item.active');
  if (activeEl) activeEl.scrollIntoView({ block: 'nearest' });

  document.getElementById('btn-prev').disabled = idx === 0;
  document.getElementById('btn-next').disabled = idx === trajectory.length - 1;
}

// prompt popup
function showPrompts(idx) {
  const s = trajectory[idx];
  if (!s.prompts) return;
  const keys = Object.keys(s.prompts);
  const tabsEl = document.getElementById('prompt-tabs');
  const contentEl = document.getElementById('prompt-content');
  tabsEl.innerHTML = '';

  function showTab(label, text) {
    tabsEl.querySelectorAll('.prompt-tab').forEach(t => t.classList.remove('active'));
    event.target.classList.add('active');
    contentEl.textContent = text;
  }

  keys.forEach((k, i) => {
    // prompt tab
    const pTab = document.createElement('span');
    pTab.className = 'prompt-tab' + (i === 0 ? ' active' : '');
    pTab.textContent = k + ' (prompt)';
    pTab.onclick = () => {
      tabsEl.querySelectorAll('.prompt-tab').forEach(t => t.classList.remove('active'));
      pTab.classList.add('active');
      contentEl.textContent = s.prompts[k];
    };
    tabsEl.appendChild(pTab);

    // response tab
    if (s.responses && s.responses[k]) {
      const rTab = document.createElement('span');
      rTab.className = 'prompt-tab';
      rTab.textContent = k + ' (response)';
      rTab.onclick = () => {
        tabsEl.querySelectorAll('.prompt-tab').forEach(t => t.classList.remove('active'));
        rTab.classList.add('active');
        contentEl.textContent = s.responses[k];
      };
      tabsEl.appendChild(rTab);
    }
  });

  contentEl.textContent = s.prompts[keys[0]];
  document.getElementById('prompt-overlay').classList.add('show');
}
function showWorldModel(idx) {
  const s = trajectory[idx];
  if (!s.world_model) return;
  const tabsEl = document.getElementById('prompt-tabs');
  const contentEl = document.getElementById('prompt-content');
  tabsEl.innerHTML = '<span class="prompt-tab active">world_model</span>';
  contentEl.textContent = JSON.stringify(s.world_model, null, 2);
  document.getElementById('prompt-overlay').classList.add('show');
}
function closePrompt() { document.getElementById('prompt-overlay').classList.remove('show'); }

function go(delta) { showStep(currentIdx + delta); }
function goTo(idx) { showStep(idx); }

function togglePlay() {
  playing = !playing;
  document.getElementById('btn-play').textContent = playing ? '⏸' : '▶ Play';
  if (playing) {
    playInterval = setInterval(() => {
      if (currentIdx >= trajectory.length - 1) { togglePlay(); return; }
      go(1);
    }, 300);
  } else { clearInterval(playInterval); }
}

document.addEventListener('keydown', e => {
  if (document.getElementById('prompt-overlay').classList.contains('show')) {
    if (e.key === 'Escape') closePrompt();
    return;
  }
  if (e.key === 'ArrowLeft') go(-1);
  else if (e.key === 'ArrowRight') go(1);
  else if (e.key === ' ') { e.preventDefault(); togglePlay(); }
});

function loadData() {
  fetch('/data').then(r => r.json()).then(data => {
    const newTraj = data.trajectory || [];
    if (newTraj.length === trajectory.length) return;

    const wasAtEnd = currentIdx >= trajectory.length - 1;
    trajectory = newTraj;
    document.getElementById('slider').max = Math.max(trajectory.length - 1, 0);

    // rebuild step list
    const listEl = document.getElementById('step-list');
    listEl.innerHTML = '';
    trajectory.forEach((s, i) => {
      const isLlm = s.llm_phase || s.llm_called;
      const div = document.createElement('div');
      div.className = 'step-item' + (isLlm ? ' llm' : '');
      const phase = s.llm_phase ? `<span class="step-phase">${s.llm_phase}</span>` : '';
      div.innerHTML = `<span class="step-num">${s.step}</span><span class="step-action">${s.action}</span>${phase}`;
      div.onclick = () => goTo(i);
      listEl.appendChild(div);
    });

    // auto-follow latest step if was at end
    if (wasAtEnd && trajectory.length > 0) {
      showStep(trajectory.length - 1);
    } else if (trajectory.length > 0 && currentIdx === 0) {
      showStep(0);
    }
  }).catch(() => {});
}

// initial load + poll every 2 seconds
loadData();
setInterval(loadData, 2000);
</script>
</body>
</html>"""


def find_latest_run(path: Path) -> Path:
    """디렉토리면 최신 json, 파일이면 그대로."""
    if path.is_file():
        return path
    runs = sorted(path.glob("run_*.json"))
    if not runs:
        print(f"[ERROR] no run files in {path}")
        sys.exit(1)
    return runs[-1]


def main():
    parser = argparse.ArgumentParser(description="ARC-AGI-3 리플레이어")
    parser.add_argument("path", help="run JSON 파일 또는 data/{game}/{agent}/ 디렉토리")
    parser.add_argument("-p", "--port", type=int, default=5556, help="포트 (기본: 5556)")
    args = parser.parse_args()

    run_path = find_latest_run(Path(args.path))
    print(f"Loading {run_path}")

    with open(run_path) as f:
        run_data = json.load(f)

    title = run_data.get("title", "?")
    agent_name = run_data.get("agent_name", "?")
    total = len(run_data["trajectory"])
    print(f"{title} — {agent_name} ({total} steps)")

    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template_string(
            HTML,
            title=title,
            agent_name=agent_name,
            total=total,
            colors=ARC_COLORS,
        )

    @app.route("/data")
    def data():
        return jsonify(run_data)

    print(f"\n http://localhost:{args.port}")
    app.run(host="0.0.0.0", port=args.port, debug=False)


if __name__ == "__main__":
    main()