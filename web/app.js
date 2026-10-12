// The Curved World -- web view & interaction layer (Tasks 6-15).
//
// The Python kernel is authoritative: world generation, analytic geometry,
// curvature, the detector model, obstacles and the information boundary all
// live in src/the_curved_world/. This file is only the view & interaction
// engine.
//
// Task 15 replaced the pseudo-3D first-person projection with a seamless
// 2D top-down local tangent map. Everything is projected from wrapped
// parameter deltas relative to the player, so the player stays pinned to the
// canvas centre and the grassland scrolls forever with no seam and no jump.

const el = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const TWO_PI = Math.PI * 2;

// Player radius (ambient world units) and the slope-damping constant: both
// mirror GameplayConfig defaults so the local client physics matches the
// server's own step model. The server stays the authority for world state.
const PLAYER_RADIUS = 0.6;
const SLOPE_DAMPING = 3.0;

// A reference half-canvas turns "nice-looking pixels" into parameter units so
// the hard-collision reach always matches the obstacle radius that is drawn,
// whatever the real canvas size is.
const REFERENCE_HALF = 300;
const MIN_OBSTACLE_PX = 12;
const MIN_PLAYER_PX = 4;
const SYNC_MS = 200;
const BASE_SPEED = 1.15;

const state = {
  player: null,
  maps: [],
  selection: [],
  godVisible: false,
  debugState: null,
  yaw: 0.85,          // god-view orbit only
  pitch: 0.55,        // god-view orbit only
  drag: null,
  slot: 1,
  speedMultiplier: 1,
  proofOpen: false,
  proof: null,
  shownRelicCount: 0,
  ropeMode: false,
  ropeFirst: null,
  measureMode: false,
  measureKind: 'length',
  measureTargets: [],
  angleMeasurements: {},
  pendingCut: null,
  codexOpen: false,
  cursor: null,
  hoverNode: null,
  hitNodes: [],
  hitRopes: [],
  scaleFactor: 1,
  difficulty: 'easy',
  readings: 0,
  victoryShown: false,
  cleared: false,
  startedAt: 0,
  compassPulse: 0,
  particles: [],
  beacons: [],
  lastMeasure: null,
  terrainCache: null,
};

// Hotbar slots map onto the tool ids (Task 19).
const SLOT_TOOLS = ['scan', 'mark', 'rope', 'measure', 'codex'];

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

// ------------------------------------------------------------ utilities ----

function clamp(value, low, high) {
  return Math.min(high, Math.max(low, value));
}

function wrapParameter(value) {
  return ((value + Math.PI) % TWO_PI + TWO_PI) % TWO_PI - Math.PI;
}

function lerpAngle(a, b, t) {
  return a + wrapParameter(b - a) * t;
}

// Nearest representative of ``a - b``: wrapped on a closed periodic map,
// linear on a bounded map (so the domain edge never wraps around).
function relativeDelta(a, b) {
  return state.player && state.player.periodic ? wrapParameter(a - b) : (a - b);
}

function dot(a, b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }

function cross(a, b) {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

function normalize3(v) {
  const n = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / n, v[1] / n, v[2] / n];
}

// ----------------------------------------------------- colour helpers -----

const RAMP = [
  [68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37],
];

function heightColor(t) {
  const value = clamp(t, 0, 1) * (RAMP.length - 1);
  const index = Math.min(RAMP.length - 2, Math.floor(value));
  const frac = value - index;
  const a = RAMP[index];
  const b = RAMP[index + 1];
  const mix = (i) => Math.round(a[i] + (b[i] - a[i]) * frac);
  return `rgb(${mix(0)},${mix(1)},${mix(2)})`;
}

const GRASS_LOW = [61, 126, 52];
const GRASS_HIGH = [104, 170, 74];
const GRASS_DRY = [178, 184, 104];
const GRASS_ROCK = [78, 88, 60];

// Grassland biome shading: height blends the green, steep ground turns mossy,
// and high dry ridges pick up a faint straw tint. Returns an [r, g, b] triple
// so the diffuse topography shading can modulate it afterwards.
function grassRGB(t, steepness) {
  const mix = (a, b, k) => a + (b - a) * k;
  const height = clamp(t, 0, 1);
  const s = clamp(steepness * 1.6, 0, 1);
  const base = [0, 1, 2].map((i) => mix(GRASS_LOW[i], GRASS_HIGH[i], height));
  const dry = clamp((height - 0.62) * 2.4 - s, 0, 1);
  const mossy = s;
  return [0, 1, 2].map((i) => {
    const value = mix(mix(base[i], GRASS_DRY[i], dry * 0.55), GRASS_ROCK[i], mossy * 0.75);
    return Math.round(clamp(value, 0, 255));
  });
}

function mixRGB(a, b, k) {
  return [0, 1, 2].map((i) => a[i] + (b[i] - a[i]) * k);
}

function rgbCss(rgb, alpha) {
  const r = Math.round(clamp(rgb[0], 0, 255));
  const g = Math.round(clamp(rgb[1], 0, 255));
  const b = Math.round(clamp(rgb[2], 0, 255));
  return alpha === undefined ? `rgb(${r},${g},${b})` : `rgba(${r},${g},${b},${alpha})`;
}

// --------------------------------------------------- hi-dpi 2D canvas -----

function frameCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.round(rect.width));
  const height = Math.max(1, Math.round(rect.height));
  const pixelWidth = Math.max(1, Math.round(width * dpr));
  const pixelHeight = Math.max(1, Math.round(height * dpr));
  if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
    canvas.width = pixelWidth;
    canvas.height = pixelHeight;
  }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, W: width, H: height };
}

// ---------------------------------------------------- patch sampling ------

function zRange(patch) {
  let low = Infinity;
  let high = -Infinity;
  for (const row of patch.z) {
    for (const value of row) {
      if (value < low) low = value;
      if (value > high) high = value;
    }
  }
  return [low, Math.max(1e-9, high - low)];
}

function centerIndex(patch) {
  return [Math.floor(patch.x.length / 2), Math.floor(patch.y.length / 2)];
}

function metricCenter(patch) {
  const [i, j] = centerIndex(patch);
  return [patch.E[j][i], patch.F[j][i], patch.G[j][i]];
}

function metricUnit(metric) {
  return Math.max(1e-6, 0.5 * (Math.sqrt(Math.max(metric[0], 1e-9)) + Math.sqrt(Math.max(metric[2], 1e-9))));
}

// Bilinear first fundamental form at an arbitrary parameter point inside the
// patch, so an obstacle's radius is converted with the metric *at the
// obstacle*, not at the player.
function metricAt(patch, u, v) {
  const [lu, lv] = localize(patch, u, v);
  const xs = patch.x;
  const ys = patch.y;
  const nx = xs.length;
  const ny = ys.length;
  const du = (xs[1] - xs[0]) || 1e-9;
  const dv = (ys[1] - ys[0]) || 1e-9;
  const i = clamp(Math.floor((lu - xs[0]) / du), 0, nx - 2);
  const j = clamp(Math.floor((lv - ys[0]) / dv), 0, ny - 2);
  const tu = clamp((lu - xs[i]) / du, 0, 1);
  const tv = clamp((lv - ys[j]) / dv, 0, 1);
  const blend = (grid) => (grid[j][i] * (1 - tu) + grid[j][i + 1] * tu) * (1 - tv)
    + (grid[j + 1][i] * (1 - tu) + grid[j + 1][i + 1] * tu) * tv;
  return [blend(patch.E), blend(patch.F), blend(patch.G)];
}

// Bring an absolute parameter point into the linear frame of the patch, which
// may straddle the periodic seam.
function localize(patch, u, v) {
  const [i, j] = centerIndex(patch);
  const cu = patch.x[i];
  const cv = patch.y[j];
  if (state.player && state.player.periodic) {
    return [cu + wrapParameter(u - cu), cv + wrapParameter(v - cv)];
  }
  return [u, v];
}

// Bilinear height sample from the server's local patch (global z coordinate).
function sampleHeight(patch, u, v) {
  const [lu, lv] = localize(patch, u, v);
  const xs = patch.x;
  const ys = patch.y;
  const nx = xs.length;
  const ny = ys.length;
  const du = (xs[1] - xs[0]) || 1e-9;
  const dv = (ys[1] - ys[0]) || 1e-9;
  const i = clamp(Math.floor((lu - xs[0]) / du), 0, nx - 2);
  const j = clamp(Math.floor((lv - ys[0]) / dv), 0, ny - 2);
  const tu = clamp((lu - xs[i]) / du, 0, 1);
  const tv = clamp((lv - ys[j]) / dv, 0, 1);
  const z = patch.z;
  const z00 = z[j][i];
  const z10 = z[j][i + 1];
  const z01 = z[j + 1][i];
  const z11 = z[j + 1][i + 1];
  return (z00 * (1 - tu) + z10 * tu) * (1 - tv) + (z01 * (1 - tu) + z11 * tu) * tv;
}

// Local slope and the Task 14 uphill damping, evaluated along a unit
// parameter-space direction: slope = dz / ||dr_tangent||, and
// speed_scale = 1 / (1 + k * slope^2) uphill, exactly 1 downhill or flat.
function localSlope(patch, uv, du, dv) {
  const step = Math.max(1e-4, (patch.radius || 1) * 0.05);
  const z0 = sampleHeight(patch, uv[0], uv[1]);
  const z1 = sampleHeight(patch, uv[0] + du * step, uv[1] + dv * step);
  const [E, F, G] = metricCenter(patch);
  const speed = Math.sqrt(Math.max(1e-12, E * du * du + 2 * F * du * dv + G * dv * dv));
  const length = speed * step;
  const slope = length > 1e-12 ? (z1 - z0) / length : 0;
  const scale = slope > 0 ? 1 / (1 + SLOPE_DAMPING * slope * slope) : 1;
  return { slope, speed_scale: scale };
}

