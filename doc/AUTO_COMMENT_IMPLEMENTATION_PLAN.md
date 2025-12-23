# План реализации: Auto-Comment под девиации (photomanager)

## Контекст и рамки
- [x] Bounded context: photomanager.
- [x] HTTP: только `DeviantArtHttpClient` + задержки через `get_recommended_delay()`.
- [x] DDD: domain без I/O, storage без HTTP, service без SQL.
- [x] Anti-repeat: deviationid уникален, повторная постановка исключается.

## Решения перед стартом
- [x] Endpoint подтвержден: `https://www.deviantart.com/api/v1/oauth2/comments/post/deviation/{deviationid}` (POST; `body` обязателен, `commentid` опционален; scopes: `browse`, `comment.post`).
- [x] Зафиксировать наименование таблиц: `deviation_comment_*`.
- [x] Добавить OAuth scope `comment.post` в `DA_SCOPES` и `.env.example`; обновить дефолт в `src/config/settings.py`.
- [x] Стратегия dedupe: статус `commented` + PK `deviationid` в queue.

## Пошаговый план (по файлам и методам)

### 1) Domain layer
`src/domain/models.py`
- [x] Добавить Enum `DeviationCommentQueueStatus` = `pending/commented/failed`.
- [x] Добавить Enum `DeviationCommentLogStatus` = `sent/failed`.
- [x] Добавить dataclass `DeviationCommentMessage`:
  - [x] поля: `message_id`, `title`, `body`, `is_active`, `created_at`, `updated_at`.
- [x] Добавить dataclass `DeviationCommentQueueItem`:
  - [x] поля: `deviationid`, `deviation_url`, `title`, `author_username`, `author_userid`, `source`, `ts`, `status`, `attempts`, `last_error`, `created_at`, `updated_at`.
- [x] Добавить dataclass `DeviationCommentLog`:
  - [x] поля: `log_id`, `message_id`, `deviationid`, `deviation_url`, `author_username`, `commentid`, `comment_text`, `status`, `error_message`, `sent_at`.

### 2) Storage tables (SQLAlchemy Core)
`src/storage/deviation_comment_tables.py` (новый)
- [x] `metadata = MetaData()`.
- [x] `deviation_comment_messages`:
  - [x] `message_id` PK, `title`, `body`, `is_active`, `created_at`, `updated_at`.
- [x] `deviation_comment_queue`:
  - [x] `deviationid` PK, `deviation_url`, `title`, `author_username`, `author_userid`, `source`, `ts`, `status`, `attempts`, `last_error`, `created_at`, `updated_at`.
  - [x] `CheckConstraint` по статусу `pending/commented/failed`.
- [x] `deviation_comment_logs`:
  - [x] `log_id` PK, `message_id` FK, `deviationid`, `deviation_url`, `author_username`, `commentid`, `comment_text`, `status`, `error_message`, `sent_at`.
  - [x] `CheckConstraint` по статусу `sent/failed`.
- [x] `deviation_comment_state`:
  - [x] `key` PK, `value`, `updated_at`.
- [x] Индексы: `status`, `ts`, `deviationid`, `source`, `message_id`.

`src/storage/adapters/sqlalchemy_adapter.py`
- [x] Импортировать `deviation_comment_tables.metadata`.
- 
- [x] В `initialize()` добавить `metadata.create_all(bind=conn)`.

### 3) Storage repositories
`src/storage/deviation_comment_message_repository.py` (новый)
- [x] `_execute_core(statement)`
- [x] `_scalar(statement)`
- [x] `create_message(title, body) -> int`
- [x] `get_message_by_id(message_id) -> DeviationCommentMessage | None`
- [x] `get_all_messages() -> list[DeviationCommentMessage]`
- [x] `get_active_messages() -> list[DeviationCommentMessage]`
- [x] `update_message(message_id, title=None, body=None, is_active=None) -> None`
- [x] `delete_message(message_id) -> None`

`src/storage/deviation_comment_queue_repository.py` (новый)
- [x] `_execute_core(statement)`
- [x] `_scalar(statement)`
- [x] `add_deviation(deviationid, ts, source, title=None, author_username=None, author_userid=None, deviation_url=None) -> None`
  - [x] Upsert: не сбрасывать `commented`, обновлять `ts = max(existing, incoming)`.
- [x] `get_one_pending() -> dict | None`
- [x] `get_pending(limit=100) -> list[DeviationCommentQueueItem]` (для UI)
- [x] `mark_commented(deviationid, commentid=None, message_id=None, comment_text=None) -> None`
- [x] `mark_failed(deviationid, error) -> None`
- [x] `bump_attempt(deviationid, error) -> None`
- [x] `reset_failed_to_pending() -> int`
- [x] `clear_queue(status=None) -> int`
- [x] `get_stats() -> dict` (pending/commented/failed/total)
- [x] `get_recent_commented(limit=50) -> list[DeviationCommentQueueItem]`
- [x] `remove_by_ids(deviationids: list[str]) -> int` (если нужен remove-selected в UI)

`src/storage/deviation_comment_log_repository.py` (новый)
- [x] `_execute_core(statement)`
- [x] `_scalar(statement)`
- [x] `add_log(message_id, deviationid, deviation_url, author_username, commentid, comment_text, status, error_message=None) -> int`
- [x] `get_logs(limit=100, status=None, offset=0) -> list[DeviationCommentLog]`
- [x] `get_commented_deviationids() -> set[str]`
- [x] `get_stats_by_template() -> dict`

