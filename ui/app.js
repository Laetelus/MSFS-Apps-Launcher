/* ===== JAVASCRIPT - DATA & UTILITIES ===== */
// Application state variables
let cfg = null,           // Full config object with all profiles
    curGame = "",         // Currently selected game executable name
    sel = -1,             // Currently selected app index in the current profile
    dragFrom = -1,        // Track drag-and-drop source index
    picking = false,      // True while the "choose your game" list is showing
    unsaved = false,      // True when there are unsaved changes
    pathValidity = {};    // Cache of path validity checks {path: true/false}

// Helper functions
const $ = s => document.querySelector(s);  // Shorthand for querySelector
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));  // Escape HTML special chars
const val = (a, k, d) => a[k] === undefined ? d : a[k];  // Get value with default fallback

// Game / sim helpers
const normSim = v => { v = (v || '').trim(); return !v ? '' : /\.exe$/i.test(v) ? v : v + '.exe'; };  // Add .exe if missing
const say = t => { $('#status').textContent = t; };  // Update status message
const updateUnsaved = () => { $('#ft').classList.toggle('unsaved', unsaved); $('#save').disabled = !unsaved; };
const touch = () => { unsaved = true; say('Unsaved changes'); updateUnsaved(); };  // Mark as modified
const simLabel = s => !s ? '' : /2024/.test(s) ? 'MSFS 2024' : /^FlightSimulator\.exe$/i.test(s) ? 'MSFS 2020' : s.replace(/\.exe$/i, '');  // Display name for a game

// Logging functions
const renderLogs = async () => {
  const logs = await pywebview.api.get_launcher_logs(50);
  const content = $('#logscontent');
  
  // Check if we're at the bottom before updating
  const wasAtBottom = content.scrollHeight - content.scrollTop <= content.clientHeight + 10;
  
  content.innerHTML = logs.map(log => `
    <div class="log-entry info">
      <span class="log-time">${esc(log.time)}</span>
      <span class="log-msg">${esc(log.msg)}</span>
    </div>`).join('');
  
  // Only auto-scroll if we were already at the bottom
  if (wasAtBottom) {
    content.scrollTop = content.scrollHeight;
  }
};

// Get the current profile
const profile = () => cfg.profiles[curGame] || null;
const GRIP = '<svg width="14" height="18" viewBox="0 0 14 18" fill="currentColor" aria-hidden="true"><circle cx="4" cy="4" r="1.5"/><circle cx="10" cy="4" r="1.5"/><circle cx="4" cy="9" r="1.5"/><circle cx="10" cy="9" r="1.5"/><circle cx="4" cy="14" r="1.5"/><circle cx="10" cy="14" r="1.5"/></svg>';  // SVG for drag handle

// Check if all app paths exist
async function checkAllPaths() {
  const prof = profile();
  if (!prof || !prof.apps) return;
  
  for (const app of prof.apps) {
    if (app.path && !(app.path in pathValidity)) {
      pathValidity[app.path] = await pywebview.api.check_path_exists(app.path);
    }
  }
}

/* ===== INITIALIZATION ===== */
// When page loads and connects to Python backend
window.addEventListener('pywebviewready', async () => {
  cfg = await pywebview.api.get_config();  // Load full config with all profiles
  // Restore the last selected game, or pick the first one
  const games = Object.keys(cfg.profiles || {});
  curGame = cfg.lastGame && games.includes(cfg.lastGame) ? cfg.lastGame : games[0] || '';
  if (curGame && profile()) {
    sel = profile().apps.length ? 0 : -1;
  } else {
    sel = -1;
  }
  await checkAllPaths();  // Check all paths for validity
  await renderLogs();  // Load initial logs
  
  // Refresh logs every 1 second
  setInterval(renderLogs, 1000);
  
  render();  // Display everything
});

// Logs panel toggle
document.addEventListener('click', e => {
  if (e.target.id === 'logstoggle') {
    const panel = $('#logspanel');
    const isCollapsed = panel.classList.toggle('collapsed');
    e.target.textContent = isCollapsed ? '+' : '−';
  }
});

