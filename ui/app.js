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
const val = (a, k, d) => a[k] === undefined ? d : a[k];  // Get value with default fallback
const template = name => document.getElementById(`tpl-${name}`).content.cloneNode(true);

// Game / sim helpers
const normSim = v => { v = (v || '').trim(); return !v ? '' : /\.exe$/i.test(v) ? v : v + '.exe'; };  // Add .exe if missing
const say = t => { $('#status').textContent = t; };  // Update status message
const updateUnsaved = () => { $('#ft').classList.toggle('unsaved', unsaved); $('#save').disabled = !unsaved; };
const touch = () => { unsaved = true; say('Unsaved changes'); updateUnsaved(); };  // Mark as modified
const simLabel = s => !s ? '' : /2024/.test(s) ? 'MSFS 2024' : /^FlightSimulator\.exe$/i.test(s) ? 'MSFS 2020' : s.replace(/\.exe$/i, '');  // Display name for a game

// Logging functions
// The log is a rolling window (last 50 lines). Instead of rebuilding the whole list every
// second (which resets the scroll position), we only drop lines that scrolled out of the
// window and append the new ones. Auto-follow only happens while you are at the bottom.
let logKeys = [];          // keys of the lines currently shown
let logPinned = true;      // true while the view is scrolled to the bottom
const logKey = l => (l.date || '') + ' ' + l.time + '|' + l.msg;
const logNode = l => {
  const entry = template('log-entry').firstElementChild;
  entry.querySelector('.log-date').textContent = l.date || '';
  entry.querySelector('.log-time').textContent = l.time || '';
  entry.querySelector('.log-msg').textContent = l.msg || '';
  return entry;
};

const logBox = $('#logscontent');
logBox.style.overflowAnchor = 'none';   // we compensate manually below
logBox.addEventListener('scroll', () => {
  logPinned = logBox.scrollHeight - logBox.scrollTop - logBox.clientHeight <= 10;
});

const renderLogs = async () => {
  const logs = await pywebview.api.get_launcher_logs(50);
  const keys = logs.map(logKey);

  // Find how many old lines dropped off the top: the shown lines (minus `drop`)
  // must match the start of the new list.
  let drop = logKeys.length, overlap = 0;
  for (let k = 0; k <= logKeys.length; k++) {
    const n = logKeys.length - k;
    if (n > keys.length) continue;
    let same = true;
    for (let j = 0; j < n; j++) if (logKeys[k + j] !== keys[j]) { same = false; break; }
    if (same) { drop = k; overlap = n; break; }
  }

  if (drop === 0 && overlap === keys.length) return;   // nothing new, leave the view alone

  // Keep the lines you are reading in place when old lines are removed above them
  const anchor = !logPinned && drop > 0 ? logBox.children[drop] : null;
  const before = anchor ? anchor.getBoundingClientRect().top : 0;
  for (let i = 0; i < drop; i++) logBox.firstElementChild.remove();
  if (anchor) logBox.scrollTop -= before - anchor.getBoundingClientRect().top;

  for (const log of logs.slice(overlap)) logBox.append(logNode(log));
  logKeys = keys;

  if (logPinned) logBox.scrollTop = logBox.scrollHeight;   // only follow if already at the bottom
};

// Get the current profile
const profile = () => cfg.profiles[curGame] || null;

const showTemplate = (target, name) => {
  target.replaceChildren(template(name));
};

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
  const startText = a.start === 'session'
    ? `After flight ready${d ? ' +' + d + ' s' : ''}`
    : d ? `After ${d} s` : 'With Sim';
  const start = template('chip').firstElementChild;
  start.classList.add('a');
  start.textContent = startText;
  const result = document.createDocumentFragment();
  result.append(start);
  if (val(a, 'closeOnExit', true)) {
    const close = template('chip').firstElementChild;
    close.textContent = 'Closes on exit';
    result.append(close);
  }
  return result;
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
  
  if (picking) {
    const picker = template('game-picker');
    const options = picker.querySelector('.game-options');
    for (const [name, exe, tile] of GAMES) {
      const option = template('game-option').firstElementChild;
      option.dataset.game = exe;
      option.querySelector('.tile').textContent = tile;
      option.querySelector('.nm b').textContent = name;
      option.querySelector('.nm span').textContent = exe;
      options.append(option);
    }
    $('#list').replaceChildren(picker);
    return;
  }
  
  if (!has) {
    showTemplate($('#list'), 'no-game');
    return;
  }
  
  $('#gname').textContent = label;
  $('#gcount').textContent = n;
  $('#count').textContent = n + ' app' + (n === 1 ? '' : 's') + ' \u00b7 launch order';
  if (!n) {
    showTemplate($('#list'), 'no-apps');
    return;
  }

  const cards = document.createDocumentFragment();
  prof.apps.forEach((a, i) => {
    const card = template('app-card').firstElementChild;
    const enabled = val(a, 'enabled', true);
    card.dataset.i = i;
    card.draggable = enabled;
    card.classList.toggle('sel', i === sel);
    card.classList.toggle('off', !enabled);
    card.classList.toggle('invalid', !pathValidity[a.path]);
    card.querySelector('.tile').textContent = (a.name || '?')[0].toUpperCase();
    card.querySelector('.nm b').textContent = a.name || '';
    const path = card.querySelector('.nm span');
    path.textContent = a.path || '';
    path.title = a.path || '';
    card.querySelector('.chips').append(chips(a));
    const enabledToggle = card.querySelector('.tog');
    enabledToggle.classList.toggle('on', enabled);
    enabledToggle.dataset.en = i;
    enabledToggle.setAttribute('aria-pressed', String(enabled));
    cards.append(card);
  });
  $('#list').replaceChildren(cards);
}

