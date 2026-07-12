# Alembic migrations

Empty placeholder for Step 1 (Backend Bootstrap) — there are no database
models yet to migrate.

Step 2 (DB layer) will run `alembic init` here properly and add:

- `alembic/env.py`
- `alembic/script.py.mako`
- `alembic/versions/0001_initial.py` (creates `users`, `trades`,
  `ai_analyses`, `scoring_weights`, `ml_exports` + the seeded
  `users(id=1)` row)

and wire `DATABASE_URL` from `app.config.get_settings()` into
`alembic/env.py` so migrations use the same connection string as the app.
