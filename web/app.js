// The Curved World -- web view & interaction layer (Task 6 + Task 7).
//
// The Python kernel is authoritative (world generation, analytic geometry,
// curvature, detector decay, information boundary). This file renders the two
// views and forwards player input. It never asks for the hidden exit and only
// calls the privileged debug endpoint when the god view is opened.

const el = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const FOG_COLS = 100;
const FOG_ROWS = 100;
const FOG_RADIUS = 12;
const WARP_GAIN = 0.35;
const TWO_PI = Math.PI * 2;

// Periodic wrap for a parameter value (closed manifolds).
function wrapParameter(value) {
  return ((value + Math.PI) % TWO_PI + TWO_PI) % TWO_PI - Math.PI;
}

// Representative of `value` closest to `reference` (universal-cover trail).
function unwrapNear(value, reference) {
  let result = value;
  while (result - reference > Math.PI) result -= TWO_PI;
  while (result - reference < -Math.PI) result += TWO_PI;
  return result;
}

const state = {
  player: null,
  domain: null,
  fog: null,
  selection: [],
  godVisible: false,
  debugState: null,
  yaw: 0.85,
  pitch: 0.55,
  drag: null,
  pointerHint: null,
  heldKeys: new Set(),
  walking: false,
  stepMultiplier: 1,
  maps: [],
};

const DIRECTIONS = {
  w: [0, 1], s: [0, -1], a: [-1, 0], d: [1, 0],
  arrowup: [0, 1], arrowdown: [0, -1], arrowleft: [-1, 0], arrowright: [1, 0],
};

// ---------------------------------------------------------------- API ----