// ----------------------------------------------------- terrain cache ------

function buildContours(grid, levels) {
  const segments = [];
  for (const level of levels) {
    for (let j = 0; j < grid.length - 1; j += 1) {
      for (let i = 0; i < grid[0].length - 1; i += 1) {
        const a = grid[j][i];
        const b = grid[j][i + 1];
        const c = grid[j + 1][i + 1];
        const d = grid[j + 1][i];
        const points = [];
        const edge = (p, q) => {
          const fa = p.z - level;
          const fb = q.z - level;
          if (fa * fb < 0) {
            const t = fa / (fa - fb);
            points.push([p.x + (q.x - p.x) * t, p.y + (q.y - p.y) * t]);
          }
        };
        edge(a, b); edge(b, c); edge(c, d); edge(d, a);
        if (points.length === 2) {
          segments.push([points[0][0], points[0][1], points[1][0], points[1][1]]);
        } else if (points.length === 4) {
          segments.push([points[0][0], points[0][1], points[1][0], points[1][1]]);
          segments.push([points[2][0], points[2][1], points[3][0], points[3][1]]);
        }
      }
    }
  }
  return segments;
}

// One cache per server patch: a subsampled shaded node grid plus the contour
// segments. The cache is rebuilt whenever a new patch arrives (~5 Hz) and only
// re-projected at 60 fps.
function buildTerrain(patch) {
  const nx = patch.x.length;
  const ny = patch.y.length;
  const stride = nx > 40 ? 2 : 1;
  const [zLow, zHigh] = zRange(patch);
  const span = Math.max(1e-9, zHigh - zLow);
  const light = normalize3([-0.35, 0.5, 0.79]);
  const grid = [];
  for (let j = 0; j < ny; j += stride) {
    const row = [];
    for (let i = 0; i < nx; i += stride) {
      const i0 = Math.max(0, i - 1);
      const i1 = Math.min(nx - 1, i + 1);
      const j0 = Math.max(0, j - 1);
      const j1 = Math.min(ny - 1, j + 1);
      const du = (patch.x[i1] - patch.x[i0]) || 1e-9;
      const dv = (patch.y[j1] - patch.y[j0]) || 1e-9;
      const ru = [
        (patch.X[j][i1] - patch.X[j][i0]) / du,
        (patch.Y[j][i1] - patch.Y[j][i0]) / du,
        (patch.z[j][i1] - patch.z[j][i0]) / du,
      ];
      const rv = [
        (patch.X[j1][i] - patch.X[j0][i]) / dv,
        (patch.Y[j1][i] - patch.Y[j0][i]) / dv,
        (patch.z[j1][i] - patch.z[j0][i]) / dv,
      ];
      let normal = normalize3(cross(ru, rv));
      if (normal[2] < 0) normal = normal.map((value) => -value);
      const shade = 0.62 + 0.38 * Math.max(0, dot(normal, light));
      const steep = Math.sqrt(Math.max(0, patch.E[j][i] - 1) + Math.max(0, patch.G[j][i] - 1));
      const rgb = grassRGB((patch.z[j][i] - zLow) / span, steep).map((value) => clamp(value * shade, 0, 255));
      row.push({ x: patch.x[i], y: patch.y[j], z: patch.z[j][i], rgb });
    }
    grid.push(row);
  }
  const levels = [];
  for (let k = 1; k <= 7; k += 1) levels.push(zLow + span * k / 8);
  return { grid, contours: buildContours(grid, levels), zLow, zHigh };
}

// ------------------------------------------------- collision geometry -----

// Convert ambient world radii into local parameter units so collision matches
// the drawn obstacle discs on any map scale. A tiny pixel floor keeps a single
// tree from becoming an invisible one-pixel trap on the very large torus.
function collisionGeometry(patch) {
  const unit = metricUnit(metricCenter(patch));
  const viewRadius = Math.max(1e-6, patch.radius || 1);
  const minObstacle = (MIN_OBSTACLE_PX / REFERENCE_HALF) * viewRadius;
  const minPlayer = (MIN_PLAYER_PX / REFERENCE_HALF) * viewRadius;
  const scale = state.scaleFactor || 1;
  const playerParam = Math.max(PLAYER_RADIUS / scale / unit, minPlayer);
  const obstacleParam = (obstacle) => Math.max(obstacle.radius / metricUnit(metricAt(patch, obstacle.u, obstacle.v)), minObstacle);
  // Tiny safety margin for float / snapshot lag; the drawn disc uses the same
  // local metric, so the visual radius and the hard constraint stay aligned.
  const safety = 1.01;
  return {
    unit,
    viewRadius,
    playerParam,
    obstacleParam,
    reachParam: (obstacle) => (obstacleParam(obstacle) + playerParam) * safety,
  };
}

// Rigid hard constraint: the requested displacement is cut along the collision
// normal (no penetration) while the tangential component survives, so the
// player slides along the obstacle edge and never sticks.
function resolveHardCollisions(fromUv, targetUv) {
  const p = state.player;
  if (!p || !p.patch) return { uv: targetUv.slice(), hit: false };
  const geometry = collisionGeometry(p.patch);
  let offset = [relativeDelta(targetUv[0], fromUv[0]), relativeDelta(targetUv[1], fromUv[1])];
  let hit = false;
  for (let iteration = 0; iteration < 4; iteration += 1) {
    let adjusted = false;
    for (const obstacle of p.obstacles || []) {
      const centre = [relativeDelta(obstacle.u, fromUv[0]), relativeDelta(obstacle.v, fromUv[1])];
      const reach = geometry.reachParam(obstacle);
      let dx = offset[0] - centre[0];
      let dy = offset[1] - centre[1];
      let distance = Math.hypot(dx, dy);
      if (distance >= reach) continue;
      hit = true;
      if (distance < 1e-9) {
        dx = -centre[0];
        dy = -centre[1];
        distance = Math.hypot(dx, dy);
      }
      if (distance < 1e-9) { dx = 1; dy = 0; distance = 1; }
      offset = [centre[0] + (dx / distance) * reach, centre[1] + (dy / distance) * reach];
      adjusted = true;
    }
    if (!adjusted) break;
  }
  let u = fromUv[0] + offset[0];
  let v = fromUv[1] + offset[1];
  if (p.periodic) {
    u = wrapParameter(u);
    v = wrapParameter(v);
  } else if (p.domain) {
    u = clamp(u, p.domain.x_min, p.domain.x_max);
    v = clamp(v, p.domain.y_min, p.domain.y_max);
  }
  return { uv: [u, v], hit };
}
// ------------------------------------------- top-down 2D world view -------

function drawTopDownTree(ctx, x, y, radius) {
  const r = Math.max(2, radius);
  ctx.fillStyle = 'rgba(10, 24, 12, 0.35)';
  ctx.beginPath(); ctx.ellipse(x + r * 0.35, y + r * 0.45, r * 1.05, r * 0.8, 0, 0, TWO_PI); ctx.fill();
  ctx.fillStyle = '#24512a';
  ctx.beginPath(); ctx.arc(x, y, r, 0, TWO_PI); ctx.fill();
  ctx.fillStyle = '#33733a';
  ctx.beginPath(); ctx.arc(x, y, r * 0.72, 0, TWO_PI); ctx.fill();
  ctx.fillStyle = '#4a9448';
  ctx.beginPath(); ctx.arc(x, y, r * 0.44, 0, TWO_PI); ctx.fill();
  ctx.fillStyle = '#6b4a2b';
  ctx.beginPath(); ctx.arc(x, y, Math.max(1.4, r * 0.16), 0, TWO_PI); ctx.fill();
}