/* ===== RENDERING FUNCTIONS ===== */
// Create chip tags showing app properties (start time, window state, etc.)
function chips(a) {
  const d = val(a, 'delay', 0);
  const start = a.start === 'session'
    ? `<span class="chip a">After flight ready${d ? ' +' + d + ' s' : ''}</span>`
    : `<span class="chip a">${d ? 'After ' + d + ' s' : 'With sim'}</span>`;
  return start + (val(a, 'closeOnExit', true) ? '<span class="chip">Closes on exit</span>' : '');
}

// Main render function - update both list and detail panel
async function render() { 
  await checkAllPaths();
  renderList();
  renderDetail();
}

// "Choose your game" list. Known games need no file picker (Windows blocks selecting
// the exe inside Xbox / Game Pass install folders), so their process names are built in.
const GAMES = [['MSFS 2024', 'FlightSimulator2024.exe', '24'], ['MSFS 2020', 'FlightSimulator.exe', '20']];
const pickerHtml = () => `
  <div class="lbl">Choose your game</div>
  ${GAMES.map(([n, e, t]) => `<div class="card" data-game="${e}"><div class="tile">${t}</div><div class="nm"><b>${n}</b><span>${e}</span></div></div>`).join('')}
  <div><button class="sec" data-act="gamecancel">Cancel</button></div>`;

// Render the app list (left/center area)
function renderList() {
  const prof = profile();
  const has = !!curGame && prof;
  const n = prof ? prof.apps.length : 0;
  const label = simLabel(curGame);
  
  // Without a game, hide everything that depends on one and show the empty state
  for (const id of ['#game', '#watch', '#add', '#count']) $(id).hidden = !has;
  $('#addgame').textContent = curGame ? 'Change game' : '+ Add game';
  $('#title').textContent = has ? label : 'No game yet';
  $('#sim').textContent = curGame || 'game.exe';  // Display current game executable
  
  if (picking) { $('#list').innerHTML = pickerHtml(); return; }
  
  if (!has) {
    $('#list').innerHTML = '<div class="empty">Add the game you fly (for example MSFS 2024), so the launcher knows which program to watch for.<br><br><button class="pri" data-act="addgame">+ Add game</button></div>';
    return;
  }
  
  $('#gname').textContent = label;
  $('#gcount').textContent = n;
  $('#count').textContent = n + ' app' + (n === 1 ? '' : 's') + ' \u00b7 launch order';
  $('#list').innerHTML = n ? prof.apps.map((a, i) => {
    const isInvalid = !pathValidity[a.path];
    return `
    <div class="card ${i === sel ? 'sel' : ''} ${val(a, 'enabled', true) ? '' : 'off'} ${isInvalid ? 'invalid' : ''}" data-i="${i}" draggable="true">
      <span class="grip" title="Drag to reorder">${GRIP}</span>
      <div class="tile">${esc((a.name || '?')[0].toUpperCase())}</div>
      <div class="nm"><b>${esc(a.name)}</b><span title="${esc(a.path)}">${esc(a.path)}</span></div>
      <div class="chips">${chips(a)}</div>
      <button class="tog ${val(a, 'enabled', true) ? 'on' : ''}" data-en="${i}" aria-label="Enabled" aria-pressed="${val(a, 'enabled', true)}"><i></i></button>
    </div>`;
  }).join('') : '<div class="empty">No apps yet. Click "Add app" to pick one.</div>';
}

// Helper to create segmented control buttons
const seg = (key, opts, cur) => `<div class="seg">${opts.map(([v, t]) => `<button data-set="${key}" data-v="${v}" class="${cur === v ? 'on' : ''}">${t}</button>`).join('')}</div>`;
// Helper to create toggle switch
const toggle = (key, label, on) => `<div class="opt">${label}<button class="tog ${on ? 'on' : ''}" data-flag="${key}" aria-label="${label}" aria-pressed="${on}"><i></i></button></div>`;

