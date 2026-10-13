# Demo Guide - The Curved World

## 1. Run it locally (recommended)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe -m src.main --serve --port 8000
# then open http://127.0.0.1:8000/
```

The lobby lets a reviewer pick one of the nine registered maps, a play mode
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

## 3. Recorded demo

`demo/TheCurvedWorld_demo_3min.mp4` - 2:59.88, 3020x1734, AAC 160 kbps. It is a full
play session; the segment from 1:10 to 2:00 plays at three times speed so the whole
tour fits in three minutes. Everything else runs at normal speed.

## 4. Three-minute recording script (for re-shooting the demo)

Tool layout of the current build: `1` Exit Detector, `2` Marker Peg, `3` Surveyor Rope,
`4` Measure Tool (`R` toggles Length / Angle), `5` Quest Codex (`J` also opens it),
`H` Easy-mode Field Guide, `G` God View (debug), right-click cuts a rope (`y` / `n`).

1. 0:00-0:30 - open the lobby, show the nine maps and their math blurbs, pick
   `Deformed Torus (genus 1)` in player mode, enter.
2. 0:30-1:20 - run with WASD (the mouse aims, Q/E turn); read the exit detector with `1`
   and watch the signal gauge, then open the Quest Codex with `5` to show the first seal.
3. 1:20-2:00 - drop three markers with `2`, link them with the rope (`3`), then use the
   Measure Tool (`4`, Angle mode) for the Gauss-Bonnet angle sum, and Length mode to pull
   the rope triangle into the Bertrand-Diquet-Puisseux circumcircle.
4. 2:00-2:30 - show the sealed instrument panel and the mission hint area while surveying;
   run into a tree or rock to show the collision disc.
5. 2:30-3:00 - reach the exit to show the victory modal (rank badge, score ledger, steps,
   readings, markers, time, topology, seed), then press `G` in a `--debug` session to
   reveal the whole surface in the omniscient view.

## 5. Automated verification

```powershell
.\.venv\Scripts\python.exe -m pytest
```
