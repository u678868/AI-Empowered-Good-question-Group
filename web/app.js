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
  capabilities: null,
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
  hitCircumcircles: [],
  hoverTriangle: null,
  hoverPullKey: null,
  pullAnimation: null,
  scaleFactor: 1,
  difficulty: 'easy',
  readings: 0,
  victoryShown: false,
  defeatShown: false,
  timeRemaining: null,
  timeRemainingAt: 0,
  timerQuestId: null,
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

function finiteNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function formatAngle(value, digits = 1, fallback = '-') {
  const number = Number(value);
  return Number.isFinite(number) ? `${number.toFixed(digits)} deg` : fallback;
}

function formatLength(value, digits = 2, fallback = '-') {
  const number = Number(value);
  return Number.isFinite(number) ? `${number.toFixed(digits)} m` : fallback;
}

function formatCurvature(value, digits = 5, fallback = '-') {
  const number = Number(value);
  return Number.isFinite(number) ? `${number.toFixed(digits)} m\u207b\u00b2` : fallback;
}
function wrapParameter(value) {
  return ((value + Math.PI) % TWO_PI + TWO_PI) % TWO_PI - Math.PI;
}

function chartPeriods() {
  const periods = state.player && state.player.chart_periods;
  return Array.isArray(periods) && periods.length === 2 ? periods : [TWO_PI, TWO_PI];
}

function isTwistedChart() {
  return !!(state.player && state.player.twisted);
}

function wrapToPeriod(value, period) {
  return ((value + period / 2) % period + period) % period - period / 2;
}

function chartCopyTransforms() {
  const published = state.player && state.player.chart_copies;
  if (Array.isArray(published) && published.length) return published;
  return isTwistedChart() ? [[0, 0, false], [TWO_PI, 0, true]] : [[0, 0, false]];
}

function chartCopies(u, v) {
  return chartCopyTransforms().map((entry) => {
    const du = Number(entry[0]) || 0;
    const dv = Number(entry[1]) || 0;
    const flip = Boolean(entry[2]);
    return [u + du, (flip ? -v : v) + dv];
  });
}

function chartDelta(u, v, refU, refV) {
  if (!(state.player && state.player.periodic)) return [u - refU, v - refV];
  const [periodU, periodV] = chartPeriods();
  let best = [0, 0];
  let bestScore = Infinity;
  for (const [copyU, copyV] of chartCopies(u, v)) {
    const deltaU = wrapToPeriod(copyU - refU, periodU);
    const deltaV = wrapToPeriod(copyV - refV, periodV);
    const score = deltaU * deltaU + deltaV * deltaV;
    if (score < bestScore) {
      bestScore = score;
      best = [deltaU, deltaV];
    }
  }
  return best;
}

function lerpAngle(a, b, t) {
  return a + wrapParameter(b - a) * t;
}

// Nearest representative of a single parameter axis. The axis argument is
// required on twisted charts because u and v may have different periods.
function relativeDelta(a, b, axis) {
  if (!(state.player && state.player.periodic)) return a - b;
  const periods = chartPeriods();
  return wrapToPeriod(a - b, axis === 'v' ? periods[1] : periods[0]);
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
const HILLSHADE_LIGHT = normalize3([-1 / Math.sqrt(3), -1 / Math.sqrt(3), 1 / Math.sqrt(3)]);

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
    const [du, dv] = chartDelta(u, v, cu, cv);
    return [cu + du, cv + dv];
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
      const steep = Math.sqrt(Math.max(0, patch.E[j][i] - 1) + Math.max(0, patch.G[j][i] - 1));
      const elevation = clamp((patch.z[j][i] - zLow) / span, 0, 1);
      const rgb = grassRGB(elevation, steep).map((value) => clamp(value * (0.78 + 0.44 * elevation), 0, 255));
      row.push({ x: patch.x[i], y: patch.y[j], z: patch.z[j][i], rgb });
    }
    grid.push(row);
  }
  const levels = [];
  for (let k = 1; k <= 7; k += 1) levels.push(zLow + span * k / 8);
  return { grid, contours: buildContours(grid, levels), zLow, zHigh };
}

