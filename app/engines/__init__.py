"""Pure-function AI engines — ports of the frontend's JS engines
(Section 6 of the architecture spec). No DB, no HTTP, no side effects:
same inputs always produce the same outputs. Services orchestrate
these; routers never call them directly.
"""
