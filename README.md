# bobthebuilder

AI-assisted designer for LEGO MINDSTORMS EV3 robots. Describe a task, get back a
buildable robot (LDraw model + instructions + bill of materials checked against
your kit) **and** the matching Pybricks program — generated from the same spec.

> Status: early scaffold. Nothing builds a robot yet.

## Idea

LLMs are weak at free-form Technic spatial reasoning but good at composing
well-defined pieces under constraints. So bobthebuilder works like a compiler:

1. **Constrained inventory** — only parts in your actual EV3 set (31313 / 45544),
   by LDraw part ID.
2. **Module library** — pre-validated, parametric sub-assemblies (drive bases,
   grippers, arms, sensor mounts, gear trains). The LLM composes modules and
   sets parameters instead of placing individual bricks.
3. **Deterministic validators** — inventory counts, collisions, legal pin/axle
   connections, gear mesh distances, motor torque vs. load. The LLM proposes,
   validators reject with specific errors, the LLM fixes.
4. **Render-and-look** — render the LDraw model and let a vision model review it.
5. **Simulation** — run the generated Pybricks code against a physics sim.
6. **Outputs** — LDraw `.mpd`, step-by-step instructions (LPub3D/Studio), BOM,
   and a Pybricks program with ports and geometry already wired in.

See [docs/architecture.md](docs/architecture.md).

## MVP scope

"Describe a task (line following, pick up a cube, sumo) → a robot assembled from
5–10 validated EV3 modules + working Pybricks code."

## Layout

```
src/bobthebuilder/
  spec.py          # RobotSpec: the single source of truth for design + code
  inventory/       # kit part lists (LDraw IDs + counts)
  modules/         # parametric, pre-validated sub-assemblies
  validators/      # deterministic checks returning actionable errors
  codegen/         # Pybricks program generation from a RobotSpec
data/inventories/  # kit inventory files
tests/
```

## Development

```bash
uv sync
uv run pytest
```
