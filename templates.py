# ── UI ────────────────────────────────────────────────────────────────────

THEME_CSS = """  :root {
    color-scheme: dark;
    --bg: #0d0f14; --bg2: #13161e; --bg3: #1a1e2a;
    --border: #252936; --amber: #e8a44a; --amber-dim: #7a5424;
    --text: #c8cdd8; --text-dim: #5a6075; --text-bright: #eef0f5;
    --green: #4ecb8d; --red: #e05c6b; --red-deep: #c4485a; --radius: 10px;
    --amber-tint: rgba(232,164,74,0.08); --amber-tint-2: rgba(232,164,74,0.16);
    --red-tint: rgba(224,92,107,0.08); --red-tint-2: rgba(224,92,107,0.16);
    --red-border: rgba(224,92,107,0.35);
    --green-tint: rgba(78,203,141,0.08); --green-border: rgba(78,203,141,0.3);
    --green-text: #94d8b3;
    --blue: #5b9dd9; --blue-2: #6ea5e8; --blue-text: #a8c5ea;
    --blue-tint: rgba(91,157,217,0.08); --blue-border: rgba(91,157,217,0.4);
    --purple: #c99ae0; --purple-border: rgba(190,130,220,0.45);
    --orange: #e8875c; --orange-border: rgba(232,135,92,0.55);
    --orange-tint: rgba(232,135,92,0.08);
    --crit: #ff3b4f; --crit-border: rgba(255,59,79,0.7);
    --crit-tint: rgba(255,59,79,0.15); --crit-glow: rgba(255,59,79,0.6);
    --info-bg: var(--blue-tint); --info-border: var(--blue-border); --info-text: var(--blue-2);
    --danger-bg: var(--red-tint); --danger-border: var(--red-border); --danger-text: #e88494;
    --code-bg: #0a0b10; --overlay: rgba(0,0,0,0.7); --qr-bg: #ffffff;
    --select-arrow-amber: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='%237a5424'><path d='M4 6l4 4 4-4z'/></svg>");
    --select-arrow-dim: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="8" height="5"><path d="M0 0l4 5 4-5z" fill="%235a6075"/></svg>');
  }
  [data-theme="light"] {
    color-scheme: light;
    --bg: #f4f2ec; --bg2: #ffffff; --bg3: #eae7df;
    --border: #d6d1c6; --amber: #8f5a0e; --amber-dim: #d8b076;
    --text: #2b2f3a; --text-dim: #6b7084; --text-bright: #111318;
    --green: #1d8a56; --red: #c23747; --red-deep: #a12a38;
    --amber-tint: rgba(143,90,14,0.08); --amber-tint-2: rgba(143,90,14,0.16);
    --red-tint: rgba(194,55,71,0.08); --red-tint-2: rgba(194,55,71,0.16);
    --red-border: rgba(194,55,71,0.35);
    --green-tint: rgba(29,138,86,0.08); --green-border: rgba(29,138,86,0.3);
    --green-text: #1f6f48;
    --blue: #2c6cb0; --blue-2: #3b7fc4; --blue-text: #2a4f7a;
    --blue-tint: rgba(44,108,176,0.08); --blue-border: rgba(44,108,176,0.35);
    --purple: #7b4fa0; --purple-border: rgba(123,79,160,0.45);
    --orange: #c4602f; --orange-border: rgba(196,96,47,0.5);
    --orange-tint: rgba(196,96,47,0.08);
    --crit: #d11a2e; --crit-border: rgba(209,26,46,0.6);
    --crit-tint: rgba(209,26,46,0.1); --crit-glow: rgba(209,26,46,0.45);
    --danger-text: #a92f40;
    --code-bg: #f1eee7; --overlay: rgba(20,22,28,0.45);
    --select-arrow-amber: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='%23d8b076'><path d='M4 6l4 4 4-4z'/></svg>");
    --select-arrow-dim: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="8" height="5"><path d="M0 0l4 5 4-5z" fill="%236b7084"/></svg>');
  }
  .theme-btn {
    padding: 4px 10px; border-radius: 6px; border: 1px solid var(--border);
    background: none; color: var(--text-dim); font-family: 'IBM Plex Mono', monospace;
    font-size: 11px; cursor: pointer; line-height: 1.4; transition: all 0.2s;
  }
  .theme-btn:hover { border-color: var(--amber-dim); color: var(--amber); }
"""

THEME_JS = """<script>
(function () {
  var KEY = 'devloops_theme';
  function pick() {
    var s = null;
    try { s = localStorage.getItem(KEY); } catch (e) {}
    if (s === 'light' || s === 'dark') return s;
    return (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches)
      ? 'light' : 'dark';
  }
  function apply(t) {
    document.documentElement.setAttribute('data-theme', t);
    var hl = document.getElementById('hljsTheme');
    if (hl) hl.href = hl.href.replace(/atelier-cave-(dark|light)/, 'atelier-cave-' + t);
    var btn = document.getElementById('themeBtn');
    if (btn) btn.textContent = t === 'dark' ? '☀ light' : '☾ dark';
  }
  window.toggleTheme = function () {
    var t = pick() === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem(KEY, t); } catch (e) {}
    apply(t);
  };
  apply(pick());
  document.addEventListener('DOMContentLoaded', function () { apply(pick()); });
})();
</script>"""

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Q&A</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='6' fill='%230d0f14'/><rect x='4' y='4' width='24' height='24' rx='4' fill='none' stroke='%23e8a44a' stroke-width='1.5'/><text x='16' y='22' text-anchor='middle' font-family='monospace' font-size='13' font-weight='500' fill='%23e8a44a'>DL</text></svg>">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500&family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,600;1,9..144,300&display=swap" rel="stylesheet">
<link rel="stylesheet" id="hljsTheme" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/base16/atelier-cave-dark.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/marked/9.1.6/marked.min.js"></script>
<style>
""" + THEME_CSS + """

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  html, body {
    height: 100%;
    background: var(--bg);
    color: var(--text);
    font-family: 'IBM Plex Mono', monospace;
    font-size: 13px;
    line-height: 1.7;
    overflow: hidden;
  }

  .shell {
    display: grid;
    grid-template-rows: 56px auto 1fr 90px;
    height: 100vh;
    max-width: 900px;
    margin: 0 auto;
  }

  /* ── Header ── */
  header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 0 24px;
    border-bottom: 1px solid var(--border);
  }
  .logo-mark {
    width: 28px; height: 28px;
    border: 1.5px solid var(--amber);
    border-radius: 6px;
    display: flex; align-items: center; justify-content: center;
    font-size: 11px; color: var(--amber); font-weight: 500;
    letter-spacing: -0.5px;
  }
  .logo-text {
    font-family: 'Fraunces', serif;
    font-size: 17px;
    font-weight: 300;
    color: var(--text-bright);
  }
  .logo-text span { color: var(--amber); font-style: italic; }
  .status-dot {
    margin-left: auto;
    width: 7px; height: 7px;
    border-radius: 50%;
    background: var(--green);
    box-shadow: 0 0 8px var(--green);
    animation: pulse 2.5s ease-in-out infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.4; }
  }

  .slider-wrap input[type=range] { position: absolute; left: 0; right: 0; top: 0;
    width: 100%; height: 32px; -webkit-appearance: none; appearance: none;
    background: none; pointer-events: none; margin: 0; }
  .slider-wrap input[type=range]::-webkit-slider-thumb { -webkit-appearance: none;
    pointer-events: auto; width: 16px; height: 16px; border-radius: 50%;
    background: var(--bg); border: 2px solid var(--amber); cursor: grab; }
  .slider-wrap input[type=range]::-moz-range-thumb { pointer-events: auto;
    width: 14px; height: 14px; border-radius: 50%; background: var(--bg);
    border: 2px solid var(--amber); cursor: grab; }

  /* ── Messages ── */
  .messages {
    overflow-y: auto;
    padding: 28px 24px;
    display: flex;
    flex-direction: column;
    gap: 28px;
    scroll-behavior: smooth;
  }
  .messages::-webkit-scrollbar { width: 4px; }
  .messages::-webkit-scrollbar-track { background: transparent; }
  .messages::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

  .msg { display: flex; flex-direction: column; gap: 10px; animation: fadeUp 0.3s ease; }
  @keyframes fadeUp {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  .msg-user .bubble {
    align-self: flex-end;
    background: var(--bg3);
    border: 1px solid var(--border);
    border-radius: var(--radius) var(--radius) 2px var(--radius);
    padding: 10px 14px;
    color: var(--amber);
    max-width: 75%;
  }

  .msg-assistant .bubble {
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: 2px var(--radius) var(--radius) var(--radius);
    padding: 18px 20px;
  }

  /* ── Markdown ── */
  .bubble h1, .bubble h2, .bubble h3 {
    font-family: 'Fraunces', serif;
    font-weight: 600;
    color: var(--text-bright);
    margin: 20px 0 8px;
    line-height: 1.3;
  }
  .bubble h1 { font-size: 20px; }
  .bubble h2 { font-size: 16px; border-bottom: 1px solid var(--border); padding-bottom: 6px; }
  .bubble h3 { font-size: 14px; color: var(--amber); }
  .bubble p  { margin: 8px 0; }
  .bubble ul, .bubble ol { padding-left: 20px; margin: 8px 0; }
  .bubble li { margin: 4px 0; }
  .bubble strong { color: var(--text-bright); font-weight: 500; }
  .bubble em { color: var(--amber); font-style: italic; }
  .bubble a  { color: var(--amber); text-decoration: underline; text-underline-offset: 3px; }

  .bubble code:not(pre code) {
    background: var(--bg3);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 1px 6px;
    font-size: 12px;
    color: var(--green);
  }
  .bubble pre {
    background: var(--code-bg) !important;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow-x: auto;
    margin: 12px 0;
  }
  .bubble pre code {
    padding: 14px 16px !important;
    display: block;
    font-size: 12px;
    line-height: 1.6;
    background: transparent !important;
  }
  .bubble table {
    width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 12px;
  }
  .bubble th {
    background: var(--bg3); color: var(--amber);
    padding: 6px 10px; text-align: left; border: 1px solid var(--border);
  }
  .bubble td { padding: 6px 10px; border: 1px solid var(--border); }
  .bubble tr:nth-child(even) td { background: var(--bg3); }
  .bubble blockquote {
    border-left: 2px solid var(--amber-dim);
    padding-left: 12px; color: var(--text-dim); margin: 8px 0;
  }
  .bubble hr { border: none; border-top: 1px solid var(--border); margin: 16px 0; }

  /* ── Sources ── */
  .sources {
    display: flex; flex-wrap: wrap; gap: 6px;
    margin-top: 14px; padding-top: 12px;
    border-top: 1px solid var(--border);
  }
  .source-chip {
    display: flex; align-items: center; gap: 5px;
    padding: 3px 8px; border-radius: 20px; font-size: 11px;
    border: 1px solid var(--border); background: var(--bg3);
    color: var(--text-dim); transition: border-color 0.2s;
    cursor: pointer;
  }
  .source-chip:hover { border-color: var(--amber-dim); color: var(--text); }

  /* ── Per-answer metrics ── */
  .metrics {
    display: flex; flex-wrap: wrap; gap: 4px 14px;
    margin-top: 10px; padding-top: 8px;
    border-top: 1px dashed var(--border);
    font-size: 11px; color: var(--text-dim); line-height: 1.6;
  }
  .metrics b { color: var(--text); font-weight: 500; }
  .source-chip.suggested { border-color: var(--amber-dim); color: var(--amber-dim); }
  .source-chip .score {
    font-size: 10px; background: var(--bg);
    padding: 0 4px; border-radius: 10px; color: var(--text-dim);
  }
  .source-label { color: var(--text-dim); font-size: 11px; align-self: center; }

  /* ── Thinking ── */
  .thinking {
    display: flex; align-items: center; gap: 10px;
    color: var(--text-dim); font-size: 12px; padding: 10px 0;
  }
  .thinking-dots { display: flex; gap: 4px; }
  .thinking-dots span {
    width: 5px; height: 5px; border-radius: 50%;
    background: var(--amber); opacity: 0.3;
    animation: blink 1.2s ease infinite;
  }
  .thinking-dots span:nth-child(2) { animation-delay: 0.2s; }
  .thinking-dots span:nth-child(3) { animation-delay: 0.4s; }
  @keyframes blink {
    0%, 80%, 100% { opacity: 0.2; transform: scale(1); }
    40%            { opacity: 1;   transform: scale(1.3); }
  }

  /* ── Empty state ── */
  .empty {
    flex: 1; display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    gap: 20px; color: var(--text-dim); text-align: center; padding: 40px;
  }
  .empty-icon {
    width: 56px; height: 56px; border: 1.5px solid var(--border);
    border-radius: 14px; display: flex; align-items: center; justify-content: center;
    font-size: 22px; color: var(--amber-dim);
  }
  .empty h2 {
    font-family: 'Fraunces', serif; font-weight: 300;
    font-size: 20px; color: var(--text);
  }
  .empty p { font-size: 12px; max-width: 340px; line-height: 1.8; }
  .suggestions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; margin-top: 8px; }
  .suggestion {
    padding: 6px 12px; border: 1px solid var(--border); border-radius: 20px;
    font-size: 11.5px; color: var(--text-dim); cursor: pointer;
    transition: all 0.2s; background: none; font-family: 'IBM Plex Mono', monospace;
  }
  .suggestion:hover { border-color: var(--amber); color: var(--amber); background: var(--amber-tint); }

  /* ── Input bar ── */
  .input-bar {
    padding: 0 24px 20px;
    display: flex; flex-direction: column; gap: 8px;
  }
  .input-row {
    display: flex; align-items: flex-end; gap: 10px;
    background: var(--bg2); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 10px 12px;
    transition: border-color 0.2s;
  }
  .input-row:focus-within { border-color: var(--amber-dim); }
  textarea {
    flex: 1; background: none; border: none; outline: none; resize: none;
    color: var(--text-bright); font-family: 'IBM Plex Mono', monospace;
    font-size: 13px; line-height: 1.6; max-height: 120px; min-height: 22px;
  }
  textarea::placeholder { color: var(--text-dim); }
  .send-btn {
    width: 32px; height: 32px; border-radius: 7px;
    border: 1px solid var(--amber-dim); background: var(--amber-tint);
    color: var(--amber); cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    font-size: 14px; transition: all 0.2s; flex-shrink: 0;
  }
  .send-btn:hover:not(:disabled) { background: var(--amber-tint-2); border-color: var(--amber); }
  .send-btn:disabled { opacity: 0.3; cursor: default; }
  .hint { font-size: 11px; color: var(--text-dim); text-align: right; padding-right: 2px; }

  .error-msg {
    background: var(--red-tint); border: 1px solid var(--red-border);
    border-radius: var(--radius); padding: 10px 14px; color: var(--red); font-size: 12px;
  }
  .mode-toggle {
    display: flex; align-items: center; gap: 2px;
    background: var(--bg3); border: 1px solid var(--border);
    border-radius: 20px; padding: 3px; margin-left: auto;
  }
  .mode-btn {
    padding: 3px 10px; border-radius: 16px; border: none;
    font-family: 'IBM Plex Mono', monospace; font-size: 11px;
    cursor: pointer; transition: all 0.2s;
    background: none; color: var(--text-dim);
  }
  .mode-btn.active { background: var(--bg); color: var(--amber); border: 1px solid var(--amber-dim); }
  .mode-badge {
    font-size: 10px; padding: 2px 6px; border-radius: 10px;
    font-family: 'IBM Plex Mono', monospace; margin-left: 6px; vertical-align: middle;
  }
  .mode-badge.tech  { background: var(--green-tint); color: var(--green); border: 1px solid var(--green-border); }
  .mode-badge.plain { background: var(--amber-tint);  color: var(--amber); border: 1px solid var(--amber-dim); }

  select#searchModeSelector {
    -webkit-appearance: none;
    -moz-appearance: none;
    appearance: none;
    background-image: var(--select-arrow-amber);
    background-repeat: no-repeat;
    background-position: right 6px center;
    padding-right: 22px !important;
  }
    select#searchModeSelector option {
    background: var(--bg2);
    color: var(--text);
  }
  .modal-overlay {
    position: fixed; inset: 0; z-index: 100;
    background: var(--overlay);
    display: flex; align-items: center; justify-content: center;
    padding: 24px;
  }
  .modal-box {
    background: var(--bg2); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 22px 24px;
    max-width: 560px; width: 100%; max-height: 75vh; overflow-y: auto;
    position: relative;
  }
  .modal-close {
    position: absolute; top: 10px; right: 12px;
    background: none; border: none; color: var(--text-dim);
    font-size: 16px; cursor: pointer; font-family: inherit;
  }
  .modal-close:hover { color: var(--amber); }
  .skill-modal-title {
    font-family: 'Fraunces', serif; font-size: 17px;
    color: var(--text-bright); margin-bottom: 2px; padding-right: 24px;
  }
  .skill-modal-loc { font-size: 11px; color: var(--amber); margin-bottom: 10px; }
  .skill-modal-tag {
    display: inline-block; font-size: 10px; color: var(--red);
    border: 1px solid var(--red-border); border-radius: 4px;
    padding: 1px 6px; margin-bottom: 10px;
  }
  .skill-modal-desc { font-size: 13px; line-height: 1.7; }
  .skill-modal-code { font-family: inherit; font-size: 12px; line-height: 1.55;
    white-space: pre-wrap; word-break: break-word; margin: 0; }
  .skill-modal-members-head {
    font-size: 11px; letter-spacing: 1px; text-transform: uppercase;
    color: var(--text-dim); margin: 18px 0 8px;
    border-top: 1px solid var(--border); padding-top: 12px;
  }
  .skill-modal-member { margin-bottom: 10px; }
  .member-sym { color: var(--green); font-size: 12px; }
  .member-obs { color: var(--red); font-size: 10px; }
  .member-desc { color: var(--text-dim); font-size: 12px; line-height: 1.6; }