function drawTopDownRock(ctx, x, y, radius, id) {
  const r = Math.max(2, radius);
  ctx.fillStyle = 'rgba(12, 14, 18, 0.35)';
  ctx.beginPath(); ctx.ellipse(x + r * 0.3, y + r * 0.4, r * 1.05, r * 0.78, 0, 0, TWO_PI); ctx.fill();
  ctx.beginPath();
  const sides = 7;
  for (let k = 0; k < sides; k += 1) {
    const angle = (k / sides) * TWO_PI + id * 0.7;
    const jitter = 0.78 + 0.30 * Math.abs(Math.sin(id * 12.9898 + k * 4.1414));
    const px = x + Math.cos(angle) * r * jitter;
    const py = y + Math.sin(angle) * r * jitter;
    if (k === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
  }
  ctx.closePath();
  ctx.fillStyle = '#8d8577';
  ctx.fill();
  ctx.strokeStyle = 'rgba(50, 48, 44, 0.7)';
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(x - r * 0.22, y - r * 0.24, r * 0.32, 0, TWO_PI);
  ctx.fillStyle = 'rgba(210, 205, 190, 0.35)';
  ctx.fill();
}

function markerByName(name) {
  const markers = (state.player && state.player.markers) || [];
  return markers.find((marker) => marker.name === name) || null;
}

function drawMarker(ctx, x, y, name, selected) {
  ctx.beginPath();
  ctx.moveTo(x, y - 8);
  ctx.lineTo(x + 7, y);
  ctx.lineTo(x, y + 8);
  ctx.lineTo(x - 7, y);
  ctx.closePath();
  ctx.fillStyle = selected ? '#4dabf7' : '#ffa94d';
  ctx.fill();
  ctx.strokeStyle = 'rgba(10, 14, 20, 0.85)';
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.fillStyle = 'rgba(240, 246, 255, 0.82)';
  ctx.font = '11px monospace';
  ctx.fillText(name, x + 10, y + 4);
}

function drawBeaconPin(ctx, x, y, life) {
  const pulse = 0.55 + 0.45 * Math.sin((performance.now() / 1000) * 4 + life);
  ctx.fillStyle = `rgba(255, 214, 102, ${0.18 * pulse})`;
  ctx.beginPath(); ctx.arc(x, y, 18, 0, TWO_PI); ctx.fill();
  ctx.strokeStyle = '#ffd166';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(x, y - 20);
  ctx.lineTo(x, y + 2);
  ctx.stroke();
  ctx.fillStyle = '#ffd166';
  ctx.beginPath();
  ctx.moveTo(x, y - 20);
  ctx.lineTo(x + 12, y - 15);
  ctx.lineTo(x, y - 9);
  ctx.closePath();
  ctx.fill();
  ctx.beginPath(); ctx.arc(x, y + 3, 3.2, 0, TWO_PI); ctx.fill();
}

function drawTopDownWorld() {
  const canvas = el('map-canvas');
  const { ctx, W, H } = frameCanvas(canvas);
  ctx.clearRect(0, 0, W, H);
  const bg = ctx.createLinearGradient(0, 0, 0, H);
  bg.addColorStop(0, '#1b3120');
  bg.addColorStop(1, '#142516');
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, W, H);

  const p = state.player;
  if (!p || !p.patch || !p.position) {
    ctx.fillStyle = '#8b98a9';
    ctx.font = '13px monospace';
    ctx.fillText('Waiting for the world...', 16, 26);
    return;
  }

  const patch = p.patch;
  const phys = (PHYS.uv || p.position).slice();
  const cx = W / 2;
  const cy = H / 2;
  const R = Math.min(W, H) / 2 - 6;
  const viewRadius = Math.max(1e-6, patch.radius || 1);
  const scale = R / viewRadius;
  const geometry = collisionGeometry(patch);
  const project = (u, v) => [
    cx + relativeDelta(u, phys[0]) * scale,
    cy - relativeDelta(v, phys[1]) * scale,
  ];
  state.hitNodes = [];
  state.hitRopes = [];

  if (!state.terrainCache || state.terrainCache.patch !== patch) {
    state.terrainCache = { patch, data: buildTerrain(patch) };
  }
  const terrain = state.terrainCache.data;

  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, R, 0, TWO_PI);
  ctx.clip();

  // 1. Shaded grassland quads (height tint + diffuse topography shading).
  const grid = terrain.grid;
  for (let j = 0; j < grid.length - 1; j += 1) {
    for (let i = 0; i < grid[0].length - 1; i += 1) {
      const a = grid[j][i];
      const b = grid[j][i + 1];
      const c = grid[j + 1][i + 1];
      const d = grid[j + 1][i];
      const points = [project(a.x, a.y), project(b.x, b.y), project(c.x, c.y), project(d.x, d.y)];
      const rgb = mixRGB(mixRGB(a.rgb, b.rgb, 0.5), mixRGB(d.rgb, c.rgb, 0.5), 0.5);
      ctx.fillStyle = rgbCss(rgb);
      ctx.strokeStyle = ctx.fillStyle;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(points[0][0], points[0][1]);
      ctx.lineTo(points[1][0], points[1][1]);
      ctx.lineTo(points[2][0], points[2][1]);
      ctx.lineTo(points[3][0], points[3][1]);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    }
  }

  // 2. Semi-transparent contour lines: the topography is visible, the global
  //    topology is not.
  ctx.strokeStyle = 'rgba(244, 248, 220, 0.20)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (const segment of terrain.contours) {
    const start = project(segment[0], segment[1]);
    const end = project(segment[2], segment[3]);
    ctx.moveTo(start[0], start[1]);
    ctx.lineTo(end[0], end[1]);
  }
  ctx.stroke();

  // 3. Very faint parameter grid, drawn from wrapped world coordinates so it
  //    scrolls with the player forever without ever resetting.
  const gridStep = viewRadius / 5;
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.055)';
  ctx.lineWidth = 1;
  const uMin = phys[0] - viewRadius - gridStep;
  const uMax = phys[0] + viewRadius + gridStep;
  for (let k = Math.ceil(uMin / gridStep); k <= Math.floor(uMax / gridStep); k += 1) {
    const u = k * gridStep;
    if (!p.periodic && p.domain && (u < p.domain.x_min || u > p.domain.x_max)) continue;
    const x = cx + relativeDelta(u, phys[0]) * scale;
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
  }
  const vMin = phys[1] - viewRadius - gridStep;
  const vMax = phys[1] + viewRadius + gridStep;
  for (let k = Math.ceil(vMin / gridStep); k <= Math.floor(vMax / gridStep); k += 1) {
    const v = k * gridStep;
    if (!p.periodic && p.domain && (v < p.domain.y_min || v > p.domain.y_max)) continue;
    const y = cy - relativeDelta(v, phys[1]) * scale;
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
  }

  // 4. Walked trajectory (local slice only, fading).
  if (p.trajectory && p.trajectory.length > 1) {
    ctx.lineWidth = 2;
    ctx.lineCap = 'round';
    ctx.strokeStyle = 'rgba(160, 220, 255, 0.30)';
    const points = p.trajectory.slice(-240);
    let previous = null;
    let previousVisible = false;
    for (const point of points) {
      const sx = cx + relativeDelta(point[0], phys[0]) * scale;
      const sy = cy - relativeDelta(point[1], phys[1]) * scale;
      const visible = Math.hypot(sx - cx, sy - cy) <= R * 0.98;
      if (visible && previousVisible && Math.hypot(sx - previous[0], sy - previous[1]) < R * 0.6) {
        ctx.beginPath();
        ctx.moveTo(previous[0], previous[1]);
        ctx.lineTo(sx, sy);
        ctx.stroke();
      }
      previous = [sx, sy];
      previousVisible = visible;
    }
  }

  // 5. Geodesic tools: the selected markers, the flashing ruler and the
  //    angle-gauge triangle are all drawn as plain 2D overlays.
  const selected = state.selection.map(markerByName).filter(Boolean);
  if (selected.length >= 2) {
    ctx.strokeStyle = 'rgba(77, 171, 247, 0.75)';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([6, 4]);
    ctx.beginPath();
    for (let k = 0; k < selected.length; k += 1) {
      const point = project(selected[k].position[0], selected[k].position[1]);
      if (k === 0) ctx.moveTo(point[0], point[1]); else ctx.lineTo(point[0], point[1]);
    }
    if (selected.length >= 3) ctx.closePath();
    ctx.stroke();
    ctx.setLineDash([]);
  }
  if (state.lastMeasure) {
    const a = markerByName(state.lastMeasure.a);
    const b = markerByName(state.lastMeasure.b);
    if (a && b) {
      const pa = project(a.position[0], a.position[1]);
      const pb = project(b.position[0], b.position[1]);
      const mx = (pa[0] + pb[0]) / 2;
      const my = (pa[1] + pb[1]) / 2;
      ctx.fillStyle = 'rgba(230, 240, 255, 0.85)';
      ctx.font = '11px monospace';
      ctx.fillText(state.lastMeasure.distance.toFixed(2), mx + 6, my - 4);
    }
  }

  // 6. Obstacles: rigid discs, drawn far to near, with shading and a soft
  //    rounded canopy / low-poly rock silhouette.
  const obstacles = (p.obstacles || []).slice().sort((a, b) => b.distance - a.distance);
  for (const obstacle of obstacles) {
    const point = project(obstacle.u, obstacle.v);
    if (Math.hypot(point[0] - cx, point[1] - cy) > R + 48) continue;
    const radius = geometry.obstacleParam(obstacle) * scale;
    if (obstacle.kind === 'tree') drawTopDownTree(ctx, point[0], point[1], radius);
    else drawTopDownRock(ctx, point[0], point[1], radius, obstacle.id || 0);
    state.hitNodes.push({
      type: 'obstacle',
      id: obstacle.id,
      label: `${obstacle.kind} #${obstacle.id}`,
      x: point[0],
      y: point[1],
      r: Math.max(12, radius + 6),
    });
  }

  // 7. Surveyor cables (Task 19): taut lines between player-known nodes.
  for (const rope of p.ropes || []) {
    const a = project(rope.a.position[0], rope.a.position[1]);
    const b = project(rope.b.position[0], rope.b.position[1]);
    ctx.strokeStyle = 'rgba(10, 14, 20, 0.55)';
    ctx.lineWidth = 4;
    ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
    ctx.strokeStyle = 'rgba(255, 214, 102, 0.85)';
    ctx.lineWidth = 1.6;
    ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
    for (const point of [a, b]) {
      ctx.fillStyle = '#ffd166';
      ctx.beginPath(); ctx.arc(point[0], point[1], 3.2, 0, TWO_PI); ctx.fill();
      ctx.strokeStyle = 'rgba(0, 0, 0, 0.6)';
      ctx.beginPath(); ctx.arc(point[0], point[1], 5.5, 0, TWO_PI); ctx.stroke();
    }
    const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
    ctx.fillStyle = 'rgba(255, 214, 102, 0.85)';
    ctx.font = '11px monospace';
    ctx.fillText(`${rope.length_3d.toFixed(1)}m`, mid[0] + 5, mid[1] - 4);
    state.hitRopes.push({ id: rope.id, a, b });
  }

  // 8. Placed markers above the terrain.
  for (const marker of p.markers || []) {
    const point = project(marker.position[0], marker.position[1]);
    if (Math.hypot(point[0] - cx, point[1] - cy) > R + 24) continue;
    drawMarker(ctx, point[0], point[1], marker.name, state.selection.includes(marker.name));
    state.hitNodes.push({
      type: 'marker',
      id: marker.name,
      label: marker.name,
      x: point[0],
      y: point[1],
      r: 16,
    });
  }

  // Task 19: node highlights + rubber-band rope preview.
  const highlightNode = (node, colour, pad) => {
    if (!node) return;
    ctx.strokeStyle = colour;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(node.x, node.y, (node.r || 14) + (pad || 3), 0, TWO_PI);
    ctx.stroke();
  };
  highlightNode(state.hoverNode, 'rgba(255, 255, 255, 0.75)', 3);
  if (state.ropeFirst) {
    const first = (state.hitNodes || []).find(
      (node) => node.type === state.ropeFirst.type && String(node.id) === String(state.ropeFirst.id)
    );
    highlightNode(first, 'rgba(77, 171, 247, 0.95)', 4);
    if (first && state.cursor) {
      ctx.setLineDash([6, 5]);
      ctx.strokeStyle = 'rgba(77, 171, 247, 0.8)';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(first.x, first.y);
      ctx.lineTo(state.cursor[0], state.cursor[1]);
      ctx.stroke();
      ctx.setLineDash([]);
    }
  }

  // 8. Beacons dropped by the hotbar.
  for (const beacon of state.beacons) {
    const point = project(beacon.u, beacon.v);
    if (Math.hypot(point[0] - cx, point[1] - cy) > R + 30) continue;
    drawBeaconPin(ctx, point[0], point[1], beacon.life);
  }

  // 9. Eye-pointer bolts: a fading trail from the player centre along the
  //    bearing reported by the server.
  for (const particle of state.particles) {
    const alpha = clamp(particle.life / particle.maxLife, 0, 1);
    if (particle.trail.length > 1) {
      ctx.lineWidth = 3;
      ctx.strokeStyle = `rgba(165, 180, 252, ${0.55 * alpha})`;
      ctx.beginPath();
      for (let k = 0; k < particle.trail.length; k += 1) {
        const point = project(particle.trail[k][0], particle.trail[k][1]);
        if (k === 0) ctx.moveTo(point[0], point[1]); else ctx.lineTo(point[0], point[1]);
      }
      ctx.stroke();
    }
    const head = project(particle.u, particle.v);
    ctx.fillStyle = `rgba(224, 231, 255, ${alpha})`;
    ctx.beginPath(); ctx.arc(head[0], head[1], 4, 0, TWO_PI); ctx.fill();
  }

  // 10. Compass resonance ripple.
  const COMPASS_TIME = 1.1;
  if (state.compassPulse > 0) {
    const progress = 1 - state.compassPulse / COMPASS_TIME;
    ctx.strokeStyle = `rgba(120, 210, 255, ${(1 - progress) * 0.7})`;
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(cx, cy, 20 + progress * R * 0.9, 0, TWO_PI); ctx.stroke();
    ctx.strokeStyle = `rgba(120, 210, 255, ${(1 - progress) * 0.3})`;
    ctx.beginPath(); ctx.arc(cx, cy, 10 + progress * R * 0.55, 0, TWO_PI); ctx.stroke();
  }

  // 11. Player pinned to the centre, with the heading indicator.
  ctx.fillStyle = 'rgba(0, 0, 0, 0.35)';
  ctx.beginPath(); ctx.arc(cx + 2, cy + 3, 8, 0, TWO_PI); ctx.fill();
  ctx.fillStyle = '#ffd166';
  ctx.beginPath(); ctx.arc(cx, cy, 6, 0, TWO_PI); ctx.fill();
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.9)';
  ctx.lineWidth = 1.5;
  ctx.stroke();
  // The physical body radius is drawn as well, so contact with an obstacle disc is visible.
  ctx.strokeStyle = 'rgba(180, 220, 255, 0.45)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.arc(cx, cy, Math.max(3, geometry.playerParam * scale), 0, TWO_PI);
  ctx.stroke();
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(-PHYS.heading);
  ctx.fillStyle = '#4dabf7';
  ctx.beginPath();
  ctx.moveTo(20, 0);
  ctx.lineTo(8, -6);
  ctx.lineTo(8, 6);
  ctx.closePath();
  ctx.fill();
  ctx.restore();

  ctx.restore();

  // Exploration fog: the local slice stays bright, the rim melts away, so the
  // global map can never be read off the screen.
  const fog = ctx.createRadialGradient(cx, cy, R * 0.45, cx, cy, R);
  fog.addColorStop(0, 'rgba(4, 8, 10, 0)');
  fog.addColorStop(0.78, 'rgba(4, 8, 10, 0.18)');
  fog.addColorStop(1, 'rgba(4, 8, 10, 0.9)');
  ctx.fillStyle = fog;
  ctx.fillRect(0, 0, W, H);
  ctx.strokeStyle = 'rgba(120, 150, 130, 0.25)';
  ctx.lineWidth = 1;
  ctx.beginPath(); ctx.arc(cx, cy, R, 0, TWO_PI); ctx.stroke();

  // Compact HUD.
  ctx.fillStyle = 'rgba(232, 242, 228, 0.72)';
  ctx.font = '12px monospace';
  ctx.fillText(`heading ${(PHYS.heading * 180 / Math.PI).toFixed(1)} deg`, 14, 22);
  const slope = PHYS.slope || { slope: 0, speed_scale: 1 };
  ctx.fillText(`slope ${slope.slope >= 0 ? '+' : ''}${slope.slope.toFixed(3)}  x${slope.speed_scale.toFixed(2)}`, 14, H - 14);
  if (PHYS.hitFlash > 0) {
    ctx.fillStyle = 'rgba(255, 120, 120, 0.9)';
    ctx.fillText('blocked', 14, 40);
  }
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

  const signal = state.player ? clamp(state.player.signal, 0, 1) : 0;
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
  ctx.beginPath(); ctx.arc(cx, cy, 5, 0, TWO_PI); ctx.fill();
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

  for (const obstacle of data.obstacles || []) {
    const point = project(obstacle.position[0], obstacle.position[1], obstacle.position[2]);
    ctx.fillStyle = '#ff6b6b';
    ctx.beginPath(); ctx.arc(point[0], point[1], 3.5, 0, TWO_PI); ctx.fill();
  }

  const exitScreen = project(data.exit_position[0], data.exit_position[1], data.exit_position[2]);
  ctx.fillStyle = '#000000';
  ctx.strokeStyle = '#ffffff';
  ctx.lineWidth = 2;
  ctx.beginPath(); ctx.arc(exitScreen[0], exitScreen[1], 6, 0, TWO_PI); ctx.fill(); ctx.stroke();

  const playerScreen = project(data.player_position[0], data.player_position[1], data.player_position[2]);
  ctx.fillStyle = '#ff4d6d';
  ctx.beginPath(); ctx.arc(playerScreen[0], playerScreen[1], 7, 0, TWO_PI); ctx.fill();
}
// ------------------------------------- client-side 60 fps locomotion -----

