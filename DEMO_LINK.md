# Demo Guide - The Curved World

## 1. Run it locally (recommended)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe -m src.main --serve --port 8000
# then open http://127.0.0.1:8000/
```

The lobby lets a reviewer pick one of the four maps, a play mode
(player / omniscient) and a seed, then enter the world. The player view
is a seamless 2D top-down local tangent map: the player stays pinned to
the centre and the grassland scrolls forever with wrapped parameter
deltas, so crossing the periodic seam never tears.

## 2. Terminal-only demo

```powershell
.\.venv\Scripts\python.exe -m src.main --demo-scenario
.\.venv\Scripts\python.exe -m src.main --play --map torus_genus1 --seed 12345
```

## 3. Three-minute screen recording (suggested script)

1. 0:00-0:30 - open the lobby, show the four maps and their math blurbs,
   pick `Deformed Torus (genus 1)` in player mode, enter.
2. 0:30-1:20 - run with WASD (the mouse aims, Q/E turns); take a detector
   reading with `1` (Compass) and watch the signal gauge.
3. 1:20-2:00 - drop three markers with `5` (Beacon) and run the goniometer
   with `3`; read the angle sum and the Gauss-Bonnet curvature integral.
4. 2:00-2:30 - release the Eye pointer with `4` and show the quantised
   tangent-plane bearing; run into a tree/rock to show the hard disc.
5. 2:30-3:00 - reach the exit to show the victory modal (steps, readings,
   markers, time, topology, seed) with Continue Free Roam / Return to
   Lobby, then switch to the omniscient view (`G`) to reveal the surface.

## 4. Automated verification

```powershell
.\.venv\Scripts\python.exe -m pytest
```
