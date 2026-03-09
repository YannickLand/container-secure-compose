# Tests TODO

Entries below document test gaps that cannot be automated yet.

---

## TODO: generate() properties merge collision warning

**Feature / function:** `csc.generator.generate()` — line 233 (`warnings.append(f"[{entry.name}] properties: {w}")`)
**Reason:** This branch is unreachable with the current `_merge` implementation. When `override=True`, `_merge` replaces scalars silently and never emits warnings. The code path would only execute if `_merge(override=True)` returned non-empty warnings for a properties-vs-block collision, but the function deliberately suppresses those warnings in override mode.
**Would verify:** That `generate()` correctly propagates any collision warnings from the properties merge step.
**Prerequisite:** Either change `_merge` to optionally emit warnings even when `override=True`, or remove the dead branch if the design intent is that properties always silently win over block defaults.

---

## TODO: `return` after `ctx.exit(1)` in CLI commands

**Feature / function:** `csc.cli` — lines 144, 152, 243, 252, 352 (and similar patterns)
**Reason:** These are `return` statements immediately after `ctx.exit(1)` calls. In Click, `ctx.exit(n)` raises `SystemExit(n)`, making any subsequent `return` unreachable. They exist as defensive coding but cannot be exercised by any test.
**Would verify:** Nothing of practical value — coverage tools flag them as missed, but they are syntactically dead.
**Prerequisite:** Remove the redundant `return` statements or replace `ctx.exit(1)` with `sys.exit(1)` (which also raises SystemExit but where a `return` would be expected by type checkers).
