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
  loop.py          # the design loop, trace and lessons
  proposers.py     # ScriptedProposer (tests) and ClaudeProposer (API)
  cli.py           # `bob` command
  inventory/       # parts catalog + kit inventories (LDraw IDs, geometry, counts)
  modules/         # parametric, pre-validated sub-assemblies
  validators/      # deterministic checks returning actionable errors
  codegen/         # Pybricks program generation from a ResolvedSpec
data/parts.json    # parts catalog (geometry per part)
data/inventories/  # kit inventories (counts per part) — 31313 is a SEED, verify it
tests/
```

## The design loop

```
task ──► Proposer ──► RobotSpec ──► validate ──► clean? ──► spec + code + BOM
             ▲                         │
             └──── errors (+ lessons) ─┘
```

Two feedback loops at different speeds:

- **Inner (seconds):** the proposer gets the validator errors for its last
  attempt — each with a code, the offending module and a fix hint — and
  tries again, up to `max_iters`.
- **Outer (across runs):** every attempt is appended to `.bob/trace.jsonl`.
  `Lessons` counts which hints keep firing and prepends the top ones to the
  next run's prompt, so recurring mistakes get fixed before the first attempt.

Validators today: ports (missing / wrong kind / conflict), attachments
(single root, socket kind, load, crowding), inventory against the kit, gear
mesh distance `(t1+t2)/32` studs and whether that distance is buildable on a
beam grid, lift torque vs payload, drive speed sanity, and task coverage.

## Usage

```bash
uv sync
uv run pytest

uv run bob library                       # what the proposer can pick from
uv run bob validate spec.json            # run validators on a hand-written spec
ANTHROPIC_API_KEY=... uv run bob design "follow a black line" --out out/
uv run bob lessons                       # what the trace has taught so far
```

`bob design` writes `spec.json`, `main.py` (Pybricks, ports and geometry
wired from the design) and `bom.json`.
