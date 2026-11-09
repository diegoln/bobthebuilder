# Architecture

```
task prompt
   │
   ▼
LLM planner ──► RobotSpec (modules + params + port map)
   ▲                 │
   │ errors          ▼
   └────────── validators (inventory, connectivity, gears, torque, collisions)
                     │ ok
                     ▼
        ┌────────────┴────────────┐
        ▼                         ▼
  LDraw assembler            Pybricks codegen
  (.mpd, BOM, steps)         (ports, wheel size, ratios)
        │                         │
        ▼                         ▼
  render → vision review     simulator run
```

## Core contract

- `RobotSpec` is the only thing the LLM produces. It references modules by id
  and sets their parameters; it never emits raw part placements.
- Every validator is pure: `validate(spec, inventory) -> list[ValidationError]`.
  Errors carry a code, the offending module, and a fix hint the LLM can act on.
- Modules declare the parts they consume, their attachment points, and any
  motors/sensors they contribute (with the port they need).
- Codegen reads geometry (wheel diameter, axle track, gear ratios) from the
  spec, so design and program can't drift apart.

## Module contract (implemented)

`Module.resolve(params) -> ResolvedModule` with: `parts` (ldraw_id → qty),
`sockets` it offers (name, kind, load_capacity), `mounts_on` (socket kind it
needs, `None` for the root), `devices` (role → motor/sensor kind), `gear_pairs`
to check, and `geometry` numbers codegen reads. Param specs carry choices and
ranges so bad params fail in `resolve_with_defaults`, before any validator.

## Validation errors are the API between code and model

`ValidationError{code, message, module, hint, severity}`. The `hint` is written
for the proposer, not a human: "Set gear_center_distance_studs=1.5." Lessons
are literally the most frequent `(code, hint)` pairs in the trace.

## Open questions

- Attachment-point model: grid coordinates on Technic beams vs. named sockets.
- Simulator: GearsBot-style JS sim, MuJoCo, or Webots.
- Instruction generation: LPub3D CLI vs. our own step ordering.