// GIS-style Lambertian hillshading: light from the north-west, natural grass
// brightening on sun-facing slopes and soft shadow in windward troughs.
function applyHillshading(ctx, patch) {
  const view = state.mapView;
  if (!view || !patch || !patch.x || !patch.X) return;
  const project = (u, v) => {
    const [du, dv] = chartDelta(u, v, view.phys[0], view.phys[1]);
    return [view.cx + du * view.scale, view.cy - dv * view.scale];
  };
  const nx = patch.x.length;
  const ny = patch.y.length;
  const stride = nx > 40 ? 2 : 1;
  for (let j = 0; j < ny - stride; j += stride) {
    for (let i = 0; i < nx - stride; i += stride) {
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
      const intensity = clamp(dot(normal, HILLSHADE_LIGHT), 0.55, 1.15);
      const delta = intensity - 1.0;
      if (Math.abs(delta) < 0.008) continue;
      const alpha = clamp(Math.abs(delta) * 0.62, 0, 0.30);
      const p0 = project(patch.x[i], patch.y[j]);
      const p1 = project(patch.x[Math.min(nx - 1, i + stride)], patch.y[j]);
      const p2 = project(patch.x[Math.min(nx - 1, i + stride)], patch.y[Math.min(ny - 1, j + stride)]);
      const p3 = project(patch.x[i], patch.y[Math.min(ny - 1, j + stride)]);
      ctx.fillStyle = delta > 0 ? `rgba(255,255,255,${alpha})` : `rgba(0,0,0,${alpha})`;


      ctx.beginPath();
      ctx.moveTo(p0[0], p0[1]);
      ctx.lineTo(p1[0], p1[1]);
      ctx.lineTo(p2[0], p2[1]);
      ctx.lineTo(p3[0], p3[1]);
      ctx.closePath();
      ctx.fill();
    }
  }
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
  let offset = [relativeDelta(targetUv[0], fromUv[0], 'u'), relativeDelta(targetUv[1], fromUv[1], 'v')];
  let hit = false;
  for (let iteration = 0; iteration < 4; iteration += 1) {
    let adjusted = false;
    for (const obstacle of p.obstacles || []) {
      const centre = [relativeDelta(obstacle.u, fromUv[0], 'u'), relativeDelta(obstacle.v, fromUv[1], 'v')];
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
    const [periodU, periodV] = chartPeriods();
    u = wrapToPeriod(u, periodU);
    v = wrapToPeriod(v, periodV);
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
  const project = (u, v) => {
    const [du, dv] = chartDelta(u, v, phys[0], phys[1]);
    return [cx + du * scale, cy - dv * scale];
  };
  state.mapView = { cx, cy, scale, phys: phys.slice() };
  state.hitNodes = [];
  state.hitRopes = [];
  state.hitCircumcircles = [];

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

  applyHillshading(ctx, patch);

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
    const x = cx + relativeDelta(u, phys[0], 'u') * scale;
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
  }
  const vMin = phys[1] - viewRadius - gridStep;
  const vMax = phys[1] + viewRadius + gridStep;
  for (let k = Math.ceil(vMin / gridStep); k <= Math.floor(vMax / gridStep); k += 1) {
    const v = k * gridStep;
    if (!p.periodic && p.domain && (v < p.domain.y_min || v > p.domain.y_max)) continue;
    const y = cy - relativeDelta(v, phys[1], 'v') * scale;
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
      const sx = cx + relativeDelta(point[0], phys[0], 'u') * scale;
      const sy = cy - relativeDelta(point[1], phys[1], 'v') * scale;
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
      ctx.fillText(formatLength(state.lastMeasure.distance, 2), mx + 6, my - 4);
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
    const visibleLimit = R + 110;
    if (Math.hypot(a[0] - cx, a[1] - cy) > visibleLimit
        || Math.hypot(b[0] - cx, b[1] - cy) > visibleLimit) {
      continue;
    }
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
    ctx.fillText(formatLength(rope.length_3d, 2), mid[0] + 5, mid[1] - 4);
    state.hitRopes.push({ id: rope.id, a, b });
  }

  // 7b. game_task7: pulled circumcircles and the hovered triangle preview.
  for (const circle of p.circumcircles || []) {
    const points = (circle.samples || []).map((sample) => projectCircleSample(circle, sample)).filter(Boolean);
    if (points.length < 3) continue;
    ctx.strokeStyle = 'rgba(0, 0, 0, 0.65)';
    ctx.lineWidth = 6;
    ctx.beginPath();
    for (let index = 0; index < points.length; index += 1) {
      if (index === 0) ctx.moveTo(points[index][0], points[index][1]);
      else ctx.lineTo(points[index][0], points[index][1]);
    }
    ctx.closePath(); ctx.stroke();
    const pullAge = state.pullAnimation ? (performance.now() - state.pullAnimation.started) / 1000 : 2.0;
    const pullProgress = clamp(pullAge / 1.2, 0, 1);
    ctx.strokeStyle = `rgba(255, 214, 102, ${0.35 + 0.60 * pullProgress})`;
    ctx.lineWidth = 2.4 + 2.2 * (1 - pullProgress);
    ctx.beginPath();
    for (let index = 0; index < points.length; index += 1) {
      if (index === 0) ctx.moveTo(points[index][0], points[index][1]);
      else ctx.lineTo(points[index][0], points[index][1]);
    }
    ctx.closePath(); ctx.stroke();
    const labelPoint = points[0];
    ctx.fillStyle = 'rgba(255, 214, 102, 0.95)';
    ctx.font = '11px monospace';
    ctx.fillText(`Circumcircle: C = ${formatLength(Number(circle.perimeter), 2)}`, labelPoint[0] + 6, labelPoint[1] - 8);
    state.hitCircumcircles.push({ id: circle.id, points });
  }
  if (state.ropeMode && state.hoverTriangle) {
    const tri = state.hoverTriangle;
    const circle = screenCircumcircle(tri.points[0], tri.points[1], tri.points[2]);
    if (circle) {
      ctx.save();
      ctx.setLineDash([6, 6]);
      ctx.strokeStyle = `rgba(120, 235, 255, ${0.72 + 0.22 * Math.sin(performance.now() * 0.006)})`;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(circle.center[0], circle.center[1], circle.radius, 0, TWO_PI);
      ctx.stroke();
      ctx.restore();
    }
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
  ctx.fillText(`heading ${formatAngle(PHYS.heading * 180 / Math.PI, 1)}`, 14, 22);
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
  state.capabilities = state.player.capabilities || state.capabilities;
  if (typeof state.player.scale_factor === 'number' && state.player.scale_factor > 0) {
    state.scaleFactor = state.player.scale_factor;
  }
  if (typeof state.player.difficulty === 'string') {
    state.difficulty = state.player.difficulty;
  }
  if (Object.prototype.hasOwnProperty.call(snapshot, 'time_remaining')) {
    if (typeof snapshot.time_remaining === 'number') {
      const serverRemaining = Number(snapshot.time_remaining);
      const localRemaining = currentTimeRemaining();
      const questId = snapshot.quest && snapshot.quest.id ? String(snapshot.quest.id) : null;
      const questLabel = (snapshot.quest && (snapshot.quest.title || snapshot.quest.id)) || 'New trial';
      const questChanged = questId !== null && questId !== state.timerQuestId;
      // The countdown is monotonic: a stale or duplicated payload can never push it
      // back up. The only legitimate restart is a brand new trial being accepted, so
      // that restart is announced in the hint area and is never a surprise.
      const restarted = questChanged && localRemaining !== null && serverRemaining > localRemaining + 0.5;
      if (state.timeRemaining === null || localRemaining === null || questChanged || serverRemaining <= localRemaining + 0.05) {
        state.timeRemaining = serverRemaining;
        state.timeRemainingAt = performance.now();
        if (restarted) hintMessage(`${questLabel} accepted - Hard-mode countdown restarts at full time.`, 'info');
      }
      if (questId !== null) state.timerQuestId = questId;
    } else {
      state.timeRemaining = null;
      state.timeRemainingAt = 0;
      state.timerQuestId = null;
    }
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
  maybeShowDefeat();
}

async function refreshState() {
  applySnapshot(await apiGet('/api/state/player'));
  renderAll();
}

function currentTimeRemaining() {
  if (state.difficulty !== 'hard' || typeof state.timeRemaining !== 'number') return null;
  const elapsed = (performance.now() - (state.timeRemainingAt || performance.now())) / 1000;
  return Math.max(0, state.timeRemaining - elapsed);
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
  if (entry.non_orientable) return 'closed periodic, non-orientable (immersed)';
  if (entry.topology === 'closed_periodic') return 'closed periodic manifold';
  if (entry.topology === 'bounded_plane') return 'bounded plane';
  return entry.topology;
}

// Task 16: when the server reports the hidden exit was reached, raise the
// victory modal once, with an honest summary of the player's own run.
function renderVictoryRelics() {
  const container = el('victory-relics');
  if (!container) return;
  container.innerHTML = '';
  const quest = state.player && state.player.quest;
  const relics = (quest && quest.relics) || [];
  if (!relics.length) {
    const empty = document.createElement('div');
    empty.className = 'victory-relic empty';
    empty.textContent = 'No geometric relics';
    container.appendChild(empty);
    return;
  }
  for (const relic of relics) {
    const card = document.createElement('div');
    card.className = 'victory-relic';
    card.textContent = String(relic);
    container.appendChild(card);
  }
}

const RANK_TITLES = {
  S: 'Archimedean Grandmaster',
  A: 'Geodesic Scholar',
  B: 'Manifold Surveyor',
  C: 'Academy Initiate',
};

function rankTitle(rank) {
  return RANK_TITLES[rank] || RANK_TITLES.C;
}

function renderVictoryScore(p) {
  const score = p.score_breakdown || {};
  const data = score.breakdown || {};
  const multipliers = data.multipliers || {};
  const total = Number(score.total_score ?? p.score ?? 0);
  const rank = score.rank || p.rank || 'C';
  el('victory-rank').textContent = `Rank: ${rank} [${rankTitle(rank)}]`;
  const row = (label, value, totalRow) => `<div class="score-row${totalRow ? ' total' : ''}"><span>${label}</span><strong>${value}</strong></div>`;
  el('victory-breakdown').innerHTML = [
    row('Base Clearance', `+${Math.round(Number(data.base) || 0)}`),
    row('Time Efficiency', `+${Math.round(Number(data.time_bonus) || 0)} (Time: ${formatDuration(Number(p.elapsed_time) || 0)})`),
    row('Frugal Surveyor', `+${Math.round((Number(data.marker_bonus) || 0) + (Number(data.rope_bonus) || 0))} (Pegs: ${Number(data.marker_count) || 0}, Rope Left: ${proofFormat(data.rope_remaining, 2)} m)`),
    row('Tool Discipline', `+${Math.round(Number(data.tool_bonus) || 0)} (${Number(data.measure_calls) || 0} calls)`),
    row('Path Exhaustion', `-${Math.round(Number(data.step_penalty) || 0)} (Effective Steps ${proofFormat(data.effective_steps, 1)})`),
    row('Difficulty & Scale Multiplier', `x${proofFormat(multipliers.combined, 2)} (${difficultyLabel(multipliers.difficulty || state.difficulty)} x ${proofFormat(multipliers.scale_mult, 2)})`),
    row('Final Score', `${Math.round(total)}`, true),
  ].join('');
  el('victory-score').textContent = `${Math.round(total)}`;
}
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
  renderVictoryScore(p);
  renderVictoryRelics();
  el('victory-modal').classList.remove('hidden');
  message('Exit found - the victory summary is open.', 'ok');
}

function hideVictory() {
  el('victory-modal').classList.add('hidden');
}

function maybeShowDefeat() {
  const p = state.player;
  const remaining = currentTimeRemaining();
  const expired = Boolean(p && (p.is_time_expired || (remaining !== null && remaining <= 0)));
  if (!p || !expired || state.defeatShown) return;
  state.defeatShown = true;
  el('defeat-modal').classList.remove('hidden');
  hintMessage('Trial expired - singular collapse.', 'error', true);
}

function continueAfterDefeat() {
  el('defeat-modal').classList.add('hidden');
  message('World remains open in defeated free roam.', 'error');
}


// ------------------------------------------- Task 18: quests & proof -----

function renderQuest() {
  const quest = state.player && state.player.quest;
  if (!quest) return;
  const relics = quest.relics || [];
  el('quest-relic-count').textContent = `${relics.length} seal${relics.length === 1 ? '' : 's'}`;
  const remaining = currentTimeRemaining();
  const timer = el('quest-timer');
  if (timer) {
    const showTimer = state.difficulty === 'hard' && typeof remaining === 'number';
    timer.classList.toggle('hidden', !showTimer);
    timer.classList.toggle('warning', showTimer && remaining <= 30);
    timer.textContent = showTimer ? `Time Remaining: ${formatDuration(remaining)}` : 'Time Remaining: --:--';
  }
  el('quest-title').textContent = quest.title || 'No active quest';
  el('quest-description').textContent = quest.description || '';
  el('quest-hint').textContent = quest.hint || '';
  const fallbackTarget = quest.target_angle_sum_degrees;
  const fallbackCurrent = quest.current_angle_sum_degrees;
  const target = typeof quest.objective_target === 'number' ? quest.objective_target : fallbackTarget;
  let current = typeof quest.objective_current === 'number' ? quest.objective_current : fallbackCurrent;
  const label = quest.objective || 'Objective';
  if (quest.id === 'homotopy_loop' && state.player && state.player.homotopy) {
    current = Number(state.player.homotopy.phase_max_pi) || 0;
  }
  if (quest.id === 'parabolic_line' && typeof current !== 'number') current = 0;
  if (typeof target === 'number') {
    el('quest-objective').textContent = label;
    if (quest.objective_unit === 'ratio') {
      const shown = typeof current === 'number' ? current.toFixed(4) : '-';
      el('quest-progress-label').textContent = `${label}: ${shown} / ${target.toFixed(4)}`;
    } else if (quest.objective_unit === 'count') {
      const shown = typeof current === 'number' ? current.toFixed(0) : '-';
      el('quest-progress-label').textContent = `Parabolic Pegs: ${shown} / ${target.toFixed(0)} (Tolerance: |K| <= 0.004)`;
    } else if (quest.objective_unit === 'pi') {
      const shown = typeof current === 'number' ? current.toFixed(3) : '-';
      el('quest-progress-label').textContent = `Circumnavigation Phase: ${shown} pi / ${target.toFixed(2)} pi (Return to origin to seal)`;
    } else {
      const shown = typeof current === 'number' ? current.toFixed(1) : '-';
      const relation = quest.objective_relation === '<=' ? '<=' : '>=';
      el('quest-progress-label').textContent = `${label}: ${shown} ${relation} ${target.toFixed(1)} deg`;
    }
  } else {
    el('quest-objective').textContent = 'Objective';
    el('quest-progress-label').textContent = 'all seals claimed';
  }
  el('quest-bar-fill').style.width = `${Math.round(clamp(quest.progress || 0, 0, 1) * 100)}%`;
  el('quest-relics').textContent = relics.length ? `Relics: ${relics.join(', ')}` : '';
  el('quest-seal').classList.toggle('hidden', !quest.exit_sealed);
  updateQuestActionButton();
}

function markerNames() {
  return ((state.player && state.player.markers) || []).map((marker) => marker.name);
}

function updateQuestActionButton() {
  const button = el('quest-action');
  if (!button) return;
  const quest = state.player && state.player.quest;
  const id = quest && quest.id;
  if (!id || !['holonomy_loop', 'parabolic_line', 'homotopy_loop'].includes(id)) {
    button.classList.add('hidden');
    return;
  }
  button.classList.remove('hidden');
  if (id === 'holonomy_loop') {
    const calibrated = Boolean(state.player.holonomy && state.player.holonomy.calibrated);
    button.textContent = calibrated ? 'Measure Holonomy' : 'Calibrate Vector';
    button.classList.toggle('ready', calibrated);
  } else if (id === 'parabolic_line') {
    button.textContent = 'Validate 3 Parabolic Pegs';
    button.classList.remove('ready');
  } else {
    button.textContent = 'Seal Homotopy Loop';
    button.classList.toggle('ready', Boolean(state.player.homotopy && state.player.homotopy.origin_label));
  }
}

async function applyQuestMeasurement(result, progressText) {
  if (!state.player) return;
  if (result.holonomy) state.player = Object.assign({}, state.player, { holonomy: result.holonomy });
  if (result.homotopy) state.player = Object.assign({}, state.player, { homotopy: result.homotopy });
  if (result.quest) state.player = Object.assign({}, state.player, { quest: result.quest });
  syncDetectorLock();
  if (result.quest_completed && result.proof) {
    state.shownRelicCount = ((result.quest && result.quest.relics) || []).length;
    await refreshState();
    showProof(result.proof);
    hintMessage(`Quest complete - ${(result.proof && result.proof.relic) || 'the seal'} claimed!`, 'ok');
    return;
  }
  await refreshState();
  hintMessage(progressText || 'Measurement recorded. Continue the field procedure.', 'info');
}

async function runQuestAction() {
  const player = state.player;
  const quest = player && player.quest;
  if (!quest) return;
  try {
    if (quest.id === 'holonomy_loop') {
      const names = markerNames();
      if (!names.length) {
        hintMessage('Holonomy: place a marker A at the base point first.', 'warn');
        return;
      }
      const calibrated = Boolean(player.holonomy && player.holonomy.calibrated);
      const start = (player.holonomy && player.holonomy.start_label && names.includes(player.holonomy.start_label))
        ? player.holonomy.start_label : names[0];
      if (!calibrated) {
        const result = await apiPost('/api/action/tool', {
          tool: 'measure', mode: 'holonomy_calibrate', targets: [{ type: 'marker', id: start }],
        });
        state.player = Object.assign({}, state.player, { holonomy: result.holonomy });
        renderAll();
        hintMessage(`Parallel vector calibrated at ${result.marker}. Walk a closed loop, then measure it.`, 'ok');
        return;
      }
      if (names.length < 3) {
        hintMessage('Holonomy: place at least three ordered path markers around the loop.', 'warn');
        return;
      }
      const selected = (state.selection || []).filter((name) => names.includes(name));
      const targets = selected.length >= 3 ? selected : names.slice(-4);
      const result = await apiPost('/api/action/tool', {
        tool: 'measure', mode: 'holonomy', start, targets,
      });
      await applyQuestMeasurement(
        result,
        `Holonomy angle ${Number(result.abs_angle_degrees || 0).toFixed(2)} deg; keep the loop closed around the height.`
      );
      return;
    }

    if (quest.id === 'parabolic_line') {
      const names = markerNames();
      const selected = (state.selection || []).filter((name) => names.includes(name));
      const targets = selected.length === 3 ? selected : names.slice(-3);
      if (targets.length !== 3) {
        hintMessage('Parabolic: place three pegs and connect them with ropes before validation.', 'warn');
        return;
      }
      const result = await apiPost('/api/action/tool', {
        tool: 'measure', mode: 'parabolic', targets,
      });
      await applyQuestMeasurement(
        result,
        `Parabolic pegs: ${((result.curvatures || []).length)} readings, minimum spacing ${formatLength(Math.min(...(result.pairwise_distances || [0])), 2)}.`
      );
      return;
    }

    if (quest.id === 'homotopy_loop') {
      const origin = player.homotopy && player.homotopy.origin_label;
      if (!origin) {
        hintMessage('Homotopy: place the origin beacon O before circumnavigating.', 'warn');
        return;
      }
      const result = await apiPost('/api/action/tool', {
        tool: 'measure', mode: 'homotopy', origin,
      });
      const tracking = result.homotopy || {};
      await applyQuestMeasurement(
        result,
        `Circumnavigation phase ${Number(tracking.phase_max_pi || 0).toFixed(3)} pi / 1.80 pi; return to O to seal.`
      );
    }
  } catch (error) {
    hintMessage(error.message, 'error');
  }
}

function drawProofFrame(ctx, W, H, clock, timeline, highlight) {
  drawProofBackdrop(ctx, W, H, clock);
  const proof = state.proof || {};
  const kind = proof.kind || 'gauss_bonnet_excess';
  if (kind === 'bdp_circle_deficit') {
    drawBdpProofStage(ctx, W, H, clock, timeline || {}, proof, highlight);
    return;
  }
  if (kind === 'holonomy_loop') {
    drawHolonomyProofStage(ctx, W, H, clock, timeline || {}, proof, highlight);
    return;
  }
  if (kind === 'parabolic_line') {
    drawParabolicProofStage(ctx, W, H, clock, timeline || {}, proof, highlight);
    return;
  }
  if (kind === 'homotopy_loop') {
    drawHomotopyProofStage(ctx, W, H, clock, timeline || {}, proof, highlight);
    return;
  }
  drawGaussProofStage(ctx, W, H, clock, timeline || {}, proof, highlight);
}

function drawProofBackdrop(ctx, W, H, clock) {
  const bg = ctx.createLinearGradient(0, 0, 0, H);
  bg.addColorStop(0, '#101823');
  bg.addColorStop(1, '#070b11');
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, W, H);

  ctx.save();
  ctx.globalAlpha = 0.62;
  ctx.strokeStyle = 'rgba(120, 160, 200, 0.16)';
  ctx.lineWidth = 1;
  for (let gx = 20; gx <= W; gx += 42) {
    ctx.beginPath();
    for (let y = 0; y <= H; y += 10) {
      const x = gx + 9 * Math.sin((y / Math.max(H, 1)) * Math.PI + gx * 0.018 + clock * 0.22);
      if (y === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  for (let gy = 20; gy <= H; gy += 42) {
    ctx.beginPath();
    for (let x = 0; x <= W; x += 10) {
      const y = gy + 8 * Math.cos((x / Math.max(W, 1)) * Math.PI + gy * 0.018 + clock * 0.22);
      if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  ctx.restore();
}

const PROOF_DURATION_MS = 4200;
let proofAnimator = null;

function easeInOutCubic(t) {
  const x = clamp(t, 0, 1);
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
}

function proofNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function proofFormat(value, digits = 3, fallback = '-') {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : fallback;
}

function proofLerp(a, b, t) {
  return a + (b - a) * clamp(t, 0, 1);
}

function proofPhase(timeline, start, end) {
  const progress = clamp((timeline && timeline.progress) || 0, 0, 1);
  if (progress <= start) return 0;
  if (progress >= end) return 1;
  return (progress - start) / Math.max(1e-9, end - start);
}

function proofMath(container, latex, options = {}) {
  const box = document.createElement('div');
  box.className = 'proof-formula';
  if (options.highlight) {
    box.dataset.proofHighlight = options.highlight;
    box.title = 'Hover to highlight the matching geometry.';
  }
  try {
    if (window.katex && typeof window.katex.render === 'function') {
      window.katex.render(latex, box, {
        displayMode: options.displayMode !== false,
        throwOnError: false,
        strict: false,
      });
    } else {
      box.textContent = latex;
      box.classList.add('proof-formula-fallback');
    }
  } catch (error) {
    box.textContent = latex;
    box.classList.add('proof-formula-fallback');
  }
  container.appendChild(box);
  return box;
}

function proofText(container, text) {
  const paragraph = document.createElement('p');
  paragraph.textContent = text;
  container.appendChild(paragraph);
  return paragraph;
}

function proofCard(title) {
  const card = document.createElement('section');
  card.className = 'proof-step-card';
  const heading = document.createElement('h3');
  heading.textContent = title;
  card.appendChild(heading);
  return card;
}

function proofValueGrid(entries) {
  const grid = document.createElement('div');
  grid.className = 'proof-value-grid';
  for (const entry of entries) {
    const value = document.createElement('div');
    value.className = 'proof-value';
    value.textContent = entry[0];
    const strong = document.createElement('strong');
    strong.textContent = entry[1];
    value.appendChild(strong);
    grid.appendChild(value);
  }
  return grid;
}

function renderProofMath(root) {
  if (window.renderMathInElement && root) {
    try {
      window.renderMathInElement(root, {
        delimiters: [
          { left: '$$', right: '$$', display: true },
          { left: '$', right: '$', display: false },
        ],
        throwOnError: false,
      });
    } catch (error) {
      // Dynamic formulas are already rendered individually; this is a fallback.
    }
  }
}

class ProofAnimator {
  constructor(canvas, proof) {
    this.canvas = canvas;
    this.proof = proof || {};
    this.ctx = canvas ? canvas.getContext('2d') : null;
    this.frameId = null;
    this.running = false;
    this.highlight = null;
    this.progress = 0;
    this.phase = 0;
    this.local = 0;
    this.W = 720;
    this.H = 520;
    this.started = performance.now();
    this.tick = this.tick.bind(this);
    this.resize();
  }

  resize() {
    if (!this.canvas || !this.ctx) return;
    const stage = el('proof-stage');
    const stageWidth = stage && stage.clientWidth ? stage.clientWidth - 44 : this.W;
    const cssWidth = clamp(Math.round(stageWidth || 720), 320, 900);
    const cssHeight = clamp(Math.round(cssWidth * 0.72), 320, 560);
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    this.W = cssWidth;
    this.H = cssHeight;
    this.canvas.width = Math.round(cssWidth * ratio);
    this.canvas.height = Math.round(cssHeight * ratio);
    this.canvas.style.height = `${cssHeight}px`;
    this.ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  }

  start() {
    this.stop();
    this.started = performance.now();
    this.progress = 0;
    this.phase = 0;
    this.local = 0;
    this.running = true;
    this.frameId = window.requestAnimationFrame(this.tick);
  }

  stop() {
    this.running = false;
    if (this.frameId !== null) window.cancelAnimationFrame(this.frameId);
    this.frameId = null;
  }

  replay() {
    this.start();
  }

  setStep(index) {
    const step = clamp(Number(index) || 0, 0, 2);
    this.started = performance.now() - (step / 3) * PROOF_DURATION_MS;
    if (!this.running) this.start();
  }

  setHighlight(target) {
    this.highlight = target || null;
    for (const formula of document.querySelectorAll('.proof-formula[data-proof-highlight]')) {
      formula.classList.toggle('is-highlighted', formula.dataset.proofHighlight === this.highlight);
    }
  }

  tick(now) {
    if (!this.running || !this.ctx) return;
    const elapsed = clamp(now - this.started, 0, PROOF_DURATION_MS);
    this.progress = elapsed / PROOF_DURATION_MS;
    this.phase = Math.min(2, Math.floor(this.progress * 3));
    this.local = clamp(this.progress * 3 - this.phase, 0, 1);
    this.updateStepDots();
    drawProofFrame(
      this.ctx,
      this.W,
      this.H,
      now / 1000,
      { progress: this.progress, phase: this.phase, local: this.local },
      this.highlight,
    );
    this.frameId = window.requestAnimationFrame(this.tick);
  }

  updateStepDots() {
    const dots = document.querySelectorAll('#proof-step-dots [data-step]');
    dots.forEach((dot) => {
      dot.classList.toggle('active', Number(dot.dataset.step) === this.phase);
    });
  }
}

function proofStepLabels(kind, isDeficit = false) {
  if (kind === 'gauss_bonnet_excess') return isDeficit ? ['01 Euclidean', '02 Deficit', '03 Negative Flux'] : ['01 Euclidean', '02 Excess', '03 Flux'];
  if (kind === 'bdp_circle_deficit') return ['01 Reference', '02 Cinch', '03 Deficit'];
  if (kind === 'holonomy_loop') return ['01 Loop', '02 Transport', '03 Flux'];
  if (kind === 'parabolic_line') return ['01 Surface', '02 Seam', '03 Asymptotic'];
  if (kind === 'homotopy_loop') return ['01 Torus', '02 Winding', '03 Obstruction'];
  return ['01 Theorem', '02 Field', '03 Relic'];
}

function proofHistoricLabels(proof) {
  const detail = proof && proof.detail ? proof.detail : {};
  const labels = detail.triangle_labels || detail.vertices || [];
  return Array.isArray(labels) && labels.length ? labels.slice(0, 3).join(' / ') : 'A / B / C';
}

const GUIDE_PROOFS = {
  gauss_bonnet_excess: {
    quest_id: 'gauss_bonnet_excess',
    kind: 'gauss_bonnet_excess',
    title: 'Academy Field Guide: Gauss-Bonnet Angle Excess',
    relic: 'Curvature Seal',
    detail: {
      kind: 'gauss_bonnet_excess',
      mode: 'excess',
      is_deficit: false,
      target_relation: '>=',
      measured_sum: 3.4034,
      target_sum: 3.2463,
      excess_rad: 0.2618,
      target_excess_rad: 0.1047,
      angle_sum_degrees: 195.0,
      target_degrees: 186.0,
      excess_degrees: 15.0,
      target_excess_degrees: 6.0,
      reference_excess_rad: 0.2094,
      reference_excess_degrees: 12.0,
      k_max: 0.0184,
      genus: 1,
      markers: ['A', 'B', 'C'],
      relic: 'Curvature Seal',
    },
  },
  bdp_circle_deficit: {
    quest_id: 'bdp_circle_deficit',
    kind: 'bdp_circle_deficit',
    title: 'Academy Field Guide: BDP Circle Deficit',
    relic: 'Metric Seal',
    detail: {
      kind: 'bdp_circle_deficit',
      center: 'O',
      vertices: ['P1', 'P2', 'P3', 'P4'],
      triangle_labels: ['A', 'B', 'C'],
      vertex_count: 48,
      radius: 18.75,
      flat_perimeter: 117.81,
      real_perimeter: 113.25,
      perimeter: 113.25,
      circle_perimeter: 117.81,
      ratio: 0.9613,
      target_ratio: 0.9650,
      deficit: 0.0387,
      deficit_ratio: 0.0387,
      k_est: 0.00875,
      k_estimate: 0.00875,
      k_exact: 0.00902,
      k_analytic: 0.00902,
      relative_error: 0.0299,
      is_circumcircle: true,
      relic: 'Metric Seal',
    },
  },
  holonomy_loop: {
    quest_id: 'holonomy_loop',
    kind: 'holonomy_loop',
    title: 'Academy Field Guide: Levi-Civita Holonomy',
    relic: 'Connection Seal',
    detail: {
      kind: 'holonomy_loop',
      start_vector: [1.0, 0.0],
      end_vector: [0.7071, 0.7071],
      holonomy_angle_deg: 45.0,
      holonomy_angle_rad: Math.PI / 4,
      target_angle_deg: 28.0,
      target_angle_rad: 0.4887,
      area_flux_rad: 0.7854,
      area_flux_deg: 45.0,
      relative_error: 0.0,
      vertex_labels: ['A', 'B', 'C', 'D'],
      vector_start: [1.0, 0.0],
      vector_end: [0.7071, 0.7071],
      transport_steps: 96,
      closure_error: 0.002,
      closure_tolerance: 0.1,
      relic: 'Connection Seal',
    },
  },
  parabolic_line: {
    quest_id: 'parabolic_line',
    kind: 'parabolic_line',
    title: 'Academy Field Guide: Parabolic Seam',
    relic: 'Singularity Seal',
    detail: {
      kind: 'parabolic_line',
      labels: ['P1', 'P2', 'P3'],
      curvatures: [0.0, 0.0001, -0.0002],
      principal_curvatures: [[0.0, -0.20], [0.0, 0.12], [0.0, -0.18]],
      asymptotic_directions: [[1.0, 0.0], [0.8, 0.6], [1.0, 0.0]],
      asymptotic_direction: [1.0, 0.0],
      pegs: [
        { k: 0.0, kappa1: 0.0, kappa2: -0.20 },
        { k: 0.0001, kappa1: 0.0, kappa2: 0.12 },
        { k: -0.0002, kappa1: 0.0, kappa2: -0.18 },
      ],
      pairwise_distances: [3.0, 3.2, 3.1],
      valid_pegs: 3,
      target_pegs: 3,
      tolerance: 0.004,
      tolerance_k: 0.004,
      min_distance: 2.0,
      spacing_ok: true,
      is_parabolic_verified: true,
      relic: 'Singularity Seal',
    },
  },
  homotopy_loop: {
    quest_id: 'homotopy_loop',
    kind: 'homotopy_loop',
    title: 'Academy Field Guide: Homotopy Circumnavigation',
    relic: 'Topology Seal',
    detail: {
      kind: 'homotopy_loop',
      u_start: 0.0,
      u_end: 2 * Math.PI,
      v_start: 0.0,
      v_end: 0.0,
      delta_u: 2 * Math.PI,
      delta_v: 0.0,
      winding_u: 1.0,
      winding_v: 0.0,
      winding_max: 1.0,
      genus: 1,
      fundamental_group: 'Z + Z',
      closure_distance: 0.02,
      capture_radius: 3.0,
      origin_label: 'O',
      current_label: 'O',
      relic: 'Topology Seal',
    },
  },
};

function showExampleGuide() {
  if (state.difficulty !== 'easy') {
    hintMessage('Field Guide preview is available in Easy mode.', 'warn');
    return;
  }
  const quest = state.player && state.player.quest;
  const kind = quest && GUIDE_PROOFS[quest.id] ? quest.id : 'gauss_bonnet_excess';
  const proof = JSON.parse(JSON.stringify(GUIDE_PROOFS[kind]));
  proof.title = 'Academy Field Guide: Theoretical Example Preview';
  proof.__guide = true;
  showProof(proof);
  hintMessage('Field Guide opened - theoretical reference only; no seal is awarded.', 'info');
}
function buildGaussProofCards(proof) {
  const detail = proof && proof.detail ? proof.detail : {};
  const measured = proofNumber(detail.measured_sum, proofNumber(detail.angle_sum_degrees, 180) * Math.PI / 180);
  const excess = proofNumber(detail.excess_rad, measured - Math.PI);
  const target = proofNumber(detail.target_sum, proofNumber(detail.target_degrees, 200) * Math.PI / 180);
  const measuredDeg = measured * 180 / Math.PI;
  const excessDeg = excess * 180 / Math.PI;
  const targetDeg = target * 180 / Math.PI;
  const deficitDeg = proofNumber(detail.angle_deficit_deg, -excessDeg);
  const isDeficit = Boolean(detail.is_deficit || detail.mode === 'deficit');
  const curvatureValue = isDeficit ? proofNumber(detail.k_min, 0) : proofNumber(detail.k_max, 0);
  const cards = [];

  const theorem = proofCard('Governing Theorem');
  if (isDeficit) {
    proofMath(theorem, '\\sum_{i=1}^{3}\\theta_i-\\pi=\\iint_{\\Delta}K\\,dA<0\\implies\\sum_{i=1}^{3}\\theta_i<180^{\\circ}', { highlight: 'curvature' });
    proofText(theorem, 'Inside a negative-curvature saddle, the curvature flux is negative, so the geodesic triangle loses angle and falls below the Euclidean 180 degree reference.');
  } else {
    proofMath(theorem, '\\sum_{i=1}^{3}\\theta_i-\\pi=\\iint_{\\Delta}K\\,dA', { highlight: 'curvature' });
    proofText(theorem, 'For a geodesic triangle on a curved surface, positive angular excess measures the positive curvature flux enclosed by its boundary.');
  }
  cards.push(theorem);

  const field = proofCard('Field Invariants');
  proofMath(field, `\\sum_{i=1}^{3}\\theta_i=${proofFormat(measured, 6)}\\,\\mathrm{rad}=${proofFormat(measuredDeg, 2)}^{\\circ}`, { highlight: 'triangle' });
  proofMath(field, `\\Delta\\theta=${proofFormat(excess, 6)}\\,\\mathrm{rad}=${proofFormat(excessDeg, 2)}^{\\circ}`, { highlight: isDeficit ? 'deficit' : 'excess', displayMode: false });
  field.appendChild(proofValueGrid([
    ['Measured sum', `${proofFormat(measuredDeg, 2)} deg`],
    ['Adaptive target', `${proofFormat(targetDeg, 2)} deg`],
    [isDeficit ? 'Angle deficit' : 'Angle excess', `${proofFormat(isDeficit ? deficitDeg : excessDeg, 2)} deg`],
    [isDeficit ? 'Curvature trough' : 'Curvature peak', formatCurvature(curvatureValue, 5)],
  ]));
  cards.push(field);

  const inversion = proofCard('Curvature Inversion & Discrepancy');
  if (isDeficit) {
    proofMath(inversion, 'K_{\\mathrm{mean}}=\\frac{\\Delta\\theta}{A_{\\Delta}}<0\\quad\\text{and}\\quad \\sum\\theta_i\\le\\theta_{\\mathrm{target}}', { highlight: 'curvature' });
    proofText(inversion, `The measured angle sum is below the prechecked upper target by ${proofFormat(targetDeg - measuredDeg, 2)} degrees once the seal is earned.`);
    inversion.appendChild(proofValueGrid([
      ['Target relation', `<= ${proofFormat(targetDeg, 2)} deg`],
      ['Negative flux', 'verified'],
    ]));
  } else {
    proofMath(inversion, 'K_{\\mathrm{mean}}=\\frac{\\Delta\\theta}{A_{\\Delta}}>0\\quad\\text{and}\\quad \\sum\\theta_i\\ge\\theta_{\\mathrm{target}}', { highlight: 'curvature' });
    proofText(inversion, `The measured angle sum exceeds the prechecked lower target by ${proofFormat(measuredDeg - targetDeg, 2)} degrees once the seal is earned.`);
    inversion.appendChild(proofValueGrid([
      ['Target relation', `>= ${proofFormat(targetDeg, 2)} deg`],
      ['Positive flux', 'verified'],
    ]));
  }
  cards.push(inversion);

  const relic = proofCard('Relic Bestowal');
  proofMath(relic, '\\mathcal{R}_{\\mathrm{Gauss\\!-\\!Bonnet}}=\\mathrm{Curvature\\ Seal}', { highlight: 'relic' });
  proofText(relic, `${proof.relic || 'Curvature Seal'} is now part of the academy ledger. The Gauss-Bonnet survey is complete.`);
  cards.push(relic);
  return cards;
}
function buildBdpProofCards(proof) {
  const detail = proof && proof.detail ? proof.detail : {};
  const radius = proofNumber(detail.radius, detail.mean_radius);
  const flat = proofNumber(detail.flat_perimeter, detail.circle_perimeter);
  const real = proofNumber(detail.real_perimeter, detail.perimeter);
  const ratio = proofNumber(detail.ratio, flat > 0 ? real / flat : 1);
  const deficit = proofNumber(detail.deficit_ratio, 1 - ratio);
  const kEst = proofNumber(detail.k_est, detail.k_estimate);
  const kExact = proofNumber(detail.k_exact, detail.k_analytic);
  const error = proofNumber(detail.relative_error, Math.abs(kExact) > 1e-12 ? Math.abs(kEst - kExact) / Math.abs(kExact) : 0);
  const cards = [];

  const theorem = proofCard('Governing Theorem');
  proofMath(theorem, 'C(r)=2\\pi r-\\frac{\\pi}{3}K r^3+O(r^4)', { highlight: 'circle' });
  proofText(theorem, 'A geodesic circle on a positively curved surface has a shorter circumference than the Euclidean circle of the same radius.');
  cards.push(theorem);

  const field = proofCard('Field Invariants');
  proofMath(field, `R=${proofFormat(radius, 3)}\\,\\mathrm{m},\\quad C_{\\mathrm{flat}}=${proofFormat(flat, 3)}\\,\\mathrm{m},\\quad C_{\\mathrm{real}}=${proofFormat(real, 3)}\\,\\mathrm{m}`, { highlight: 'deficit' });
  proofMath(field, `\\Delta C=1-\\frac{C_{\\mathrm{real}}}{C_{\\mathrm{flat}}}=${proofFormat(deficit * 100, 2)}\\%`, { highlight: 'deficit', displayMode: false });
  field.appendChild(proofValueGrid([
    ['Flat circumference', `${proofFormat(flat, 3)} m`],
    ['Measured circumference', `${proofFormat(real, 3)} m`],
    ['Ratio', proofFormat(ratio, 6)],
    ['Target ratio', proofFormat(detail.target_ratio, 6)],
  ]));
  cards.push(field);

  const inversion = proofCard('Curvature Inversion & Discrepancy');
  proofMath(inversion, 'K_{\\mathrm{est}}=\\frac{3(C_{\\mathrm{flat}}-C_{\\mathrm{real}})}{\\pi R^3}', { highlight: 'curvature' });
  inversion.appendChild(proofValueGrid([
    ['Estimated K', formatCurvature(kEst, 5)],
    ['Analytic K', formatCurvature(kExact, 5)],
    ['Relative error', proofFormat(error * 100, 3) + '%'],
    ['Ring vertices', String(detail.vertex_count || '-')],
  ]));
  proofText(inversion, 'The inversion closes the loop between the measured rope ring and the surface curvature sampled at its centre.');
  cards.push(inversion);

  const relic = proofCard('Relic Bestowal');
  proofMath(relic, '\\mathcal{R}_{\\mathrm{BDP}}=\\mathrm{Metric\\ Seal}', { highlight: 'relic' });
  proofText(relic, `${proof.relic || 'Metric Seal'} is now part of the academy ledger. The geodesic circle has been cinched and verified.`);
  cards.push(relic);
  return cards;
}

function proofVector(value, fallback = [0, 0]) {
  return Array.isArray(value) && value.length >= 2
    ? [proofNumber(value[0], fallback[0]), proofNumber(value[1], fallback[1])]
    : fallback.slice();
}

function proofDirection(value, fallback = [1, 0]) {
  const direction = proofVector(value, fallback);
  const norm = Math.hypot(direction[0], direction[1]);
  if (!Number.isFinite(norm) || norm <= 1e-12) return fallback.slice();
  return [direction[0] / norm, direction[1] / norm];
}

function buildHolonomyProofCards(proof) {
  const detail = proof && proof.detail ? proof.detail : {};
  const start = proofVector(detail.start_vector || detail.vector_start);
  const end = proofVector(detail.end_vector || detail.vector_end);
  const angleRad = proofNumber(detail.holonomy_angle_rad, detail.holonomy_angle);
  const angleDeg = proofNumber(detail.holonomy_angle_deg, detail.holonomy_degrees !== undefined ? detail.holonomy_degrees : angleRad * 180 / Math.PI);
  const targetDeg = proofNumber(detail.target_angle_deg, detail.target_degrees);
  const fluxRad = proofNumber(detail.area_flux_rad);
  const fluxDeg = proofNumber(detail.area_flux_deg, fluxRad * 180 / Math.PI);
  const error = proofNumber(detail.relative_error);
  const cards = [];

  const theorem = proofCard('Governing Theorem');
  proofMath(theorem, '\\Delta\\alpha=\\oint_\\gamma \\Gamma^k_{ij}v^j\\,dx^i\\equiv\\iint_\\Omega K\\,dA\\pmod{2\\pi}', { highlight: 'loop' });
  proofText(theorem, 'Parallel transport around a closed loop measures the curvature flux enclosed by the loop, up to the integer winding ambiguity of a full rotation.');
  cards.push(theorem);

  const vectors = proofCard('Start & End Tangent Vectors');
  proofMath(vectors, `\\vec v_{\\mathrm{start}}=(${proofFormat(start[0], 5)},${proofFormat(start[1], 5)})^\\top\\;\\longrightarrow\\;\\vec v_{\\mathrm{end}}=(${proofFormat(end[0], 5)},${proofFormat(end[1], 5)})^\\top`, { highlight: 'vector' });
  vectors.appendChild(proofValueGrid([
    ['Start vector', `(${proofFormat(start[0], 5)}, ${proofFormat(start[1], 5)})`],
    ['End vector', `(${proofFormat(end[0], 5)}, ${proofFormat(end[1], 5)})`],
    ['Transport steps', String(detail.transport_steps || '-')],
    ['Closure error', `${proofFormat(detail.closure_error, 4)} m`],
  ]));
  cards.push(vectors);

  const flux = proofCard('Holonomy & Curvature Flux');
  proofMath(flux, `\\Delta\\alpha=${proofFormat(angleDeg, 2)}^\\circ,\\quad \\iint_\\Omega K\\,dA=${proofFormat(fluxDeg, 2)}^\\circ\\quad(\\varepsilon=${proofFormat(error * 100, 3)}\\%)`, { highlight: 'flux' });
  flux.appendChild(proofValueGrid([
    ['Measured holonomy', `${proofFormat(angleDeg, 2)} deg`],
    ['Reference flux', `${proofFormat(fluxDeg, 2)} deg`],
    ['Target threshold', `${proofFormat(targetDeg, 2)} deg`],
    ['Relative error', `${proofFormat(error * 100, 3)}%`],
  ]));
  cards.push(flux);

  const relic = proofCard('Relic Bestowal');
  proofMath(relic, '\\mathcal{R}_{\\mathrm{Connection}}=\\mathrm{Connection\\ Seal}', { highlight: 'relic' });
  proofText(relic, `${proof.relic || 'Connection Seal'} confirms that the transported vector remembers the curvature flux of the closed loop.`);
  cards.push(relic);
  return cards;
}

function buildParabolicProofCards(proof) {
  const detail = proof && proof.detail ? proof.detail : {};
  const labels = detail.labels || ['P1', 'P2', 'P3'];
  const curvatures = detail.curvatures || [];
  const principal = detail.principal_curvatures || [];
  const pegs = Array.isArray(detail.pegs) && detail.pegs.length
    ? detail.pegs
    : labels.map((_label, index) => ({
        k: proofNumber(curvatures[index], 0),
        kappa1: proofNumber(principal[index] && principal[index][0], 0),
        kappa2: proofNumber(principal[index] && principal[index][1], 0),
      }));
  const direction = proofDirection(detail.asymptotic_direction || [1, 0]);
  const tolerance = proofNumber(detail.tolerance_k, detail.tolerance);
  const verified = Boolean(detail.is_parabolic_verified);
  const cards = [];

  const theorem = proofCard('Principal Curvature Identity');
  proofMath(theorem, 'K=\\kappa_1\\kappa_2=\\frac{LN-M^2}{EG-F^2}=0\\iff \\kappa_1=0,\\ \\kappa_2\\ne0', { highlight: 'seam' });
  proofText(theorem, 'A parabolic seam is the zero-curvature boundary where one principal curvature vanishes while the other remains nonzero.');
  cards.push(theorem);

  const field = proofCard('Parabolic Peg Measurements');
  pegs.slice(0, 3).forEach((peg, index) => {
    proofMath(field, `P_{${index + 1}}: K\\approx ${formatCurvature(peg.k, 5)},\\quad \\kappa_1\\approx ${proofFormat(peg.kappa1, 5) + ' m\u207b\u00b9'},\\quad \\kappa_2\\approx ${proofFormat(peg.kappa2, 5) + ' m\u207b\u00b9'}\\ \\mathrm{m}^{-1}`, { highlight: 'pegs', displayMode: false });
  });
  field.appendChild(proofValueGrid([
    ['Valid pegs', `${detail.valid_pegs !== undefined ? detail.valid_pegs : pegs.length} / 3`],
    ['Tolerance |K|', formatCurvature(tolerance, 5)],
    ['Spacing verified', detail.spacing_ok ? 'yes' : 'no'],
    ['Seam verified', verified ? 'yes' : 'no'],
  ]));
  cards.push(field);

  const asymptotic = proofCard('Asymptotic Direction');
  proofMath(asymptotic, `II(\\vec v_{\\mathrm{asymp}},\\vec v_{\\mathrm{asymp}})\\approx0,\\quad \\vec v_{\\mathrm{asymp}}=(${proofFormat(direction[0], 5)},${proofFormat(direction[1], 5)})`, { highlight: 'asymptotic' });
  proofText(asymptotic, 'The highlighted direction is the null eigenvector of the second fundamental form at the parabolic seam.');
  cards.push(asymptotic);

  const relic = proofCard('Relic Bestowal');
  proofMath(relic, '\\mathcal{R}_{\\mathrm{Singularity}}=\\mathrm{Singularity\\ Seal}', { highlight: 'relic' });
  proofText(relic, `${proof.relic || 'Singularity Seal'} is awarded for tracing the zero-curvature seam and verifying its asymptotic tangent.`);
  cards.push(relic);
  return cards;
}

function buildHomotopyProofCards(proof) {
  const detail = proof && proof.detail ? proof.detail : {};
  const uStart = proofNumber(detail.u_start, 0);
  const uEnd = proofNumber(detail.u_end, proofNumber(detail.delta_u));
  const deltaU = proofNumber(detail.delta_u, uEnd - uStart);
  const windingU = proofNumber(detail.winding_u, deltaU / (2 * Math.PI));
  const windingV = proofNumber(detail.winding_v);
  const deltaV = proofNumber(detail.delta_v, windingV * 2 * Math.PI);
  const genus = detail.genus !== undefined && detail.genus !== null ? detail.genus : '-';
  const group = detail.fundamental_group || 'Z + Z';
  const cards = [];

  const theorem = proofCard('Discrete Winding Number');
  proofMath(theorem, 'n_u=\\frac{1}{2\\pi}\\oint_\\gamma du\\in\\mathbb Z,\\quad [\\gamma]\\in\\pi_1(\\mathbb T^2)\\cong\\mathbb Z\\oplus\\mathbb Z', { highlight: 'torus' });
  proofText(theorem, 'The unwrapped coordinate change records the homotopy class of the closed path on the torus.');
  cards.push(theorem);

  const cover = proofCard('Universal Cover Phase');
  proofMath(cover, `\\Delta u=u_{\\mathrm{end}}-u_{\\mathrm{start}}=${proofFormat(deltaU, 3)}\\approx${proofFormat(deltaU / Math.PI, 3)}\\pi\\implies n_u=${proofFormat(windingU, 3)},\\ n_v=${proofFormat(windingV, 3)}`, { highlight: 'winding' });
  cover.appendChild(proofValueGrid([
    ['u start', proofFormat(uStart, 3)],
    ['u end', proofFormat(uEnd, 3)],
    ['Delta v', proofFormat(deltaV, 3)],
    ['Capture radius', `${proofFormat(detail.capture_radius, 3)} m`],
  ]));
  cards.push(cover);

  const obstruction = proofCard('Topological Obstruction');
  proofMath(obstruction, `[\\gamma]=(${proofFormat(windingU, 2)},${proofFormat(windingV, 2)})\\ne(0,0)\\implies \\gamma\\not\\sim\\mathrm{point}\\quad(\\mathrm{Genus}\\ g=${genus})`, { highlight: 'hole' });
  proofText(obstruction, `The fundamental group is ${group}; the central hole prevents the lasso from contracting to a point.`);
  cards.push(obstruction);

  const relic = proofCard('Relic Bestowal');
  proofMath(relic, '\\mathcal{R}_{\\mathrm{Topology}}=\\mathrm{Topology\\ Seal}', { highlight: 'relic' });
  proofText(relic, `${proof.relic || 'Topology Seal'} marks a non-contractible circumnavigation of the closed surface.`);
  cards.push(relic);
  return cards;
}
function buildGenericProofCards(proof) {
  const cards = [];
  const theorem = proofCard('Governing Theorem');
  proofText(theorem, proof.theorem || 'The field measurement is checked against the local geometric invariant.');
  cards.push(theorem);
  const steps = proof.steps || [];
  steps.forEach((step, index) => {
    const card = proofCard(`Field Step ${index + 1}`);
    proofText(card, String(step));
    cards.push(card);
  });
  const relic = proofCard('Relic Bestowal');
  proofMath(relic, `\\mathcal{R}=\\text{${String(proof.relic || 'Geometric Seal').replace(/\s+/g, '\\ ')}}`, { highlight: 'relic' });
  cards.push(relic);
  return cards;
}

function buildProofCards(proof) {
  if (proof && proof.kind === 'gauss_bonnet_excess') return buildGaussProofCards(proof);
  if (proof && proof.kind === 'bdp_circle_deficit') return buildBdpProofCards(proof);
  if (proof && proof.kind === 'holonomy_loop') return buildHolonomyProofCards(proof);
  if (proof && proof.kind === 'parabolic_line') return buildParabolicProofCards(proof);
  if (proof && proof.kind === 'homotopy_loop') return buildHomotopyProofCards(proof);
  return buildGenericProofCards(proof || {});
}

function drawAngleLedger(ctx, cx, cy, width, measured, phase, highlight) {
  const total = Math.PI + (measured - Math.PI) * phase;
  const radius = Math.min(width * 0.5, 118);
  const segment = total / 3;
  const start = Math.PI;
  const colors = ['rgba(77, 171, 247, 0.42)', 'rgba(81, 207, 102, 0.38)', 'rgba(255, 214, 102, 0.44)'];
  ctx.save();
  ctx.translate(cx, cy);
  ctx.lineWidth = 1.2;
  for (let index = 0; index < 3; index += 1) {
    const from = start + segment * index;
    const to = start + segment * (index + 1);
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.arc(0, 0, radius, from, to);
    ctx.closePath();
    ctx.fillStyle = colors[index];
    ctx.fill();
    ctx.strokeStyle = 'rgba(232, 242, 228, 0.38)';
    ctx.stroke();
  }
  const gap = Math.max(0, Math.PI - total);
  if (gap > 1e-6) {
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.arc(0, 0, radius, Math.PI + total, Math.PI * 2);
    ctx.closePath();
    ctx.fillStyle = 'rgba(150, 126, 204, ' + (0.24 + 0.22 * (highlight === 'deficit' || highlight === 'curvature' ? 1 : 0)) + ')';

    ctx.fill();
    ctx.strokeStyle = 'rgba(190, 156, 235, 0.9)';
    ctx.lineWidth = 2;
    ctx.stroke();
  }
  const excess = Math.max(0, total - Math.PI);
  if (excess > 1e-6) {
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.arc(0, 0, radius, Math.PI * 2, Math.PI * 2 + excess);
    ctx.closePath();
    ctx.fillStyle = `rgba(255, 214, 102, ${0.38 + 0.22 * (highlight === 'excess' || highlight === 'curvature' ? 1 : 0)})`;
    ctx.fill();
    ctx.strokeStyle = '#ffd166';
    ctx.lineWidth = 2;
    ctx.stroke();
  }
  ctx.strokeStyle = 'rgba(232, 242, 228, 0.55)';
  ctx.beginPath();
  ctx.moveTo(-radius, 0);
  ctx.lineTo(radius, 0);
  ctx.stroke();
  ctx.fillStyle = '#f3e5ab';
  ctx.font = '12px monospace';
  ctx.textAlign = 'center';
  ctx.fillText(`Sigma theta = ${(total * 180 / Math.PI).toFixed(1)} deg`, 0, -radius - 12);
  ctx.restore();
}

function sampleQuadratic(a, control, b, steps = 16) {
  const points = [];
  for (let index = 0; index <= steps; index += 1) {
    const t = index / steps;
    const one = 1 - t;
    points.push([
      one * one * a[0] + 2 * one * t * control[0] + t * t * b[0],
      one * one * a[1] + 2 * one * t * control[1] + t * t * b[1],
    ]);
  }
  return points;
}

function proofTriangleEdges(vertices, cx, cy, bulge) {
  return vertices.map((a, index) => {
    const b = vertices[(index + 1) % vertices.length];
    const mx = (a[0] + b[0]) / 2;
    const my = (a[1] + b[1]) / 2;
    const ox = mx - cx;
    const oy = my - cy;
    const norm = Math.hypot(ox, oy) || 1;
    const control = [mx + ox / norm * bulge, my + oy / norm * bulge];
    return sampleQuadratic(a, control, b, 18);
  });
}

function traceProofPolyline(ctx, points, close = false) {
  if (!points.length) return;
  ctx.beginPath();
  ctx.moveTo(points[0][0], points[0][1]);
  for (let index = 1; index < points.length; index += 1) ctx.lineTo(points[index][0], points[index][1]);
  if (close) ctx.closePath();
}

function drawGaussProofStage(ctx, W, H, clock, timeline, proof, highlight) {
  const detail = proof && proof.detail ? proof.detail : {};
  const measured = proofNumber(detail.measured_sum, proofNumber(detail.angle_sum_degrees, 180) * Math.PI / 180);
  const excess = proofNumber(detail.excess_rad, measured - Math.PI);
  const isDeficit = Boolean(detail.is_deficit || detail.mode === 'deficit');
  const p1 = easeInOutCubic(proofPhase(timeline, 0, 0.34));
  const p2 = easeInOutCubic(proofPhase(timeline, 0.28, 0.68));
  const p3 = easeInOutCubic(proofPhase(timeline, 0.62, 1));
  const cx = W / 2;
  const cy = H * 0.44;
  const radius = Math.min(W * 0.32, H * 0.34);
  const vertices = [0, 1, 2].map((index) => {
    const angle = -Math.PI / 2 + index * TWO_PI / 3;
    return [cx + radius * Math.cos(angle), cy + radius * Math.sin(angle)];
  });
  const straight = vertices.map((point) => point.slice());
  const bulge = isDeficit ? -(8 + 30 * p2 + 8 * p3) : (8 + 34 * p2 + 10 * p3);
  const edges = proofTriangleEdges(vertices, cx, cy, bulge);
  const pulse = 0.5 + 0.5 * Math.sin(clock * 2.6);
  const curvatureHot = ['curvature', 'excess', 'triangle', 'deficit'].includes(highlight);
  const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius * 1.35);
  glow.addColorStop(0, isDeficit ? `rgba(150, 126, 204, ${0.06 + 0.18 * p3})` : `rgba(255, 214, 102, ${0.05 + (0.16 + (curvatureHot ? 0.12 : 0)) * p3})`);
  glow.addColorStop(0.62, isDeficit ? 'rgba(205, 180, 230, 0.08)' : `rgba(77, 171, 247, ${0.035 + 0.06 * p2})`);
  glow.addColorStop(1, 'rgba(7, 11, 17, 0)');
  ctx.save();
  ctx.fillStyle = glow;
  ctx.beginPath();
  const flat = edges.flat();
  traceProofPolyline(ctx, flat, true);
  ctx.fill();
  ctx.restore();

  ctx.save();
  ctx.setLineDash([6, 6]);
  ctx.strokeStyle = `rgba(205, 212, 224, ${0.35 + 0.45 * (1 - p2)})`;
  ctx.lineWidth = 1.4;
  traceProofPolyline(ctx, straight, true);
  ctx.stroke();
  ctx.restore();

  ctx.save();
  ctx.setLineDash([]);
  ctx.lineWidth = 2.6;
  ctx.strokeStyle = isDeficit ? `rgba(190, 156, 235, ${0.72 + 0.18 * pulse})` : `rgba(255, 214, 102, ${0.82 + 0.16 * pulse})`;
  ctx.shadowColor = isDeficit ? 'rgba(170, 135, 220, 0.75)' : (curvatureHot ? '#ffd166' : 'rgba(77, 171, 247, 0.55)');
  ctx.shadowBlur = 12 + (curvatureHot ? 16 : 0);
  for (const edge of edges) {
    traceProofPolyline(ctx, edge, false);
    ctx.stroke();
  }
  ctx.restore();

  for (let index = 0; index < vertices.length; index += 1) {
    const vertex = vertices[index];
    const next = vertices[(index + 1) % 3];
    const previous = vertices[(index + 2) % 3];
    const a1 = Math.atan2(previous[1] - vertex[1], previous[0] - vertex[0]);
    const a2 = Math.atan2(next[1] - vertex[1], next[0] - vertex[0]);
    const arcRadius = 20 + 5 * p2;
    ctx.save();
    ctx.strokeStyle = isDeficit ? 'rgba(190, 156, 235, 0.9)' : (curvatureHot && p3 > 0.1 ? '#ffd166' : 'rgba(120, 210, 255, 0.72)');
    ctx.fillStyle = isDeficit ? `rgba(150, 126, 204, ${0.07 + 0.18 * p3})` : `rgba(255, 214, 102, ${0.06 + 0.18 * p3})`;
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    ctx.moveTo(vertex[0], vertex[1]);
    ctx.arc(vertex[0], vertex[1], arcRadius, a1, a2, false);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
    ctx.restore();
    ctx.fillStyle = isDeficit ? '#c7a8ff' : '#ffd166';
    ctx.beginPath();
    ctx.arc(vertex[0], vertex[1], 4, 0, TWO_PI);
    ctx.fill();
  }

  drawAngleLedger(ctx, cx, H - 48, Math.min(W * 0.72, 360), measured, p3, highlight);

  ctx.fillStyle = 'rgba(232, 242, 228, 0.82)';
  ctx.font = '12px monospace';
  ctx.textAlign = 'left';
  const signedAngle = isDeficit ? -proofNumber(detail.angle_deficit_deg, -excess * 180 / Math.PI) : excess * 180 / Math.PI;
  ctx.fillText(isDeficit ? `measured deficit = ${Math.abs(signedAngle).toFixed(2)} deg` : `measured excess = ${signedAngle.toFixed(2)} deg`, 16, 24);
  ctx.fillText(`phase = ${(p2 > 0 ? p2 > 0.95 ? 'curvature flux' : 'geodesic bend' : 'Euclidean reference')}`, 16, 42);
  if (p3 > 0.02) {
    ctx.fillStyle = isDeficit ? 'rgba(150, 126, 204, ' + (0.18 + 0.18 * pulse) + ')' : 'rgba(255, 214, 102, ' + (0.18 + 0.18 * pulse) + ')';
    ctx.beginPath();
    ctx.arc(cx, cy, radius * 1.12, 0, TWO_PI);
    ctx.fill();
  }
}

function drawBdpProofStage(ctx, W, H, clock, timeline, proof, highlight) {
  const detail = proof && proof.detail ? proof.detail : {};
  const ratio = clamp(proofNumber(detail.ratio, 1 - proofNumber(detail.deficit_ratio, 0.05)), 0.1, 1.2);
  const deficit = clamp(proofNumber(detail.deficit_ratio, 1 - ratio), 0, 0.8);
  const p1 = easeInOutCubic(proofPhase(timeline, 0, 0.32));
  const p2 = easeInOutCubic(proofPhase(timeline, 0.28, 0.72));
  const p3 = easeInOutCubic(proofPhase(timeline, 0.66, 1));
  const cx = W / 2;
  const cy = H * 0.44;
  const flatRadius = Math.min(W * 0.31, H * 0.34);
  const targetRadius = flatRadius * clamp(ratio, 0.35, 1);
  const startRadius = flatRadius * 0.68;
  const overshoot = Math.sin(Math.PI * p2) * flatRadius * 0.08;
  const ropeRadius = proofLerp(startRadius, targetRadius, p2) + overshoot;
  const pulse = 0.5 + 0.5 * Math.sin(clock * 2.8);
  const deficitHot = highlight === 'deficit';
  const circleHot = highlight === 'circle';

  ctx.save();
  ctx.setLineDash([8, 6]);
  ctx.strokeStyle = `rgba(205, 212, 224, ${0.42 + 0.42 * p1})`;
  ctx.lineWidth = circleHot ? 2.3 : 1.5;
  ctx.beginPath();
  ctx.arc(cx, cy, flatRadius, 0, TWO_PI);
  ctx.stroke();
  ctx.restore();

  const triangle = [0, 1, 2].map((index) => {
    const angle = -Math.PI / 2 + index * TWO_PI / 3;
    return [cx + flatRadius * 0.62 * Math.cos(angle), cy + flatRadius * 0.62 * Math.sin(angle)];
  });
  ctx.save();
  ctx.setLineDash([5, 5]);
  ctx.strokeStyle = 'rgba(120, 235, 255, 0.82)';
  ctx.lineWidth = 1.5;
  traceProofPolyline(ctx, triangle, true);
  ctx.stroke();
  ctx.restore();
  for (const point of triangle) {
    ctx.fillStyle = '#78ebff';
    ctx.beginPath();
    ctx.arc(point[0], point[1], 4, 0, TWO_PI);
    ctx.fill();
  }

  if (p3 > 0.001) {
    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, flatRadius, 0, TWO_PI);
    ctx.arc(cx, cy, targetRadius, 0, TWO_PI, true);
    ctx.fillStyle = `rgba(120, 210, 255, ${0.06 + 0.15 * p3 + (deficitHot ? 0.10 : 0)})`;
    ctx.fill();
    ctx.restore();
  }

  ctx.save();
  ctx.strokeStyle = `rgba(255, 214, 102, ${0.72 + 0.24 * pulse})`;
  ctx.shadowColor = 'rgba(255, 214, 102, 0.65)';
  ctx.shadowBlur = 10 + (highlight === 'rope' ? 15 : 0);
  ctx.lineWidth = 2.8;
  ctx.beginPath();
  const sides = 72;
  for (let index = 0; index <= sides; index += 1) {
    const angle = TWO_PI * index / sides;
    const ripple = 1 + Math.sin(angle * 5 + clock * 3.2) * 0.012 * p2;
    const x = cx + ropeRadius * ripple * Math.cos(angle);
    const y = cy + ropeRadius * ripple * Math.sin(angle);
    if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.closePath();
  ctx.stroke();
  ctx.restore();

  ctx.setLineDash([4, 4]);
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.48)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(cx + ropeRadius, cy);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = '#e0e7ff';
  ctx.beginPath();
  ctx.arc(cx, cy, 5, 0, TWO_PI);
  ctx.fill();
  ctx.fillStyle = 'rgba(232, 242, 228, 0.84)';
  ctx.font = '12px monospace';
  ctx.textAlign = 'left';
  ctx.fillText(`C_flat = ${proofFormat(detail.flat_perimeter, 2)} m`, 16, 24);
  ctx.fillText(`C_real = ${proofFormat(detail.real_perimeter, 2)} m`, 16, 42);
  ctx.fillText(`deficit = ${(deficit * 100).toFixed(2)}%`, 16, 60);
  ctx.fillStyle = deficitHot ? '#ffd166' : '#78ebff';
  ctx.textAlign = 'center';
  ctx.fillText(`phase = ${p3 > 0.5 ? 'deficit band' : p2 > 0.1 ? 'rope cinch' : 'Euclidean reference'}`, cx, H - 28);
}

function proofPointLerp(a, b, t) {
  return [proofLerp(a[0], b[0], t), proofLerp(a[1], b[1], t)];
}

function proofPolylineLength(points) {
  let total = 0;
  for (let index = 1; index < points.length; index += 1) {
    total += Math.hypot(points[index][0] - points[index - 1][0], points[index][1] - points[index - 1][1]);
  }
  return total;
}

function proofPointAlong(points, t) {
  if (!points.length) return [0, 0];
  if (points.length === 1) return points[0].slice();
  const total = proofPolylineLength(points) || 1;
  const target = clamp(t, 0, 1) * total;
  let travelled = 0;
  for (let index = 1; index < points.length; index += 1) {
    const a = points[index - 1];
    const b = points[index];
    const segment = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (travelled + segment >= target) {
      return proofPointLerp(a, b, segment > 1e-9 ? (target - travelled) / segment : 0);
    }
    travelled += segment;
  }
  return points[points.length - 1].slice();
}

function drawProofArrow(ctx, origin, vector, length, color, dashed = false, width = 2.2) {
  const direction = proofDirection(vector);
  const end = [origin[0] + direction[0] * length, origin[1] + direction[1] * length];
  const head = 8;
  const angle = Math.atan2(direction[1], direction[0]);
  ctx.save();
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = width;
  ctx.setLineDash(dashed ? [6, 5] : []);
  ctx.beginPath();
  ctx.moveTo(origin[0], origin[1]);
  ctx.lineTo(end[0], end[1]);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.beginPath();
  ctx.moveTo(end[0], end[1]);
  ctx.lineTo(end[0] - head * Math.cos(angle - 0.42), end[1] - head * Math.sin(angle - 0.42));
  ctx.lineTo(end[0] - head * Math.cos(angle + 0.42), end[1] - head * Math.sin(angle + 0.42));
  ctx.closePath();
  ctx.fill();
  ctx.restore();
  return end;
}

function drawHolonomyProofStage(ctx, W, H, clock, timeline, proof, highlight) {
  const detail = proof && proof.detail ? proof.detail : {};
  const p1 = easeInOutCubic(proofPhase(timeline, 0, 0.33));
  const p2 = easeInOutCubic(proofPhase(timeline, 0.30, 0.72));
  const p3 = easeInOutCubic(proofPhase(timeline, 0.68, 1));
  const loopHot = ['loop', 'flux'].includes(highlight);
  const vectorHot = highlight === 'vector';
  const cx = W * 0.5;
  const cy = H * 0.49;
  const radius = Math.min(W, H) * 0.25;
  const points = [];
  for (let index = 0; index < 12; index += 1) {
    const angle = -Math.PI / 2 + TWO_PI * index / 12;
    const wobble = 1 + 0.055 * Math.sin(index * 2.1) + 0.02 * Math.cos(index * 0.7);
    points.push([
      cx + radius * wobble * Math.cos(angle),
      cy + radius * 0.74 * wobble * Math.sin(angle),
    ]);
  }
  points.push(points[0].slice());

  ctx.save();
  ctx.strokeStyle = 'rgba(120, 210, 255, 0.16)';
  ctx.lineWidth = 1;
  for (let row = -5; row <= 5; row += 1) {
    ctx.beginPath();
    for (let column = -5; column <= 5; column += 0.25) {
      const x = cx + column * 20 + row * 2.2;
      const y = cy + row * 10 + Math.sin(column * 0.8 + row * 0.4) * 4;
      if (column === -5) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  ctx.restore();

  ctx.save();
  traceProofPolyline(ctx, points, true);
  ctx.fillStyle = `rgba(77, 171, 247, ${0.055 + 0.06 * p1 + (loopHot ? 0.06 : 0)})`;
  ctx.fill();
  ctx.strokeStyle = `rgba(255, 214, 102, ${0.52 + 0.34 * p1 + (loopHot ? 0.14 : 0)})`;
  ctx.lineWidth = loopHot ? 3.5 : 2.4;
  ctx.shadowColor = loopHot ? '#ffd166' : 'rgba(120, 210, 255, 0.45)';
  ctx.shadowBlur = loopHot ? 22 : 9;
  ctx.stroke();
  ctx.restore();

  const start = points[0];
  const startVector = proofDirection(detail.start_vector || detail.vector_start);
  const endVector = proofDirection(detail.end_vector || detail.vector_end, startVector);
  const angleRad = proofNumber(detail.holonomy_angle_rad, Math.atan2(endVector[1], endVector[0]) - Math.atan2(startVector[1], startVector[0]));
  const baseAngle = Math.atan2(startVector[1], startVector[0]);
  const initialEnd = drawProofArrow(ctx, start, startVector, 72, vectorHot ? '#ffd166' : 'rgba(120, 210, 255, 0.92)', false, 2.4);
  ctx.fillStyle = '#78d6ff';
  ctx.beginPath();
  ctx.arc(start[0], start[1], 5, 0, TWO_PI);
  ctx.fill();

  if (p2 > 0.001) {
    const travel = easeInOutCubic(p2);
    const moving = proofPointAlong(points, travel);
    const liveAngle = baseAngle + angleRad * travel;
    const liveVector = [Math.cos(liveAngle), Math.sin(liveAngle)];
    drawProofArrow(ctx, moving, liveVector, 44, 'rgba(255, 214, 102, 0.95)', false, 2.2);
    ctx.fillStyle = '#ffd166';
    ctx.beginPath();
    ctx.arc(moving[0], moving[1], 5 + 2 * Math.sin(clock * 4), 0, TWO_PI);
    ctx.fill();
    ctx.strokeStyle = `rgba(255, 214, 102, ${0.35 + 0.35 * p2})`;
    ctx.lineWidth = 3;
    ctx.beginPath();
    for (let index = 0; index <= 30; index += 1) {
      const point = proofPointAlong(points, travel * index / 30);
      if (index === 0) ctx.moveTo(point[0], point[1]); else ctx.lineTo(point[0], point[1]);
    }
    ctx.stroke();
  }

  if (p3 > 0.001) {
    const end = drawProofArrow(ctx, start, endVector, 72, vectorHot ? '#ffd166' : 'rgba(120, 210, 255, 0.95)', false, 2.5);
    ctx.save();
    ctx.fillStyle = `rgba(77, 220, 255, ${0.10 + 0.14 * p3 + (highlight === 'flux' ? 0.08 : 0)})`;
    ctx.beginPath();
    ctx.moveTo(start[0], start[1]);
    ctx.arc(start[0], start[1], 92, baseAngle, baseAngle + angleRad, angleRad < 0);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
    const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius * 1.15);
    glow.addColorStop(0, `rgba(255, 214, 102, ${0.055 + 0.08 * p3})`);
    glow.addColorStop(1, 'rgba(255, 214, 102, 0)');
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(cx, cy, radius * 1.15, 0, TWO_PI);
    ctx.fill();
    ctx.fillStyle = '#78d6ff';
    ctx.beginPath();
    ctx.arc(end[0], end[1], 4, 0, TWO_PI);
    ctx.fill();
  }

  ctx.fillStyle = 'rgba(232, 242, 228, 0.84)';
  ctx.font = '12px monospace';
  ctx.textAlign = 'left';
  ctx.fillText(`holonomy = ${(angleRad * 180 / Math.PI).toFixed(2)} deg`, 16, 24);
  ctx.fillText(`curvature flux = ${proofFormat(detail.area_flux_deg, 2)} deg`, 16, 42);
  ctx.fillText('parallel transport returns rotated', 16, H - 18);
}

function isoProject(x, y, z, cx, cy, scale) {
  return [cx + (x - y) * scale, cy + (x + y) * scale * 0.48 - z * scale * 1.05];
}

function drawParabolicSurfaceGrid(ctx, cx, cy, scale, phase) {
  const height = (x, y) => 0.16 * (x * x - y * y)
    + 0.75 * Math.exp(-((x - 2.0) ** 2 + y * y) / 3.0)
    - 0.28 * Math.exp(-((x + 2.0) ** 2 + y * y) / 3.0);
  const grid = 11;
  for (let row = 0; row < grid; row += 1) {
    const y = -4.5 + row * 9.0 / (grid - 1);
    ctx.beginPath();
    for (let column = 0; column < grid; column += 1) {
      const x = -4.5 + column * 9.0 / (grid - 1);
      const point = isoProject(x, y, height(x, y), cx, cy, scale);
      if (column === 0) ctx.moveTo(point[0], point[1]); else ctx.lineTo(point[0], point[1]);
    }
    ctx.strokeStyle = `rgba(120, 210, 255, ${0.08 + 0.16 * phase})`;
    ctx.stroke();
  }
  for (let column = 0; column < grid; column += 1) {
    const x = -4.5 + column * 9.0 / (grid - 1);
    ctx.beginPath();
    for (let row = 0; row < grid; row += 1) {
      const y = -4.5 + row * 9.0 / (grid - 1);
      const point = isoProject(x, y, height(x, y), cx, cy, scale);
      if (row === 0) ctx.moveTo(point[0], point[1]); else ctx.lineTo(point[0], point[1]);
    }
    ctx.strokeStyle = `rgba(120, 210, 255, ${0.08 + 0.16 * phase})`;
    ctx.stroke();
  }
  return height;
}

function drawParabolicProofStage(ctx, W, H, clock, timeline, proof, highlight) {
  const detail = proof && proof.detail ? proof.detail : {};
  const p1 = easeInOutCubic(proofPhase(timeline, 0, 0.33));
  const p2 = easeInOutCubic(proofPhase(timeline, 0.30, 0.72));
  const p3 = easeInOutCubic(proofPhase(timeline, 0.68, 1));
  const seamHot = highlight === 'seam' || highlight === 'pegs';
  const asymptoticHot = highlight === 'asymptotic';
  const cx = W * 0.5;
  const cy = H * 0.46;
  const scale = Math.min(W, H) / 15;
  const height = drawParabolicSurfaceGrid(ctx, cx, cy, scale, p1);
  const seam = [];
  const seamHeight = (x) => height(x, -0.06 * x * x + 0.45 * Math.sin(x * 0.75));
  for (let index = 0; index <= 80; index += 1) {
    const x = -4.5 + index * 9.0 / 80;
    const y = -0.06 * x * x + 0.45 * Math.sin(x * 0.75);
    seam.push(isoProject(x, y, seamHeight(x), cx, cy, scale));
  }
  ctx.save();
  ctx.strokeStyle = `rgba(77, 235, 235, ${0.25 + 0.65 * p2 + (seamHot ? 0.16 : 0)})`;
  ctx.lineWidth = seamHot ? 4 : 2.5;
  ctx.shadowColor = seamHot ? '#78ebff' : 'rgba(77, 235, 235, 0.4)';
  ctx.shadowBlur = seamHot ? 20 : 8;
  traceProofPolyline(ctx, seam, false);
  ctx.stroke();
  ctx.restore();

  const pegs = detail.pegs || [];
  const pegPositions = [-2.8, 0.0, 2.8];
  const directions = Array.isArray(detail.asymptotic_directions) && detail.asymptotic_directions.length
    ? detail.asymptotic_directions
    : [detail.asymptotic_direction || [1, 0]];
  pegPositions.forEach((x, index) => {
    if (p2 < (index + 1) / 4) return;
    const y = -0.06 * x * x + 0.45 * Math.sin(x * 0.75);
    const point = isoProject(x, y, height(x, y), cx, cy, scale);
    const radius = 5 + 3 * Math.sin(clock * 3 + index);
    ctx.fillStyle = '#ffd166';
    ctx.beginPath();
    ctx.arc(point[0], point[1], radius, 0, TWO_PI);
    ctx.fill();
    ctx.strokeStyle = 'rgba(255, 214, 102, 0.6)';
    ctx.beginPath();
    ctx.arc(point[0], point[1], radius + 7, 0, TWO_PI);
    ctx.stroke();
    ctx.fillStyle = '#e0e7ff';
    ctx.font = '12px monospace';
    ctx.fillText(`P${index + 1}`, point[0] + 8, point[1] - 8);

    if (p3 > 0.001) {
      const direction = proofDirection(directions[index % directions.length] || [1, 0]);
      const tangentA = isoProject(x - 0.65, y - 0.24, height(x - 0.65, y - 0.24), cx, cy, scale);
      const tangentB = isoProject(x + 0.65, y + 0.24, height(x + 0.65, y + 0.24), cx, cy, scale);
      ctx.save();
      ctx.strokeStyle = `rgba(255, 214, 102, ${0.25 + 0.45 * p3 + (asymptoticHot ? 0.16 : 0)})`;
      ctx.fillStyle = 'rgba(255, 214, 102, 0.06)';
      ctx.lineWidth = asymptoticHot ? 3 : 1.8;
      ctx.beginPath();
      ctx.moveTo(tangentA[0], tangentA[1]);
      ctx.lineTo(tangentB[0], tangentB[1]);
      ctx.stroke();
      const lineScale = 46;
      const screenDirection = proofDirection([
        direction[0] + direction[1],
        direction[1] - direction[0],
      ]);
      drawProofArrow(ctx, point, screenDirection, lineScale, 'rgba(77, 235, 235, 0.95)', false, asymptoticHot ? 3 : 2);
      ctx.restore();
    }
  });

  ctx.fillStyle = 'rgba(232, 242, 228, 0.84)';
  ctx.font = '12px monospace';
  ctx.textAlign = 'left';
  ctx.fillText(`parabolic band |K| <= ${formatCurvature(detail.tolerance_k, 5)}`, 16, 24);
  ctx.fillText(`verified pegs = ${detail.valid_pegs !== undefined ? detail.valid_pegs : 0} / 3`, 16, 42);
  ctx.fillText('zero-curvature seam: one principal curvature vanishes', 16, H - 18);
}

function projectTorusPoint(u, v, cx, cy, scale, yaw, pitch, R = 1.0, r = 0.38) {
  const ring = R + r * Math.cos(v);
  let x = ring * Math.cos(u);
  let y = ring * Math.sin(u);
  let z = r * Math.sin(v);
  const cyaw = Math.cos(yaw);
  const syaw = Math.sin(yaw);
  const x1 = x * cyaw - y * syaw;
  const y1 = x * syaw + y * cyaw;
  const cp = Math.cos(pitch);
  const sp = Math.sin(pitch);
  const y2 = y1 * cp - z * sp;
  const z2 = y1 * sp + z * cp;
  return [cx + x1 * scale, cy - z2 * scale + y2 * 0.18 * scale];
}

function drawHomotopyProofStage(ctx, W, H, clock, timeline, proof, highlight) {
  const detail = proof && proof.detail ? proof.detail : {};
  const p1 = easeInOutCubic(proofPhase(timeline, 0, 0.33));
  const p2 = easeInOutCubic(proofPhase(timeline, 0.30, 0.72));
  const p3 = easeInOutCubic(proofPhase(timeline, 0.68, 1));
  const torusHot = highlight === 'torus';
  const windingHot = highlight === 'winding';
  const holeHot = highlight === 'hole';
  const cx = W * 0.5;
  const cy = H * 0.5;
  const scale = Math.min(W, H) * 0.30;
  const yaw = 0.55 + clock * 0.18;
  const pitch = 0.48 + 0.12 * Math.sin(clock * 0.5);
  const project = (u, v) => projectTorusPoint(u, v, cx, cy, scale, yaw, pitch);

  ctx.save();
  ctx.lineWidth = 1;
  for (let u = 0; u < TWO_PI; u += Math.PI / 9) {
    ctx.strokeStyle = `rgba(120, 210, 255, ${0.08 + 0.10 * p1 + (torusHot ? 0.08 : 0)})`;
    ctx.beginPath();
    for (let v = 0; v <= TWO_PI + 0.1; v += 0.14) {
      const point = project(u, v);
      if (v === 0) ctx.moveTo(point[0], point[1]); else ctx.lineTo(point[0], point[1]);
    }
    ctx.stroke();
  }
  for (let v = 0; v < TWO_PI; v += Math.PI / 6) {
    ctx.strokeStyle = `rgba(120, 210, 255, ${0.06 + 0.10 * p1 + (torusHot ? 0.08 : 0)})`;
    ctx.beginPath();
    for (let u = 0; u <= TWO_PI + 0.1; u += 0.14) {
      const point = project(u, v);
      if (u === 0) ctx.moveTo(point[0], point[1]); else ctx.lineTo(point[0], point[1]);
    }
    ctx.stroke();
  }
  ctx.restore();

  const windingU = proofNumber(detail.winding_u, 1);
  const direction = windingU < 0 ? -1 : 1;
  const path = [];
  for (let index = 0; index <= 100; index += 1) {
    const u = TWO_PI * direction * index / 100;
    path.push(project(u, 0));
  }
  if (p2 > 0.001) {
    ctx.save();
    ctx.strokeStyle = `rgba(255, 214, 102, ${0.35 + 0.55 * p2 + (windingHot ? 0.15 : 0)})`;
    ctx.lineWidth = windingHot ? 4 : 2.6;
    ctx.shadowColor = '#ffd166';
    ctx.shadowBlur = windingHot ? 20 : 10;
    ctx.beginPath();
    const end = Math.max(2, Math.floor(path.length * easeInOutCubic(p2)));
    for (let index = 0; index < end; index += 1) {
      if (index === 0) ctx.moveTo(path[index][0], path[index][1]); else ctx.lineTo(path[index][0], path[index][1]);
    }
    ctx.stroke();
    const head = path[Math.max(0, end - 1)];
    ctx.fillStyle = '#ffd166';
    ctx.beginPath();
    ctx.arc(head[0], head[1], 6 + 2 * Math.sin(clock * 4), 0, TWO_PI);
    ctx.fill();
    ctx.restore();
  }

  if (p3 > 0.001) {
    const inner = scale * 0.48;
    const outer = scale * 0.86;
    const lassoRadius = proofLerp(outer, inner, easeInOutCubic(p3));
    ctx.save();
    ctx.setLineDash([8, 6]);
    ctx.strokeStyle = `rgba(255, 120, 120, ${0.55 + 0.25 * p3 + (holeHot ? 0.15 : 0)})`;
    ctx.lineWidth = holeHot ? 3.5 : 2.4;
    ctx.beginPath();
    ctx.ellipse(cx, cy + scale * 0.02, lassoRadius, lassoRadius * 0.48, 0, 0, TWO_PI);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.beginPath();
    ctx.ellipse(cx, cy + scale * 0.02, inner * 0.92, inner * 0.40, 0, 0, TWO_PI);
    ctx.fillStyle = `rgba(255, 120, 120, ${0.04 + 0.08 * p3})`;
    ctx.fill();
    ctx.strokeStyle = 'rgba(255, 120, 120, 0.75)';
    ctx.stroke();
    ctx.restore();
    ctx.fillStyle = 'rgba(255, 180, 180, 0.92)';
    ctx.font = '12px monospace';
    ctx.textAlign = 'center';
    ctx.fillText('the central hole blocks contraction', cx, cy + inner * 0.55);
  }

  ctx.fillStyle = 'rgba(232, 242, 228, 0.84)';
  ctx.font = '12px monospace';
  ctx.textAlign = 'left';
  ctx.fillText(`winding = (${proofFormat(detail.winding_u, 3)}, ${proofFormat(detail.winding_v, 3)})`, 16, 24);
  ctx.fillText(`pi_1 = ${detail.fundamental_group || 'Z + Z'}`, 16, 42);
  ctx.fillText(`genus = ${detail.genus !== undefined && detail.genus !== null ? detail.genus : '-'}`, 16, H - 18);
}
function bindProofHighlighting() {
  const details = el('proof-details');
  if (!details || details.dataset.highlightBound === 'true') return;
  details.dataset.highlightBound = 'true';
  details.addEventListener('mouseover', (event) => {
    const target = event.target.closest('[data-proof-highlight]');
    if (!target || target.contains(event.relatedTarget)) return;
    if (proofAnimator) proofAnimator.setHighlight(target.dataset.proofHighlight);
  });
  details.addEventListener('mouseout', (event) => {
    const target = event.target.closest('[data-proof-highlight]');
    if (!target || target.contains(event.relatedTarget)) return;
    if (proofAnimator) proofAnimator.setHighlight(null);
  });
}

function startProofAnimation() {
  if (proofAnimator) proofAnimator.start();
}

function stopProofAnimation() {
  if (proofAnimator) {
    proofAnimator.stop();
    proofAnimator = null;
  }
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
  stopProofAnimation();
  const safeProof = state.proof;
  el('proof-title').textContent = safeProof.title || 'Geometric Proof';
  el('proof-accept').textContent = safeProof.__guide ? 'Close Guide & Return to Surveying' : 'Accept Seal & Continue';
  const relicBadge = el('proof-relic-badge');
  const relic = safeProof.relic || (safeProof.detail && safeProof.detail.relic) || '';
  relicBadge.textContent = relic;
  relicBadge.classList.toggle('hidden', !relic);

  const details = el('proof-steps');
  details.innerHTML = '';
  for (const card of buildProofCards(safeProof)) details.appendChild(card);
  renderProofMath(details);

  const dots = el('proof-step-dots');
  dots.innerHTML = '';
  const labels = proofStepLabels(safeProof.kind, Boolean(safeProof.detail && safeProof.detail.is_deficit));
  labels.forEach((label, index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'proof-step-dot';
    button.dataset.step = String(index);
    button.textContent = label;
    button.addEventListener('click', () => {
      if (proofAnimator) proofAnimator.setStep(index);
    });
    dots.appendChild(button);
  });

  el('proof-modal').classList.remove('hidden');
  proofAnimator = new ProofAnimator(el('proof-canvas'), safeProof);
  proofAnimator.resize();
  bindProofHighlighting();
  proofAnimator.start();
}


function showProofModal(proof) {
  showProof(proof);
}

function hideProof() {
  stopProofAnimation();
  state.proofOpen = false;
  el('proof-accept').textContent = 'Accept Seal & Continue';
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
  el('defeat-modal').classList.add('hidden');
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
  el('heading').textContent = formatAngle(PHYS.heading * 180 / Math.PI, 1);
  const slope = PHYS.slope || { slope: 0, speed_scale: 1 };
  const uphill = slope.slope > 0.001;
  el('slope').textContent =
    `${slope.slope >= 0 ? '+' : ''}${slope.slope.toFixed(3)} (x${slope.speed_scale.toFixed(2)}${uphill ? ', uphill' : ''})`;
  if (typeof p.signal === 'number') el('detector-text').textContent = `signal ${p.signal.toFixed(4)} (${p.label}, ${p.trend})`;
  if (typeof p.curvature === 'number') el('curvature').textContent = formatCurvature(p.curvature, 5);
  el('mode').textContent = state.godVisible ? 'god view (debug)' : 'top-down map';
  el('score').textContent = `${Math.round(p.score || 0)}`;
  el('scale-readout').textContent = `${(state.scaleFactor || 1).toFixed(2)}x`;
  el('difficulty-readout').textContent = difficultyLabel(state.difficulty);
  const guideButton = el('field-guide');
  if (guideButton) guideButton.classList.toggle('hidden', state.difficulty !== 'easy');
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
  if (state.difficulty === 'hard') maybeShowDefeat();
}

function difficultyLabel(tier) {
  if (tier === 'medium') return 'Medium';
  if (tier === 'hard') return 'Hard - timed survival';
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
      const limit = state.player && typeof state.player.max_markers_allowed === 'number' ? state.player.max_markers_allowed : 0;
      const remaining = limit > 0 ? Math.max(0, limit - (state.player.markers || []).length) : null;
      hintMessage(`Marker ${result.name} placed at (${result.position[0].toFixed(2)}, ${result.position[1].toFixed(2)})${remaining !== null ? `; ${remaining} slots remaining` : ''}.`, 'ok');
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
    note.textContent = 'Hard: timed survival. Rope pool 500 m, maximum 8 marker pegs, quest countdown, detector offline.';
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
    state.defeatShown = false;
    state.timeRemaining = null;
    state.timeRemainingAt = 0;
    state.timerQuestId = null;
    el('defeat-modal').classList.add('hidden');
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
  updateQuestActionButton();
  const label = document.querySelector(`.hotbar .slot[data-slot="${state.slot}"] span`);
  const name = label ? label.textContent : '';
  const player = state.player;
  if (state.ropeMode) {
    const remaining = player && typeof player.rope_remaining === 'number' ? formatLength(player.rope_remaining, 2) : '-';
    const total = player && typeof player.rope_total === 'number' ? formatLength(player.rope_total, 2) : '-';
    hintMessage(`Surveyor Rope: ${remaining} remaining of ${total}. Select two path points.`, 'info');
  } else if (state.slot === 2) {
    const count = player && Array.isArray(player.markers) ? player.markers.length : 0;
    const limit = player && typeof player.max_markers_allowed === 'number' ? player.max_markers_allowed : 0;
    const remaining = limit > 0 ? Math.max(0, limit - count) : null;
    const suffix = limit > 0 ? ` / ${limit} placed, ${remaining} remaining` : ' placed';
    hintMessage(`Marker Peg: ${count}${suffix}.`, 'info');
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
  if (best) return best.node;
  // Fallback for angle/path clicks: marker hit-caches can be one frame stale
  // after a canvas resize or a position sync. Project directly from markers.
  for (const marker of (state.player && state.player.markers) || []) {
    const point = projectMarkerForPull(marker);
    if (!point) continue;
    const distance = Math.hypot(point[0] - x, point[1] - y);
    if (distance <= 22 && (!best || distance < best.distance)) {
      best = {
        node: { type: 'marker', id: marker.name, label: marker.name, x: point[0], y: point[1], r: 22 },
        distance,
      };
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

function pointInTriangle(x, y, a, b, c) {
  const sign = (p1, p2, p3) => (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1]);
  const d1 = sign([x, y], a, b);
  const d2 = sign([x, y], b, c);
  const d3 = sign([x, y], c, a);
  const hasNegative = d1 < 0 || d2 < 0 || d3 < 0;
  const hasPositive = d1 > 0 || d2 > 0 || d3 > 0;
  return !(hasNegative && hasPositive);
}

function screenCircumcircle(a, b, c) {
  const d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]));
  if (Math.abs(d) < 1e-6) return null;
  const aa = a[0] * a[0] + a[1] * a[1];
  const bb = b[0] * b[0] + b[1] * b[1];
  const cc = c[0] * c[0] + c[1] * c[1];
  const center = [
    (aa * (b[1] - c[1]) + bb * (c[1] - a[1]) + cc * (a[1] - b[1])) / d,
    (aa * (c[0] - b[0]) + bb * (a[0] - c[0]) + cc * (b[0] - a[0])) / d,
  ];
  return { center, radius: Math.hypot(center[0] - a[0], center[1] - a[1]) };
}

function projectMarkerForPull(marker) {
  const view = state.mapView;
  if (!view) return null;
  const [du, dv] = chartDelta(
    marker.position[0], marker.position[1], view.phys[0], view.phys[1]
  );
  return [
    view.cx + du * view.scale,
    view.cy - dv * view.scale,
  ];
}

function projectCircleSample(circle, sample) {
  const view = state.mapView;
  if (!view || !circle || !circle.center) return null;
  const [centerDu, centerDv] = chartDelta(
    circle.center[0], circle.center[1], view.phys[0], view.phys[1]
  );
  const periods = chartPeriods();
  const localU = wrapToPeriod(sample[0] - circle.center[0], periods[0]);
  const localV = wrapToPeriod(sample[1] - circle.center[1], periods[1]);
  return [
    view.cx + (centerDu + localU) * view.scale,
    view.cy - (centerDv + localV) * view.scale,
  ];
}

function pullableTriangleAt(x, y) {
  const p = state.player;
  if (!p || !state.mapView) return null;
  const markers = (p.markers || []).map((marker) => {
    const point = projectMarkerForPull(marker);
    return point ? { type: 'marker', id: marker.name, label: marker.name, x: point[0], y: point[1] } : null;
  }).filter(Boolean);
  for (let i = 0; i < markers.length; i += 1) {
    for (let j = i + 1; j < markers.length; j += 1) {
      for (let k = j + 1; k < markers.length; k += 1) {
        const a = markers[i];
        const b = markers[j];
        const c = markers[k];
        if (!findRopeBetween(a, b) || !findRopeBetween(b, c) || !findRopeBetween(c, a)) continue;
        const points = [[a.x, a.y], [b.x, b.y], [c.x, c.y]];
        const inside = pointInTriangle(x, y, points[0], points[1], points[2]);
        const edgeNear = Math.min(
          pointSegmentDistance(x, y, points[0], points[1]),
          pointSegmentDistance(x, y, points[1], points[2]),
          pointSegmentDistance(x, y, points[2], points[0]),
        ) <= 22;
        if (inside || edgeNear) {
          return { labels: [a.id, b.id, c.id], points };
        }
      }
    }
  }
  return null;
}

function nearestCircumcircle(x, y) {
  let best = null;
  for (const circle of state.hitCircumcircles || []) {
    for (let index = 0; index < circle.points.length; index += 1) {
      const a = circle.points[index];
      const b = circle.points[(index + 1) % circle.points.length];
      const distance = pointSegmentDistance(x, y, a, b);
      if (distance <= 16 && (!best || distance < best.distance)) best = { circle, distance };
    }
  }
  return best ? best.circle : null;
}

async function pullCircumcircle(labels) {
  try {
    const result = await apiPost('/api/action/tool', {
      tool: 'rope_pull_circumcircle',
      markers: labels,
    });
    applyRopeState(result);
    state.hoverTriangle = null;
    state.pullAnimation = { started: performance.now(), labels: labels.slice() };
    renderAll();
    if (result.quest_completed && result.proof) {
      state.player = Object.assign({}, state.player, { quest: result.quest });
      state.shownRelicCount = (result.quest.relics || []).length;
      syncDetectorLock();
      await refreshState();
      showProof(result.proof);
      hintMessage(`Quest complete - ${result.proof.relic} claimed!`, 'ok');
    } else {
      hintMessage(
        `Circumcircle pulled: C_real = ${formatLength(Number(result.circumcircle.perimeter), 2)}, ` +
        `C_flat = ${formatLength(Number(result.circumcircle.flat_perimeter), 2)}.`,
        'ok'
      );
    }
  } catch (error) {
    const message = String((error && error.message) || error || '');
    if (message.toLowerCase().includes('unknown tool')) {
      hintMessage(
        'The running server does not have the circle-pull endpoint. Restart the Python server, then press Ctrl+F5.',
        'error',
        true
      );
    } else {
      hintMessage(message, 'error');
    }
  }
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
  // Angle measurement must win over circumcircle pulling: clicking a vertex
  // in Angle mode should measure its rope angle, not pull the BDP circle.
  const pullMode = state.ropeMode || (state.measureMode && state.measureKind === 'length');
  if (pullMode) {
    const pull = pullableTriangleAt(x, y);
    if (pull) {
      pullCircumcircle(pull.labels);
      return;
    }
  }
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
    circumcircles: result.circumcircles || [],
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
    hintMessage(`Rope #${result.rope.id} tied: ${formatLength(result.rope.length_3d, 2)} (remaining ${formatLength(result.rope_remaining, 2)}).`, 'ok');
  } catch (error) {
    hintMessage(error.message, 'error');
  }
}

async function cutRope(ropeId) {
  try {
    const result = await apiPost('/api/action/tool', { tool: 'rope_clear', rope_id: ropeId });
    applyRopeState(result);
    renderAll();
    hintMessage(`Rope #${ropeId} cut (remaining ${formatLength(result.rope_remaining, 2)}).`, 'ok');
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
    hintMessage(`All ropes cut (remaining ${formatLength(result.rope_remaining, 2)}).`, 'ok');
  } catch (error) {
    hintMessage(error.message, 'error');
  }
}

function handleRopeClick(x, y) {
  const pull = pullableTriangleAt(x, y);
  if (pull) {
    pullCircumcircle(pull.labels);
    return;
  }
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
  for (const button of document.querySelectorAll('#measure-mode button[data-mode]')) {
    button.classList.toggle('active', button.dataset.mode === state.measureKind);
  }
  if (state.slot !== 4) selectSlot(4);
  updateQuestActionButton();
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
    const circumcircle = nearestCircumcircle(x, y);
    if (circumcircle) {
      try {
        const result = await apiPost('/api/action/tool', {
          tool: 'measure',
          mode: 'ruler',
          targets: [{ type: 'circumcircle', id: circumcircle.id }],
        });
        if (result.quest_completed && result.proof) {
          state.player = Object.assign({}, state.player, { quest: result.quest });
          state.shownRelicCount = (result.quest.relics || []).length;
          syncDetectorLock();
          await refreshState();
          showProof(result.proof);
          hintMessage(`Quest complete - ${result.proof.relic} claimed!`, 'ok');
        } else {
          hintMessage(`Circumcircle length: ${result.distance.toFixed(2)} m.`, 'ok');
        }
      } catch (error) {
        hintMessage(error.message, 'error');
      }
      return;
    }
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
      hintMessage(`Rope #${result.rope_id} length: ${formatLength(result.distance, 2)}.`, 'ok');
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
        hintMessage(`Angle at ${node.label}: ${formatAngle(result.angle_degrees, 2)}.`, 'ok');
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
          `Angle at ${node.label}: ${formatAngle(result.angle_degrees, 2)} (${measured}/3 vertices measured).`,
          'info'
        );
        return;
      }
      const targets = Object.values(entry.vertices).map((vertex) => ({ type: vertex.type, id: vertex.id }));
      delete state.angleMeasurements[key];
      const summed = await apiPost('/api/action/tool', { tool: 'measure', mode: 'angle_sum', targets });
      hintMessage(
        `Triangle angle sum: ${formatAngle(summed.angle_sum_degrees, 2)} (excess ${formatAngle(summed.excess_degrees, 2)}).`,
        'ok'
      );
      if (summed.quest_completed && summed.proof) {
        state.player = Object.assign({}, state.player, { quest: summed.quest });
        state.shownRelicCount = (summed.quest.relics || []).length;
        syncDetectorLock();
        await refreshState();
        showProof(summed.proof);
        hintMessage(`Quest complete - ${(summed.proof && summed.proof.relic) || 'the seal'} claimed!`, 'ok');
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
      hintMessage(`Quest complete - ${(result.proof && result.proof.relic) || 'the seal'} claimed!`, 'ok');
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
  const fallbackTarget = quest.target_angle_sum_degrees;
  const fallbackCurrent = quest.current_angle_sum_degrees;
  const target = typeof quest.objective_target === 'number' ? quest.objective_target : fallbackTarget;
  const current = typeof quest.objective_current === 'number' ? quest.objective_current : fallbackCurrent;
  const label = quest.objective || 'Objective';
  if (typeof target === 'number') {
    const shown = typeof current === 'number'
      ? (quest.objective_unit === 'ratio' ? current.toFixed(4) : current.toFixed(1))
      : '-';
    if (quest.objective_unit === 'count') {
      el('codex-progress').textContent =
        `${label} ${shown} / ${target.toFixed(0)} (${Math.round((quest.progress || 0) * 100)}%)`;
    } else if (quest.objective_unit === 'pi') {
      el('codex-progress').textContent =
        `${label} ${shown} / ${target.toFixed(2)} pi (${Math.round((quest.progress || 0) * 100)}%)`;
    } else {
      const suffix = quest.objective_unit === 'ratio' ? '' : ' deg';
      const relation = quest.objective_relation === '<=' ? '<=' : '>=';
      el('codex-progress').textContent =
        `${label} ${shown} ${relation} ${target.toFixed(quest.objective_unit === 'ratio' ? 4 : 1)}${suffix} (${Math.round((quest.progress || 0) * 100)}%)`;

    }
  } else {
    el('codex-progress').textContent = 'All geometric seals claimed';
  }
  const relics = quest.relics || [];
  el('codex-relics').innerHTML = relics.length
    ? relics.map((relic) => `&#9670; ${relic}`).join('<br />')
    : '<em>none yet</em>';
}

window.addEventListener('keydown', (event) => {
  const key = event.key.toLowerCase();
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  const targetTag = String((event.target && event.target.tagName) || '').toLowerCase();
  if (['input', 'select', 'textarea'].includes(targetTag)) return;
  if (key === 'e' && (state.ropeMode || (state.measureMode && state.measureKind === 'length')) && state.hoverTriangle) {
    event.preventDefault();
    pullCircumcircle(state.hoverTriangle.labels);
    return;
  }
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
  } else if (key === 'h') {
    showExampleGuide();
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
  const previousPull = state.hoverTriangle;
  const pullMode = state.ropeMode || (state.measureMode && state.measureKind === 'length');
  state.hoverTriangle = pullMode ? pullableTriangleAt(localX, localY) : null;
  if (state.hoverTriangle && (!previousPull || previousPull.labels.join('|') !== state.hoverTriangle.labels.join('|'))) {
    hintMessage('[Press E or Click to Pull into Circle]', 'ok');
  }
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
for (const button of document.querySelectorAll('#measure-mode button[data-mode]')) {
  button.addEventListener('click', () => setMeasureKind(button.dataset.mode));
}
el('codex-close').addEventListener('click', () => toggleCodex(false));
el('quest-action').addEventListener('click', runQuestAction);

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
el('defeat-continue').addEventListener('click', continueAfterDefeat);
el('defeat-lobby').addEventListener('click', returnToLobby);
el('proof-accept').addEventListener('click', hideProof);
el('field-guide').addEventListener('click', showExampleGuide);
el('proof-replay').addEventListener('click', () => {
  if (proofAnimator) proofAnimator.replay();
});
window.addEventListener('resize', () => {
  if (proofAnimator) proofAnimator.resize();
});
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
