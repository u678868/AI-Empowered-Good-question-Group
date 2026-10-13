# The Curved World

> A mathematical exploration prototype set on smooth surfaces embedded in ordinary
> three-dimensional Euclidean space. The player receives only a distance-sensitive
> detector and a local tangent view, then must reconstruct the hidden geometry by
> moving, measuring and reasoning.

## Quick Start & Interaction (一键启动与交互说明)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
python -m src.main --serve --port 8000
```

Open `http://127.0.0.1:8000/`, choose a map, difficulty and seed, then enter the world.

Run the full test suite with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Run the terminal version with:

```powershell
.\.venv\Scripts\python.exe -m src.main
.\.venv\Scripts\python.exe -m src.main --demo-scenario
.\.venv\Scripts\python.exe -m src.main --render
```

## Core Controls & Keybinds (核心操作与快捷键)

| Input | Action |
| :--- | :--- |
| `W` `A` `S` `D` | Move in the local tangent frame |
| Mouse over map | Aim the player frame |
| `Q` / `E` | Turn the frame |
| `1` | Exit Detector |
| `2` | Marker Peg |
| `3` | Surveyor Rope |
| `4` | Measure Tool |
| `5` | Quest Codex |
| Left-click | Use the selected tool or interact |
| Right-click | Cut the rope under the cursor |
| `R` | Toggle Length / Angle measurement |
| `J` | Open the Quest Codex |
| `H` | Open the Easy-mode theoretical Field Guide |
| `G` | Toggle the privileged God View |
| `Esc` | Close overlays |

## Three-Tier Difficulty Modes

| Difficulty | Detector | Guidance | Survival constraints |
| :--- | :--- | :--- | :--- |
| Easy | Active distance signal | `H` opens a standard reference proof preview | Relaxed rope and marker limits |
| Medium | Offline | Pure geometry, curvature readings and measurements | Relaxed rope and marker limits |
| Hard | Offline | Full survival mode | 500 m rope pool, maximum 8 marker pegs, scale-adaptive quest timer |

Hard-mode quest time limits:

| Scale | Limit |
| :--- | :--- |
| `0.5x` | 120 s |
| `1.0x` | 240 s |
| `2.0x` | 360 s |
| `4.0x` | 480 s |
| Custom `S` | `240 x S` s |

When the timer reaches zero, the run becomes **Defeated**. The Defeat modal lets the
player continue free roaming or return to the lobby. A defeated run cannot claim a
clean victory.

## The 5 Surveyor Tools

1. **Exit Detector (1)** - Reads the hidden-exit signal strength only. It is sealed until
   every geometric trial is complete, and it is offline in Medium and Hard.
2. **Marker Peg (2)** - Places a named survey point. Hard mode allows at most eight pegs.
3. **Surveyor Rope (3)** - Connects two known nodes. Left-click selects nodes;
   right-click cuts a rope. Hard mode uses a finite 500 m pool.
4. **Measure Tool (4)** - `R` toggles between Length and Angle. Length measures a rope or
   two points; Angle measures a vertex or a three-vertex triangle sum.
5. **Quest Codex (5)** - Shows the active trial, objective, hint, progress and relics.

## Master Walkthrough: The 5 Geometric Trials

### Trial 1 - Gauss-Bonnet Angle Excess / Deficit

- **Geometry**: `sum(theta_i) - pi = iint_Delta K dA`.
- **Terrain**: excess wants a positive-curvature dome; deficit wants a negative-curvature saddle.
- **Operation**: place three pegs, rope them into a triangle, then use the goniometer angle sum.
- **Pass**: exceed the lower target in excess mode, or stay below the upper target in deficit mode.

### Trial 2 - Bertrand-Diquet-Puisseux Circle Deficit

- **Geometry**: `C(r) = 2*pi*r - (pi/3) K r^3 + O(r^4)`.
- **Terrain**: a positive-curvature peak.
- **Operation**: place three pegs around the dome, connect them, then use the Measure Tool in
  Length mode to pull the triangle into its circumscribed geodesic circle.
- **Pass**: the measured surface perimeter ratio must be at or below the adaptive target.