// Render the detail panel on the right (shows/edits selected app)
function renderDetail() {
  const prof = profile();
  if (!curGame || !prof) { $('#det').innerHTML = '<div class="empty">Add a game first, then add the apps you want to launch with it.</div>'; return; }
  const a = prof.apps[sel];
  if (!a) { $('#det').innerHTML = '<div class="empty">Select an app to edit it.</div>'; return; }
  const session = a.start === 'session', d = val(a, 'delay', 0);
  $('#det').innerHTML = `
    <div class="dh"><div class="tile">${esc((a.name || '?')[0].toUpperCase())}</div>
      <div class="dt"><input class="title-in" id="f-name" value="${esc(a.name)}" aria-label="Name" spellcheck="false">
        <span class="path" title="${esc(a.path)}">${esc(a.path)}</span></div></div>
    <div class="fl"><span class="lbl">Start</span>
      ${seg('start', [['sim', 'With sim'], ['session', 'Flight ready']], session ? 'session' : 'sim')}
      <span class="hint">${session ? 'Starts once a flight has loaded and you are in the aircraft.' : 'Starts as soon as the sim is running.'}</span></div>
    <div class="fl"><label class="lbl" for="f-delay">Delay (seconds)</label>
      <div class="dl"><input class="num" id="f-delay" type="number" min="0" value="${d}"><div class="spins"><button type="button" data-spin="up">▲</button><button type="button" data-spin="down">▼</button></div></div>
      <span class="hint">${session ? 'Counted from when the flight is ready.' : 'Counted from when the sim starts, not from the previous app.'}</span></div>
    <div class="fl"><span class="lbl">Behavior</span>
      ${toggle('closeOnExit', 'Close when sim exits', val(a, 'closeOnExit', true))}
    <div class="fl"><label class="lbl" for="f-args">Launch arguments</label>
      <input class="inp" id="f-args" placeholder="Optional" value="${esc((a.args || []).join(' '))}" spellcheck="false"></div>
    <div class="row" style="margin-top:auto"><button class="sec dng" id="remove" style="flex:1">Remove</button></div>`;
}

/* ===== EVENT HANDLERS ===== */
// Handle clicks on buttons and cards
document.addEventListener('click', async e => {
  const t = e.target.closest('button, .card'); if (!t || !cfg) return;
  const prof = profile();
  const a = prof ? prof.apps[sel] : null;
  
  // Add or change the game
  if (t.dataset.act === 'addgame') { picking = true; await render(); return; }
  if (t.dataset.act === 'gamecancel') { picking = false; await render(); return; }
  if (t.dataset.game || t.dataset.act === 'gamebrowse') {
    let exe = t.dataset.game;
    if (!exe) { const p = await pywebview.api.browse_exe(); if (!p) return; exe = p.split(/[\\/]/).pop(); }
    exe = normSim(exe);
    
    // Create a new profile for this game if it doesn't exist
    if (!cfg.profiles) cfg.profiles = {};
    if (!cfg.profiles[exe]) {
      cfg.profiles[exe] = { apps: [] };
    }
    
    curGame = exe;
    cfg.lastGame = exe;
    sel = cfg.profiles[exe].apps.length ? 0 : -1;
    picking = false;
    touch();
    await render();
    return;
  }
  
  if (!prof) return;  // Need a profile for the rest
  
  // Toggle app enabled/disabled
  if (t.dataset.en !== undefined) { 
    const x = prof.apps[+t.dataset.en];
    const newState = !val(x, 'enabled', true);
    x.enabled = newState;
    touch(); 
    await render(); 
    return; 
  }
  // Toggle behavior flags
  if (t.dataset.flag) { a[t.dataset.flag] = !val(a, t.dataset.flag, true); touch(); await render(); return; }
  // Segmented control buttons (start type)
  if (t.dataset.set) {
    if (t.dataset.set === 'start') { if (t.dataset.v === 'session') a.start = 'session'; else delete a.start; }
    touch(); await render(); return;
  }
  // Click on app card to select it
  if (t.dataset.i !== undefined) { sel = +t.dataset.i; await render(); return; }
  // Add new app button
  if (t.id === 'add') {
    const p = await pywebview.api.browse_exe(); if (!p) return;
    if (prof.apps.some(app => app.path === p)) { 
      say('This app is already in the list'); 
      return; 
    }
    const appName = p.split(/[\\/]/).pop().replace(/\.exe$/i, '');
    prof.apps.push({ name: appName, path: p, delay: 0, closeOnExit: true });
    sel = prof.apps.length - 1; 
    touch(); 
    await render(); 
    return;
  }
  // Remove button - delete app
  if (t.id === 'remove') { 
    prof.apps.splice(sel, 1); 
    sel = Math.min(sel, prof.apps.length - 1); 
    touch(); 
    await render(); 
    return; 
  }
  // Save button - write config to file
  if (t.id === 'save') {
    if (!curGame) { say('Add a game first.'); return; }
    const r = await pywebview.api.save_config(cfg);
    if (r.ok) { 
      unsaved = false; 
      updateUnsaved(); 
      say('Saved. Changes apply the next time the sim starts.'); 
    } else {
      say('Not saved: ' + r.error);
    }
  }
});