const PHYS = {
  uv: null,
  heading: 0,
  headingTarget: 0,
  dirty: false,
  syncing: false,
  lastSync: 0,
  slope: { slope: 0, speed_scale: 1 },
  hitFlash: 0,
};

const keysDown = new Set();

function inputAxes() {
  const down = (key) => keysDown.has(key);
  const forward = ((down('w') || down('arrowup')) ? 1 : 0) - ((down('s') || down('arrowdown')) ? 1 : 0);
  const strafe = ((down('d') || down('arrowright')) ? 1 : 0) - ((down('a') || down('arrowleft')) ? 1 : 0);
  return { forward, strafe };
}

// Parameter-space heading of the server's own forward vector, so a brand new
// session starts with the on-screen arrow matching the kernel frame.
function forwardParamAngle(p) {
  const patch = p.patch;
  const forward = p.forward_3d;
  if (!patch || !forward) return p.yaw || 0;
  const nx = patch.x.length;
  const ny = patch.y.length;
  const i = clamp(Math.floor(nx / 2), 1, nx - 2);
  const j = clamp(Math.floor(ny / 2), 1, ny - 2);
  const du = (patch.x[i + 1] - patch.x[i - 1]) || 1e-9;
  const dv = (patch.y[j + 1] - patch.y[j - 1]) || 1e-9;
  const ru = [
    (patch.X[j][i + 1] - patch.X[j][i - 1]) / du,
    (patch.Y[j][i + 1] - patch.Y[j][i - 1]) / du,
    (patch.z[j][i + 1] - patch.z[j][i - 1]) / du,
  ];
  const rv = [
    (patch.X[j + 1][i] - patch.X[j - 1][i]) / dv,
    (patch.Y[j + 1][i] - patch.Y[j - 1][i]) / dv,
    (patch.z[j + 1][i] - patch.z[j - 1][i]) / dv,
  ];
  const E = dot(ru, ru);
  const F = dot(ru, rv);
  const G = dot(rv, rv);
  const det = E * G - F * F;
  if (det < 1e-12) return p.yaw || 0;
  const b1 = dot(forward, ru);
  const b2 = dot(forward, rv);
  return Math.atan2((E * b2 - F * b1) / det, (G * b1 - F * b2) / det);
}

function applySnapshot(snapshot) {
  state.player = state.player ? Object.assign({}, state.player, snapshot) : snapshot;
  if (typeof state.player.scale_factor === 'number' && state.player.scale_factor > 0) {
    state.scaleFactor = state.player.scale_factor;
  }
  if (typeof state.player.difficulty === 'string') {
    state.difficulty = state.player.difficulty;
  }
  syncDetectorLock();
  state.terrainCache = null;
  maybeShowQuestProof();
  if (!PHYS.uv) {
    PHYS.uv = state.player.position.slice();
    PHYS.heading = forwardParamAngle(state.player);
    PHYS.headingTarget = PHYS.heading;
  } else if (!PHYS.dirty) {
    PHYS.uv = state.player.position.slice();
  }
  maybeShowVictory();
}

async function refreshState() {
  applySnapshot(await apiGet('/api/state/player'));
  renderAll();
}

function formatDuration(seconds) {
  const total = Math.max(0, Math.floor(seconds));
  const minutes = String(Math.floor(total / 60)).padStart(2, '0');
  const secs = String(total % 60).padStart(2, '0');
  return `${minutes}:${secs}`;
}

