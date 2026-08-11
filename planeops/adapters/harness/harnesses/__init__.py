"""Known harnesses: one module per harness, discovered, never listed.

The same seam pattern as adapters and mcp clients, one level down: each
module here exposes a `HARNESS` declaring where that tool keeps its settings
and how to read the hooks out of that file's own schema. The adapter above
names no tool; everything vendor-shaped lives here, so supporting another
harness is dropping a module in and nothing central changes.
"""