### Trial 3 - Levi-Civita Holonomy Loop

- **Geometry**: parallel transport around a closed loop rotates by `iint K dA` modulo `2*pi`.
- **Terrain**: a loop encircling a curved height or saddle.
- **Operation**: place an origin marker, calibrate a tangent vector, walk a closed loop through
  ordered markers, then measure the transport rotation.
- **Pass**: the loop closes and the measured holonomy reaches the adaptive target angle.

### Trial 4 - Parabolic Seam

- **Geometry**: `K = kappa_1 * kappa_2 = 0`; one principal curvature vanishes.
- **Terrain**: the transition boundary between a dome and a saddle.
- **Operation**: place three separated pegs on the zero-curvature seam, connect them, and
  run parabolic validation.
- **Pass**: all three pegs lie inside the tolerance band with valid spacing.

### Trial 5 - Homotopy Circumnavigation

- **Geometry**: `pi_1(T^2) = Z + Z`; a non-zero winding class cannot contract to a point.
- **Terrain**: a closed torus or handle.
- **Operation**: place the origin beacon `O`, travel one full coordinate circuit, return to
  `O`, then seal the homotopy loop.
- **Pass**: the unwrapped winding number is non-zero and the path returns inside the capture radius.

## How the Knowledge Becomes the Game Rules (知识如何成为游戏规则)

The five theorems are not decoration: each one is the *only* way to open one of the
five seals that unseal the exit detector.

| Theorem | In-game rule | Player-facing consequence |
| :--- | :--- | :--- |
| Gauss-Bonnet, `sum(theta_i) - pi = iint K dA` | The angle sum of a geodesic triangle is measured with the goniometer and compared against the curvature integral of the same triangle. | Excess and deficit trials want opposite signs of curvature, so the same tool must be used twice with opposite intent. |
| Bertrand-Diquet-Puisseux, `C(r) = 2*pi*r - (pi/3) K r^3 + O(r^4)` | A geodesic circle is *constructed* by pulling a rope triangle into its circumcircle; the surface perimeter is then compared with the Euclidean one. | The player performs the expansion instead of reading it: the circle is rope geometry, not a menu item. |
| Levi-Civita holonomy | Parallel transport around a closed loop of markers is executed and the net rotation is measured. | The measured rotation equals the enclosed curvature integral, so a wrong loop is detected by the instrument itself. |
| Parabolic points, `K = kappa_1 * kappa_2 = 0` | Three pegs must sit inside the zero-curvature tolerance band with valid spacing. | The player must find the boundary between a dome and a saddle, i.e. locate a curve, not a point. |
| Homotopy, `pi_1(T^2) = Z + Z` | A full coordinate circuit must be walked and sealed; the unwrapped winding number must be non-zero. | A contractible loop cannot seal, so the player must reason about the topology of the map. |

### The surface model

The world is a graph surface embedded in ordinary Euclidean space:

```text
S = { (x, y, f(x, y)) : (x, y) in D }
```

`D` is the parameter domain and `f` is a smooth height function assembled from sine waves
and Gaussian hills. All first and second derivatives are analytic; the project does not use
finite-difference derivatives for its core geometry.

The detector uses ambient Euclidean distance:

```text
d_E(P, Q) = ||P - Q||_2
signal = exp(-d_E / scale)
```

This is deliberately not the geodesic distance along the surface. The detector reports only
signal strength; it never exposes the hidden exit, true distance or direction.

## Information Boundary

Player-facing API responses never include the hidden exit coordinates or the true exit
distance. The privileged God View and `/api/state/debug` endpoint are available only when
the server is started with `--debug` or the session is opened in omniscient mode.

## Scoring & Scholar Rank

The final score is computed from four components:

- **Base Clearance**: `+2000` when the exit is reached.
- **Time Efficiency**: up to `+3000`, based on elapsed time relative to `240 x scale`.
- **Frugal Surveyor**: marker frugality, remaining rope ratio and measurement discipline.
- **Path Exhaustion**: `min(1000, effective_steps x 0.2)` is subtracted.

