# Model and Discord review — 2026-10-29

The backtest and port validator now use the same calibrated drive count as Discord/live v6.1. The Python simulator loads a committed `sim_base.json` copied exactly from the deployed data/index.json baseline, instead of silently re-estimating drive rates from changing raw pbp at import while retaining an old calibration grid. Recalibrate the baseline and grid together for future changes.

The CLI now uses the listed starter by default, matching Discord (explicit starter overrides still apply). `/nfl` rejects impossible calendar dates.

Validation: three 100,000-simulation Python/JS distribution comparisons pass; offline `/nfl` payload tests cover 1 and 12-game slates, message limits and each corresponding model result; invalid-date tests pass. Full point-model backtest/validator needs games.csv and teamgames/qbgames/raw pbp, which are not in the checkout. Existing reported historical backtest metrics are not recomputed here. They also require a cutoff audit of calibration fitting before being treated as untouched out-of-sample estimates.

A read-only PR workflow now runs the model/command regressions. No dashboard presentation files were changed.

## Deployment prerequisites

Merge after checks pass. Redeploy the existing Worker for NBA/NHL/LoL changes as applicable; restart the NFL gateway bot after updating its checkout. Live Discord delivery, command registration and hosted secret state have not been verified by these offline tests.
