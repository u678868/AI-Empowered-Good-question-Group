# Demo Guide - The Curved World

## 1. Run it locally (recommended)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe -m src.main --serve --port 8000
# then open http://127.0.0.1:8000/
```

The lobby lets a reviewer pick one of the five maps, a play mode
(player / omniscient) and a seed, then enter the world. The player view
is a seamless 2D top-down local tangent map: the player stays pinned to
the centre and the grassland scrolls forever with wrapped parameter
deltas, so crossing the periodic seam never tears.

Map list: `Deformed Torus (genus 1)`, `Wavy Ellipsoid (genus 0)`,
`Two-hole Surface (genus-2 look)`, `Klein Bottle (non-orientable)`,
`Traditional Klein Bottle (bottle shape)`, `Knotted Torus (trefoil knot tube)`,
`Elliptic Curve C/(Z + iZ)`, `Real Projective Plane RP^2 (antipodal)` and
`Classic Planar Landscape`.

Three of them are worth showing off in a demo:

* **Klein Bottle** -- the honest one: it cannot be embedded in R^3, so the level
  shows the classical figure-8 *immersion*. It passes through itself, and its
  chart closes only after 4*pi in `u`, because a 2*pi shift there mirrors `v`.
* **Knotted Torus** -- topologically still a plain torus, but the *embedding* is
  a trefoil knot. Two strands pass about 12 units apart in space while being
  half the knot apart along the surface, so the ambient detector simply cannot
  tell them apart.
* **Real Projective Plane** -- the sphere with antipodal points identified: your
  antipode IS you. It is the only level that switches the distance policy
  (`orbit_min`), so a reading is the nearest of the two antipodal realizations.

## 2. Terminal-only demo

```powershell
.\.venv\Scripts\python.exe -m src.main --demo-scenario
.\.venv\Scripts\python.exe -m src.main --play --map torus_genus1 --seed 12345
.\.venv\Scripts\python.exe -m src.main --play --map klein_bottle --seed 12345
.\.venv\Scripts\python.exe -m src.main --play --map knot_garden --seed 12345
```

## 3. Three-minute screen recording (suggested script)

1. 0:00-0:30 - open the lobby, show the nine maps and their math blurbs,
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