The subtotal is multiplied by a difficulty multiplier (Easy `1.0`, Medium `1.5`, Hard `2.2`)
and a scale multiplier (`0.5x -> 0.8`, `1x -> 1.0`, `2x -> 1.25`, `4x -> 1.5`, custom
`clamp(0.8 x sqrt(S), 0.6, 2.0)`). The minimum final score is `100`.

Scholar rank:

| Score | Rank |
| :--- | :--- |
| `>= 8000` | `S` - Archimedean Grandmaster |
| `>= 5500` | `A` - Geodesic Scholar |
| `>= 3500` | `B` - Manifold Surveyor |
| below `3500` | `C` - Academy Initiate |

The victory modal shows the full score ledger and rank badge.
## Architecture & Core Files (核心文件清单与架构设计)

| Area | Core files | Role |
| :--- | :--- | :--- |
| Differential geometry kernel | `src/the_curved_world/manifold.py`, `geometry.py`, `differential.py` | Surface parametrisation, fundamental forms, curvature, parallel transport |
| World and objects | `src/the_curved_world/world.py`, `obstacles.py`, `detector.py` | Deterministic world generation, obstacles and detector model |
| Gameplay and quests | `src/the_curved_world/gameplay.py`, `quest.py`, `scanner.py` | Movement, surveying tools, quest chain, feasibility precheck |
| Rope geometry | `src/the_curved_world/ropes.py` | Finite rope pool, rope rings and circumcircle pulling |
| Web API | `src/the_curved_world/server.py` | Local HTTP API, static Web server and player-safe state payloads |
| Web UI | `web/index.html`, `web/app.js`, `web/style.css` | Local tangent map, instruments, codex, proof stage and defeat flow |
| Local KaTeX | `web/vendor/katex/` | Offline formula typesetting assets |
| Tests | `tests/` | Geometry, world, API, information boundary, quests and UI payload tests |

## Feature Status (功能实现状态表)

Honest status of every shipped subsystem. "Implemented" means there is code plus at
least one automated test or an audited payload check behind it.

| Feature | Core files | Status |
| :--- | :--- | :--- |
| Deterministic world generation from an explicit seed (9 registered manifolds) | `src/the_curved_world/world.py`, `maps/` | ✅ Implemented |
| Analytic first/second derivatives, fundamental forms, Gaussian curvature | `manifold.py`, `geometry.py`, `differential.py` | ✅ Implemented |
| Seamless 2D local tangent-map roaming (player pinned, world scrolls, periodic wrap) | `web/app.js`, `server.py` | ✅ Implemented |
| Information boundary: no exit coordinates, no true distance in player payloads | `observations.py`, `server.py` | ✅ Implemented, audited by tests |
| Marker pegs, surveyor rope with a finite pool, right-click rope cutting | `ropes.py`, `gameplay.py` | ✅ Implemented |
| Trial 1 - Gauss-Bonnet angle excess / deficit | `quest.py` | ✅ Implemented |
| Trial 2 - Bertrand-Diquet-Puisseux geodesic-circle deficit (rope circumcircle pull) | `ropes.py`, `quest.py` | ✅ Implemented |
| Trial 3 - Levi-Civita holonomy loop | `quest.py`, `differential.py` | ✅ Implemented |
| Trial 4 - Parabolic seam measurement | `quest.py`, `scanner.py` | ✅ Implemented |
| Trial 5 - Homotopy (`pi_1`) circumnavigation | `quest.py` | ✅ Implemented |
| Data-driven KaTeX derivation stage with step animation | `web/app.js`, `web/vendor/katex/` | ✅ Implemented |
| Three difficulty tiers; Hard survival (500 m rope, 8 pegs, per-trial countdown) | `config.py`, `gameplay.py` | ✅ Implemented |
| Structured scoring with S/A/B/C scholar rank | `gameplay.py`, `web/app.js` | ✅ Implemented |
| God View and privileged `/api/state/debug` | `server.py`, `web/app.js` | ✅ Implemented (debug-gated) |
| Local HTTP API and static server using only the standard library | `server.py` | ✅ Implemented |
| Terminal session and Matplotlib renderer | `cli.py`, `session.py`, `render.py` | ✅ Implemented |
| Localization: English UI plus a Chinese README | `README_CN.md` | ✅ Implemented |
| Detector measurement noise / error model | `detector.py` | ⏳ Not implemented - the detector is deterministic by design |
| Geodesic physics for player locomotion | `gameplay.py` | ⏳ Not implemented - movement is parameter-space kinematics with slope damping |
| Audio, save/load slots, multiplayer, extra languages | - | ⏳ Not implemented |
| Browser screenshots and the 3-minute demo recording | `screenshots/`, `demo/` | ✅ Implemented - 8 screenshots (3 head-less renders plus 5 browser captures) and a 2:59.88 demo recording |

