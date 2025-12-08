# feature/stat vs main changes

- Added a Flask-based stats dashboard entrypoint (`run_stats.py`, `src/api/stats_api.py`) exposing `/api/stats`, `/api/stats/sync`, `/api/options`, `/api/user_stats/latest` and serving `static/stats.html`.
- Introduced `StatsService` with rate-limit-aware DeviantArt fetching, optional deviation detail enrichment, and watcher snapshots; new `StatsRepository` persists current stats, daily snapshots, metadata, and user watcher history.
- Database/schema updates: new tables (`deviation_stats`, `stats_snapshots`, `user_stats_snapshots`, `deviation_metadata`), deviations gain `published_time`, and SQLite connections now use `check_same_thread=False` plus migration hooks for new stats columns.
- Domain/repository changes: `Deviation` carries `published_time`; new dataclasses `DeviationStats`, `StatsSnapshot`, `DeviationMetadata`; `DeviationRepository` stores `published_time` and can update it by deviationid; `create_repositories` returns the stats repository and callers were updated.
- Frontend and tooling: stats dashboard UI added in `static/stats.html` with sorting, sync controls, and watcher header; Flask dependency added; tests cover stats service rate-limit handling and default `published_time` on deviations.