// Handle text input changes
document.addEventListener('input', async e => {
  if (!cfg) return;
  const prof = profile();
  if (!prof) return;
  
  const id = e.target.id, a = prof.apps[sel], v = e.target.value;
  
  if (!a) return;
  
  // App name
  if (id === 'f-name') a.name = v;
  // Launch arguments
  else if (id === 'f-args') { const parts = v.trim().split(/\s+/).filter(Boolean); if (parts.length) a.args = parts; else delete a.args; }
  // Delay value
  else if (id === 'f-delay' || id === 'f-range') {
    a.delay = Math.max(0, parseInt(v, 10) || 0);
    if (id === 'f-range') $('#f-delay').value = a.delay; else $('#f-range').value = Math.min(a.delay, 300);
  } else return;
  
  touch(); await renderList();   // list only, so the field keeps focus
});

// Handle spinner buttons
document.addEventListener('click', async e => {
  if (e.target.closest('[data-spin]')) {
    e.preventDefault(); e.stopPropagation();
    const btn = e.target.closest('[data-spin]'), inp = $('#f-delay'), prof = profile(), a = prof ? prof.apps[sel] : null;
    if (!inp || !a) return;
    const delta = btn.dataset.spin === 'up' ? 1 : -1;
    inp.value = Math.max(0, parseInt(inp.value, 10) + delta);
    a.delay = Math.max(0, parseInt(inp.value, 10));
    touch(); await renderList();
  }
}, true);

/* ===== DRAG AND DROP HANDLERS ===== */
// Start dragging an app card
document.addEventListener('dragstart', e => {
  const c = e.target.closest('.card'); if (!c) return;
  dragFrom = +c.dataset.i; e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', String(dragFrom));
  c.classList.add('drag');
});

// Drag over a card
document.addEventListener('dragover', e => {
  const c = e.target.closest('.card'); if (!c || dragFrom < 0) return;
  e.preventDefault();
  document.querySelectorAll('.card.over').forEach(x => x.classList.remove('over'));
  c.classList.add('over');
});

// Drop to reorder
document.addEventListener('drop', async e => {
  const c = e.target.closest('.card'); if (!c || dragFrom < 0) return;
  e.preventDefault();
  const to = +c.dataset.i;
  const prof = profile();
  if (to !== dragFrom && prof) {
    const cur = prof.apps[sel], [m] = prof.apps.splice(dragFrom, 1);
    prof.apps.splice(to, 0, m); sel = prof.apps.indexOf(cur); touch();
  }
});

// End drag
document.addEventListener('dragend', async () => { dragFrom = -1; if (cfg) await render(); });