</style>
""" + THEME_JS + """
</head>
<body>
<div class="shell">
  <header>
    <div class="logo-mark">DL</div>
    <div class="logo-text">unified<span>brain</span> — ask the codebase</div>
    <div class="mode-toggle">
      <button class="mode-btn active" id="btnTech"  onclick="setMode('technical')">developer</button>
      <button class="mode-btn"        id="btnPlain" onclick="setMode('plain')">plain english</button>
    </div>
    <button class="mode-btn" id="histBtn" onclick="toggleHistory()"
      style="margin-left:8px">⏱ range</button>
    <button class="mode-btn" onclick="clearHistory()" style="margin-left:8px; display: none;">clear</button>
    <a class="mode-btn" href="/timeline" style="margin-left:8px; text-decoration:none">timeline</a>
    <button class="theme-btn" id="themeBtn" onclick="toggleTheme()" style="margin-left:8px"></button>
    <div class="status-dot" title="Connected" style="margin-left:14px"></div>
  </header>

  <div id="rangeStrip" style="display:none; border-bottom:1px solid var(--border);
       padding:14px 24px 10px;">
    <div style="display:flex; justify-content:space-between; font-size:11px;
         color:var(--text-dim); margin-bottom:6px;">
      <span><b id="qFrom" style="color:var(--amber); font-weight:500">—</b>
        <span id="qFromGoal"></span></span>
      <span style="text-align:right"><b id="qTo" style="color:var(--amber);
        font-weight:500">—</b> <span id="qToGoal"></span></span>
    </div>
    <div class="slider-wrap" style="position:relative; height:32px;">
      <div style="position:absolute; top:14px; left:0; right:0; height:4px;
           border-radius:2px; background:var(--bg3);"></div>
      <div id="qFill" style="position:absolute; top:14px; height:4px;
           border-radius:2px; background:var(--amber-dim);"></div>
      <input type="range" id="qKnobA" min="0" max="0" value="0">
      <input type="range" id="qKnobB" min="0" max="0" value="0">
    </div>
    <div id="qRangeMeta" style="font-size:11px; color:var(--text-dim);"></div>
  </div>

  <div class="messages" id="messages">
    <div class="empty" id="emptyState">
      
      <div class="empty-icon">⌘</div>
      <h2>Ask anything about the codebase</h2>
      <p>Powered by your skill corpus. Searches real code, explains patterns, surfaces constraints.</p>
      <div class="suggestions">
        <button class="suggestion" onclick="fillQ('How does state management work?')">How does state management work?</button>
        <button class="suggestion" onclick="fillQ('What API routes exist?')">What API routes exist?</button>
        <button class="suggestion" onclick="fillQ('How is weather data fetched?')">How is weather data fetched?</button>
        <button class="suggestion" onclick="fillQ('What is not yet implemented?')">What is not yet implemented?</button>
      </div>
    </div>
  </div>

  <div class="input-bar">
    <div class="input-row">
      <textarea id="input" placeholder="Ask about the codebase..." rows="1" autocomplete="off"></textarea>
      <button class="send-btn" id="sendBtn" onclick="send()" title="Send (Enter)">↑</button>
    </div>
    <div class="hint">Enter to send &middot; Shift+Enter for newline</div>
  </div>
</div>

<div class="modal-overlay" id="skillModal" style="display:none">
  <div class="modal-box">
    <button class="modal-close" onclick="closeSkillModal()">✕</button>
    <div id="skillModalBody"></div>
  </div>
</div>

<script>

const messagesEl = document.getElementById('messages');
const inputEl    = document.getElementById('input');
const sendBtn    = document.getElementById('sendBtn');

marked.setOptions({ breaks: true });

let currentMode = 'technical';

let qCommits = [], histOn = false;
const qA = document.getElementById('qKnobA'),
      qB = document.getElementById('qKnobB');
function qLo() { return Math.min(+qA.value, +qB.value); }
function qHi() { return Math.max(+qA.value, +qB.value); }

async function toggleHistory() {
  histOn = !histOn;
  document.getElementById('histBtn').style.color = histOn ? 'var(--amber)' : '';
  document.getElementById('rangeStrip').style.display = histOn ? '' : 'none';
  if (histOn && !qCommits.length) {
    const r = await fetch('/api/timeline/commits');
    const d = await r.json();
    qCommits = d.commits || [];
    if (!qCommits.length) {
      document.getElementById('qRangeMeta').textContent = 'No ingested commits.';
      return;
    }
    qA.max = qB.max = qCommits.length - 1;
    qA.value = 0; qB.value = qCommits.length - 1;
  }
  qRender();
  clearHistory();   // window changed → prior turns answered a different world
}

function qRender() {
  if (!qCommits.length) return;
  const a = qCommits[qLo()], b = qCommits[qHi()];
  document.getElementById('qFrom').textContent = a.hash.slice(0, 12);
  document.getElementById('qTo').textContent   = b.hash.slice(0, 12);
  document.getElementById('qFromGoal').textContent = (a.goal || '').slice(0, 40);
  document.getElementById('qToGoal').textContent   = (b.goal || '').slice(0, 40);
  const n = qCommits.length - 1 || 1;
  document.getElementById('qFill').style.left  = (qLo() / n * 100) + '%';
  document.getElementById('qFill').style.right = (100 - qHi() / n * 100) + '%';
  document.getElementById('qRangeMeta').textContent =
    (qHi() - qLo() + 1) + ' commit(s) — answers scoped to this range';
}
let qDeb = null;
[qA, qB].forEach(k => k.addEventListener('input', () => {
  qRender();
  clearTimeout(qDeb);
  qDeb = setTimeout(clearHistory, 400);   // range moved → stale conversation
}));

function setMode(mode) {
  currentMode = mode;
  document.getElementById('btnTech').classList.toggle('active',  mode === 'technical');
  document.getElementById('btnPlain').classList.toggle('active', mode === 'plain');
}

function clearHistory() {
  conversationHistory = [];
  document.getElementById('messages').innerHTML = `
    <div class="empty" id="emptyState">
      <div class="empty-icon">⌘</div>
      <h2>Ask anything about the codebase</h2>
      <p>Powered by your skill corpus.</p>
    </div>`;
}


function fillQ(text) { inputEl.value = text; inputEl.focus(); autoResize(); }

