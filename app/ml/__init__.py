"""Sprint 7 — Machine Learning package.

Everything under ``app/ml`` is new in Sprint 7 and does not modify any
Sprint 6 module. It builds on top of the Sprint 6 ML dataset contract
(``app/engines/ml_dataset.py`` / ``app/services/ml_service.py``) rather
than changing it: Sprint 6's ``build_dataset()``/``validate_row()`` are
imported and reused as-is.

Modules:

- ``dataset_validation.py`` — Phase 1: a richer, dataset-level
  validation report (missing-field breakdown, duplicate detection,
  class distribution) on top of Sprint 6's per-row validation.
- ``features.py`` — Phase 2: turns flattened ML rows into a feature
  matrix (categorical encoding + numeric scaling happen inside the
  persisted scikit-learn ``Pipeline``, not here) and computes the one
  new engineered feature Sprint 6 didn't have (``hist_strategy_health_score``).
- ``train.py`` — Phase 3/4: train/validation/test split, trains and
  compares Logistic Regression / Random Forest / Gradient Boosting,
  and selects the best model.
- ``persistence.py`` — Phase 6: joblib save/load with versioning.
- ``predict.py`` — Phase 5: turns a candidate (not-yet-logged) trade
  into a feature row using the user's real trade history, and runs it
  through the active persisted model.
"""