## Installation & Testing

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
node --check web/app.js
```

Current regression status: 269 Python tests pass.

## Reproducible Demo

The fixed seed `12345` provides a deterministic end-to-end demonstration:

```powershell
.\.venv\Scripts\python.exe -m src.main --demo-scenario
```

The script prints real detector readings while moving, placing markers, measuring, and
approaching the hidden exit in a controlled developer-assisted sequence.

A 2:59.88 screen recording of a full session is shipped in `demo/`; the segment from 1:10 to
2:00 plays at three times speed so the tour fits inside three minutes. See `DEMO_LINK.md`
for the recording script and the map notes.

## Comparison with Related Works (相近已有作品对比)

| Work | What it is | How this project differs |
| :--- | :--- | :--- |
| *Hyperbolica* (CodeParade, 2022) | A first-person walking sim inside constant-curvature hyperbolic space. | Hyperbolica lives in a hyperbolic model with a closed-form distance function. This project lives on **variable**-curvature surfaces, computes `K` analytically at every point, and never tells the player the distance: curvature must be *measured* (Gauss-Bonnet, holonomy, BDP circle) before the exit detector unlocks. |
| *Manifold Garden* (William Chyr, 2019) | Hand-authored impossible-geometry puzzle spaces with wrap-around architecture. | Manifold Garden's impossible spaces are designed by hand and the geometry is felt rather than measured. Here the manifolds (torus, Klein bottle, projective plane, knotted torus, elliptic curve) are generated procedurally from parameters, and the game ships real surveying instruments whose readings are the puzzle answers. |
| *HyperRogue* (Zeno Rogue, 2011-) | A roguelike on a hyperbolic tiling, played on a discrete grid. | HyperRogue's curvature is constant and its world is a tiling with a known metric. This project keeps a continuous parameter space, an edited rope/circle construction, and an explicit derivation stage that shows the numeric intermediates of each claim. |

What this project does that the above do not combine:

1. **A seamless 2D local tangent-space map.** The player is pinned to the centre, the
   world scrolls, and periodic seams are crossed with chart-relative deltas, so the
   surface never tears at a seam and no 3D camera cone is needed.
2. **Knowledge as the only key.** The exit detector stays sealed until all five
   geometric seals are claimed, and the player-facing payload never contains exit
   coordinates or true distance.
3. **Measurement as construction.** Three pegs plus a rope pulled into its circumcircle
   *is* the Bertrand-Diquet-Puisseux circle; the geometry is performed, not narrated.
4. **A live derivation stage.** Every seal opens a two-column KaTeX proof that replays
   the real numbers of that run, step by step, instead of a static explanation card.

## Core Design Decisions & Trade-offs (核心设计决策与技术取舍)

1. **2D local tangent map instead of a 3D first-person camera.** On an embedded surface
   there is no canonical "forward". An earlier 3D first-person prototype produced
   clipping artefacts and unsmooth motion around obstacles and seam regions. The local
   tangent map removes that class of bug, keeps the metric visible through grid
   distortion, and makes the instruments readable at a glance.
   Trade-off: less immersive, no horizon, and the surface is inferred rather than seen.
2. **Ambient Euclidean detector distance instead of geodesic distance.** Geodesic
   distance on a variable-curvature surface needs an eikonal solve per query and would
   leak the metric. The ambient distance is analytic and deterministic, and it forces the
   player to use intrinsic measurements.
   Trade-off: the detector is not an intrinsic quantity, so the game supplies intrinsic
   instruments (goniometer, holonomy transport, rope length).
3. **Adaptive, tolerant quest thresholds.** Analytic targets are exact, but peg placement
   is pixel-level. Thresholds scale with the local curvature magnitude so the required
   physical precision stays roughly constant across map scales (`0.5x` to `4x`).
   Trade-off: high-curvature maps forgive more sloppiness than flat ones.
4. **A finite rope pool in Hard mode.** Rope becomes a budget resource, which adds a
   planning layer and feeds the frugality part of the score.
   Trade-off: it punishes free exploration, which is why it is confined to Hard mode.
5. **Client-owned movement, server-owned truth.** The browser integrates locomotion at
   60 FPS for zero perceived latency and posts its position about every 200 ms; the
   server still owns world state, collision audit, victory, timing and every privileged
   value, and it re-clamps the adopted position.
   Trade-off: tiny client/server divergence is tolerated instead of fought.
6. **Standard-library HTTP server.** No framework, no build step, no deployment risk:
   `python -m src.main --serve` is the whole stack.
   Trade-off: no server push, so the client polls (200 ms) instead of receiving events.
7. **A per-trial countdown in Hard mode.** Each seal is a self-contained timed exercise,
   and the countdown is monotonic inside a trial: only accepting a new trial restarts it.
   Trade-off: a single run-level timer would make the fifth trial nearly unwinnable.
8. **Scoring weighted toward frugality.** Time alone would reward reckless sprinting, so
   marker, rope and tool discipline are scored alongside the clear bonus.

## Data Statement (数据说明)

- **Everything is programmatic.** The manifold parameters, terrain undulation, obstacle
  placement, start point and hidden exit are generated by the mathematical model from an
  explicit seed. There is no imported terrain, mesh or heightmap asset.
- **No real-world or personal data.** The project contains no faces, no location data, no
  user accounts, no telemetry and no student or teacher evaluation content. The server
  binds `127.0.0.1` only and never uploads anything.
- **No third-party datasets or imagery.** All figures come from the project's own
  geometry kernel (Matplotlib renders) or from captures of the running web UI.
- **Reproducibility.** The fixed seed `12345` reproduces the same surface, start, exit and
  every proof number; the derivation stage recomputes its values live instead of
  replaying a recording.
- **Synthetic randomness.** Where randomness is used (obstacle scatter), it comes from a
  seeded deterministic generator, so the same seed always yields the same world.

## Submission Materials (提交材料)

| Item | Location | Notes |
| :--- | :--- | :--- |
| Source code | `src/`, `web/`, `tests/` | 269 automated tests plus `node --check web/app.js` |
| Documentation | `README.md`, `README_CN.md`, `docs/` | English main README plus a full Chinese translation |
| AI collaboration log | `AI_USAGE.md`, `ai-logs/` | Per-task record of AI-assisted work |
| Runtime screenshots | `screenshots/` | 8 images: three head-less renders plus the lobby, three live player views (roaming, tool readouts, survey overlays) and the omniscient view |
| Demo | `demo/`, `DEMO_LINK.md` | 3-minute recording or an external link, plus a suggested recording script |
| Email package | `submission/TheCurvedWorld_MidnightAcademy_Submission.zip` | Rebuild with `make package` (`scripts/package_submission.py`) |

## Known Limitations

- The renderer is a lightweight local canvas/Matplotlib prototype, not a full game engine.
- The detector is deterministic and currently has no measurement noise.
- Movement happens in parameter space and is not a geodesic physical simulation.
- Klein bottles, the projective plane and the knotted torus are immersed models, so ambient
  self-intersections are intentional mathematical properties rather than rendering bugs.
- `double_torus` is a genus-2 visual approximation; the chart remains genus 1.
- Hard mode is intentionally severe: it combines a 500 m rope pool, eight marker pegs and a
  quest countdown.
- The eye pointer (three limited uses, a quantised tangent-plane bearing) is implemented in
  the server kernel and its counter is shown in the HUD, but the current web build exposes
  no button or key for it: the `1`-`5` hotbar is Detector / Marker Peg / Rope / Measure /
  Codex. The lobby label that still says "eye pointer" is legacy wording.