async function apiGet(path) {
  const response = await fetch(path, { cache: 'no-store' });
  const data = await response.json().catch(() => ({ error: response.statusText }));
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

async function apiPost(path, body) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  const data = await response.json().catch(() => ({ error: response.statusText }));
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

// ------------------------------------------------- fog of war (client) ----

function ensureFog(domain) {
  if (state.fog && state.domain
      && state.domain.x_min === domain.x_min && state.domain.x_max === domain.x_max
      && state.domain.y_min === domain.y_min && state.domain.y_max === domain.y_max) return;
  state.domain = domain;
  state.fog = { cells: new Uint8Array(FOG_COLS * FOG_ROWS) };
}

function domainContains(domain, x, y) {
  return x >= domain.x_min && x <= domain.x_max && y >= domain.y_min && y <= domain.y_max;
}

function cellOf(domain, x, y) {
  // On a closed manifold the fog bitmap itself is periodic, so the parameter is
  // wrapped before indexing: crossing the seam never tears the fog.
  const u = state.periodic ? wrapParameter(x) : x;
  const v = state.periodic ? wrapParameter(y) : y;
  const ix = Math.floor((u - domain.x_min) / (domain.x_max - domain.x_min) * FOG_COLS);
  const iy = Math.floor((v - domain.y_min) / (domain.y_max - domain.y_min) * FOG_ROWS);
  return [
    Math.min(FOG_COLS - 1, Math.max(0, ix)),
    Math.min(FOG_ROWS - 1, Math.max(0, iy)),
  ];
}

function explore(domain, x, y) {
  ensureFog(domain);
  const [cx, cy] = cellOf(domain, x, y);
  const r = FOG_RADIUS;
  for (let j = -r; j <= r; j += 1) {
    for (let i = -r; i <= r; i += 1) {
      if (i * i + j * j > r * r) continue;
      const gx = cx + i;
      const gy = cy + j;
      if (gx < 0 || gy < 0 || gx >= FOG_COLS || gy >= FOG_ROWS) continue;
      state.fog.cells[gy * FOG_COLS + gx] = 1;
    }
  }
}

function isExplored(domain, x, y) {
  if (!state.fog) return false;
  const [cx, cy] = cellOf(domain, x, y);
  return state.fog.cells[cy * FOG_COLS + cx] === 1;
}

// ----------------------------------------------------- colour helpers ----

const RAMP = [
  [68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37],
];

function heightColor(t) {
  const clamped = Math.min(1, Math.max(0, t)) * (RAMP.length - 1);
  const index = Math.min(RAMP.length - 2, Math.floor(clamped));
  const frac = clamped - index;
  const a = RAMP[index];
  const b = RAMP[index + 1];
  const mix = (i) => Math.round(a[i] + (b[i] - a[i]) * frac);
  return `rgb(${mix(0)},${mix(1)},${mix(2)})`;
}

// --------------------------------------------------------- player view ----

function buildWarp(patch) {
  const nx = patch.x.length;
  const ny = patch.y.length;
  const raw = [];
  let sum = 0;
  let count = 0;
  for (let j = 0; j < ny; j += 1) {
    const row = [];
    for (let i = 0; i < nx; i += 1) {
      const E = patch.E[j][i];
      const F = patch.F[j][i];
      const G = patch.G[j][i];
      const stretch = Math.sqrt(Math.max(1e-9, E * G - F * F));
      row.push(stretch);
      sum += stretch;
      count += 1;
    }
    raw.push(row);
  }
  const mean = count ? sum / count : 1;
  for (let j = 0; j < ny; j += 1) {
    for (let i = 0; i < nx; i += 1) {
      raw[j][i] = 1 + WARP_GAIN * (raw[j][i] / mean - 1);
    }
  }
  return raw;
}

function drawPlayerView() {
  const canvas = el('player-canvas');
  const ctx = canvas.getContext('2d');
  const W = canvas.width;
  const H = canvas.height;
  ctx.fillStyle = '#05070c';
  ctx.fillRect(0, 0, W, H);

  const p = state.player;
  if (!p) return;

  const patch = p.patch;
  const domain = p.domain;
  const nx = patch.x.length;
  const ny = patch.y.length;
  const px = p.position[0];
  const py = p.position[1];
  const radius = patch.radius || Math.max(1e-6, (patch.x[nx - 1] - patch.x[0]) / 2);
  const scale = (W / 2) / radius;

  const warp = buildWarp(patch);
  const screen = (x, y, w) => [
    W / 2 + (x - px) * scale * w,
    H / 2 - (y - py) * scale * w,
  ];
  const warpAt = (x, y) => {
    const fi = (x - patch.x[0]) / Math.max(1e-9, patch.x[nx - 1] - patch.x[0]) * (nx - 1);
    const fj = (y - patch.y[0]) / Math.max(1e-9, patch.y[ny - 1] - patch.y[0]) * (ny - 1);
    const i0 = Math.min(nx - 2, Math.max(0, Math.floor(fi)));
    const j0 = Math.min(ny - 2, Math.max(0, Math.floor(fj)));
    const tx = Math.min(1, Math.max(0, fi - i0));
    const ty = Math.min(1, Math.max(0, fj - j0));
    const top = warp[j0][i0] * (1 - tx) + warp[j0][i0 + 1] * tx;
    const bottom = warp[j0 + 1][i0] * (1 - tx) + warp[j0 + 1][i0 + 1] * tx;
    return top * (1 - ty) + bottom * ty;
  };

  let zmin = Infinity;
  let zmax = -Infinity;
  for (const row of patch.z) {
    for (const value of row) {
      if (value < zmin) zmin = value;
      if (value > zmax) zmax = value;
    }
  }
  const span = Math.max(1e-6, zmax - zmin);

  // warped height raster (banded -> contour-ish) with fog of war
  for (let j = 0; j < ny - 1; j += 1) {
    for (let i = 0; i < nx - 1; i += 1) {
      const xc = (patch.x[i] + patch.x[i + 1]) / 2;
      const yc = (patch.y[j] + patch.y[j + 1]) / 2;
      const visible = domainContains(domain, xc, yc) && isExplored(domain, xc, yc);
      if (visible) {
        const z = (patch.z[j][i] + patch.z[j][i + 1] + patch.z[j + 1][i] + patch.z[j + 1][i + 1]) / 4;
        ctx.fillStyle = heightColor(Math.floor(((z - zmin) / span) * 12) / 12);
      } else {
        ctx.fillStyle = '#05070c';
      }
      const q00 = screen(patch.x[i], patch.y[j], warp[j][i]);
      const q10 = screen(patch.x[i + 1], patch.y[j], warp[j][i + 1]);
      const q11 = screen(patch.x[i + 1], patch.y[j + 1], warp[j + 1][i + 1]);
      const q01 = screen(patch.x[i], patch.y[j + 1], warp[j + 1][i]);
      ctx.beginPath();
      ctx.moveTo(q00[0], q00[1]);
      ctx.lineTo(q10[0], q10[1]);
      ctx.lineTo(q11[0], q11[1]);
      ctx.lineTo(q01[0], q01[1]);
      ctx.closePath();
      ctx.fill();
      ctx.strokeStyle = ctx.fillStyle;
      ctx.lineWidth = 1;
      ctx.stroke();
    }
  }

  // grid lines, warped by the metric
  ctx.strokeStyle = 'rgba(255,255,255,0.10)';
  ctx.lineWidth = 1;
  for (let i = 0; i < nx; i += 4) {
    ctx.beginPath();
    for (let j = 0; j < ny; j += 1) {
      const point = screen(patch.x[i], patch.y[j], warp[j][i]);
      if (j === 0) ctx.moveTo(point[0], point[1]);
      else ctx.lineTo(point[0], point[1]);
    }
    ctx.stroke();
  }
  for (let j = 0; j < ny; j += 4) {
    ctx.beginPath();
    for (let i = 0; i < nx; i += 1) {
      const point = screen(patch.x[i], patch.y[j], warp[j][i]);
      if (i === 0) ctx.moveTo(point[0], point[1]);
      else ctx.lineTo(point[0], point[1]);
    }
    ctx.stroke();
  }

  // trajectory
  if (p.trajectory.length > 1) {
    ctx.strokeStyle = '#4dabf7';
    ctx.lineWidth = 2;
    ctx.beginPath();
    p.trajectory.forEach(([x, y], index) => {
      const tx = state.periodic ? unwrapNear(x, px) : x;
      const ty = state.periodic ? unwrapNear(y, py) : y;
      const point = screen(tx, ty, warpAt(x, y));
      if (index === 0) ctx.moveTo(point[0], point[1]);
      else ctx.lineTo(point[0], point[1]);
    });
    ctx.stroke();
  }

  // markers
  for (const marker of p.markers) {
    const mx = state.periodic ? unwrapNear(marker.position[0], px) : marker.position[0];
    const my = state.periodic ? unwrapNear(marker.position[1], py) : marker.position[1];
    const point = screen(mx, my, warpAt(marker.position[0], marker.position[1]));
    const selected = state.selection.includes(marker.name);
    ctx.fillStyle = selected ? '#ffd43b' : '#ffa94d';
    ctx.beginPath();
    ctx.arc(point[0], point[1], selected ? 7 : 5, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = '#ffd8a8';
    ctx.font = '12px monospace';
    ctx.fillText(marker.name, point[0] + 8, point[1] - 8);
  }

  // pointer hint (limited-use tangent-plane indicator)
  if (state.pointerHint) {
    const hint = state.pointerHint;
    const radians = hint.bearing_degrees * Math.PI / 180;
    const ax = Math.cos(radians);
    const ay = -Math.sin(radians);
    const cx = W / 2;
    const cy = H / 2;
    const length = 90;
    const tipX = cx + ax * length;
    const tipY = cy + ay * length;
    ctx.strokeStyle = '#ffd43b';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(tipX, tipY);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(tipX, tipY);
    ctx.lineTo(tipX - ax * 12 - ay * 7, tipY - ay * 12 + ax * 7);
    ctx.lineTo(tipX - ax * 12 + ay * 7, tipY - ay * 12 - ax * 7);
    ctx.closePath();
    ctx.fillStyle = '#ffd43b';
    ctx.fill();
    ctx.font = '12px monospace';
    ctx.fillText(`pitch ${hint.pitch_degrees.toFixed(0)} deg`, cx + 14, cy + 22);
  }

  // player, always at the centre
  ctx.fillStyle = '#ff4d6d';
  ctx.beginPath();
  ctx.arc(W / 2, H / 2, 8, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = '#ffffff';
  ctx.lineWidth = 2;
  ctx.stroke();

  ctx.strokeStyle = 'rgba(255,255,255,0.25)';
  ctx.lineWidth = 1;
  ctx.strokeRect(0.5, 0.5, W - 1, H - 1);
}

// -------------------------------------------------------------- gauge ----

function drawGauge() {
  const canvas = el('gauge');
  const ctx = canvas.getContext('2d');
  const W = canvas.width;
  const H = canvas.height;
  ctx.clearRect(0, 0, W, H);

  const cx = W / 2;
  const cy = H - 14;
  const radius = Math.min(W / 2 - 14, H - 28);

  ctx.strokeStyle = '#26303d';
  ctx.lineWidth = 10;
  ctx.beginPath();
  ctx.arc(cx, cy, radius, Math.PI, 2 * Math.PI);
  ctx.stroke();

  const signal = state.player ? Math.min(1, Math.max(0, state.player.signal)) : 0;
  const label = state.player ? state.player.label : 'Weak';
  const colour = label === 'Strong' ? '#ff6b6b' : label === 'Moderate' ? '#ffd43b' : '#4dabf7';

  ctx.strokeStyle = colour;
  ctx.beginPath();
  ctx.arc(cx, cy, radius, Math.PI, Math.PI + Math.PI * signal);
  ctx.stroke();

  const angle = Math.PI + Math.PI * signal;
  ctx.strokeStyle = '#e6edf5';
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(cx + Math.cos(angle) * (radius - 8), cy + Math.sin(angle) * (radius - 8));
  ctx.stroke();

  ctx.fillStyle = '#e6edf5';
  ctx.beginPath();
  ctx.arc(cx, cy, 5, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = '#8b98a9';
  ctx.font = '11px monospace';
  ctx.fillText('weak', 6, cy - 4);
  ctx.fillText('strong', cx + radius - 38, cy - 4);
}

// ---------------------------------------------------------- god view ----

function drawGodView() {
  const canvas = el('god-canvas');
  const ctx = canvas.getContext('2d');
  const W = canvas.width;
  const H = canvas.height;
  ctx.fillStyle = '#06080d';
  ctx.fillRect(0, 0, W, H);

  const data = state.debugState;
  if (!data) {
    ctx.fillStyle = '#8b98a9';
    ctx.font = '14px monospace';
    ctx.fillText('God view unavailable - start the server with --debug', 16, 26);
    return;
  }

  // Closed-surface mesh: x, y and z are all 2D embedded-coordinate grids.
  const gridX = data.surface.x;
  const gridY = data.surface.y;
  const gridZ = data.surface.z;
  const ny = gridX.length;
  const nx = gridX[0].length;

  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity, minZ = Infinity, maxZ = -Infinity;
  for (let j = 0; j < ny; j += 1) {
    for (let i = 0; i < nx; i += 1) {
      const x = gridX[j][i], y = gridY[j][i], z = gridZ[j][i];
      if (x < minX) minX = x; if (x > maxX) maxX = x;
      if (y < minY) minY = y; if (y > maxY) maxY = y;
      if (z < minZ) minZ = z; if (z > maxZ) maxZ = z;
    }
  }
  const centreX = (minX + maxX) / 2;
  const centreY = (minY + maxY) / 2;
  const centreZ = (minZ + maxZ) / 2;
  const unit = 1 / Math.max(maxX - minX, maxY - minY, maxZ - minZ, 1e-6);
  const cosY = Math.cos(state.yaw);
  const sinY = Math.sin(state.yaw);
  const cosP = Math.cos(state.pitch);
  const sinP = Math.sin(state.pitch);

  const project = (x, y, z) => {
    const X = (x - centreX) * unit;
    const Y = (y - centreY) * unit;
    const Z = (z - centreZ) * unit;
    const rx = X * cosY - Y * sinY;
    const ry = X * sinY + Y * cosY;
    return [W / 2 + rx * W * 0.42, H / 2 + (ry * sinP - Z * cosP) * H * 0.42];
  };

  const nodes = new Array(nx * ny);
  for (let j = 0; j < ny; j += 1) {
    for (let i = 0; i < nx; i += 1) {
      const X = (gridX[j][i] - centreX) * unit;
      const Y = (gridY[j][i] - centreY) * unit;
      const Z = (gridZ[j][i] - centreZ) * unit;
      const rx = X * cosY - Y * sinY;
      const ry = X * sinY + Y * cosY;
      nodes[j * nx + i] = [
        W / 2 + rx * W * 0.42,
        H / 2 + (ry * sinP - Z * cosP) * H * 0.42,
        ry * cosP + Z * sinP,
      ];
    }
  }

  const quads = [];
  for (let j = 0; j < ny - 1; j += 1) {
    for (let i = 0; i < nx - 1; i += 1) {
      const a = nodes[j * nx + i];
      const b = nodes[j * nx + i + 1];
      const c = nodes[(j + 1) * nx + i + 1];
      const d = nodes[(j + 1) * nx + i];
      const z = (gridZ[j][i] + gridZ[j][i + 1] + gridZ[j + 1][i + 1] + gridZ[j + 1][i]) / 4;
      quads.push({ a, b, c, d, depth: (a[2] + b[2] + c[2] + d[2]) / 4, z });
    }
  }
  quads.sort((u, v) => u.depth - v.depth);

  const zSpan = Math.max(1e-6, maxZ - minZ);
  for (const quad of quads) {
    ctx.beginPath();
    ctx.moveTo(quad.a[0], quad.a[1]);
    ctx.lineTo(quad.b[0], quad.b[1]);
    ctx.lineTo(quad.c[0], quad.c[1]);
    ctx.lineTo(quad.d[0], quad.d[1]);
    ctx.closePath();
    ctx.fillStyle = heightColor((quad.z - minZ) / zSpan);
    ctx.fill();
    ctx.strokeStyle = 'rgba(0,0,0,0.16)';
    ctx.lineWidth = 0.4;
    ctx.stroke();
  }

  const exitPoint = data.exit_position;
  const exitScreen = project(exitPoint[0], exitPoint[1], exitPoint[2]);
  ctx.fillStyle = '#000000';
  ctx.strokeStyle = '#ffffff';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(exitScreen[0], exitScreen[1], 6, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();

  const playerPoint = data.player_position;
  const playerScreen = project(playerPoint[0], playerPoint[1], playerPoint[2]);
  ctx.fillStyle = '#ff4d6d';
  ctx.beginPath();
  ctx.arc(playerScreen[0], playerScreen[1], 7, 0, Math.PI * 2);
  ctx.fill();
}
// ------------------------------------------------------------ chrome ----

function updateReadouts() {
  const p = state.player;
  if (!p) return;
  el('seed').textContent = `seed ${p.seed}`;
  el('map-name').textContent = mapLabel(p.map_id);
  el('steps').textContent = `steps ${p.steps}`;
  el('pointers').textContent = `pointers ${p.pointer_uses_remaining}`;
  el('position').textContent =
    `(${p.position[0].toFixed(2)}, ${p.position[1].toFixed(2)}, ${p.position3d[2].toFixed(2)})`;
  el('detector-text').textContent = `signal ${p.signal.toFixed(4)} (${p.label}, ${p.trend})`;
  el('curvature').textContent = p.curvature.toFixed(6);
}

function renderMarkers() {
  const box = el('markers');
  const markers = state.player ? state.player.markers : [];
  box.innerHTML = '';
  if (!markers.length) {
    box.innerHTML = '<em>none yet</em>';
    return;
  }
  for (const marker of markers) {
    const button = document.createElement('button');
    button.className = 'marker' + (state.selection.includes(marker.name) ? ' selected' : '');
    button.textContent =
      `${marker.name}  (${marker.position[0].toFixed(1)}, ${marker.position[1].toFixed(1)})  ${marker.label}`;
    button.addEventListener('click', () => toggleSelection(marker.name));
    box.appendChild(button);
  }
}

function toggleSelection(name) {
  const index = state.selection.indexOf(name);
  if (index >= 0) state.selection.splice(index, 1);
  else state.selection.push(name);
  renderMarkers();
}

function showCard(html, kind) {
  const card = el('tool-card');
  card.className = 'card' + (kind ? ` ${kind}` : '');
  card.innerHTML = html;
}

function hideCard() {
  el('tool-card').className = 'card hidden';
}

function message(text, kind) {
  const box = el('message');
  box.textContent = text;
  box.className = 'message' + (kind ? ` ${kind}` : '');
}

function renderAll() {
  drawPlayerView();
  drawGauge();
  updateReadouts();
  renderMarkers();
  if (state.godVisible) drawGodView();
}

// ------------------------------------------------------------ actions ----

async function refreshState() {
  const player = await apiGet('/api/state/player');
  state.player = player;
  state.periodic = Boolean(player.periodic);
  explore(player.domain, player.position[0], player.position[1]);
  renderAll();
}

async function move(dx, dy) {
  try {
    await apiPost('/api/action/move', { dx, dy, steps: state.stepMultiplier });
    await refreshState();
    if (state.player.won) message('Exit found - you reached the hidden exit.', 'ok');
  } catch (error) {
    message(error.message, 'error');
  }
}

const DEG = 180 / Math.PI;

function describeTool(result) {
  if (result.tool === 'scan') {
    return `scan: signal ${result.signal.toFixed(4)} (${result.label}, ${result.trend})`;
  }
  if (result.tool === 'mark') {
    return `marker ${result.name} placed at (${result.position[0].toFixed(2)}, ${result.position[1].toFixed(2)})`;
  }
  if (result.tool === 'measure') {
    return `straight-line 3D distance ${result.a} -> ${result.b} = ${result.distance.toFixed(4)}`;
  }
  if (result.tool === 'curvature') {
    return `Gaussian curvature K = ${result.curvature.toFixed(6)}`;
  }
  if (result.tool === 'triangle') {
    return `geodesic angle sum (${result.markers.join(', ')}) = ${(result.sum * DEG).toFixed(2)} deg`;
  }
  if (result.tool === 'pointer') {
    return `pointer: bearing ${result.bearing_degrees.toFixed(1)} deg, pitch ${result.pitch_degrees.toFixed(1)} deg`
      + ` (${result.uses_remaining} left)`;
  }
  return JSON.stringify(result);
}

function triangleCard(result) {
  const sum = result.sum * DEG;
  const excess = result.excess * DEG;
  const integral = result.curvature_integral;
  const kind = result.excess > 0 ? 'positive' : result.excess < 0 ? 'negative' : '';
  return `
    <h4>Geodesic angle gauge</h4>
    <div class="big">${sum.toFixed(2)}&deg;</div>
    <div class="sub">
      vertices ${result.markers.join(' / ')}<br />
      excess over 180&deg;: ${excess.toFixed(3)}&deg;<br />
      &#8748; K dA (numeric): ${integral.toExponential(3)} rad<br />
      Gauss-Bonnet residual: ${result.gauss_bonnet_residual.toExponential(3)} rad<br />
      ${result.character}
    </div>`;
}

function pointerCard(result) {
  return `
    <h4>Tangent-plane pointer</h4>
    <div class="big">${result.bearing_degrees.toFixed(1)}&deg;</div>
    <div class="sub">
      bearing in the tangent plane (coarse, ${result.sector_width_degrees.toFixed(1)}&deg; sectors)<br />
      pitch above the tangent plane: ${result.pitch_degrees.toFixed(1)}&deg;<br />
      uses remaining: ${result.uses_remaining}
    </div>`;
}

async function runTool(tool) {
  try {
    if (tool === 'scan' || tool === 'curvature') {
      const result = await apiPost('/api/action/tool', { tool });
      await refreshState();
      message(describeTool(result), 'ok');
      return;
    }
    if (tool === 'mark') {
      const count = state.player ? state.player.markers.length : 0;
      const result = await apiPost('/api/action/tool', { tool: 'mark', name: `P${count + 1}` });
      await refreshState();
      message(describeTool(result), 'ok');
      return;
    }
    if (tool === 'measure') {
      const selected = state.selection.slice(0, 2);
      if (selected.length < 2) {
        message('Ruler: select two markers in the list first.', 'error');
        return;
      }
      const result = await apiPost('/api/action/tool', { tool: 'measure', a: selected[0], b: selected[1] });
      message(describeTool(result), 'ok');
      return;
    }
    if (tool === 'triangle') {
      const selected = state.selection.slice(0, 3);
      if (selected.length < 3) {
        message('Angle gauge: select three markers in the list first.', 'error');
        return;
      }
      const result = await apiPost('/api/action/tool', { tool: 'triangle', markers: selected });
      showCard(triangleCard(result), result.excess > 0 ? 'positive' : 'negative');
      message(describeTool(result), 'ok');
      return;
    }
    if (tool === 'pointer') {
      const result = await apiPost('/api/action/tool', { tool: 'pointer' });
      state.pointerHint = result;
      showCard(pointerCard(result));
      message(describeTool(result), 'ok');
      drawPlayerView();
      return;
    }
    message(`unknown tool ${tool}`, 'error');
  } catch (error) {
    message(error.message, 'error');
  }
}

async function toggleGodView() {
  state.godVisible = !state.godVisible;
  el('god-panel').classList.toggle('hidden', !state.godVisible);
  el('mode').textContent = state.godVisible ? 'god view (debug)' : 'player view';
  if (!state.godVisible) return;
  try {
    state.debugState = await apiGet('/api/state/debug');
  } catch (error) {
    state.debugState = null;
    message(`god view unavailable: ${error.message}`, 'error');
  }
  drawGodView();
}

// ------------------------------------------- continuous walking (hold) ----

async function walkLoop() {
  if (state.walking) return;
  state.walking = true;
  try {
    while (state.heldKeys.size) {
      const key = Array.from(state.heldKeys).pop();
      const direction = DIRECTIONS[key];
      if (!direction) break;
      await move(direction[0], direction[1]);
      await sleep(90);
    }
  } finally {
    state.walking = false;
  }
}

// ------------------------------------------------------------- wiring ----

// Toolbar is configuration driven: append an entry here to add a tool -- the
// button and its hotkey binding are generated automatically.
const TOOLS = [
  { id: 'scan', name: 'Scan', key: null },
  { id: 'curvature', name: '3 Curvature', key: '3' },
  { id: 'mark', name: 'Mark here', key: null },
  { id: 'measure', name: '1 Ruler', key: '1' },
  { id: 'triangle', name: '2 Angle gauge', key: '2' },
  { id: 'pointer', name: '4 Pointer', key: '4' },
];

const HOTKEYS = Object.fromEntries(TOOLS.filter((tool) => tool.key).map((tool) => [tool.key, tool.id]));

function renderToolbar() {
  const bar = el('toolbar');
  bar.innerHTML = '';
  for (const tool of TOOLS) {
    const button = document.createElement('button');
    button.dataset.tool = tool.id;
    button.textContent = tool.name;
    button.addEventListener('click', () => runTool(tool.id));
    bar.appendChild(button);
  }
}

window.addEventListener('keydown', (event) => {
  const key = event.key.toLowerCase();
  if (DIRECTIONS[key]) {
    event.preventDefault();
    if (!state.heldKeys.has(key)) {
      state.heldKeys.add(key);
      walkLoop();
    }
    return;
  }
  if (event.repeat) return;
  if (HOTKEYS[key]) {
    runTool(HOTKEYS[key]);
  } else if (key === 'g') {
    toggleGodView();
  } else if (key === 'escape' && state.godVisible) {
    toggleGodView();
  }
});

window.addEventListener('keyup', (event) => {
  state.heldKeys.delete(event.key.toLowerCase());
});

const godCanvas = el('god-canvas');
godCanvas.addEventListener('mousedown', (event) => {
  state.drag = { x: event.clientX, y: event.clientY };
});
window.addEventListener('mouseup', () => { state.drag = null; });
window.addEventListener('mousemove', (event) => {
  if (!state.drag) return;
  state.yaw += (event.clientX - state.drag.x) * 0.01;
  state.pitch = Math.max(0.1, Math.min(1.4, state.pitch + (event.clientY - state.drag.y) * 0.008));
  state.drag = { x: event.clientX, y: event.clientY };
  if (state.godVisible) drawGodView();
});

// toolbar buttons are bound by renderToolbar()

el('map-select').addEventListener('change', showMapDescription);
el('enter-world').addEventListener('click', enterWorld);
el('open-lobby').addEventListener('click', showLobby);

el('step-size').addEventListener('change', (event) => {
  state.stepMultiplier = Number(event.target.value) || 1;
  message(`step multiplier set to ${state.stepMultiplier}x`);
});

function mapLabel(mapId) {
  const found = state.maps.find((entry) => entry.id === mapId);
  return found ? found.name : (mapId || 'map');
}

function renderMapOptions(maps) {
  const select = el('map-select');
  select.innerHTML = '';
  for (const entry of maps) {
    const option = document.createElement('option');
    option.value = entry.id;
    option.textContent = entry.name;
    select.appendChild(option);
  }
  showMapDescription();
}

function showMapDescription() {
  const selected = el('map-select').value;
  const entry = state.maps.find((item) => item.id === selected);
  el('map-description').textContent = entry ? entry.description : '';
}

function showLobby() {
  el('lobby-modal').classList.remove('hidden', 'fading');
  el('lobby-error').textContent = '';
  if (!el('map-select').options.length && state.maps.length) renderMapOptions(state.maps);
}

function hideLobby() {
  const modal = el('lobby-modal');
  modal.classList.add('fading');
  window.setTimeout(() => modal.classList.add('hidden'), 240);
}

async function setGodView(visible) {
  if (Boolean(visible) === Boolean(state.godVisible)) {
    if (state.godVisible) drawGodView();
    return;
  }
  await toggleGodView();
}

async function enterWorld() {
  const mapId = el('map-select').value;
  const mode = document.querySelector('input[name="mode"]:checked').value;
  const seedText = el('seed-input').value.trim();
  const seed = seedText === '' ? null : Number(seedText);
  if (seedText !== '' && !Number.isFinite(seed)) {
    el('lobby-error').textContent = 'The seed must be an integer.';
    return;
  }
  try {
    await apiPost('/api/session/new', { map_id: mapId, seed, mode });
    state.selection = [];
    state.pointerHint = null;
    state.fog = null;
    state.domain = null;
    hideCard();
    await refreshState();
    hideLobby();
    await setGodView(mode === 'god');
    message(`entered ${mapLabel(mapId)} (${mode} mode)`);
  } catch (error) {
    el('lobby-error').textContent = error.message;
  }
}
async function init() {
  try {
    renderToolbar();
    const payload = await apiGet('/api/maps');
    state.maps = payload.maps || [];
    renderMapOptions(state.maps);
    const preferred = payload.default && state.maps.some((m) => m.id === payload.default);
    if (preferred) el('map-select').value = payload.default;
    showMapDescription();
    await refreshState();      // background state so the canvas is not empty behind the lobby
    showLobby();
    message('Lobby ready: choose a map, a mode and a seed, then click Enter the World.');
  } catch (error) {
    message(`failed to load the lobby: ${error.message}`, 'error');
  }
}

init();