// Render the detail panel on the right (shows/edits selected app)
function renderDetail() {
  const prof = profile();
  if (!curGame || !prof) { showTemplate($('#det'), 'detail-empty'); return; }
  const a = prof.apps[sel];
  if (!a) { showTemplate($('#det'), 'select-empty'); return; }
  const session = a.start === 'session', d = val(a, 'delay', 0), wnd = val(a, 'window', 'minimized');
  const detail = template('app-detail');
  const name = a.name || '';
  const nameTile = detail.querySelector('.dh .tile');
  nameTile.textContent = (name || '?')[0].toUpperCase();
  const nameInput = detail.querySelector('#f-name');
  nameInput.value = name;
  const path = detail.querySelector('.path');
  path.textContent = a.path || '';
  path.title = a.path || '';

  detail.querySelector('[data-v="sim"]').classList.toggle('on', !session);
  detail.querySelector('[data-v="session"]').classList.toggle('on', session);
  detail.querySelector('[data-field="start-hint"]').textContent = session
    ? 'Starts once a flight has loaded and you are in the aircraft.'
    : 'Starts as soon as the sim is running.';
  detail.querySelector('#f-delay').value = d;
  detail.querySelector('[data-field="delay-hint"]').textContent = session
    ? 'Counted from when the flight is ready.'
    : 'Counted from when the sim starts, not from the previous app.';
  const closeToggle = detail.querySelector('[data-flag="closeOnExit"]');
  const closeOnExit = val(a, 'closeOnExit', true);
  closeToggle.classList.toggle('on', closeOnExit);
  closeToggle.setAttribute('aria-pressed', String(closeOnExit));
  const minimizedToggle = detail.querySelector('[data-flag="minimized"]');
  const minimized = wnd !== 'normal' && wnd !== 'maximized';
  minimizedToggle.classList.toggle('on', minimized);
  minimizedToggle.setAttribute('aria-pressed', String(minimized));
  detail.querySelector('#f-args').value = (a.args || []).join(' ');
  $('#det').replaceChildren(detail);
}

/* ===== EVENT HANDLERS ===== */
// Handle clicks on buttons and cards
document.addEventListener('click', async e => {
  const t = e.target.closest('button, .card'); if (!t || !cfg) return;
  const prof = profile();
  const a = prof ? prof.apps[sel] : null;
  
  // Toggle app enabled/disabled - check this BEFORE checking for card clicks
  if (t.classList.contains('tog') && t.dataset.en !== undefined) {
    e.stopPropagation();
    const apps = prof;
    const x = prof.apps[+t.dataset.en];
    if (!x) return;
    const selected = prof.apps[sel];            // remember which app is selected
    x.enabled = !val(x, 'enabled', true);

    // Keep enabled apps on top, disabled apps at the bottom.
    prof.apps.splice(+t.dataset.en, 1);         // take the app out of the list
    if (x.enabled) {
      // Re-enabled: goes right after the last enabled app
      let last = -1;
      prof.apps.forEach((app, i) => { if (val(app, 'enabled', true)) last = i; });
      prof.apps.splice(last + 1, 0, x);
    } else {
      prof.apps.push(x);                        // Disabled: goes to the very bottom
    }
    sel = prof.apps.indexOf(selected);          // selection follows the app, not the row

    touch();
    await render();
    return;
  }
  
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
  
  // Toggle behavior flags
  if (t.dataset.flag) {
    if (t.dataset.flag === 'minimized') {
      a.window = val(a, 'window', 'minimized') === 'minimized' ? 'normal' : 'minimized';
    } else {
      a[t.dataset.flag] = !val(a, t.dataset.flag, true);
    }
    touch(); await render(); return;
  }
  // Segmented control buttons (start type, window mode)
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
      say('Saved! Changes apply the next time the sim starts.'); 
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
  if (c.classList.contains('off')) { e.preventDefault(); return; }   // disabled apps are locked
  dragFrom = +c.dataset.i; e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', String(dragFrom));
  c.classList.add('drag');
});

// Drag over a card
document.addEventListener('dragover', e => {
  const c = e.target.closest('.card'); if (!c || dragFrom < 0) return;
  document.querySelectorAll('.card.over').forEach(x => x.classList.remove('over'));
  if (c.classList.contains('off')) return;   // can't drop onto the disabled section
  e.preventDefault();
  c.classList.add('over');
});

// Drop to reorder
document.addEventListener('drop', async e => {
  const c = e.target.closest('.card'); if (!c || dragFrom < 0) return;
  if (c.classList.contains('off')) return;   // can't drop onto the disabled section
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