function topologyLabel(mapId) {
  const entry = state.maps.find((item) => item.id === mapId);
  if (!entry) return '-';
  if (entry.topology === 'closed_periodic') return 'closed periodic manifold';
  if (entry.topology === 'bounded_plane') return 'bounded plane';
  return entry.topology;
}

// Task 16: when the server reports the hidden exit was reached, raise the
// victory modal once, with an honest summary of the player's own run.
function maybeShowVictory() {
  const p = state.player;
  if (!p || !p.won || state.victoryShown) return;
  state.victoryShown = true;
  el('victory-steps').textContent = `${p.steps}`;
  el('victory-readings').textContent = `${state.readings}`;
  el('victory-markers').textContent = `${(p.markers || []).length}`;
  el('victory-time').textContent = formatDuration((Date.now() - (state.startedAt || Date.now())) / 1000);
  el('victory-map').textContent = mapLabel(p.map_id);
  el('victory-topology').textContent = topologyLabel(p.map_id);
  el('victory-seed').textContent = `${p.seed}`;
  el('victory-difficulty').textContent = difficultyLabel(state.difficulty);
  el('victory-scale').textContent = `${(state.scaleFactor || 1).toFixed(2)}x`;
  el('victory-score').textContent = `${Math.round(p.score || 0)}`;
  el('victory-modal').classList.remove('hidden');
  message('Exit found - the victory summary is open.', 'ok');
}

function hideVictory() {
  el('victory-modal').classList.add('hidden');
}


// ------------------------------------------- Task 18: quests & proof -----

function renderQuest() {
  const quest = state.player && state.player.quest;
  if (!quest) return;
  const relics = quest.relics || [];
  el('quest-relic-count').textContent = `${relics.length} seal${relics.length === 1 ? '' : 's'}`;
  el('quest-title').textContent = quest.title || 'No active quest';
  el('quest-description').textContent = quest.description || '';
  el('quest-hint').textContent = quest.hint || '';
  const target = quest.target_angle_sum_degrees;
  const current = quest.current_angle_sum_degrees;
  if (typeof target === 'number') {
    el('quest-objective').textContent = quest.objective || 'Angle Sum';
    const shown = typeof current === 'number' ? current.toFixed(1) : '-';
    el('quest-progress-label').textContent = `Angle Sum: ${shown} / ${target.toFixed(1)} deg`;
  } else {
    el('quest-objective').textContent = 'Objective';
    el('quest-progress-label').textContent = 'all seals claimed';
  }
  el('quest-bar-fill').style.width = `${Math.round(clamp(quest.progress || 0, 0, 1) * 100)}%`;
  el('quest-relics').textContent = relics.length ? `Relics: ${relics.join(', ')}` : '';
  el('quest-seal').classList.toggle('hidden', !quest.exit_sealed);
}

let proofFrame = null;

