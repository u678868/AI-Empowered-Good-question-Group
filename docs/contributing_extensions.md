# Extension Slots

Two plug-in points keep future work cheap: **maps** and **geometry tools**.
Neither requires touching `world.py` or `server.py`.

---

## 1. New map (drop-in file)

Maps live in the package `src/the_curved_world/maps/`. Adding a map is three steps.

**Step 1.** Create `src/the_curved_world/maps/my_map.py`.

**Step 2.** Define a builder class and decorate it.

```python
from src.the_curved_world.manifold import DeformedTorus
from src.the_curved_world.maps import CLOSED_PERIODIC, register_map


@register_map(
    map_id="small_ring",                       # unique id used by the API / lobby
    name="Small Ring (genus 1)",
    description="A compact torus used as an example extension map.",
    topology=CLOSED_PERIODIC,                  # or BOUNDED_PLANE
    placement={"min_separation": 4.0, "boundary_margin": 0.0, "detector_scale": 4.0},
)
class SmallRingMap:
    def build(self, params):                   # params is a dict (may be empty)
        return DeformedTorus(ring_radius=12.0, tube_radius=4.0)
```

**Step 3.** Nothing else. `MapRegistry.discover()` imports every module in the
package on startup, so the registry, `GET /api/maps`, the `--map` CLI flag and
the lobby dropdown all pick the map up automatically.

Rules of thumb:

* the builder must return an object with `position(...)` and `domain`
  (`SmoothSurface`, `DeformedTorus`, `DeformedEllipsoid`, `GenusTwoApproximation`,
  `KleinBottle` or your own duck-typed surface);
* `topology` must be `closed_periodic` or `bounded_plane`;
* keep the parameters in `placement` so the world generator can place the
  start/exit and scale the detector.

### Closed surfaces publish their own chart identification

If your surface identifies points in a way that is *not* the plain periodic
square, subclass `ClosedManifold` and override `chart_periods()` (and
`chart_copy_transforms()`, if one surface point has several chart copies). The
default is one copy and `(2*pi, 2*pi)`.

```python
def chart_copy_transforms(self):
    # each entry: (du, dv, flip_v) -> the copy (u + du, (-v if flip_v else v) + dv)
    return ((0.0, 0.0, False), (math.pi, 0.0, True))
```

Worked examples in the repo: `KleinBottle` (periods `(4*pi, 2*pi)`, two sheets),
`BottleKleinBottle` (same shape of contract, different immersion),
`ProjectivePlane` (four sheets, two of them antipodal).

Never hard-code those numbers in gameplay, obstacle or front-end code: call
`surface.wrap(u, v)` / `surface.chart_relative(u_ref, v_ref, u, v)`.
`/api/state/player` forwards the same contract to the browser as `twisted`,
`orientable`, `chart_periods` and `chart_copies`, and `web/app.js` wraps deltas
with it.

Set `non_orientable=True` in `@register_map(...)` when the model has no global
"outside" (the lobby and the victory modal then label it honestly).

### Quotient worlds: the distance policy

If one *place* on your surface has several 3D realizations that are genuinely
different points (the antipodal pairs of `RP^2`, and not the Klein bottle's
sheets, which land on the same point), plain Euclidean distance is wrong. Put

```python
placement={"distance_mode": "orbit_min", ...}
```

in the `@register_map(...)` call: the detector, the victory check, marker
measurement, the pointer, obstacle collision/vision and the exit placement then
all minimise over the chart copies. Every other map keeps the default
`euclidean` policy, so nothing else changes.

---

## 2. New geometry tool

**Step 1.** Add the measurement to `ExplorationGame` (`src/the_curved_world/gameplay.py`).

```python
def geodesic_step_estimate(self) -> float:
    """Example: a new local measurement the player may request."""
    ...
```

**Step 2.** Dispatch it in `server.py` inside `GameSession.tool(...)`.

```python
if tool == "step_estimate":
    return {"ok": True, "tool": "step_estimate", "value": game.geodesic_step_estimate()}
```

**Step 3.** Add one entry to the front-end tool array (`web/app.js`).

```js
const TOOLS = [
  // ...
  { id: 'step_estimate', name: 'Step estimate', key: '5' },
];
```

The toolbar button, click handler and keyboard shortcut are generated from that
array -- no HTML edit is needed.

---

## 3. Verifying an extension

```powershell
.\.venv\Scripts\python.exe -m pytest                 # full suite
.\.venv\Scripts\python.exe -c "from src.the_curved_world.maps import MapRegistry; print(MapRegistry.ids())"
.\.venv\Scripts\python.exe -m src.main --serve --map <your_map_id>
```

Information boundary reminder: a new tool must never return the hidden exit
position or the exact player-to-exit distance.