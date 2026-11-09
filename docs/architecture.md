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

## Open questions

- Attachment-point model: grid coordinates on Technic beams vs. named sockets.
- Simulator: GearsBot-style JS sim, MuJoCo, or Webots.
- Instruction generation: LPub3D CLI vs. our own step ordering.
