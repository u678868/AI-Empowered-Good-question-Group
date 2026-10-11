# Demo Guide - The Curved World

## 1. Run it locally (recommended)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe -m src.main --serve --port 8000
# then open http://127.0.0.1:8000/
```

The lobby lets a reviewer pick one of the four maps, a play mode
(player / omniscient) and a seed, then enter the world.

## 2. Terminal-only demo

```powershell
.\.venv\Scripts\python.exe -m src.main --demo-scenario
.\.venv\Scripts\python.exe -m src.main --play --map torus_genus1 --seed 12345
```

## 3. Three-minute screen recording (suggested script)

1. 0:00-0:30 - open the lobby, show the four maps and their math blurbs,
   pick `Deformed Torus (genus 1)` in player mode, enter.
2. 0:30-1:20 - walk with WASD (hold), show the fog of war filling in and the
   metric-warped grid; take a detector reading with `Scan`.
3. 1:20-2:00 - drop three markers and run the angle gauge; read the angle sum
   and the Gauss-Bonnet curvature integral.
4. 2:00-2:30 - release a pointer (limited uses) and show the tangent-plane
   bearing plus the pitch angle.
5. 2:30-3:00 - switch to the omniscient view (`G`) to reveal the closed surface
   and the exit, then reopen the lobby and switch to another map.

## 4. Automated verification

```powershell
.\.venv\Scripts\python.exe -m pytest
```