function drawProofFrame(ctx, W, H, time) {
  const bg = ctx.createLinearGradient(0, 0, 0, H);
  bg.addColorStop(0, '#101823');
  bg.addColorStop(1, '#0a0f16');
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, W, H);

  ctx.strokeStyle = 'rgba(120, 160, 200, 0.16)';
  ctx.lineWidth = 1;
  for (let gx = 20; gx <= W; gx += 40) {
    ctx.beginPath();
    for (let y = 0; y <= H; y += 8) {
      const x = gx + 10 * Math.sin((y / H) * Math.PI + gx * 0.02 + time * 0.4);
      if (y === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  for (let gy = 20; gy <= H; gy += 40) {
    ctx.beginPath();
    for (let x = 0; x <= W; x += 8) {
      const y = gy + 9 * Math.cos((x / W) * Math.PI + gy * 0.02 + time * 0.4);
      if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }

  const cx = W / 2;
  const cy = H / 2 + 6;
  const pulse = 1 + 0.06 * Math.sin(time * 2.2);
  const radius = Math.min(W, H) * 0.30 * pulse;
  const vertices = [0, 1, 2].map((k) => {
    const angle = -Math.PI / 2 + k * 2 * Math.PI / 3;
    return [cx + radius * Math.cos(angle), cy + radius * Math.sin(angle)];
  });

  ctx.beginPath();
  for (let k = 0; k < 3; k += 1) {
    const a = vertices[k];
    const b = vertices[(k + 1) % 3];
    const mx = (a[0] + b[0]) / 2;
    const my = (a[1] + b[1]) / 2;
    const ox = mx - cx;
    const oy = my - cy;
    const norm = Math.hypot(ox, oy) || 1;
    const bulge = 16;
    const px = mx + (ox / norm) * bulge;
    const py = my + (oy / norm) * bulge;
    if (k === 0) ctx.moveTo(a[0], a[1]);
    ctx.quadraticCurveTo(px, py, b[0], b[1]);
  }
  ctx.closePath();
  ctx.fillStyle = 'rgba(77, 171, 247, 0.12)';
  ctx.fill();
  ctx.strokeStyle = `rgba(255, 214, 102, ${0.7 + 0.25 * Math.sin(time * 3)})`;
  ctx.lineWidth = 2.5;
  ctx.stroke();

  for (let k = 0; k < 3; k += 1) {
    const v = vertices[k];
    ctx.strokeStyle = 'rgba(120, 210, 255, 0.85)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(v[0], v[1], 16, time * 1.5 + k * 2, time * 1.5 + k * 2 + 1.6);
    ctx.stroke();
    ctx.fillStyle = '#ffd166';
    ctx.beginPath();
    ctx.arc(v[0], v[1], 4, 0, TWO_PI);
    ctx.fill();
  }

  ctx.fillStyle = 'rgba(232, 242, 228, 0.8)';
  ctx.font = '13px monospace';
  const proof = state.proof || {};
  if (typeof proof.angle_sum_degrees === 'number') {
    ctx.fillText(`measured ${proof.angle_sum_degrees.toFixed(1)} deg`, 16, 24);
  }
  if (typeof proof.target_degrees === 'number') {
    ctx.fillText(`target ${proof.target_degrees.toFixed(1)} deg`, 16, 42);
  }
}

function startProofAnimation() {
  stopProofAnimation();
  const canvas = el('proof-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const W = canvas.width;
  const H = canvas.height;
  const started = performance.now();
  const frame = (now) => {
    drawProofFrame(ctx, W, H, (now - started) / 1000);
    proofFrame = window.requestAnimationFrame(frame);
  };
  proofFrame = window.requestAnimationFrame(frame);
}

function stopProofAnimation() {
  if (proofFrame) window.cancelAnimationFrame(proofFrame);
  proofFrame = null;
}

function maybeShowQuestProof() {
  const quest = state.player && state.player.quest;
  if (!quest) return;
  const count = (quest.relics || []).length;
  if (count > (state.shownRelicCount || 0) && quest.last_proof) {
    state.shownRelicCount = count;
    syncDetectorLock();
    renderAll();
    showProof(quest.last_proof);
    hintMessage('Geometric seal claimed - the proof is open.', 'ok');
    return;
  }
  state.shownRelicCount = count;
}

function showProof(proof) {
  state.proof = proof || {};
  state.proofOpen = true;
  el('proof-title').textContent = proof && proof.title ? proof.title : 'Geometric Proof';
  const list = el('proof-steps');
  list.innerHTML = '';
  for (const step of (proof && proof.steps) || []) {
    const item = document.createElement('li');
    item.textContent = step;
    list.appendChild(item);
  }
  el('proof-modal').classList.remove('hidden');
  startProofAnimation();
}

function hideProof() {
  stopProofAnimation();
  state.proofOpen = false;
  el('proof-modal').classList.add('hidden');
}


function continueFreeRoam() {
  hideVictory();
  state.cleared = true;
  el('cleared').classList.remove('hidden');
  message('Cleared - free roam continues, all instruments stay available.', 'ok');
}

function returnToLobby() {
  hideVictory();
  state.cleared = false;
  el('cleared').classList.add('hidden');
  showLobby();
}

function physicsStep(dt) {
  const p = state.player;
  if (!p || !p.patch) return;
  if (!PHYS.uv) PHYS.uv = p.position.slice();

  if (keysDown.has('q')) PHYS.headingTarget -= 1.6 * dt;
  if (keysDown.has('e')) PHYS.headingTarget += 1.6 * dt;
  PHYS.heading = lerpAngle(PHYS.heading, PHYS.headingTarget, Math.min(1, dt * 12));

  const { forward, strafe } = inputAxes();
  if (!forward && !strafe) {
    if (PHYS.dirty && !PHYS.syncing && Date.now() - PHYS.lastSync > 120) syncPosition();
    return;
  }
  let du = forward * Math.cos(PHYS.heading) + strafe * Math.sin(PHYS.heading);
  let dv = forward * Math.sin(PHYS.heading) - strafe * Math.cos(PHYS.heading);
  const magnitude = Math.hypot(du, dv);
  if (magnitude < 1e-9) return;
  du /= magnitude;
  dv /= magnitude;

  const slope = localSlope(p.patch, PHYS.uv, du, dv);
  PHYS.slope = slope;
  const speed = BASE_SPEED * slope.speed_scale * (state.speedMultiplier || 1) / (state.scaleFactor || 1);
  const target = [PHYS.uv[0] + du * speed * dt, PHYS.uv[1] + dv * speed * dt];
  const resolved = resolveHardCollisions(PHYS.uv, target);
  const moved = Math.hypot(resolved.uv[0] - PHYS.uv[0], resolved.uv[1] - PHYS.uv[1]) > 1e-7;
  PHYS.uv = resolved.uv;
  if (resolved.hit && !moved) PHYS.hitFlash = 0.35;
  if (moved) PHYS.dirty = true;
  if (PHYS.dirty && !PHYS.syncing && Date.now() - PHYS.lastSync > SYNC_MS) syncPosition();
}

async function syncPosition() {
  if (!PHYS.uv || PHYS.syncing) return;
  PHYS.syncing = true;
  PHYS.lastSync = Date.now();
  const sent = PHYS.uv.slice();
  try {
    const snapshot = await apiPost('/api/action/sync_position', { u: sent[0], v: sent[1] });
    applySnapshot(snapshot);
    if (Math.hypot(PHYS.uv[0] - sent[0], PHYS.uv[1] - sent[1]) < 1e-9) PHYS.dirty = false;
    if (snapshot.won) message('Exit found - you reached the hidden exit.', 'ok');
  } catch (error) {
    message(error.message, 'error');
  } finally {
    PHYS.syncing = false;
  }
}

function updateEffects(dt) {
  if (state.compassPulse > 0) state.compassPulse = Math.max(0, state.compassPulse - dt);
  if (PHYS.hitFlash > 0) PHYS.hitFlash = Math.max(0, PHYS.hitFlash - dt);
  for (const particle of state.particles) {
    particle.life -= dt;
    const step = particle.speed * dt;
    particle.u += particle.dx * step;
    particle.v += particle.dy * step;
    particle.trail.push([particle.u, particle.v]);
    if (particle.trail.length > 16) particle.trail.shift();
  }
  state.particles = state.particles.filter((particle) => particle.life > 0);
  for (const beacon of state.beacons) beacon.life -= dt;
  state.beacons = state.beacons.filter((beacon) => beacon.life > 0);
}

function spawnPointerBolt(result) {
  if (!PHYS.uv) return;
  let dx = 1;
  let dy = 0;
  if (result && Array.isArray(result.tangent_direction) && result.tangent_direction.length === 2) {
    dx = result.tangent_direction[0];
    dy = result.tangent_direction[1];
  } else if (result && Number.isFinite(result.bearing_degrees)) {
    const angle = result.bearing_degrees * Math.PI / 180;
    dx = Math.cos(angle);
    dy = Math.sin(angle);
  }
  const magnitude = Math.hypot(dx, dy) || 1;
  const viewRadius = (state.player && state.player.patch && state.player.patch.radius) || 1;
  state.particles.push({
    u: PHYS.uv[0],
    v: PHYS.uv[1],
    dx: dx / magnitude,
    dy: dy / magnitude,
    speed: viewRadius * 1.7,
    life: 0.9,
    maxLife: 0.9,
    trail: [[PHYS.uv[0], PHYS.uv[1]]],
  });
}

function spawnBeacon() {
  if (!PHYS.uv) return;
  state.beacons.push({ u: PHYS.uv[0], v: PHYS.uv[1], life: 45, maxLife: 45 });
}

function renderLoop(now) {
  const previous = renderLoop._last || now;
  const dt = Math.min(0.05, Math.max(0, (now - previous) / 1000));
  renderLoop._last = now;
  if (state.player) {
    physicsStep(dt);
    updateEffects(dt);
    drawTopDownWorld();
    renderLoop._readout = (renderLoop._readout || 0) + dt;
    if (renderLoop._readout > 0.1) {
      renderLoop._readout = 0;
      updateReadouts();
      drawGauge();
    }
  }
  window.requestAnimationFrame(renderLoop);
}

// ------------------------------------------------------------ chrome -----

function mapLabel(mapId) {
  const found = state.maps.find((entry) => entry.id === mapId);
  return found ? found.name : (mapId || 'map');
}

function updateReadouts() {
  const p = state.player;
  if (!p) return;
  el('seed').textContent = `seed ${p.seed}`;
  el('map-name').textContent = mapLabel(p.map_id);
  el('steps').textContent = `steps ${p.steps}`;
  el('pointers').textContent = `pointers ${p.pointer_uses_remaining}`;
  const z = (p.position3d || [0, 0, 0])[2] || 0;
  el('position').textContent = `(${p.position[0].toFixed(2)}, ${p.position[1].toFixed(2)}, ${z.toFixed(2)})`;
  el('heading').textContent = `${(PHYS.heading * 180 / Math.PI).toFixed(1)}\u00b0`;
  const slope = PHYS.slope || { slope: 0, speed_scale: 1 };
  const uphill = slope.slope > 0.001;
  el('slope').textContent =
    `${slope.slope >= 0 ? '+' : ''}${slope.slope.toFixed(3)} (x${slope.speed_scale.toFixed(2)}${uphill ? ', uphill' : ''})`;
  if (typeof p.signal === 'number') el('detector-text').textContent = `signal ${p.signal.toFixed(4)} (${p.label}, ${p.trend})`;
  if (typeof p.curvature === 'number') el('curvature').textContent = p.curvature.toFixed(6);
  el('mode').textContent = state.godVisible ? 'god view (debug)' : 'top-down map';
  el('score').textContent = `${Math.round(p.score || 0)}`;
  el('scale-readout').textContent = `${(state.scaleFactor || 1).toFixed(2)}x`;
  el('difficulty-readout').textContent = difficultyLabel(state.difficulty);
  const offline = state.difficulty === 'medium';
  const locked = Boolean(p.detector_locked);
  const offlineNote = el('sensor-offline');
  if (offlineNote) {
    offlineNote.textContent = locked
      ? '[Exit Detector Sealed - complete the geometric trials]'
      : '[Sensor Offline in Medium Mode]';
    offlineNote.classList.toggle('hidden', !(offline || locked));
  }
  const detectorSlot = document.querySelector('.hotbar .slot[data-slot="1"]');
  if (detectorSlot) {
    detectorSlot.classList.toggle('offline', offline && !locked);
    detectorSlot.classList.toggle('locked', locked);
  }
  renderQuest();
  if (state.codexOpen) renderCodex();
}

function difficultyLabel(tier) {
  if (tier === 'medium') return 'Medium';
  if (tier === 'hard') return 'Hard (reserved)';
  return 'Easy';
}

function renderMarkers() {
  const box = el('markers');
  const markers = (state.player && state.player.markers) || [];
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

function message(text, kind) {
  const box = el('message');
  box.textContent = text;
  box.className = 'message' + (kind ? ` ${kind}` : '');
}

function renderAll() {
  drawTopDownWorld();
  drawGauge();
  updateReadouts();
  renderMarkers();
  if (state.godVisible) drawGodView();
}

// ----------------------------------------------------------- actions -----

const DEG = 180 / Math.PI;

let hintTimer = null;

function hintMessage(text, kind, sticky) {
  const box = el('hint-box');
  if (!box) return;
  if (!text) {
    box.classList.add('hidden');
    return;
  }
  box.textContent = text;
  box.className = `hint-box ${kind || 'info'}`;
  if (hintTimer) {
    window.clearTimeout(hintTimer);
    hintTimer = null;
  }
  if (!sticky) {
    hintTimer = window.setTimeout(() => box.classList.add('hidden'), 7000);
  }
}

function askCut(target) {
  state.pendingCut = target;
  hintMessage(
    target === 'all'
      ? 'Cut all ropes? Press y to confirm, n to cancel.'
      : `Cut rope #${target}? Press y to confirm, n to cancel.`,
    'warn',
    true
  );
}

async function runTool(tool) {
  try {
    if (tool === 'scan') {
      if (state.player && state.player.detector_locked) {
        hintMessage('The exit detector is sealed. Complete the geometric trials first.', 'warn');
        return;
      }
      if (state.difficulty === 'medium') {
        hintMessage('[Sensor Offline in Medium Mode]', 'warn');
        return;
      }
      const result = await apiPost('/api/action/tool', { tool });
      state.compassPulse = 1.1;
      if (Number.isFinite(result.readings)) state.readings = result.readings;
      else state.readings += 1;
      await refreshState();
      hintMessage(`Signal ${result.signal.toFixed(4)} (${result.label}, ${result.trend}).`, 'ok');
      return;
    }
    if (tool === 'mark') {
      const count = state.player ? state.player.markers.length : 0;
      const result = await apiPost('/api/action/tool', { tool: 'mark', name: markerName(count) });
      spawnBeacon();
      await refreshState();
      hintMessage(`Marker ${result.name} placed at (${result.position[0].toFixed(2)}, ${result.position[1].toFixed(2)}).`, 'ok');
      return;
    }
    hintMessage(`Unknown tool ${tool}.`, 'error');
  } catch (error) {
    hintMessage(error.message, 'error');
  }
}

async function setGodView(visible) {
  if (Boolean(visible) === Boolean(state.godVisible)) {
    if (state.godVisible) drawGodView();
    return;
  }
  await toggleGodView();
}

async function toggleGodView() {
  state.godVisible = !state.godVisible;
  el('god-panel').classList.toggle('hidden', !state.godVisible);
  el('mode').textContent = state.godVisible ? 'god view (debug)' : 'top-down map';
  if (!state.godVisible) return;
  try {
    state.debugState = await apiGet('/api/state/debug');
  } catch (error) {
    state.debugState = null;
    message(`god view unavailable: ${error.message}`, 'error');
  }
  drawGodView();
}

// -------------------------------------------------------------- lobby -----

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

function updateScaleField() {
  const custom = el('scale-select').value === 'custom';
  el('custom-scale-field').classList.toggle('hidden', !custom);
}

function updateDifficultyNote() {
  const tier = document.querySelector('input[name="difficulty"]:checked').value;
  const note = el('difficulty-note');
  if (tier === 'medium') {
    note.textContent = 'Medium: the distance detector is offline; use the eye pointer, curvature and the goniometer.';
  } else if (tier === 'hard') {
    note.textContent = 'Hard is [Reserved / Work in Progress] - entering uses a safe placeholder with the detector offline.';
  } else {
    note.textContent = '';
  }
}

async function enterWorld() {
  const mapId = el('map-select').value;
  const mode = document.querySelector('input[name="mode"]:checked').value;
  const difficulty = document.querySelector('input[name="difficulty"]:checked').value;
  const seedText = el('seed-input').value.trim();
  const seed = seedText === '' ? null : Number(seedText);
  if (seedText !== '' && !Number.isFinite(seed)) {
    el('lobby-error').textContent = 'The seed must be an integer.';
    return;
  }
  const scaleText = el('scale-select').value;
  const scale = scaleText === 'custom' ? Number(el('custom-scale-input').value) : Number(scaleText);
  if (!Number.isFinite(scale) || scale < 0.2 || scale > 10) {
    el('lobby-error').textContent = 'The map scale S must be a number within [0.2, 10.0].';
    return;
  }
  try {
    await apiPost('/api/session/new', { map_id: mapId, seed, mode, scale, difficulty });
    state.selection = [];
    state.particles = [];
    state.beacons = [];
    state.lastMeasure = null;
    state.pendingCut = null;
    state.angleMeasurements = {};
    state.compassPulse = 0;
    state.terrainCache = null;
    state.scaleFactor = scale;
    state.difficulty = difficulty;
    state.readings = 0;
    state.shownRelicCount = 0;
    state.victoryShown = false;
    state.cleared = false;
    state.startedAt = Date.now();
    hideVictory();
    hideProof();
    el('cleared').classList.add('hidden');
    PHYS.uv = null;
    PHYS.dirty = false;
    PHYS.hitFlash = 0;
    await refreshState();
    hideLobby();
    await setGodView(mode === 'god');
    message(`entered ${mapLabel(mapId)} (${mode}, ${scale.toFixed(2)}x, ${difficultyLabel(difficulty)}) - WASD to run, mouse to aim, Q/E to turn`);
  } catch (error) {
    el('lobby-error').textContent = error.message;
  }
}

// -------------------------------------------------------- input wiring ----

const MOVE_KEYS = ['w', 'a', 's', 'd', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright'];

function selectSlot(slot) {
  state.pendingCut = null;
  state.angleMeasurements = {};
  state.measureTargets = [];
  state.slot = clamp(Math.round(slot), 1, 5);
  state.ropeMode = state.slot === 3;
  state.measureMode = state.slot === 4;
  state.ropeFirst = null;
  state.measureTargets = [];
  for (const button of document.querySelectorAll('.hotbar .slot')) {
    button.classList.toggle('active', Number(button.dataset.slot) === state.slot);
  }
  const capsule = el('measure-mode');
  if (capsule) capsule.classList.toggle('hidden', !state.measureMode);
  const label = document.querySelector(`.hotbar .slot[data-slot="${state.slot}"] span`);
  const name = label ? label.textContent : '';
  if (state.ropeMode) {
    hintMessage('Rope: select two path points.', 'info');
  } else if (state.measureMode) {
    hintMessage('Measure: choose Length or Angle.', 'info');
  } else {
    message(`hand tool ${state.slot}: ${name}`);
  }
}

function useSlot() {
  const slot = state.slot;
  if (slot === 1) {
    if (state.player && state.player.detector_locked) {
      hintMessage('The exit detector is sealed by the academy geometric trial. Complete the quests to unlock it.', 'warn');
      return;
    }
    runTool('scan');
    return;
  }
  if (slot === 2) {
    runTool('mark');
    return;
  }
  if (slot === 3) {
    selectSlot(3);
    hintMessage('Rope: select two path points.', 'info');
    return;
  }
  if (slot === 4) {
    selectSlot(4);
    hintMessage('Measure: choose Length or Angle.', 'info');
    return;
  }
  if (slot === 5) {
    toggleCodex();
    return;
  }
}

function markerName(index) {
  const letter = String.fromCharCode(65 + (index % 26));
  const cycle = Math.floor(index / 26);
  return cycle === 0 ? letter : `${letter}${cycle}`;
}

function sameNode(a, b) {
  return Boolean(a && b && a.type === b.type && String(a.id) === String(b.id));
}

function nodeKeyOf(node) {
  return `${node.type}:${node.id}`;
}

function syncDetectorLock() {
  const quest = state.player && state.player.quest;
  if (quest && typeof quest.exit_sealed === 'boolean') {
    state.player.detector_locked = quest.exit_sealed;
  }
}

function findRopeBetween(a, b) {
  const ropes = (state.player && state.player.ropes) || [];
  return ropes.find(
    (rope) => (sameNode(rope.a, a) && sameNode(rope.b, b)) || (sameNode(rope.a, b) && sameNode(rope.b, a))
  ) || null;
}

function nearestNode(x, y) {
  let best = null;
  for (const node of state.hitNodes || []) {
    const distance = Math.hypot(node.x - x, node.y - y);
    if (distance <= (node.r || 14) && (!best || distance < best.distance)) {
      best = { node, distance };
    }
  }
  return best ? best.node : null;
}

function pointSegmentDistance(px, py, a, b) {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const lengthSq = dx * dx + dy * dy;
  if (lengthSq < 1e-9) return Math.hypot(px - a[0], py - a[1]);
  const t = clamp(((px - a[0]) * dx + (py - a[1]) * dy) / lengthSq, 0, 1);
  return Math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy));
}

function nearestRope(eventOrX, y) {
  let x = eventOrX;
  if (eventOrX && typeof eventOrX === 'object' && eventOrX.clientX !== undefined) {
    const rect = el('map-canvas').getBoundingClientRect();
    x = eventOrX.clientX - rect.left;
    y = eventOrX.clientY - rect.top;
  }
  let best = null;
  for (const rope of state.hitRopes || []) {
    const distance = pointSegmentDistance(x, y, rope.a, rope.b);
    if (distance <= 14 && (!best || distance < best.distance)) best = { rope, distance };
  }
  return best ? best.rope : null;
}

function handleMapClick(event) {
  const rect = el('map-canvas').getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  state.cursor = [x, y];
  if (state.ropeMode) {
    handleRopeClick(x, y);
    return;
  }
  if (state.measureMode) {
    handleMeasureClick(x, y);
    return;
  }
  useSlot();
}

function applyRopeState(result) {
  if (!state.player) return;
  state.player = Object.assign({}, state.player, {
    ropes: result.ropes || [],
    rope_remaining: result.rope_remaining,
    rope_used: result.rope_used,
    rope_total: result.rope_total,
    rope_max_segment: result.rope_max_segment,
  });
}

async function connectRope(a, b) {
  try {
    const result = await apiPost('/api/action/tool', {
      tool: 'rope_connect',
      from_type: a.type,
      from_id: a.id,
      to_type: b.type,
      to_id: b.id,
    });
    applyRopeState(result);
    renderAll();
    hintMessage(`Rope #${result.rope.id} tied: ${result.rope.length_3d.toFixed(2)} m (remaining ${result.rope_remaining.toFixed(2)} m).`, 'ok');
  } catch (error) {
    hintMessage(error.message, 'error');
  }
}

async function cutRope(ropeId) {
  try {
    const result = await apiPost('/api/action/tool', { tool: 'rope_clear', rope_id: ropeId });
    applyRopeState(result);
    renderAll();
    hintMessage(`Rope #${ropeId} cut (remaining ${result.rope_remaining.toFixed(2)} m).`, 'ok');
  } catch (error) {
    hintMessage(error.message, 'error');
  }
}

async function clearRopes() {
  if (!state.player || !(state.player.ropes || []).length) {
    message('No ropes to cut.');
    return;
  }
  try {
    const result = await apiPost('/api/action/tool', { tool: 'rope_clear' });
    applyRopeState(result);
    renderAll();
    hintMessage(`All ropes cut (remaining ${result.rope_remaining.toFixed(2)} m).`, 'ok');
  } catch (error) {
    hintMessage(error.message, 'error');
  }
}

function handleRopeClick(x, y) {
  if (!state.ropeFirst) {
    const node = nearestNode(x, y);
    if (!node) {
      hintMessage('Rope: select two path points.', 'warn');
      return;
    }
    state.ropeFirst = { type: node.type, id: node.id, label: node.label };
    hintMessage(`Rope anchor ${node.label}: click the second path point.`, 'ok');
    return;
  }
  const node = nearestNode(x, y);
  if (!node) {
    hintMessage('Rope: click the second path point.', 'warn');
    return;
  }
  if (sameNode(state.ropeFirst, node)) {
    hintMessage('Rope: choose a different second path point.', 'warn');
    return;
  }
  const first = state.ropeFirst;
  state.ropeFirst = null;
  connectRope(first, node);
}

function setMeasureKind(kind) {
  state.measureKind = kind === 'angle' ? 'angle' : 'length';
  state.measureTargets = [];
  for (const button of document.querySelectorAll('#measure-mode button')) {
    button.classList.toggle('active', button.dataset.mode === state.measureKind);
  }
  if (state.slot !== 4) selectSlot(4);
  hintMessage(
    state.measureKind === 'angle'
      ? 'Angle: pick a path point bound to exactly two ropes (or three markers for a triangle).'
      : 'Length: click a rope (or two path points) to measure it.',
    'info'
  );
}

function countRopesAt(node) {
  const ropes = (state.player && state.player.ropes) || [];
  return ropes.filter(
    (rope) =>
      (rope.a.type === node.type && String(rope.a.id) === String(node.id)) ||
      (rope.b.type === node.type && String(rope.b.id) === String(node.id))
  ).length;
}

async function handleMeasureClick(x, y) {
  if (state.measureKind === 'length') {
    const rope = nearestRope(x, y);
    if (!rope) {
      hintMessage('Length: click a rope to measure it.', 'warn');
      return;
    }
    try {
      const result = await apiPost('/api/action/tool', {
        tool: 'measure',
        mode: 'ruler',
        targets: [{ type: 'rope', id: rope.id }],
      });
      hintMessage(`Rope #${result.rope_id} length: ${result.distance.toFixed(3)} m.`, 'ok');
    } catch (error) {
      hintMessage(error.message, 'error');
    }
    return;
  }

  const node = nearestNode(x, y);
  if (!node) {
    hintMessage('Angle: click a path point with two ropes, or pick three markers.', 'warn');
    return;
  }
  if (countRopesAt(node) === 2) {
    try {
      const result = await apiPost('/api/action/tool', {
        tool: 'measure',
        mode: 'angle',
        targets: [{ type: node.type, id: node.id }],
      });
      const farNodes = (result.far_nodes || []).map((item) => ({ type: item.type, id: item.id, label: item.label }));
      const closing = farNodes.length === 2 ? findRopeBetween(farNodes[0], farNodes[1]) : null;
      if (!closing) {
        hintMessage(`Angle at ${node.label}: ${result.angle_degrees.toFixed(2)} deg.`, 'ok');
        return;
      }
      const vertices = [node, ...farNodes];
      const key = vertices.map(nodeKeyOf).sort().join('|');
      const entry = state.angleMeasurements[key] || { vertices: {}, angles: {} };
      entry.vertices[nodeKeyOf(node)] = node;
      entry.angles[nodeKeyOf(node)] = result.angle_degrees;
      state.angleMeasurements[key] = entry;
      const measured = Object.keys(entry.angles).length;
      if (measured < 3) {
        hintMessage(
          `Angle at ${node.label}: ${result.angle_degrees.toFixed(2)} deg (${measured}/3 vertices measured).`,
          'info'
        );
        return;
      }
      const targets = Object.values(entry.vertices).map((vertex) => ({ type: vertex.type, id: vertex.id }));
      delete state.angleMeasurements[key];
      const summed = await apiPost('/api/action/tool', { tool: 'measure', mode: 'angle_sum', targets });
      hintMessage(
        `Triangle angle sum: ${summed.angle_sum_degrees.toFixed(2)} deg (excess ${summed.excess_degrees.toFixed(2)} deg).`,
        'ok'
      );
      if (summed.quest_completed && summed.proof) {
        state.player = Object.assign({}, state.player, { quest: summed.quest });
        state.shownRelicCount = (summed.quest.relics || []).length;
        syncDetectorLock();
        await refreshState();
        showProof(summed.proof);
        hintMessage('Quest complete - the Curvature Seal is yours!', 'ok');
      } else if (summed.quest) {
        state.player = Object.assign({}, state.player, { quest: summed.quest });
        syncDetectorLock();
        renderAll();
      }
    } catch (error) {
      hintMessage(error.message, 'error');
    }
    return;
  }

  if (node.type !== 'marker') {
    hintMessage(`Angle: ${node.label} needs exactly two ropes.`, 'warn');
    return;
  }
  if (state.measureTargets.some((item) => item.id === node.id)) {
    hintMessage('Angle: that marker is already selected.', 'warn');
    return;
  }
  state.measureTargets.push({ type: 'marker', id: node.id, label: node.label });
  if (state.measureTargets.length < 3) {
    hintMessage(`Angle (triangle): ${state.measureTargets.length}/3 markers selected.`, 'info');
    return;
  }
  const names = state.measureTargets.slice(0, 3).map((item) => item.id);
  state.measureTargets = [];
  try {
    const result = await apiPost('/api/action/tool', { tool: 'measure', mode: 'protractor', targets: names });
    if (result.quest_completed && result.proof) {
      state.player = Object.assign({}, state.player, { quest: result.quest });
      state.shownRelicCount = (result.quest.relics || []).length;
      syncDetectorLock();
      await refreshState();
      showProof(result.proof);
      hintMessage('Quest complete - the Curvature Seal is yours!', 'ok');
    } else {
      if (result.quest) {
        state.player = Object.assign({}, state.player, { quest: result.quest });
        syncDetectorLock();
        renderAll();
      }
      hintMessage(`Angle sum ${names.join(' / ')} = ${(result.sum * DEG).toFixed(2)} deg.`, 'ok');
    }
  } catch (error) {
    hintMessage(error.message, 'error');
  }
}

function toggleCodex(force) {
  const open = force === undefined ? !state.codexOpen : Boolean(force);
  state.codexOpen = open;
  el('codex-modal').classList.toggle('hidden', !open);
  if (open) renderCodex();
}

function renderCodex() {
  const quest = state.player && state.player.quest;
  if (!quest) return;
  el('codex-quest-title').textContent = quest.title || 'No active quest';
  el('codex-quest-description').textContent = quest.description || '';
  el('codex-quest-hint').textContent = quest.hint ? `Hint: ${quest.hint}` : '';
  const target = quest.target_angle_sum_degrees;
  const current = quest.current_angle_sum_degrees;
  el('codex-progress').textContent = typeof target === 'number'
    ? `Angle Sum ${typeof current === 'number' ? current.toFixed(1) : '-'} / ${target.toFixed(1)} deg (${Math.round((quest.progress || 0) * 100)}%)`
    : 'All geometric seals claimed';
  const relics = quest.relics || [];
  el('codex-relics').innerHTML = relics.length
    ? relics.map((relic) => `&#9670; ${relic}`).join('<br />')
    : '<em>none yet</em>';
}

window.addEventListener('keydown', (event) => {
  const key = event.key.toLowerCase();
  if (MOVE_KEYS.includes(key) || key === 'q' || key === 'e') {
    keysDown.add(key);
    event.preventDefault();
    return;
  }
  if (event.repeat) return;
  if (key >= '1' && key <= '5') {
    selectSlot(Number(key));
    return;
  }
  if (state.pendingCut !== null) {
    if (key === 'y') {
      const target = state.pendingCut;
      state.pendingCut = null;
      if (target === 'all') clearRopes();
      else cutRope(target);
    } else if (key === 'n' || key === 'escape') {
      state.pendingCut = null;
      hintMessage('Cut cancelled.', 'info');
    }
    return;
  }
  if (key === ' ') {
    event.preventDefault();
    useSlot();
  } else if (key === 'r') {
    setMeasureKind(state.measureKind === 'angle' ? 'length' : 'angle');
    if (state.slot !== 4) selectSlot(4);
  } else if (key === 'j') {
    toggleCodex();
  } else if (key === 'c') {
    if (state.player && (state.player.ropes || []).length) askCut('all');
  } else if (key === 'escape' && state.proofOpen) {
    hideProof();
  } else if (key === 'escape' && state.codexOpen) {
    toggleCodex(false);
  } else if (key === 'g') toggleGodView();
  else if (key === 'escape' && state.godVisible) toggleGodView();
});

window.addEventListener('keyup', (event) => {
  keysDown.delete(event.key.toLowerCase());
});
window.addEventListener('blur', () => keysDown.clear());

const mapCanvas = el('map-canvas');
mapCanvas.addEventListener('mousemove', (event) => {
  const rect = mapCanvas.getBoundingClientRect();
  const localX = event.clientX - rect.left;
  const localY = event.clientY - rect.top;
  state.cursor = [localX, localY];
  state.hoverNode = nearestNode(localX, localY);
  const x = localX - rect.width / 2;
  const y = localY - rect.height / 2;
  if (Math.hypot(x, y) < 12) return;
  PHYS.headingTarget = Math.atan2(-y, x);
});
mapCanvas.addEventListener('click', (event) => handleMapClick(event));
mapCanvas.addEventListener('contextmenu', (event) => {
  event.preventDefault();
  const rope = nearestRope(event, true);
  if (rope) askCut(rope.id);
});
for (const button of document.querySelectorAll('#measure-mode button')) {
  button.addEventListener('click', () => setMeasureKind(button.dataset.mode));
}
el('codex-close').addEventListener('click', () => toggleCodex(false));

const godCanvas = el('god-canvas');
godCanvas.addEventListener('mousedown', (event) => {
  state.drag = { x: event.clientX, y: event.clientY };
});
window.addEventListener('mouseup', () => { state.drag = null; });
window.addEventListener('mousemove', (event) => {
  if (!state.drag) return;
  state.yaw += (event.clientX - state.drag.x) * 0.01;
  state.pitch = clamp(state.pitch + (event.clientY - state.drag.y) * 0.008, 0.1, 1.4);
  state.drag = { x: event.clientX, y: event.clientY };
  if (state.godVisible) drawGodView();
});

for (const button of document.querySelectorAll('.hotbar .slot')) {
  button.addEventListener('click', (event) => {
    event.stopPropagation();
    const slot = Number(button.dataset.slot);
    selectSlot(slot);
    if (slot === 5) toggleCodex(true);
  });
}
window.addEventListener('wheel', (event) => {
  if (event.target !== mapCanvas) return;
  const next = clamp(state.slot + (event.deltaY > 0 ? 1 : -1), 1, 5);
  selectSlot(next);
});

el('map-select').addEventListener('change', showMapDescription);
el('enter-world').addEventListener('click', enterWorld);
el('scale-select').addEventListener('change', updateScaleField);
for (const radio of document.querySelectorAll('input[name="difficulty"]')) {
  radio.addEventListener('change', updateDifficultyNote);
}
updateScaleField();
updateDifficultyNote();
el('victory-continue').addEventListener('click', continueFreeRoam);
el('victory-lobby').addEventListener('click', returnToLobby);
el('proof-accept').addEventListener('click', hideProof);
el('open-lobby').addEventListener('click', showLobby);
el('step-size').addEventListener('change', (event) => {
  state.speedMultiplier = clamp(Number(event.target.value) || 1, 0.25, 4);
  message(`run speed set to ${state.speedMultiplier}x`);
});

async function init() {
  try {
    window.requestAnimationFrame(renderLoop);
    const payload = await apiGet('/api/maps');
    state.maps = payload.maps || [];
    renderMapOptions(state.maps);
    if (payload.default && state.maps.some((entry) => entry.id === payload.default)) {
      el('map-select').value = payload.default;
    }
    showMapDescription();
    await refreshState();
    showLobby();
    message('Lobby ready: choose a map, a mode and a seed, then click Enter the World.');
  } catch (error) {
    message(`failed to load the lobby: ${error.message}`, 'error');
  }
}

init();