`src/storage/deviation_comment_state_repository.py` (новый, если state не в queue repo)
- [x] `get_state(key) -> str | None`
- [x] `set_state(key, value) -> None` (upsert)

`src/storage/__init__.py`
- [x] Экспортировать новые репозитории.

### 4) Service layer
`src/service/comment_collector_service.py` (новый)
- [x] `class CommentCollectorService`
- [x] `collect_from_watch_feed(access_token: str, max_pages: int = 5) -> dict`
  - [x] state key: `comment_watch_offset`.
- [x] `collect_from_global_feed(access_token: str, max_pages: int = 5) -> dict`
  - [x] state key: `comment_global_offset`.
- [x] `_collect(url, access_token, offset_key, max_pages) -> dict`
- [x] `_normalize_deviation(api_item) -> dict`
- [x] Между страницами: `delay = http_client.get_recommended_delay()` + `time.sleep(delay)`.

`src/service/comment_poster_service.py` (новый)
- [x] `class CommentPosterService`
- [x] Константа `COMMENT_URL` = `https://www.deviantart.com/api/v1/oauth2/comments/post/deviation/{deviationid}`.
- [x] `start_worker(access_token: str, template_id: int | None = None) -> dict`
- [x] `stop_worker() -> dict`
- [x] `get_worker_status() -> dict`
- [x] `_worker_loop(access_token, template_id) -> None`
- [x] `_select_template(template_id) -> DeviationCommentMessage | None`
- [x] `_render_comment(body: str) -> str` (через `randomize_template`)
- [x] `_post_comment(access_token, deviationid, body, commentid: str | None = None) -> response`
- [x] `_handle_success(queue_item, template, comment_text, commentid) -> None`
- [x] `_handle_failure(queue_item, error_msg) -> None`
- [x] Ограничения: `MAX_CONSECUTIVE_FAILURES`, `MAX_ATTEMPTS` (например 3).
- [x] Все HTTP через `DeviantArtHttpClient`. Сон - только `get_recommended_delay()`.

`src/service/__init__.py`
- [x] Экспортировать новые сервисы.

### 5) API layer
`src/api/stats_routes/deviation_comments.py` (новый)
- [x] `register_deviation_comment_routes(app, get_services, get_deviation_comment_service)`
- [x] Templates:
  - [x] `GET /api/deviation-comments/messages`
  - [x] `POST /api/deviation-comments/messages`
  - [x] `PUT /api/deviation-comments/messages/<id>`
  - [x] `DELETE /api/deviation-comments/messages/<id>`
  - [x] (опционально) `POST /api/deviation-comments/messages/<id>/toggle`
- [x] Collect:
  - [x] `POST /api/deviation-comments/collect/watch-feed`
  - [x] `POST /api/deviation-comments/collect/global-feed`
- [x] Queue:
  - [x] `GET /api/deviation-comments/queue?status=pending&limit=...`
  - [x] `POST /api/deviation-comments/queue/clear`
  - [x] `POST /api/deviation-comments/queue/reset-failed`
  - [x] `POST /api/deviation-comments/queue/remove-selected` (опционально)
- [x] Worker:
  - [x] `POST /api/deviation-comments/worker/start`
  - [x] `POST /api/deviation-comments/worker/stop`
  - [x] `GET /api/deviation-comments/worker/status`
- [x] Logs:
  - [x] `GET /api/deviation-comments/logs`
  - [x] `GET /api/deviation-comments/logs/stats`
- [x] Сериализация дат: поддержка `str` и `datetime` (как в profile_messages).

`src/api/stats_routes/__init__.py`
- [x] Экспортировать `register_deviation_comment_routes`.

`src/api/stats_api.py`
- [x] Добавить `get_deviation_comment_service()`:
  - [x] отдельные соединения для repo (message/log/queue/state)
  - [x] собрать сервисы collector + poster.
- [x] В `create_app()` зарегистрировать новые роуты.

### 6) Frontend
`static/auto_comment.html` (новый)
- [x] Раздел Templates (CRUD).
- [x] Раздел Queue/Collector (watch feed / global feed).
- [x] Раздел Worker (start/stop, статус).
- [x] Раздел Logs/Recent.

`static/auto_comment.js` (новый)
- [x] API-клиент для эндпоинтов.
- [x] Polling статуса/очереди.
- [x] Рендер списков шаблонов и логов.

`static/stats.html` и/или `static/profile_broadcast.html`
- [x] Добавить пункт меню и ссылку на Auto Comment.

### 7) Config/Docs
`.env.example`
- [x] Добавить `comment.post` в `DA_SCOPES`.

`README.md` / `README_RU.md`
- [x] Краткое описание нового раздела и базового запуска.

### 8) Tests (по стандарту проекта)
`tests/test_deviation_comment_repositories.py`
- [x] CRUD шаблонов, upsert очереди, get_one_pending, reset_failed, stats.

`tests/test_deviation_comment_services.py`
- [x] Collector: дедуп, offset/state, delay через http_client.
- [x] Poster: выбор шаблона, логирование, статусы, лимит попыток, consecutive failures.

## Примечания
- [x] Endpoint: `POST /api/v1/oauth2/comments/post/deviation/{deviationid}` (body обязателен, commentid опционален).
- [x] OAuth scopes: `browse`, `comment.post`.
- [x] Dedupe реализуется через unique PK deviationid + статус `commented`.
- [x] Все задержки и повторы - через `DeviantArtHttpClient`.