function autoResize() {
  inputEl.style.height = 'auto';
  inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + 'px';
}
inputEl.addEventListener('input', autoResize);
inputEl.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
});

function scrollBottom() { messagesEl.scrollTop = messagesEl.scrollHeight; }

function escapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function renderUser(text, mode) {
  const el = document.createElement('div');
  el.className = 'msg msg-user';
  const badge = mode === 'plain'
    ? '<span class="mode-badge plain">plain english</span>'
    : '<span class="mode-badge tech">developer</span>';
  el.innerHTML = `<div class="bubble">${escapeHtml(text)}${badge}</div>`;
  return el;
}

function renderAssistant(answer, sources) {
  const el = document.createElement('div');
  el.className = 'msg msg-assistant';

  let sourcesHtml = '';
  if (sources && sources.length > 0) {
    const chips = sources.map(s => {
      const label = s.file_path ? s.file_path.split('/').slice(-2).join('/') : s.skill_id;
      const cls   = s.suggested ? 'source-chip suggested' : 'source-chip';
      return `<div class="${cls}" title="${escapeHtml(s.file_path || s.skill_id)}">
        ${s.suggested ? '~ ' : ''}${escapeHtml(label)}
        <span class="score">${s.score}</span>
      </div>`;
    }).join('');
    sourcesHtml = `<div class="sources"><span class="source-label">sources</span>${chips}</div>`;
  }

  el.innerHTML = `<div class="bubble">${marked.parse(answer)}${sourcesHtml}</div>`;
  el.querySelectorAll('pre code').forEach(b => hljs.highlightElement(b));
  return el;
}

function renderError(msg) {
  const el = document.createElement('div');
  el.className = 'msg msg-assistant';
  el.innerHTML = `<div class="error-msg">&#9888; ${escapeHtml(msg)}</div>`;
  return el;
}

let loading = false;
let conversationHistory = [];

async function send() {
  const question = inputEl.value.trim();
  if (!question || loading) return;

  loading = true;
  sendBtn.disabled = true;
  inputEl.value = '';
  autoResize();

  const empty = document.getElementById('emptyState');
  if (empty) empty.remove();

  while (messagesEl.querySelectorAll('.msg').length >= 60) {
    messagesEl.querySelector('.msg').remove();
  }
  messagesEl.appendChild(renderUser(question, currentMode));
  if (histOn && qCommits.length) {
    const tag = document.createElement('div');
    tag.style.cssText = 'align-self:flex-end; font-size:10px; color:var(--text-dim);';
    tag.textContent = '⏱ ' + qCommits[qLo()].hash.slice(0,8) + ' → '
      + qCommits[qHi()].hash.slice(0,8);
    messagesEl.lastElementChild.appendChild(tag);
  }
  scrollBottom();

  // Build the assistant message bubble that will stream into
  const assistantEl = document.createElement('div');
  assistantEl.className = 'msg msg-assistant';
  assistantEl.innerHTML = `
    <div class="bubble">
      <div class="stream-chain" style="color: var(--text-dim); font-size: 11px; margin: 4px 0;"></div>
      <div class="stream-answer"></div>
      <div class="stream-sources"></div>
      <div class="stream-metrics"></div>
      <div class="thinking stream-wait">
        <div class="thinking-dots"><span></span><span></span><span></span></div>
        <div class="stream-status" style="font-style: italic; min-height: 18px;"></div>
      </div>
    </div>`;
  messagesEl.appendChild(assistantEl);

  const statusEl  = assistantEl.querySelector('.stream-status');
  const waitEl    = assistantEl.querySelector('.stream-wait');
  const chainEl   = assistantEl.querySelector('.stream-chain');
  const answerEl  = assistantEl.querySelector('.stream-answer');
  const sourcesEl = assistantEl.querySelector('.stream-sources');
  const metricsEl = assistantEl.querySelector('.stream-metrics');

  statusEl.textContent = 'Searching skill corpus…';
  scrollBottom();

  const investigationSteps = [];
  let accumulatedAnswer = '';
  let doneReceived = false;
  const sourcesMap = new Map(); 
  let errorShown = false;
  let metrics = null;

  try {
    const response = await fetch('/ask/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question,
        mode:        currentMode,
        history:     conversationHistory,
        from_commit: (histOn && qCommits.length) ? qCommits[qLo()].hash : '',
        to_commit:   (histOn && qCommits.length) ? qCommits[qHi()].hash : '',
      }),
    });

    if (!response.ok) {
      statusEl.textContent = '';
      const err = await response.json().catch(() => ({}));
      answerEl.innerHTML = `<div class="error-msg">&#9888; ${escapeHtml(err.detail || 'Request failed')}</div>`;
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split('\\n\\n');
      buffer = events.pop();

      for (const eventText of events) {
        if (!eventText.startsWith('data: ')) continue;

        let event;
        try {
          event = JSON.parse(eventText.slice(6));
        } catch {
          continue;
        }

        switch (event.type) {
          case 'status':
            statusEl.textContent = event.message;
            scrollBottom();
            break;

          case 'investigating':
            statusEl.textContent = `🔍 Investigating (${event.chain_position}): ${event.question}`;
            investigationSteps.push({
              position: event.chain_position,
              question: event.question,
            });
            renderChain(chainEl, investigationSteps);
            scrollBottom();
            break;

          case 'investigation_complete':
            // Could add a checkmark to the matching step
            break;

          // case 'answer_chunk':
          //  if (!accumulatedAnswer) {
          //    statusEl.textContent = '';
          //  }
          //  accumulatedAnswer += event.text;
          //  answerEl.innerHTML = marked.parse(accumulatedAnswer);
          //  answerEl.querySelectorAll('pre code').forEach(b => hljs.highlightElement(b));
          //  // scrollBottom();
          //  break;

          case 'answer_chunk':
            // Buffer silently — don't render until done
            accumulatedAnswer += event.text;
            break;

          case 'sources':
            // MERGE new batch into accumulator (dedupe by skill_id, keep highest score)
            for (const source of (event.sources || [])) {
                const existing = sourcesMap.get(source.skill_id);
                if (!existing || (source.score || 0) > (existing.score || 0)) {
                sourcesMap.set(source.skill_id, source);
                }
            }
            // Re-render the full accumulated set
            renderSourcesInline(sourcesEl, sourcesMap);
            break;

          case 'metrics':
            metrics = event.metrics;
            break;

          case 'error':
            errorShown = true;
            statusEl.textContent = '';
            answerEl.innerHTML = `<div class="error-msg">&#9888; ${escapeHtml(event.message)}</div>`;
            break;

          case 'done':
            doneReceived = true;
            statusEl.textContent = '';
            if (errorShown) return;  // error already on screen — don't overwrite
            if (!accumulatedAnswer.trim()) {
                answerEl.innerHTML = `<div class="error-msg">&#9888; The model finished without producing a response. This often happens in graph-only mode (no skills indexed) when the model can't navigate the codebase. Try <code>./devloops.sh bootstrap</code>, or rephrase with specific function names.</div>`;
                return;  // don't push empty assistant turn into history
            }
            answerEl.innerHTML = marked.parse(accumulatedAnswer);
            answerEl.querySelectorAll('pre code').forEach(b => hljs.highlightElement(b));
            if (metrics) metricsEl.innerHTML = renderMetrics(metrics);
            conversationHistory.push({ role: 'user', content: question });
            conversationHistory.push({ role: 'assistant', content: accumulatedAnswer });
            break;
        }
      }
    }

    // Stream closed without a 'done' event — backend likely crashed silently.
    // Render whatever we got, or show an error. But never overwrite an error
    // that was already streamed in.
    if (!doneReceived && !errorShown) {
        statusEl.textContent = '';
        if (accumulatedAnswer.trim()) {
            answerEl.innerHTML = marked.parse(accumulatedAnswer);
            answerEl.querySelectorAll('pre code').forEach(b => hljs.highlightElement(b));
        } else {
            answerEl.innerHTML = `<div class="error-msg">&#9888; Stream ended unexpectedly. Check server logs.</div>`;
        }
    }
  } catch (e) {
    statusEl.textContent = '';
    answerEl.innerHTML = `<div class="error-msg">&#9888; Could not reach the server. Is it running?</div>`;
  } finally {
    waitEl.style.display = 'none';   // the request is over: no dots, no status
    loading = false;
    sendBtn.disabled = false;
    scrollBottom();
    inputEl.focus();
  }
}

function renderChain(el, steps) {
  if (!steps.length) {
    el.innerHTML = '';
    return;
  }
  el.innerHTML = '<strong>Investigation chain:</strong><ul style="margin: 4px 0 0 16px; padding-left: 16px;">' +
    steps.map(s => `<li>${s.position}: ${escapeHtml(s.question)}</li>`).join('') +
    '</ul>';
}

function renderMetrics(m) {
  // One muted line under the answer: time per phase, Jev cost, writer speed.
  const s   = v => (v == null ? '–' : `${v} s`);
  const usd = v => (v == null ? '' : ` ($${Number(v).toFixed(3)})`);
  const n   = v => (v == null ? '–' : Number(v).toLocaleString());
  const parts = [
    `search <b>${s(m.search_secs)}</b>`,
    `Jev scoring <b>${s(m.select_secs)}</b>${usd(m.select_cost)} · ${n(m.select_calls)} judged, ${n(m.seeds)} seeds`,
    `chains <b>${s(m.expand_secs)}</b>${usd(m.expand_cost)} · ${n(m.expand_calls)} judged`
      + (m.triage_calls ? `, ${n(m.triage_calls)} triage` : '') + `, +${n(m.expand_added)} bodies`,
    `writer <b>${s(m.writer_secs)}</b> · first token ${s(m.writer_first_token_secs)} · `
      + `${n(m.writer_out_tokens)} tokens out` + (m.writer_tok_per_sec ? ` · <b>${m.writer_tok_per_sec} tok/s</b>` : ''),
    `${n(m.bodies)} bodies, ${n(m.context_chars)} chars in · ${n(m.writer_in_tokens)} tokens in`,
    `total <b>${s(m.total_secs)}</b> · Jev <b>$${Number(m.jev_cost || 0).toFixed(3)}</b>`,
  ];
  return parts.map(p => `<span>${p}</span>`).join('');
}

function renderSourcesInline(el, sourcesMap) {
  if (!sourcesMap || sourcesMap.size === 0) {
    el.innerHTML = '';
    return;
  }
  
  // Sort by score descending so highest-relevance appears first
  const sorted = Array.from(sourcesMap.values())
    .sort((a, b) => (b.score || 0) - (a.score || 0));
  
  const chips = sorted.map(s => {
    const label = s.file_path ? s.file_path.split('/').slice(-2).join('/') : s.skill_id;
    const cls = s.suggested ? 'source-chip suggested' : 'source-chip';
    const scoreDisplay = s.score && s.score.toFixed ? s.score.toFixed(3) : (s.score || '');
    return `<div class="${cls}" data-skill="${escapeHtml(s.skill_id)}" title="${escapeHtml(s.file_path || s.skill_id)}">
      ${s.suggested ? '~ ' : ''}${escapeHtml(label)}
      <span class="score">${scoreDisplay}</span>
    </div>`;
  }).join('');
  
  el.innerHTML = `<div class="sources"><span class="source-label">sources</span>${chips}</div>`;
}

messagesEl.addEventListener('click', e => {
  const chip = e.target.closest('.source-chip');
  if (chip && chip.dataset.skill) showSkillModal(chip.dataset.skill);
});

function closeSkillModal() {
  document.getElementById('skillModal').style.display = 'none';
}
document.getElementById('skillModal').addEventListener('click', e => {
  if (e.target.id === 'skillModal') closeSkillModal();
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeSkillModal();
});

