# Task 4 — Final Validation Report

This report covers the whole prototype (Task 1-4). It is written to be honest:
things that were not tested are not claimed to work.

## 1. Implemented features

| Feature | Where | Status |
| :--- | :--- | :--- |
| Smooth graph-surface geometry (`height` / `position` / analytic `gradient` / `normal` / `contains` / `sample_grid`) | `src/the_curved_world/geometry.py` | implemented, tested |
| Deterministic world generation from an explicit seed (surface + start + hidden exit + minimum separation) | `src/the_curved_world/world.py` | implemented, tested |
| Ambient Euclidean distance (`||P - Q||_2`) | `src/the_curved_world/geometry.py` | implemented, tested |
| Exponential detector `signal = exp(-d/scale)`, strictly decreasing in distance | `src/the_curved_world/detector.py` | implemented, tested |
| Information boundary (privileged `WorldState` / `DebugView` vs player-facing `PlayerView` / `PlayerObserver`) | `observations.py`, `world.py` | implemented, audited by tests |
| Parameter-space movement, boundary clamping, diagonal normalisation | `src/the_curved_world/gameplay.py` | implemented, tested |
| Observation with signal + qualitative label + trend | `observations.py`, `gameplay.py` | implemented, tested |
| Exploration log, named markers, measurement probe between markers | `src/the_curved_world/gameplay.py` | implemented, tested |
| Victory by capture radius + completion summary (seed included) | `src/the_curved_world/gameplay.py` | implemented, tested |
| Terminal command interface with input validation | `src/the_curved_world/cli.py` | implemented, tested |
| Matplotlib 3D player view that does not leak hidden state | `src/the_curved_world/render.py` | implemented, tested |
| Explicit developer view (exit, true distance, seed, parameters) | `render.py`, `world.py` | implemented, tested |
| Reproducible demo scenario | `src/the_curved_world/demo.py` | implemented, tested |

## 2. Tests and results

Exact command:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Result on the validation machine (Python 3.13.2, numpy 2.5.4, matplotlib 3.11.2, pytest 9.1.1):

- Total: **70**
- Passed: **70**
- Failed: **0**
- Skipped: **0**
- Warnings: none reported by pytest

Test modules:

| Module | Focus |
| :--- | :--- |
| `tests/test_geometry.py` | surface coordinates, `z = f(x,y)`, gradient vs central differences, unit normals, ambient distance |
| `tests/test_world_generation.py` | reproducibility, domain containment, minimum separation, invalid configuration |
| `tests/test_detector.py` | signal bounds/monotonicity, exponential model, invalid scale, player-facing observation fields |
| `tests/test_gameplay.py` | movement, boundary clamping, diagonal normalisation, markers, measurement, victory, no hidden state in log |
| `tests/test_cli.py` | command parsing, input validation, restart reproducibility, no crash on bad input |
| `tests/test_render.py` | scene matches simulation surface, player view leaks nothing, debug view exposes exit, mesh cache |
| `tests/test_math_audit.py` | Task 4 mathematical audit (numerical checks only - see caveat) |
| `tests/test_information_boundary.py` | Task 4 leak audit over a full CLI transcript and record shapes |
| `tests/test_demo.py` | end-to-end victory, reproducibility, first reading matches the detector model |

### Caveat on the mathematical audit

The gradient and smoothness checks are **numerical** (finite sample sets, central
differences). They do not prove global smoothness for arbitrary user-supplied
height functions. The built-in surface family is smooth by construction (sum of
a sine/cosine wave and Gaussian bumps, all C-infinity) and its derivatives are
analytic. No runtime numerical differentiation is used.

## 3. Reproducible demo

Fixed seed: **12345**.

```powershell
.\.venv\Scripts\python.exe -m src.main --demo-scenario
```

The scenario prints a real transcript: start, initial reading, moves with
comparisons, two markers, a marker-to-marker measurement, then a controlled
approach to the exit whose steering uses the developer view while every printed
detector reading remains genuine. It ends with the victory summary.

Deterministic outcome with seed 12345: victory in **14 steps**, **9 readings**,
**2 markers**.

Interactive play:

```powershell
.\.venv\Scripts\python.exe -m src.main --seed 12345              # terminal
.\.venv\Scripts\python.exe -m src.main --render --view player    # + 3D player view
.\.venv\Scripts\python.exe -m src.main --render --view debug     # + 3D developer view
```

## 4. Known limitations

- The detector is deterministic; there is **no** measurement noise.
- Movement is in parameter space; it is **not** geodesic motion and **not** a
  physically realistic walking simulation.
- Matplotlib interaction is a command-driven, redraw-per-action prototype. It is
  **not** a real-time 3D game; keyboard movement callbacks are not implemented.
- The surface family is "sine wave + Gaussian hills". Global smoothness is
  guaranteed for this family, not for arbitrary user-supplied functions.
- This is a smooth surface embedded in Euclidean 3D with an ambient-Euclidean
  detector. It is **not** a complete non-Euclidean physics simulation.

## 5. Files created / modified (Task 4)

- `src/the_curved_world/demo.py` (new)
- `src/main.py` (`--demo-scenario`)
- `src/the_curved_world/cli.py` (removed an unused import)
- `tests/test_math_audit.py`, `tests/test_information_boundary.py`, `tests/test_demo.py` (new)
- `README.md`, `AI_USAGE.md`, `docs/final_report.md`