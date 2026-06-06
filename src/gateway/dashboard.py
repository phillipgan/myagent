"""Web Dashboard — Built-in SPA Management Interface

Provides browser-based Agent status, tools, skills, scheduler status,
and WebSocket real-time chat functionality.

Embedded as HTML string in source code, served via GET /.
Frontend uses vanilla HTML/CSS/JS, no external dependencies.
"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MyAgent Dashboard</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, sans-serif; background: #f0f2f5; color: #333; }
  .header { background: linear-gradient(135deg, #1a73e8, #34a853); color: #fff; padding: 20px 30px; }
  .header h1 { font-size: 1.5em; }
  .header .sub { opacity: 0.8; font-size: 0.9em; }
  .container { max-width: 1200px; margin: 20px auto; padding: 0 20px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
  .card { background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  .card h3 { color: #1a73e8; margin-bottom: 12px; }
  .stat { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #eee; }
  .stat:last-child { border: none; }
  .stat .value { font-weight: 600; color: #1a73e8; }
  .skill-list { max-height: 300px; overflow-y: auto; }
  .skill-item { padding: 4px 0; font-size: 0.9em; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 0.75em; font-weight: 600; }
  .badge-green { background: #e6f4ea; color: #137333; }
  .badge-blue { background: #e8f0fe; color: #1967d2; }
  .chat-box { margin-top: 16px; }
  .chat-box input { width: 100%; padding: 12px; border: 2px solid #e0e0e0; border-radius: 8px; font-size: 1em; }
  .chat-box input:focus { outline: none; border-color: #1a73e8; }
  .messages { max-height: 400px; overflow-y: auto; margin-top: 12px; }
  .msg { padding: 8px 12px; margin: 4px 0; border-radius: 8px; max-width: 80%; }
  .msg-user { background: #e8f0fe; margin-left: auto; }
  .msg-agent { background: #f1f3f4; }
  .msg small { color: #999; }
  #ws-status { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
  .connected { background: #34a853; }
  .disconnected { background: #ea4335; }
</style>
</head>
<body>
<div class="header">
  <h1>🤖 MyAgent Dashboard</h1>
  <div class="sub"><span id="ws-status" class="disconnected"></span>Personal Office Assistant | <span id="status-text">Connecting...</span></div>
</div>
<div class="container">
  <div class="grid">
    <div class="card">
      <h3>📊 Agent Status</h3>
      <div id="agent-status">Loading...</div>
    </div>
    <div class="card">
      <h3>🔧 Tools</h3>
      <div id="tools-list">Loading...</div>
    </div>
    <div class="card">
      <h3>⏰ Scheduler</h3>
      <div id="scheduler-status">Not started</div>
    </div>
    <div class="card">
      <h3>📦 Skills (<span id="skill-count">0</span>)</h3>
      <div id="skill-list" class="skill-list">Loading...</div>
    </div>
  </div>
  <div class="card chat-box">
    <h3>💬 Chat</h3>
    <input type="text" id="msg-input" placeholder="Type a message..." onkeypress="if(event.key==='Enter')sendMsg()">
    <div class="messages" id="messages"></div>
  </div>
</div>
<script>
const ws = new WebSocket(`ws://${location.host}/ws`);
ws.onopen = () => {
  document.getElementById('ws-status').className = 'connected';
  document.getElementById('status-text').textContent = 'Connected';
};
ws.onclose = () => {
  document.getElementById('ws-status').className = 'disconnected';
  document.getElementById('status-text').textContent = 'Disconnected';
};
ws.onmessage = (e) => {
  const data = JSON.parse(e.data);
  if (data.type === 'text') {
    addMsg('agent', data.content);
  } else if (data.type === 'tool_start') {
    addMsg('agent', `🔧 ${data.name}(${JSON.stringify(data.args).slice(0,60)}...)`, true);
  }
};
function sendMsg() {
  const input = document.getElementById('msg-input');
  const text = input.value.trim();
  if (!text) return;
  addMsg('user', text);
  ws.send(JSON.stringify({message: text}));
  input.value = '';
}
function addMsg(role, text, dim=false) {
  const div = document.createElement('div');
  div.className = `msg msg-${role}`;
  if (dim) {
      const small = document.createElement('small');
      small.textContent = text;
      div.appendChild(small);
    } else {
      div.textContent = text;
    }
  document.getElementById('messages').appendChild(div);
  div.scrollIntoView();
}
// Load status
fetch('/api/status').then(r=>r.json()).then(data => {
  const esc = s => (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  document.getElementById('agent-status').innerHTML = `
    <div class="stat"><span>Name</span><span class="value">${esc(data.name)}</span></div>
    <div class="stat"><span>Skills</span><span class="value">${data.skills_count}</span></div>
    <div class="stat"><span>Model</span><span class="value">${esc(data.model_default)}</span></div>
    <div class="stat"><span>User</span><span class="value">${esc(data.memory?.user_name)}</span></div>
  `;
  document.getElementById('tools-list').innerHTML = data.tools.map(t =>
    `<span class="badge badge-blue">${esc(t)}</span> `
  ).join('');
  document.getElementById('skill-count').textContent = data.skills_count;
  document.getElementById('skill-list').innerHTML = data.skills.slice(0,30).map(s =>
    `<div class="skill-item">${esc('• ' + s)}</div>`
  ).join('') + (data.skills_count > 30 ? `<div class="skill-item" style="color:#999">${esc('...+' + (data.skills_count-30) + ' more')}</div>` : '');
});
</script>
</body>
</html>"""