async function showSkillModal(skillId) {
  const overlay = document.getElementById('skillModal');
  const body = document.getElementById('skillModalBody');
  overlay.style.display = 'flex';
  body.innerHTML = '<div style="color:var(--text-dim)">Loading…</div>';
  const qs = (histOn && qCommits.length)
    ? ('?to_commit=' + encodeURIComponent(qCommits[qHi()].hash)) : '';
  try {
    const r = await fetch('/api/skills/' + encodeURIComponent(skillId) + qs);
    if (!r.ok) throw new Error();
    const d = await r.json();
    let html = `<div class="skill-modal-title">${escapeHtml(d.name || d.skill_id)}</div>`;
    if (d.loc) html += `<div class="skill-modal-loc">${escapeHtml(d.loc)}</div>`;
    if (d.is_obsolete) html += `<div class="skill-modal-tag">obsolete at HEAD</div>`;
    if (d.description) {
      html += `<div class="skill-modal-desc">${escapeHtml(d.description)}</div>`;
    } else if (d.code) {
      html += `<pre class="skill-modal-code">${escapeHtml(d.code)}</pre>`;
    } else {
      html += `<div class="skill-modal-desc">${d.removed_at
        ? '(removed by commit ' + escapeHtml(d.removed_at) + ': no body at this commit)'
        : '(no body stored at this commit)'}</div>`;
    }
    if (d.is_composite && d.members && d.members.length) {
      html += `<div class="skill-modal-members-head">Mechanism members (${d.members.length})</div>`;
      html += d.members.map(m => `
        <div class="skill-modal-member">
          <span class="member-sym">${escapeHtml(m.symbol || m.skill_id)}</span>
          ${m.is_obsolete ? '<span class="member-obs"> obsolete</span>' : ''}
          <div class="member-desc">${escapeHtml(m.description || '')}</div>
        </div>`).join('');
    }
    body.innerHTML = html;
  } catch {
    body.innerHTML = '<div class="error-msg">⚠ Could not load skill details.</div>';
  }
}

</script>
</body>
</html>"""

TIMELINE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='6' fill='%230d0f14'/><rect x='4' y='4' width='24' height='24' rx='4' fill='none' stroke='%23e8a44a' stroke-width='1.5'/><text x='16' y='22' text-anchor='middle' font-family='monospace' font-size='13' font-weight='500' fill='%23e8a44a'>DL</text></svg>">
<title>DevLoops — Timeline</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500&family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,600;1,9..144,300&display=swap" rel="stylesheet">
<style>
""" + THEME_CSS + """
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { min-height: 100%; background: var(--bg); color: var(--text);
    font-family: 'IBM Plex Mono', monospace; font-size: 13px; line-height: 1.7; }
  .shell { max-width: 980px; margin: 0 auto; padding: 0 24px 60px; }
  header { display: flex; align-items: center; gap: 12px; padding: 18px 0;
    border-bottom: 1px solid var(--border); margin-bottom: 32px; }
  .logo-mark { width: 28px; height: 28px; border: 1.5px solid var(--amber);
    border-radius: 6px; display: flex; align-items: center; justify-content: center;
    font-size: 11px; color: var(--amber); }
  .logo-text { font-family: 'Fraunces', serif; font-size: 17px; font-weight: 300;
    color: var(--text-bright); }
  .logo-text span { color: var(--amber); font-style: italic; }
  .nav { margin-left: auto; display: flex; gap: 8px; }
  .nav-btn { padding: 4px 12px; border-radius: 6px; border: 1px solid var(--border);
    background: none; color: var(--text-dim); font-family: inherit; font-size: 11px;
    cursor: pointer; text-decoration: none; }
  .nav-btn:hover { border-color: var(--amber-dim); color: var(--amber); }
  h1 { font-family: 'Fraunces', serif; font-weight: 300; font-size: 28px;
    color: var(--text-bright); margin-bottom: 6px; }
  h1 em { color: var(--amber); font-style: italic; }
  .subtitle { color: var(--text-dim); font-size: 13px; margin-bottom: 28px; }
  #ingestStrip { margin: 4px 0 22px; padding: 10px 14px; border: 1px solid var(--border);
    border-radius: 8px; font-size: 12px; color: var(--text-dim);
    display: flex; gap: 18px; align-items: center; flex-wrap: wrap; }
  #ingestStrip b { color: var(--text); font-weight: 500; }
  #ingestStrip .bar { flex: 1 1 160px; height: 6px; background: var(--bg3);
    border-radius: 3px; overflow: hidden; }
  #ingestStrip .bar i { display: block; height: 100%; background: var(--amber); }
  #ingestStrip.failed { border-color: var(--red); }

  /* ── Dual-knob range ── */
  .range-card { background: var(--bg2); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 26px 26px 18px; margin-bottom: 24px; }
  .range-labels { display: flex; justify-content: space-between; margin-bottom: 14px;
    gap: 16px; }
  .range-label { font-size: 11px; color: var(--text-dim); max-width: 46%; }
  .range-label b { display: block; color: var(--amber); font-weight: 500; }
  .range-label .goal { color: var(--text); display: block; white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis; }
  .range-label .meta { color: var(--text-dim); display: block; font-size: 10px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .slider-wrap { position: relative; height: 32px; }
  .slider-track, .slider-fill { position: absolute; top: 14px; height: 4px;
    border-radius: 2px; }
  .slider-track { left: 0; right: 0; background: var(--bg3); }
  .slider-fill { background: var(--amber-dim); }
  .slider-wrap input[type=range] { position: absolute; left: 0; right: 0; top: 0;
    width: 100%; height: 32px; -webkit-appearance: none; appearance: none;
    background: none; pointer-events: none; margin: 0; }
  .slider-wrap input[type=range]::-webkit-slider-thumb { -webkit-appearance: none;
    pointer-events: auto; width: 16px; height: 16px; border-radius: 50%;
    background: var(--bg); border: 2px solid var(--amber); cursor: grab; }
  .slider-wrap input[type=range]::-moz-range-thumb { pointer-events: auto;
    width: 14px; height: 14px; border-radius: 50%; background: var(--bg);
    border: 2px solid var(--amber); cursor: grab; }
  /* Focus control: input is an invisible drag strip below the track;
     the visible marker is the arrow div. A/B thumbs stay unobstructed. */
  #knobC { top: 16px; height: 22px; }
  #knobC::-webkit-slider-thumb { opacity: 0; width: 20px; height: 20px;
    cursor: grab; }
  #knobC::-moz-range-thumb { opacity: 0; width: 20px; height: 20px;
    cursor: grab; }
  .focus-arrow { position: absolute; top: 21px; width: 0; height: 0;
    border-left: 6px solid transparent; border-right: 6px solid transparent;
    border-bottom: 9px solid var(--blue); transform: translateX(-50%);
    pointer-events: none; }
  .focus-chip { margin-left: 12px; padding: 1px 10px; border-radius: 5px;
    border: 1px solid var(--border); color: var(--text-dim); cursor: pointer;
    font-size: 10px; background: none; font-family: inherit; }
  .focus-chip.on { border-color: var(--blue); color: var(--blue); }
  #findCommit { margin-left: 10px; padding: 1px 10px; width: 150px;
    border-radius: 5px; border: 1px solid var(--border); background: var(--bg3);
    color: var(--text); font-family: inherit; font-size: 10px; }
  #findCommit:focus { outline: none; border-color: var(--blue); }
  #commitFilter { margin-left: auto; padding: 1px 10px; width: 260px;
    border-radius: 5px; border: 1px solid var(--border); background: var(--bg3);
    color: var(--text); font-family: inherit; font-size: 10px; }
  #commitFilter:focus { outline: none; border-color: var(--blue); }
  #findMsg { margin-left: 8px; font-size: 10px; }
  #findMsg.ok { color: var(--blue); }
  #findMsg.err { color: var(--red); }
  .vcount { color: var(--text-dim); font-size: 10px; }
  .range-meta { margin-top: 10px; font-size: 11px; color: var(--text-dim); }

  /* ── Grid ── */
  .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px;
    margin-bottom: 16px; }
  @media (max-width: 800px) { .grid { grid-template-columns: 1fr; } }
  .skill-card { background: var(--bg2); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 14px 16px; display: flex;
    flex-direction: column; gap: 6px; }
  .skill-card.obsolete { opacity: 0.5; }
  .skill-head { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  .skill-id { color: var(--amber); font-size: 11px; }
  .badge { font-size: 9px; letter-spacing: 0.5px; padding: 1px 7px;
    border-radius: 4px; border: 1px solid; }
  .badge.new { color: var(--green); border-color: var(--green-border); }
  .badge.updated { color: var(--amber); border-color: var(--amber-dim); }
  .badge.obsoleted { color: var(--red); border-color: var(--red-border); }
  .badge.composite { color: var(--blue-2); border-color: var(--blue-border); }
  .skill-loc { color: var(--text-dim); font-size: 10px; white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis; }
  .skill-desc { color: var(--text); font-size: 11.5px; line-height: 1.55;
    display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical;
    overflow: hidden; }
  .skill-code { color: var(--text); font-family: inherit; font-size: 10.5px;
    line-height: 1.5; white-space: pre; tab-size: 4; overflow: hidden; max-height: 7.5em;
    margin: 4px 0; padding: 6px 8px; border: 1px solid var(--border);
    border-radius: 6px; }
  .skill-code.note { color: var(--text-dim); white-space: normal; }
  .pager { display: flex; align-items: center; gap: 10px; justify-content: center;
    margin-bottom: 28px; color: var(--text-dim); font-size: 11px; }
  .pager button { padding: 4px 12px; border-radius: 6px;
    border: 1px solid var(--border); background: none; color: var(--text-dim);
    font-family: inherit; font-size: 11px; cursor: pointer; }
  .pager button:not(:disabled):hover { border-color: var(--amber-dim); color: var(--amber); }
  .pager button:disabled { opacity: 0.35; cursor: default; }
  .empty { text-align: center; color: var(--text-dim); padding: 32px 0; }
  .filters { display: flex; gap: 14px; margin-bottom: 14px; font-size: 11px;
    color: var(--text-dim); }
  #verdictFilters { display: grid;
    grid-template-columns: repeat(5, minmax(0, auto));
    justify-content: center; gap: 8px 22px; }
  #verdictFilters label { white-space: nowrap; }
  .vcount { margin-left: 2px; }
  .filters label { cursor: pointer; display: flex; gap: 5px; align-items: center; }

  /* ── Report ── */
  .report-bar { display: flex; justify-content: center; margin-bottom: 24px; gap: 12px; }
  #pastReports { -webkit-appearance: none; appearance: none; padding-right: 28px;
    background-image: var(--select-arrow-dim);
    background-repeat: no-repeat; background-position: right 10px center; }
  .btn-report { padding: 12px 28px; border-radius: 7px;
    background: var(--amber-tint); border: 1px solid var(--amber-dim);
    color: var(--amber); font-family: inherit; font-size: 13px; cursor: pointer; }
  .btn-report:not(:disabled):hover { background: var(--amber-tint-2);
    border-color: var(--amber); }
  .btn-report:disabled { opacity: 0.4; cursor: default; }
  .report-panel { display: none; background: var(--bg2);
    border: 1px solid var(--border); border-radius: var(--radius);
    padding: 22px 26px; white-space: pre-wrap; font-size: 12.5px;
    line-height: 1.7; }
  .report-status { color: var(--text-dim); font-size: 11px; margin-bottom: 10px; }
  .report-status { display: flex; align-items: center; gap: 10px; }
  .report-ctl { background: none; border: 1px solid var(--border);
    border-radius: 5px; color: var(--text-dim); font-family: inherit;
    font-size: 11px; padding: 2px 10px; cursor: pointer; }
  .report-ctl:hover { border-color: var(--amber-dim); color: var(--amber); }
  .verdict-like-stopped { color: var(--amber); }
  /* ── Skill modal ── */
  .skill-card { cursor: pointer; }
  .skill-card:hover { border-color: var(--amber-dim); }
  .modal-overlay { display: none; position: fixed; inset: 0;
    background: var(--overlay); z-index: 50;
    align-items: center; justify-content: center; padding: 24px; }
  .modal-overlay.open { display: flex; }
  .modal { background: var(--bg2); border: 1px solid var(--border);
    border-radius: var(--radius); max-width: 640px; width: 100%;
    max-height: 80vh; overflow-y: auto; padding: 22px 26px; }
  .modal-head { display: flex; align-items: center; gap: 8px;
    flex-wrap: wrap; margin-bottom: 6px; }
  .modal-close { margin-left: auto; background: none; border: 1px solid var(--border);
    border-radius: 6px; color: var(--text-dim); font-family: inherit;
    font-size: 11px; padding: 3px 10px; cursor: pointer; }
  .modal-close:hover { border-color: var(--amber-dim); color: var(--amber); }
  .modal-desc { color: var(--text); font-size: 12.5px; line-height: 1.7;
    white-space: pre-wrap; margin-top: 10px; }
  .modal-syms { color: var(--text-dim); font-size: 11px; margin-top: 12px; }
  .modal-syms code { color: var(--amber); }

  .probe-list { display: flex; flex-direction: column; gap: 10px; }
  .probe { background: var(--bg2); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 12px 16px; }
  .probe-head { display: flex; align-items: center; gap: 8px; cursor: pointer; }
  .probe-head .skill-id { flex: 1; }
  .verdict { font-size: 10px; letter-spacing: 0.5px; padding: 2px 9px;
    border-radius: 4px; border: 1px solid; }
  .verdict.BENIGN { color: var(--green); border-color: var(--green-border); }
  .verdict.SUSPICIOUS { color: var(--red); border-color: var(--red-border);
    background: var(--red-tint); }
  .verdict.FLAGRANTLY_MALICIOUS { color: var(--crit);
    border-color: var(--crit-border); background: var(--crit-tint);
    font-weight: 500; }
  .verdict.FLAW, .verdict.MINOR_FLAW { color: var(--purple);
    border-color: var(--purple-border); }
  .verdict.MAJOR_FLAW { color: var(--orange); border-color: var(--orange-border);
    background: var(--orange-tint); }
  .commit-group { display: flex; align-items: center; gap: 8px;
    margin: 10px 0 2px; color: var(--text-dim); font-size: 11px; }
  .commit-group b { color: var(--amber); font-weight: 500; }
  .commit-group span { white-space: nowrap; overflow: hidden;
    text-overflow: ellipsis; max-width: 55%; }
  .commit-group .rule { flex: 1; height: 1px; background: var(--border); }
  .verdict.UNCLEAR { color: var(--amber); border-color: var(--amber-dim); }
  #verdictFilters { grid-template-columns: repeat(6, minmax(0, auto)); }
  .mode-switch { display: flex; border: 1px solid var(--border);
    border-radius: 7px; overflow: hidden; }
  .mode-opt { padding: 0 14px; background: none; border: none;
    color: var(--text-dim); font-family: inherit; font-size: 11px;
    cursor: pointer; }
  .mode-opt.on { background: var(--amber-tint); color: var(--amber); }
  .verdict.DORMANT { color: var(--blue-2); border-color: var(--blue-border); }
  .verdict.INDEX_MISMATCH { color: var(--text-dim); border-color: var(--border); }
  .verdict.ERROR { color: var(--text-dim); border-color: var(--border); }
  .verdict.PENDING { color: var(--text-dim); border-color: var(--border);
    animation: pulse 1.2s infinite; }
  .probe-rerun { background: none; border: 1px solid var(--border);
    border-radius: 5px; color: var(--text-dim); font-family: inherit;
    font-size: 12px; padding: 1px 8px; cursor: pointer; line-height: 1.4; }
  .probe-rerun:hover { border-color: var(--amber-dim); color: var(--amber); }
  .probe-rerun:disabled { opacity: 0.35; cursor: default; }
  .badge.contested { color: var(--amber); border-color: var(--amber-dim);
    background: var(--amber-tint); cursor: pointer; }
  .worst-dot { width: 8px; height: 8px; border-radius: 50%;
    display: inline-block; flex: none; }
  .worst-dot.BENIGN { background: var(--green); }
  .worst-dot.MINOR_FLAW, .worst-dot.FLAW { background: var(--purple); }
  .worst-dot.MAJOR_FLAW { background: var(--orange); }
  .worst-dot.SUSPICIOUS { background: var(--red); }
  .worst-dot.FLAGRANTLY_MALICIOUS { background: var(--crit);
    box-shadow: 0 0 6px var(--crit-glow); }
  .worst-dot.UNCLEAR, .worst-dot.INDEX_MISMATCH { background: var(--amber); }
  .worst-dot.ERROR, .worst-dot.PENDING, .worst-dot.DORMANT {
    background: var(--text-dim); }
  .probe-findings { display: none; margin-top: 8px; padding: 8px 12px;
    border: 1px dashed var(--amber-dim); border-radius: 6px;
    font-size: 11px; color: var(--text); }
  .probe-findings.open { display: block; }
  .probe-findings .f-row { margin: 2px 0; }
  .probe-findings .f-sev { color: var(--amber); }
  .probe-findings .f-src { color: var(--text-dim); }
  @keyframes pulse { 50% { opacity: 0.4; } }
  .probe-body { display: none; margin-top: 10px; white-space: pre-wrap;
    font-size: 12px; line-height: 1.65; color: var(--text);
    border-top: 1px solid var(--border); padding-top: 10px; }
  .probe.open .probe-body { display: block; }
  /* ── Evidence panel: what the probe read ── */
  .probe-evidence { display: none; margin-top: 10px;
    border-top: 1px solid var(--border); padding-top: 8px; }
  .probe.open .probe-evidence.has { display: block; }
  .ev-toggle { background: none; border: 1px solid var(--border);
    border-radius: 5px; color: var(--text-dim); font-family: inherit;
    font-size: 11px; padding: 2px 10px; cursor: pointer; }
  .ev-toggle:hover, .ev-toggle.on { border-color: var(--amber-dim);
    color: var(--amber); }
  .ev-box { display: none; margin-top: 8px; font-size: 11.5px;
    line-height: 1.6; }
  .ev-box.open { display: block; }
  .ev-top { color: var(--text-dim); margin-bottom: 4px; }
  .ev-top b { color: var(--text); font-weight: 500; }
  .ev-h { color: var(--amber); font-size: 10px; letter-spacing: 0.08em;
    text-transform: uppercase; margin: 12px 0 4px; }
  .ev-row { padding: 2px 0; overflow-wrap: anywhere; }
  .ev-row code { color: var(--green); }
  .ev-dim { color: var(--text-dim); }
  .ev-warn { color: var(--red); }
  .ev-hash { color: var(--text-dim); font-size: 10px; cursor: help;
    border-bottom: 1px dotted var(--border); }
  .ev-trail { color: var(--text-dim); font-size: 10.5px; padding-left: 14px; }
  .ev-scroll { max-height: 240px; overflow-y: auto;
    border-left: 2px solid var(--border); padding-left: 10px; }
  .ev-chip { display: inline-block; margin: 2px 6px 2px 0; padding: 0 8px;
    border: 1px solid var(--border); border-radius: 10px;
    color: var(--text-dim); font-size: 10.5px; }
</style>
""" + THEME_JS + """
</head>
<body>
<div class="shell">
  <header>
    <div class="logo-mark">DL</div>
    <div class="logo-text">unified<span>brain</span></div>
    <nav class="nav">
      <a href="/" class="nav-btn">Ask</a>
      <button class="theme-btn" id="themeBtn" onclick="toggleTheme()"></button>
    </nav>
  </header>

  <div id="ingestStrip" style="display:none"></div>

  <h1>Commit <em>timeline</em>.</h1>
  <p class="subtitle">Pick a range of ingested commits — inspect the mechanisms it introduced, then conduct a report.</p>

  <div class="range-card">
    <div class="range-labels">
      <div class="range-label"><b id="fromHash">—</b><span class="goal" id="fromGoal"></span><span class="meta" id="fromMeta"></span></div>
      <div class="range-label" style="text-align:right"><b id="toHash">—</b><span class="goal" id="toGoal"></span><span class="meta" id="toMeta"></span></div>
    </div>
    <div class="slider-wrap">
      <div class="slider-track"></div>
      <div class="slider-fill" id="fill"></div>
      <input type="range" id="knobA" min="0" max="0" value="0">
      <input type="range" id="knobB" min="0" max="0" value="0">
      <input type="range" id="knobC" min="0" max="0" value="0" style="display:none">
      <div class="focus-arrow" id="focusArrow" style="display:none"></div>
    </div>
    <div class="range-meta"><span id="rangeMeta">Loading commit history…</span>
      <button class="focus-chip" id="focusChip">◎ focus commit</button>
      <input type="text" id="findCommit" placeholder="find commit…"
             spellcheck="false">
      <span id="findMsg"></span></div>
  </div>

  <div class="filters">
    <label><input type="checkbox" id="fNew" checked> new</label>
    <label><input type="checkbox" id="fUpd" checked> updated</label>
    <label><input type="checkbox" id="fObs"> obsoleted</label>
  </div>

  <div class="grid" id="grid"></div>
  <div class="pager" id="pager" style="display:none">
    <button id="prevBtn">← prev</button>
    <span id="pageInfo"></span>
    <button id="nextBtn">next →</button>
  </div>

  <div class="report-bar">
    <button class="btn-report" id="reportBtn" disabled>Conduct Report</button>
    <select id="pastReports" class="nav-btn" style="max-width:340px"></select>
    <button id="deleteReportBtn" class="nav-btn" title="Delete this report permanently" style="display:none">🗑 delete</button>
  </div>
  <div class="report-panel" id="reportPanel">
    <div class="report-status" id="reportStatus">
      <span id="reportStatusText"></span>
      <button id="reportCtl" class="report-ctl" style="display:none"></button>
      <input type="text" id="commitFilter" placeholder="filter by commit(s)… space-separated" spellcheck="false">
    </div>
    <div class="filters" id="verdictFilters">
      <label><input type="checkbox" value="FLAGRANTLY_MALICIOUS" checked> flagrant <span class="vcount" data-v="FLAGRANTLY_MALICIOUS"></span></label>
      <label><input type="checkbox" value="SUSPICIOUS" checked> suspicious <span class="vcount" data-v="SUSPICIOUS"></span></label>
      <label><input type="checkbox" value="MAJOR_FLAW" checked> major_flaw <span class="vcount" data-v="MAJOR_FLAW"></span></label>
      <label><input type="checkbox" value="MINOR_FLAW" checked> minor_flaw <span class="vcount" data-v="MINOR_FLAW"></span></label>
      <label><input type="checkbox" value="UNCLEAR" checked> unclear <span class="vcount" data-v="UNCLEAR"></span></label>
      <label><input type="checkbox" value="DORMANT" checked> dormant <span class="vcount" data-v="DORMANT"></label>
      <label><input type="checkbox" value="BENIGN" checked> benign <span class="vcount" data-v="BENIGN"></label>
      <label><input type="checkbox" value="INDEX_MISMATCH" checked> index_mismatch <span class="vcount" data-v="INDEX_MISMATCH"></label>
      <label><input type="checkbox" value="ERROR" checked> error <span class="vcount" data-v="ERROR"></label>
      <label><input type="checkbox" value="PENDING" checked> pending <span class="vcount" data-v="PENDING"></label>
    </div>
    <div class="probe-list" id="probeList"></div>
    <div class="pager" id="probePager" style="display:none; margin-top:14px">
      <button id="pPrev">← prev</button>
      <span id="pInfo"></span>
      <button id="pNext">next →</button>
    </div>
  </div>
</div>
<div class="modal-overlay" id="modalOverlay">
    <div class="modal">
      <div class="modal-head">
        <span class="skill-id" id="mId"></span>
        <span id="mBadges"></span>
        <button class="modal-close" id="mClose">✕ close</button>
      </div>
      <div class="skill-loc" id="mLoc"></div>
      <div class="modal-desc" id="mDesc"></div>
      <div class="modal-syms" id="mSyms"></div>
    </div>
  </div>

<script>
const H = { 'Content-Type': 'application/json' };

let commits = [], page = 1, pages = 1, pageSkillIds = [], debounce = null;

const $ = id => document.getElementById(id);
const A = $('knobA'), B = $('knobB');

function lo() { return Math.min(+A.value, +B.value); }
function hi() { return Math.max(+A.value, +B.value); }

function includeParam() {
  const inc = [];
  if ($('fNew').checked) inc.push('new');
  if ($('fUpd').checked) inc.push('updated');
  if ($('fObs').checked) inc.push('obsoleted');
  return inc.join(',') || 'new';
}

function renderRange() {
  if (!commits.length) return;
  const a = commits[lo()], b = commits[hi()];
  $('fromHash').textContent = a.hash.slice(0, 12);
  $('toHash').textContent   = b.hash.slice(0, 12);
  $('fromGoal').textContent = a.goal || '';
  $('toGoal').textContent   = b.goal || '';
  const fm = c => [c.author, (c.date || '').slice(0, 10)].filter(Boolean).join(' · ');
  $('fromMeta').textContent = fm(a);
  $('toMeta').textContent   = fm(b);
  const n = commits.length - 1 || 1;
  $('fill').style.left  = (lo() / n * 100) + '%';
  $('fill').style.right = (100 - hi() / n * 100) + '%';
  if (focusOn) $('focusArrow').style.left = (+C.value / n * 100) + '%';
  let meta = (hi() - lo() + 1) + ' commit(s) selected of ' + commits.length + ' ingested';
  if (focusOn) {
    const f = commits[+C.value];
    meta += ' · focus ' + f.hash.slice(0, 12) + (f.goal ? ' — ' + f.goal.slice(0, 50) : '');
  }
  $('rangeMeta').textContent = meta;
}

async function loadCommits() {
  const r = await fetch('/api/timeline/commits', { headers: H });
  const d = await r.json();
  commits = d.commits || [];
  if (!commits.length) {
    $('rangeMeta').textContent = 'No commits in the ingestion index yet.';
    return;
  }
  A.max = B.max = C.max = commits.length - 1;
  A.value = 0; B.value = commits.length - 1; C.value = 0;
  renderRange();
  loadSkills(1);
}

async function loadSkills(p) {
  const seq = ++skillsSeq;
  page = p;
  const fh = focusHash();
  const a = fh ? { hash: fh } : commits[lo()];
  const b = fh ? { hash: fh } : commits[hi()];
  const q = new URLSearchParams({
    from_commit: a.hash, to_commit: b.hash,
    page: p, page_size: 12, include: includeParam(),
  });
  const r = await fetch('/api/timeline/skills?' + q, { headers: H });
  if (seq !== skillsSeq) return;       // superseded by a newer page/range/filter
  if (!r.ok) { $('grid').innerHTML = '<div class="empty">Failed to load skills.</div>'; return; }
  const d = await r.json();
  if (seq !== skillsSeq) return;
  pages = d.pages;
  pageSkillIds = (d.skills || []).map(s => s.skill_id);
  const grid = $('grid');
  grid.innerHTML = '';
  if (!d.skills.length) {
    grid.innerHTML = '<div class="empty" style="grid-column:1/-1">No mechanisms recorded in this range.</div>';
  }
  for (const s of d.skills) {
    const card = document.createElement('div');
    card.className = 'skill-card' + (s.is_obsolete ? ' obsolete' : '');
    const badges = (s.events || []).map(e => '<span class="badge ' + e + '">' + e + '</span>').join('');
    const comp = s.is_composite ? '<span class="badge composite">composite</span>' : '';
    card.innerHTML =
      '<div class="skill-head"><span class="skill-id">' + s.skill_id + '</span>' + badges + comp + '</div>' +
      (s.loc ? '<div class="skill-loc">' + s.loc + '</div>' : '') +
      (s.description
        ? '<div class="skill-desc">' + esc(s.description) + '</div>'
        : '<pre class="skill-code' + (s.code ? '' : ' note') + '">'
          + esc(s.code || bodyNote(s)) + '</pre>') +
      '<div class="skill-loc">commit ' + s.commit + '</div>';
    card.onclick = () => openModal(s, badges + comp);
    grid.appendChild(card);
  }
  $('pager').style.display = pages > 1 ? 'flex' : 'none';
  $('pageInfo').textContent = 'page ' + d.page + ' / ' + pages + ' · ' + d.total + ' mechanism(s)';
  $('prevBtn').disabled = d.page <= 1;
  $('nextBtn').disabled = d.page >= pages;
  $('reportBtn').disabled = d.total === 0;
}

function rangeChanged() {
  let focusMoved = false;
  if (focusOn) {
    const clamped = Math.min(Math.max(+C.value, lo()), hi());
    if (clamped !== +C.value) { C.value = clamped; focusMoved = true; }
  }
  renderRange();
  clearTimeout(debounce);
  debounce = setTimeout(() => {
    loadSkills(1);
    if (focusMoved && currentReportId) {
      lastReportFingerprint = ''; viewReport(currentReportId, 1);
    }
  }, 350);
}

A.addEventListener('input', rangeChanged);
B.addEventListener('input', rangeChanged);
['fNew','fUpd','fObs'].forEach(id => $(id).addEventListener('change', () => loadSkills(1)));
const ALL_VERDICTS = ['FLAGRANTLY_MALICIOUS','SUSPICIOUS','MAJOR_FLAW','MINOR_FLAW','UNCLEAR','DORMANT','BENIGN','INDEX_MISMATCH','ERROR','PENDING'];
function verdictParam() {
  const sel = [...document.querySelectorAll('#verdictFilters input:checked')].map(c => c.value);
  return (sel.length === 0 || sel.length === ALL_VERDICTS.length) ? '' : sel.join(',');
}
document.querySelectorAll('#verdictFilters input').forEach(cb =>
  cb.addEventListener('change', () => {
    if (currentReportId) { lastReportFingerprint = ''; viewReport(currentReportId, 1); }
  }));
$('commitFilter').addEventListener('keydown', e => {
  if (e.key !== 'Enter') return;
  if (currentReportId) { lastReportFingerprint = ''; viewReport(currentReportId, 1); }
});
const C = $('knobC');
let focusOn = false;
function focusHash() { return (focusOn && commits.length) ? commits[+C.value].hash : ''; }

$('focusChip').onclick = () => {
  focusOn = !focusOn;
  $('focusChip').classList.toggle('on', focusOn);
  C.style.display = focusOn ? '' : 'none';
  $('focusArrow').style.display = focusOn ? '' : 'none';
  if (focusOn) C.value = Math.min(Math.max(+C.value, lo()), hi());
  renderRange();
  loadSkills(1);
  if (currentReportId) { lastReportFingerprint = ''; viewReport(currentReportId, 1); }
};
C.addEventListener('input', () => {
  // clamp focus inside the selected range
  if (+C.value < lo()) C.value = lo();
  if (+C.value > hi()) C.value = hi();
  renderRange();
  clearTimeout(debounce);
  debounce = setTimeout(() => {
    loadSkills(1);
    if (currentReportId) { lastReportFingerprint = ''; viewReport(currentReportId, 1); }
  }, 350);
});
$('findCommit').addEventListener('keydown', e => {
  if (e.key !== 'Enter') return;
  const q = $('findCommit').value.trim().toLowerCase();
  const msg = $('findMsg');
  msg.className = '';
  if (q.length < 6) {
    msg.textContent = 'min 6 chars'; msg.className = 'err'; return;
  }
  const hits = commits
    .map((c, i) => ({ c, i }))
    .filter(x => x.c.hash.toLowerCase().startsWith(q));
  if (!hits.length) {
    msg.textContent = 'not in ingestion index'; msg.className = 'err'; return;
  }
  if (hits.length > 1) {
    msg.textContent = hits.length + ' matches — be more specific';
    msg.className = 'err'; return;
  }
  const idx = hits[0].i;
  // widen the range if the commit falls outside it
  if (idx < lo()) (+A.value <= +B.value ? A : B).value = idx;
  if (idx > hi()) (+A.value <= +B.value ? B : A).value = idx;
  if (!focusOn) {
    focusOn = true;
    $('focusChip').classList.add('on');
    C.style.display = ''; $('focusArrow').style.display = '';
  }
  C.value = idx;
  msg.textContent = '→ ' + hits[0].c.hash.slice(0, 12); msg.className = 'ok';
  renderRange();
  loadSkills(1);
  if (currentReportId) { lastReportFingerprint = ''; viewReport(currentReportId, 1); }
});
$('prevBtn').onclick = () => loadSkills(page - 1);
$('nextBtn').onclick = () => loadSkills(page + 1);

$('reportBtn').onclick = async () => {
  const a = commits[lo()], b = commits[hi()];
  $('reportBtn').disabled = true;
  try {
    const r = await fetch('/api/timeline/report', {
      method: 'POST', headers: H,
      body: JSON.stringify({ from_commit: a.hash, to_commit: b.hash }),
    });
    const d = await r.json();
    if (!r.ok) { alert(d.detail || 'Report failed'); return; }
    loadReportList();
    viewReport(d.report_id, 1);   // polling auto-starts while status=running
  } finally {
    $('reportBtn').disabled = false;
  }
};

// Shown in the place of the body when there is none.
function bodyNote(s) {
  if (s.missing) return '(record missing)';
  if (s.removed_at) return '(removed by commit ' + s.removed_at + ': no body at the end of this range)';
  return '(no body stored at the end of this range)';
}

let modalSkill = '';                   // the skill the modal shows now
function openModal(s, badgesHtml) {
  $('mId').textContent = s.skill_id;
  $('mBadges').innerHTML = badgesHtml;
  $('mLoc').textContent = (s.loc ? s.loc + ' · ' : '') + 'commit ' + s.commit;
  $('mDesc').textContent = s.description || s.code || bodyNote(s);
  modalSkill = s.skill_id;
  if (!s.description && s.code) {
    // The card holds the first part of the body. Get the whole body, as of
    // the right side of the range (or the focused commit).
    const at = focusHash() || commits[hi()].hash;
    fetch('/api/skills/' + encodeURIComponent(s.skill_id)
          + '?to_commit=' + encodeURIComponent(at), { headers: H })
      .then(r => r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)))
      .then(d => {
        if (modalSkill !== s.skill_id) return;
        if (d && d.code) $('mDesc').textContent = d.code;
        else $('mDesc').textContent += '\\n\\n… (preview only: the full body came back empty)';
      })
      .catch(e => {
        if (modalSkill === s.skill_id)
          $('mDesc').textContent += '\\n\\n… (preview only: the full body could not be loaded — ' + e.message + ')';
      });
  }
  $('mSyms').innerHTML = (s.symbols && s.symbols.length)
    ? 'symbols: ' + s.symbols.map(x => '<code>' + x + '</code>').join(', ')
    : '';
  $('modalOverlay').classList.add('open');
}
$('mClose').onclick = () => $('modalOverlay').classList.remove('open');
$('modalOverlay').onclick = e => {
  if (e.target === $('modalOverlay')) $('modalOverlay').classList.remove('open');
};
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') $('modalOverlay').classList.remove('open');
});

let currentReportId = null, probePage = 1;
let pollTimer = null, pollingId = null;
let reportSeq = 0, skillsSeq = 0;
const openProbes = new Set();          // skill_ids the user has expanded
let lastReportFingerprint = '';

function startPolling(rid) {
  if (pollingId === rid && pollTimer) return;
  clearInterval(pollTimer);
  pollingId = rid;
  pollTimer = setInterval(async () => {
    if (currentReportId !== rid) { clearInterval(pollTimer); pollingId = null; return; }
    const finished = await viewReport(rid, probePage);
    if (finished) { clearInterval(pollTimer); pollingId = null; loadReportList(); }
  }, 3000);
}

// ── Evidence panel: what the probe read ──
const openEvidence = new Set();        // probes whose panel the user opened
const evidenceCache = new Map();       // report|probe|run time → record

function esc(s) {
  return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function evHash(h) {
  return h ? ' <span class="ev-hash" title="SHA-256: ' + esc(h) + '">'
    + esc(h.slice(0, 12)) + '</span>' : '';
}
function evSize(n) { return ' <span class="ev-dim">' + (+n || 0).toLocaleString() + ' chars</span>'; }

function renderEvidence(ev) {
  if (!ev) {
    return '<div class="ev-dim">No evidence record for this run. A record is '
      + 'kept for every probe the report runs.</div>';
  }
  const h = [];
  const head = t => h.push('<div class="ev-h">' + t + '</div>');
  const row = t => h.push('<div class="ev-row">' + t + '</div>');

  h.push('<div class="ev-top">Read as of commit <b>'
    + esc((ev.as_of_commit || '?').slice(0, 12)) + '</b>'
    + (ev.ts ? ' · run on ' + esc(new Date(ev.ts * 1000).toISOString().slice(0, 16).replace('T', ' ')) + ' UTC' : '')
    + (ev.run_verdict ? ' · this run said <b>' + esc(ev.run_verdict) + '</b>' : '')
    + '</div>');
  if (ev.error) row('<span class="ev-warn">Run error: ' + esc(ev.error) + '</span>');

  const t = ev.target || {};
  head('Target');
  row(esc(t.file) + ' <code>' + esc(t.symbol) + '</code>' + evSize(t.chars) + evHash(t.sha256));

  head('Diffs of the target (' + (ev.diffs || []).length + ')');
  for (const d of ev.diffs || []) {
    row('commit ' + esc((d.commit || '').slice(0, 12))
      + (d.chars ? evSize(d.chars) + evHash(d.sha256)
                 : ' <span class="ev-dim">' + esc(d.status || 'no diff') + '</span>'));
  }

  for (const sc of ev.same_commit || []) {
    const ch = sc.changes || [];
    const full = ch.filter(c => c.shown === 'full').length;
    head('Other changes in commit ' + esc((sc.commit || '').slice(0, 12)) + ' (' + ch.length + ')');
    row('<span class="ev-dim">' + full + ' read with their full diff, '
      + (ch.length - full) + ' by name only'
      + (sc.picked_by_jev ? ' (Jev chose which)' : '')
      + (sc.no_code_change ? ' · ' + sc.no_code_change + ' more with no code change' : '')
      + '</span>');
    h.push('<div class="ev-scroll">' + ch.map(c =>
      '<div class="ev-row">' + esc(c.loc) + ' <code>' + esc(c.symbol) + '</code> '
      + (c.shown === 'full' ? 'full diff' : '<span class="ev-warn">name only</span>')
      + evSize(c.chars) + evHash(c.sha256) + '</div>').join('') + '</div>');
  }

  head('Callers and referrers (' + (ev.lookups || []).length + ')');
  for (const l of ev.lookups || []) {
    row(esc(l.tool) + ' <code>' + esc(l.symbol) + '</code>' + evSize(l.chars) + evHash(l.sha256));
  }

  head('Code read by following names (' + (ev.read || []).length + ')');
  for (const x of ev.read || []) {
    row(esc(x.file) + ' <code>' + esc(x.symbol) + '</code>' + evSize(x.chars) + evHash(x.sha256)
      + (x.excerpt ? ' <span class="ev-warn">excerpt of a '
          + (+x.body_chars || 0).toLocaleString() + '-char body</span>' + evHash(x.body_sha256) : ''));
    h.push('<div class="ev-trail">reached by: ' + (x.trail || []).map(esc).join(' → ') + '</div>');
  }

  head('Reached but not read (' + (ev.leads || []).length + ')');
  for (const l of ev.leads || []) {
    row(esc(l.file) + ' <code>' + esc(l.symbol) + '</code>');
    h.push('<div class="ev-trail">reached by: ' + esc(l.trail) + '</div>');
  }

  head('Searches (' + (ev.searches || []).length + ')');
  h.push('<div class="ev-row">' + (ev.searches || []).map(s =>
    '<span class="ev-chip">' + esc(s.word) + ' · ' + (+s.hits || 0) + '</span>').join('') + '</div>');

  const c = ev.chain;
  if (c) {
    head('Chain step');
    row('<span class="ev-dim">' + (c.jev_calls || 0) + ' Jev calls · ' + (c.greps || 0)
      + ' searches · ' + (c.hops || 0) + ' hop(s) · $' + (+c.cost || 0).toFixed(4)
      + ' · ' + (c.secs || 0) + 's · model ' + esc(ev.jev_model || '') + '</span>');
    // Every decision of the step, in order: what Jev scored, what was
    // searched, what each search gave, what Jev said about each place.
    const pct = o => Object.entries(o || {}).map(([k, v]) =>
      esc(k) + ' ' + Math.round(v * 100) + '%').join(' · ');
    const names = o => Object.entries(o || {}).map(([k, v]) =>
      '<span class="ev-chip">' + esc(k) + ' · ' + Math.round(v * 100) + '%</span>').join('');
    for (const d of c.decisions || []) {
      if (d.kind === 'start') {
        row('start · Jev scored ' + Object.keys(d.scored || {}).length + ' names in '
          + esc(d.from) + (d.call_failed ? ' <span class="ev-warn">(the call failed: names taken in the order they appear)</span>' : '')
          + ' · chains start with: ' + (d.chosen || []).map(n => '<code>' + esc(n) + '</code>').join(', '));
        if (Object.keys(d.scored || {}).length) h.push('<div class="ev-trail">' + names(d.scored) + '</div>');
      } else if (d.kind === 'search') {
        row('step ' + d.step + ' · searched <code>' + esc(d.name) + '</code> from ' + esc(d.from)
          + ' · ' + (+d.hits || 0) + ' hit(s), ' + (+d.places || 0) + ' place(s)'
          + (d.took ? ' · read ' + esc(d.took) : ' · <span class="ev-warn">nothing new to read</span>'));
      } else if (d.kind === 'read') {
        row('step ' + d.step + ' · ' + esc(d.symbol ? '`' + d.symbol + '` in ' + d.file : d.file)
          + ' · verdict <b>' + esc(d.verdict || '?') + '</b>'
          + (Object.keys(d.probs || {}).length ? ' <span class="ev-dim">(' + pct(d.probs) + ')</span>' : '')
          + (d.reason ? ' <span class="ev-dim">' + esc(d.reason) + '</span>' : '')
          + evSize(d.chars) + (d.excerpt ? ' <span class="ev-warn">excerpt</span>' : ''));
        h.push('<div class="ev-trail">reached by: ' + esc(d.reached_by) + '</div>');
        h.push('<div class="ev-trail">next names: '
          + (Object.keys(d.next_names || {}).length ? names(d.next_names) : '<span class="ev-dim">none offered</span>')
          + (d.followed && d.followed.length ? ' → followed: ' + d.followed.map(n => '<code>' + esc(n) + '</code>').join(', ')
                                             : ' → <span class="ev-dim">chain ends here</span>') + '</div>');
      } else if (d.kind === 'second_look') {
        row('second look · ' + esc('`' + d.symbol + '` in ' + d.file) + ' · led to ' + (+d.led_to || 0)
          + ' place(s) · verdict <b>' + esc(d.verdict || '?') + '</b>'
          + (Object.keys(d.probs || {}).length ? ' <span class="ev-dim">(' + pct(d.probs) + ')</span>' : ''));
      }
    }
  }

  const j = ev.judge;
  head('Judge');
  if (j) {
    row((j.kind === 'jev' ? 'Jev' : 'LLM') + ' <code>' + esc(j.model) + '</code>');
    row('<span class="ev-dim">It was given: ' + esc(j.given) + '</span>');
    row('input' + evSize(j.input_chars) + evHash(j.input_sha256)
      + ' · gathered evidence' + evSize(j.evidence_chars) + evHash(j.evidence_sha256)
      + (j.context_chars != null ? ' · related-skill context' + evSize(j.context_chars) + evHash(j.context_sha256) : ''));
    if (j.probs) row('<span class="ev-dim">' + Object.entries(j.probs).sort((a, b) => b[1] - a[1])
      .map(([k, p]) => esc(k.toLowerCase()) + ' ' + Math.round(p * 100) + '%').join(' · ') + '</span>');
  } else {
    row('<span class="ev-warn">The run ended before a judge was called.</span>');
  }

  const b = ev.budget;
  if (b && b.dropped) {
    head('Left out by the size limit (' + b.dropped + ')');
    row('<span class="ev-warn">The evidence text is limited to ' + (+b.cap || 0).toLocaleString()
      + ' chars. These blocks were gathered but not given to the judge:</span>');
    for (const n of b.not_shown || []) row(esc(n));
  }
  return h.join('');
}

async function showEvidence(box, pid, key) {
  if (!evidenceCache.has(key)) {
    box.innerHTML = '<div class="ev-dim">Loading…</div>';
    const r = await fetch('/api/timeline/reports/' + currentReportId
      + '/probes/' + encodeURIComponent(pid) + '/evidence', { headers: H });
    if (!r.ok) { box.innerHTML = '<div class="ev-warn">Could not load the evidence record.</div>'; return; }
    evidenceCache.set(key, (await r.json()).evidence);
  }
  box.innerHTML = renderEvidence(evidenceCache.get(key));
}

function probeEl(p) {
  const pid = p.probe_id || p.skill_id;
  const isSplit = pid.includes('@');
  const el = document.createElement('div');
  el.className = 'probe';
  el.innerHTML =
    '<div class="probe-head"><span class="skill-id">' + p.skill_id
    + (p.symbol ? ' · ' + p.symbol : '') + '</span>'
    + (isSplit ? '<span class="badge composite" style="border-color:var(--blue-border);color:var(--blue)">focused</span>' : '')
    + '<span class="skill-loc">' + (p.loc || '') + '</span>'
    + '<span class="skill-loc" title="'
    + ((p.commits || []).join(', ')) + '">@' + (p.commit || '?')
    + ((p.commits || []).length > 1
       ? ' +' + ((p.commits || []).length - 1) : '')
    + '</span>'
    + ((p.findings_in || []).length
       ? '<span class="badge contested"'
         + (p.contested ? '' : ' style="color:var(--text-dim);border-color:var(--border);background:none"')
         + ' title="Unverified claims from other probes — click to view">'
         + (p.contested ? '⚑ contested' : '⚑ ' + p.findings_in.length)
         + '</span>'
       : '')
    + '<span class="verdict ' + (p.verdict || 'PENDING') + '">'
    + (p.verdict || 'PENDING') + '</span>'
    + (p.verdict && p.verdict !== 'PENDING'
       ? '<button class="probe-rerun" title="Re-run this probe">↻</button>' : '')
    + '</div>'
    + '<div class="probe-findings"></div>'
    + '<div class="probe-body"></div>'
    + '<div class="probe-evidence"><button class="ev-toggle">Evidence ▸</button>'
    + '<div class="ev-box"></div></div>';
  const pf = el.querySelector('.probe-findings');
  if ((p.findings_in || []).length) {
    pf.innerHTML = '<div class="f-src">Cross-slice claims (unverified — '
      + 'never evidence; ↻ reruns this probe with them as leads):</div>'
      + p.findings_in.map(f =>
        '<div class="f-row"><span class="f-sev">[' + (f.severity || '?')
        + ']</span> ' + (f.note || '')
        + ' <span class="f-src">— by ' + ((f.by || '?').slice(0, 12))
        + (f.model ? ' (' + f.model.split('/').pop() + ')' : '') + '</span></div>'
      ).join('');
  }
  el.querySelector('.probe-body').textContent =
    p.answer || (p.error ? '(no answer) ' + p.error : '');
  el.querySelector('.probe-head').onclick = () => {
    el.classList.toggle('open');
    if (el.classList.contains('open')) openProbes.add(pid);
    else openProbes.delete(pid);
  };
  const cb = el.querySelector('.badge.contested');
  if (cb) cb.onclick = (e) => {
    e.stopPropagation();
    pf.classList.toggle('open');
  };
  const rr = el.querySelector('.probe-rerun');
  if (rr) rr.onclick = async (e) => {
    e.stopPropagation();
    rr.disabled = true;
    const r = await fetch('/api/timeline/reports/' + currentReportId
      + '/probes/' + encodeURIComponent(pid) + '/rerun',
      { method: 'POST', headers: H });
    if (!r.ok) { alert((await r.json()).detail || 'Re-run failed'); rr.disabled = false; return; }
    await viewReport(currentReportId, probePage);   // shows PENDING, restarts polling
  };
  // Evidence panel: for a probe that has a verdict from a full run.
  const evWrap = el.querySelector('.probe-evidence');
  const evBtn = el.querySelector('.ev-toggle');
  const evBox = el.querySelector('.ev-box');
  const judged = p.verdict && p.verdict !== 'PENDING';
  if (judged) evWrap.classList.add('has');
  const lastRun = (p.history || []).slice(-1)[0] || {};
  const evKey = currentReportId + '|' + pid + '|' + (lastRun.ts || '');
  const setEv = open => {
    evBox.classList.toggle('open', open);
    evBtn.classList.toggle('on', open);
    evBtn.textContent = open ? 'Evidence ▾' : 'Evidence ▸';
    if (open) showEvidence(evBox, pid, evKey);
  };
  evBtn.onclick = (e) => {
    e.stopPropagation();
    const open = !evBox.classList.contains('open');
    if (open) openEvidence.add(pid); else openEvidence.delete(pid);
    setEv(open);
  };
  if (judged && openEvidence.has(pid)) setEv(true);

  if (openProbes.has(pid)) el.classList.add('open');
  return el;
}

async function loadReportList() {
  const r = await fetch('/api/timeline/reports', { headers: H });
  if (!r.ok) return;
  const d = await r.json();
  const sel = $('pastReports');
  sel.innerHTML = '<option value="">— past reports —</option>';
  for (const m of d.reports || []) {
    const o = document.createElement('option');
    o.value = m.report_id;
    o.textContent = (m.created_at || '').slice(0, 16).replace('T', ' ')
      + ' · ' + m.from_commit.slice(0, 8) + '→' + m.to_commit.slice(0, 8)
      + ' · ' + m.done + '/' + m.total
      + (+m.flagrant > 0 ? ' · ☠' + m.flagrant : '')
      + (m.suspicious > 0 ? ' · ⚠' + m.suspicious : '')
      + (+m.major_flaw > 0 ? ' · ◆' + m.major_flaw : '')
      + (m.status === 'interrupted' ? ' ⚠ interrupted'
         : m.status !== 'done' ? ' (' + m.status + ')' : '');
    sel.appendChild(o);
  }
}

async function viewReport(rid, page) {
  const seq = ++reportSeq;
  const vf = verdictParam();
  const typed = ($('commitFilter').value || '').trim().replace(/\\s+/g, ' ');
  const cf = typed || focusHash();          // typed filter wins over the focus knob
  const r = await fetch('/api/timeline/reports/' + rid + '?page=' + page
    + '&page_size=10' + (vf ? '&verdict=' + encodeURIComponent(vf) : '')
    + (cf ? '&commit=' + encodeURIComponent(cf) : ''),       // F5
    { headers: H });
  if (!r.ok) return;
  if (seq !== reportSeq) return;
  const d = await r.json();
  if (seq !== reportSeq) return;
  const isNewSelection = rid !== currentReportId;
  const fp = rid + '|' + vf + '|' + cf + '|' + d.page + '|' + d.meta.done + '|' + d.meta.status + '|'
    + d.probes.map(p => (p.probe_id || p.skill_id) + ':' + (p.verdict || '')).join(',');
  if (rid === currentReportId && fp === lastReportFingerprint) {
    if (d.meta.status === 'running') startPolling(rid);
    return d.meta.status !== 'running';
  }
  lastReportFingerprint = fp;
  currentReportId = rid; probePage = d.page;
  $('reportPanel').style.display = 'block';
  $('deleteReportBtn').style.display = '';
  let statusTxt = d.meta.status;
  if (d.meta.status === 'running' && d.meta.phase && d.meta.phase !== 'probes')
    statusTxt = 'running · ' + d.meta.phase;
  if (d.meta.status === 'interrupted') statusTxt = '⚠ interrupted';
  if (d.meta.status === 'stopped')     statusTxt = '⏸ stopped';
  $('reportStatusText').textContent = d.meta.from_commit.slice(0, 12) + ' → '
    + d.meta.to_commit.slice(0, 12) + ' · ' + d.meta.done + '/' + d.meta.total
    + ' probed · Jev $' + (+(d.meta.jev_cost_usd || 0)).toFixed(4) + ' · '
    + (d.meta.flagrant || 0) + ' flagrant · '   // F7
    + d.meta.suspicious + ' suspicious · '
    + (d.meta.major_flaw || 0) + ' major_flaw · ' + statusTxt;

  const ctl = $('reportCtl');
  if (d.meta.status === 'running') {
    ctl.style.display = ''; ctl.textContent = '⏸ stop';
    ctl.onclick = () => reportCtl(rid, 'stop');
  } else if (d.meta.status !== 'running'
             && (+d.meta.pending > 0 || +d.meta.errors > 0 || d.meta.phase !== 'done')) {
    ctl.style.display = ''; ctl.textContent = '▶ resume';
    ctl.onclick = () => reportCtl(rid, 'resume');
  } else {
    ctl.style.display = 'none';
  }

  if (isNewSelection) syncRangeToReport(d.meta);

  // ── F6b: verdict tallies into the filter row (NO dropdown block here) ──
  document.querySelectorAll('#verdictFilters .vcount').forEach(el => {
    const n = (d.verdict_counts || {})[el.dataset.v] || 0;
    el.textContent = n ? '(' + n + ')' : '';
  });

  // ── Commit-major grouping: one header per commit on this page; a probe
  // appears under EVERY commit it covers (merged probes show more than once,
  // labeled "shared"). ──
  $('probeList').innerHTML = '';
  const groups = new Map();               // commit12 → [probe, ...] page-local
  for (const p of d.probes) {
    const cs = (p.commits && p.commits.length) ? p.commits : [p.commit || '?'];
    for (const c of cs) {
      if (!groups.has(c)) groups.set(c, []);
      groups.get(c).push(p);
    }
  }
  for (const [c, plist] of groups) {
    const info = (d.commits || []).find(x => x.commit === c);
    const g = document.createElement('div');
    g.className = 'commit-group';
    if (info && info.worst) {
      const dot = document.createElement('span');
      dot.className = 'worst-dot ' + info.worst;
      dot.title = 'worst verdict in this commit: ' + info.worst;
      g.appendChild(dot);
    }
    const b = document.createElement('b');
    b.textContent = 'Commit ' + c;
    g.appendChild(b);
    if (info && info.goal) {
      const s = document.createElement('span');
      s.textContent = info.goal;
      g.appendChild(s);
    }
    const n = document.createElement('span');
    n.textContent = '(' + plist.length + ' probe(s) on this page)';
    g.appendChild(n);
    const rule = document.createElement('div');
    rule.className = 'rule';
    g.appendChild(rule);
    $('probeList').appendChild(g);
    for (const p of plist) {
      const el = probeEl(p);
      if ((p.commits || []).length > 1) {
        const chip = document.createElement('span');
        chip.className = 'skill-loc';
        chip.textContent = 'shared across ' + p.commits.length + ' commits';
        el.querySelector('.probe-head').insertBefore(
          chip, el.querySelector('.verdict'));
      }
      $('probeList').appendChild(el);
    }
  }
  if (!d.probes.length) {
    const e = document.createElement('div');
    e.className = 'empty';
    e.textContent = (vf || cf) ? 'No probes match the selected filters.' : 'No probes.';
    $('probeList').appendChild(e);
  }
  $('probePager').style.display = d.pages > 1 ? 'flex' : 'none';
  $('pInfo').textContent = 'page ' + d.page + ' / ' + d.pages
    + (d.filtered_total != null ? ' · ' + d.filtered_total + ' match' : '');
  $('pPrev').disabled = d.page <= 1;
  $('pNext').disabled = d.page >= d.pages;
  if (d.meta.status === 'running') startPolling(rid);
  return d.meta.status !== 'running';
}

async function reportCtl(rid, action) {
  const ctl = $('reportCtl');
  ctl.disabled = true;
  try {
    const r = await fetch('/api/timeline/reports/' + rid + '/' + action,
      { method: 'POST', headers: H });
    if (!r.ok) { alert((await r.json()).detail || action + ' failed'); return; }
    lastReportFingerprint = '';          // force a redraw on next fetch
    await viewReport(rid, probePage);
    loadReportList();
  } finally {
    ctl.disabled = false;
  }
}

function syncRangeToReport(meta) {
  if (!commits.length) return;
  const iFrom = commits.findIndex(c => c.hash === meta.from_commit);
  const iTo   = commits.findIndex(c => c.hash === meta.to_commit);
  if (iFrom < 0 || iTo < 0) return;      // range predates current index (re-ingest)
  A.value = Math.min(iFrom, iTo);
  B.value = Math.max(iFrom, iTo);
  renderRange();
  loadSkills(1);                          // direct — skip the debounce
}

$('pastReports').onchange = e => { if (e.target.value) viewReport(e.target.value, 1); };
$('deleteReportBtn').onclick = async () => {
  if (!currentReportId) return;
  if (!confirm('Delete report ' + currentReportId + ' permanently? This cannot be undone.')) return;
  const btn = $('deleteReportBtn');
  btn.disabled = true;
  try {
    const r = await fetch('/api/timeline/reports/' + currentReportId,
      { method: 'DELETE', headers: H });
    if (!r.ok) {
      let msg = 'Delete failed';
      try { msg = (await r.json()).detail || msg; } catch (_) {}
      alert(msg); return;
    }
    clearInterval(pollTimer); pollingId = null;
    currentReportId = null; lastReportFingerprint = '';
    $('reportPanel').style.display = 'none';
    btn.style.display = 'none';
    $('pastReports').value = '';
    loadReportList();
  } finally {
    btn.disabled = false;
  }
};
$('pPrev').onclick = () => viewReport(currentReportId, probePage - 1);
$('pNext').onclick = () => viewReport(currentReportId, probePage + 1);

async function resumeRunning() {
  const r = await fetch('/api/timeline/reports?limit=5', { headers: H });
  if (!r.ok) return;
  const d = await r.json();
  const running = (d.reports || []).find(m => m.status === 'running');
  if (running) viewReport(running.report_id, 1);
}

// ── Ingestion in progress (python next_claude.py …) ─────────────────────
// Shown while a run is going or just finished; the commit list reloads
// when the run ends so the new commits appear.
let ingestWasRunning = false;
async function pollIngest() {
  let d;
  try { d = await (await fetch('/api/ingest/status')).json(); } catch (e) { return; }
  const ing = d.ingest || {}, embeds = d.embed || {};
  const strip = $('ingestStrip');
  if (ing.status === 'running' && !ing.alive) ing.status = 'interrupted';
  for (const e of Object.values(embeds))
    if ((e.status === 'running' || e.status === 'waiting') && !e.alive) e.status = 'interrupted';
  const running = ing.status === 'running'
    || Object.values(embeds).some(e => e.status === 'running' || e.status === 'waiting');
  const recent = ing.finished_at && (Date.now() / 1000 - +ing.finished_at) < 600;
  if (!running && !recent && ing.status !== 'interrupted') { strip.style.display = 'none'; return; }
  const total = +ing.total || 0, done = +ing.done || 0;
  const pct = total ? Math.round(100 * done / total) : 0;
  const parts = [];
  parts.push(`<span>${ing.status === 'running' ? 'Ingesting' : ing.status === 'interrupted' ? 'Ingest interrupted:' : 'Ingested'} <b>${esc(ing.repo || '')}</b></span>`);
  parts.push(`<span><b>${done}</b> / ${total} commits${+ing.failed ? ` · <b>${ing.failed}</b> failed` : ''}</span>`);
  if (ing.current_commit) parts.push(`<span>${esc(String(ing.current_commit).slice(0, 12))}</span>`);
  parts.push(`<span class="bar"><i style="width:${pct}%"></i></span>`);
  for (const [name, e] of Object.entries(embeds)) {
    const n = e.status === 'running' ? ` ${e.done || 0}/${e.total || 0} skills` : '';
    parts.push(`<span>embedding [${esc(name)}]: <b>${esc(e.status || '—')}</b>${n}</span>`);
  }
  if (ing.last_error) parts.push(`<span style="color:var(--red)">${esc(ing.last_error)}</span>`);
  if (ing.status === 'interrupted') parts.push(`<span>continue with <code>python next_claude.py /repo --resume</code></span>`);
  strip.innerHTML = parts.join('');
  strip.className = (ing.status === 'failed' || ing.status === 'interrupted') ? 'failed' : '';
  strip.style.display = 'flex';
  if (ingestWasRunning && !running) loadCommits();   // the run just ended
  ingestWasRunning = running;
}
pollIngest();
setInterval(pollIngest, 3000);

loadCommits();
loadReportList();
resumeRunning();
</script>
</body>
</html>"""