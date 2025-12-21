### Беклог / Issue: Автокомментинг под девиации (photomanager)

#### Контекст

В проекте уже есть работающий механизм «бродкастинга» комментариев на стены профилей
подписчиков (см. `Profile Broadcast`). Там используются:

- шаблоны сообщений + шаблонизатор/синонимайзер (`src\service\message_randomizer.py`)
- центральный HTTP-клиент с retry/backoff и соблюдением `Retry-After`
  (`src\service\http_client.py::DeviantArtHttpClient`)
- воркер с очередью и статусами, управляемый из фронта
- лог отправок в отдельной таблице (для аудита и анализа)

Теперь нужен аналогичный «постер» комментариев, но **под девиации**.

#### Цель

Сделать новый раздел (UI + API + сервис + репозитории) для автоматического
комментинга девиаций:

1) источники девиаций — два:
   - лента «deviantsyouwatch» (подписки)
   - «общая живая лента» DeviantArt (поток общих девиаций)
2) воркер, который перебирает очередь deviation UUID и постит комментарии
3) хранение:
   - очереди девиаций для комментинга со статусами `pending/commented/failed`
   - лога комментирования (включая UUID поста и результат)
   - фиксации успешно обработанных deviation UUID, чтобы не повторяться

Bounded context: `photomanager`.

#### Не-цели (на этом этапе)

- Не менять существующий бродкастинг профилей.
- Не делать «умный» контент-план (расписания, семантика, A/B) — только
  минимальный workflow как у текущих воркеров.
- Не вводить прямые вызовы `requests.get/post` в сервисах — только
  `DeviantArtHttpClient`.

---

### Что можно переиспользовать (эталонные реализации)

#### UI (паттерн раздела и polling)

- `static\profile_broadcast.html` (+ `static\profile_broadcast.js`) — шаблон UI
  раздела с шаблонами, очередью, управлением воркером и статистикой.
- `static\mass_fave.html` (+ `static\mass_fave.js`) — минимальный UI для коллектора
  + воркер-контроля + статусов.

#### API-роуты (структура эндпоинтов)

- `src\api\stats_routes\profile_messages.py` — CRUD шаблонов/очередь/статусы для
  профайл-бродкаста.
- `src\api\stats_routes\mass_fave.py` — паттерн эндпоинтов:
  - `POST /collect`
  - `POST /worker/start`, `POST /worker/stop`
  - `GET /status`
  - `POST /reset-failed`

#### Сервисы (воркер + rate limit)

- `src\service\profile_message_service.py` — воркер:
  - очередь выбранных элементов
  - выбор случайного активного шаблона
  - запись логов в репозиторий
  - останов по лимиту consecutive failures
  - задержка через `http_client.get_recommended_delay()`
- `src\service\mass_fave_service.py` — collector + worker для очереди deviations:
  - сбор из `browse/deviantsyouwatch`
  - сохранение курсора/offset в `feed_state`
  - очередь `feed_deviations` со статусами

#### Storage / репозитории (SQLAlchemy Core)

- Таблицы профайл-бродкаста: `src\storage\profile_message_tables.py`
  - `profile_messages` (шаблоны)
  - `profile_message_logs` (лог)
- Таблицы автофава: `src\storage\feed_tables.py`
  - `feed_deviations` (очередь deviation UUID + статусы)
  - `feed_state` (курсор/offset)
- Репозиторий очереди автофава: `src\storage\feed_deviation_repository.py`
  - статусная модель, attempts/last_error, выборка `get_one_pending()`

---

### Требования к архитектуре (обязательные)

1) **Single Requester Pattern**: все HTTP-запросы к DeviantArt API идут через
   `DeviantArtHttpClient`.
2) **Retry-After Compliance**: воркер и collector используют задержку
   `http_client.get_recommended_delay()`; при 429/503 клиент уважает `Retry-After`.
3) Разделение по слоям:
   - Domain не импортирует storage/service
   - Repositories не ходят в сеть
   - Services не содержат raw SQL (только репозитории)
4) Идемпотентность:
   - один deviation UUID не должен комментироваться повторно
     (минимум — статус `commented` в очереди + уникальность deviationid)

---

### Предлагаемая модель данных (беклог)

Ниже — ориентировочная схема. Имена таблиц/полей могут быть уточнены при
реализации, но смысл должен сохраниться.

#### 1) Шаблоны комментариев

Аналог `profile_messages`, но для комментов под девиации.

- Таблица: `deviation_comment_messages`
  - `message_id` (PK)
  - `title`
  - `body`
  - `is_active`
  - `created_at`, `updated_at`

Репозиторий: `DeviationCommentMessageRepository`.

#### 2) Очередь задач на комментинг

Аналог `feed_deviations` / логики очереди.

- Таблица: `deviation_comment_queue`
  - `deviationid` (PK, уникальный)
  - `source` (например: `watch_feed`, `global_feed`)
  - `ts` (published_time или время попадания в очередь)
  - `status` ENUM-like: `pending`, `commented`, `failed`
  - `attempts` (int)
  - `last_error` (text)
  - `updated_at`

Репозиторий: `DeviationCommentQueueRepository`:

- `add_deviation(deviationid, ts, source)` — upsert; не сбрасывает `commented`
- `get_one_pending()` — выбрать 1 pending (по ts desc)
- `mark_commented(deviationid, commentid, message_id, body_hash?)`
- `mark_failed(deviationid, error)`
- `reset_failed_to_pending()`
- `get_stats()` (pending/commented/failed)

#### 3) Лог комментинга

Аналог `profile_message_logs`, но привязка к deviation.

- Таблица: `deviation_comment_logs`
  - `log_id` (PK)
  - `deviationid`
  - `message_id` (FK на `deviation_comment_messages`)
  - `commentid` (UUID комментария на стороне DA, если есть)
  - `status` (`sent`/`failed`)
  - `error_message`
  - `sent_at`

Репозиторий: `DeviationCommentLogRepository`.

#### 4) Фиксация успешно обработанных deviation UUID (anti-repeat)

Есть два варианта (выбрать один при реализации):

1) **Только очередь**: статус `commented` в `deviation_comment_queue` и
   первичный ключ `deviationid` предотвращают повторную постановку как pending.
2) **Отдельная сущность**: таблица `commented_deviations` (deviationid PK,
   commented_at). Тогда очередь может периодически чиститься.

В рамках требований достаточно варианта (1), но вариант (2) полезен для
«компактизации» очереди.

---

### Источники девиаций (collector) — 2 шт.

#### A) Лента подписок (уже есть эталон)

Использовать подход из `MassFaveService.collect_from_feed()`:

- URL: `https://www.deviantart.com/api/v1/oauth2/browse/deviantsyouwatch`
- пагинация: `offset`, `limit=50`
- хранение курсора: state-таблица (по аналогии с `feed_state`)

#### B) «Общая живая лента» DeviantArt

Точный эндпоинт нужно подтвердить по DA API (TODO).
Сервис должен быть спроектирован так, чтобы можно было легко добавить второй
collector, похожий на A, но с другим URL и своей state-меткой.

Ориентировочно это может быть один из browse-эндпоинтов (`browse/newest`,
`browse/popular`, `browse/hot` и т.п.) или специализированный feed.

---

### Воркер «постера» комментариев

Семантика должна быть максимально похожа на `ProfileMessageService._worker_loop()`:

1) взять 1 `pending` deviationid
2) выбрать случайный активный шаблон
3) сгенерировать тело через `randomize_template()`
4) отправить комментарий под deviation через `DeviantArtHttpClient.post()`
5) на успех:
   - пометить `commented`
   - записать лог со `status=sent`, `commentid`
6) на ошибку:
   - увеличить attempts
   - пометить `failed` при достижении лимита или сразу (как в автофаве)
   - записать лог `status=failed`
7) соблюдать задержку `get_recommended_delay()`
8) останов по `MAX_CONSECUTIVE_FAILURES`

**Важно:** сервис не должен напрямую использовать `requests.*`.

#### URL для постинга комментариев (TODO)

В профайл-бродкасте используется:

- `https://www.deviantart.com/api/v1/oauth2/comments/post/profile/{username}`

Для девиаций требуется подтвердить корректный endpoint.
Ожидаемый паттерн (гипотеза):

- `https://www.deviantart.com/api/v1/oauth2/comments/post/deviation/{deviationid}`

Параметры запроса, вероятно, аналогичные: `body`, `access_token`.

---

### UI / Frontend (новый раздел)

Нужен новый раздел по аналогии с `profile_broadcast.html`:

- Навигация: добавить пункт, например `Auto Comments`.
- Статистика: pending/commented/failed/processed.
- Управление шаблонами:
  - список шаблонов (CRUD)
  - переключение `is_active`
- Коллекторы (2 источника):
  - кнопка «Collect from Watch Feed»
  - кнопка «Collect from Global Feed»
  - параметр `pages` / `limit`
- Управление воркером:
  - start/stop
  - reset-failed
  - clear-queue (опционально)
- Очередь девиаций:
  - таблица deviationid, source, ts, status, attempts, last_error
  - возможность удалить выбранные/очистить

Во многом можно копировать структуру и UX из `static\profile_broadcast.html`.

---

### API (черновой контракт)

Именование ниже — предложение, можно скорректировать под текущий стиль роутов.

- `POST /api/deviation-comments/collect/watch-feed` `{pages}`
- `POST /api/deviation-comments/collect/global-feed` `{pages}`
- `POST /api/deviation-comments/worker/start`
- `POST /api/deviation-comments/worker/stop`
- `GET  /api/deviation-comments/status`
- `POST /api/deviation-comments/reset-failed`

Templates:

- `GET  /api/deviation-comments/messages`
- `POST /api/deviation-comments/messages`
- `PUT  /api/deviation-comments/messages/<id>`
- `DELETE /api/deviation-comments/messages/<id>`

Queue management (опционально):

- `GET /api/deviation-comments/queue?status=pending&limit=...`
- `POST /api/deviation-comments/queue/clear` `{status?}`
- `POST /api/deviation-comments/queue/remove-selected` `{deviationids: [...]}`

---

### Acceptance Criteria (MVP)

1) Очередь deviation UUID заполняется из 2 источников.
2) Воркер успешно постит комментарии под девиации, используя:
   - `DeviantArtHttpClient`
   - `randomize_template()`
3) Повторная обработка того же deviationid не происходит (anti-repeat).
4) В UI есть:
   - управление воркером
   - статистика
   - управление шаблонами
   - видимость очереди и статусов
5) Все операции логируются в DB (sent/failed + error).

---

### Беклог задач (разбиение)

#### P0 (MVP)

1) Storage:
   - добавить SQLAlchemy Core таблицы: очередь + лог + шаблоны
   - создать репозитории: message/queue/log
2) Service:
   - `DeviationCommentService` (collector(2) + worker)
   - интеграция с `DeviantArtHttpClient` и `message_randomizer`
3) API:
   - endpoints по шаблону `mass_fave` + CRUD шаблонов как у `profile_messages`
4) UI:
   - новый HTML/JS раздел, UI-паттерн как у `profile_broadcast.html`
5) Tests:
   - unit: репозитории (SQLite in-memory) — статусы, upsert, get_one_pending
   - unit: сервис воркера — мок HTTP клиента, проверка anti-repeat

#### P1

- Раздельные state-курсоры для двух источников (watch/global)
- Фильтры (mature_content, язык, теги, исключения)
- Лимиты: max comments/day, max per hour, «окна» активности
- Улучшенная идемпотентность: хранить `comment_body_hash` и/или `commentid`

#### P2

- Очистка очереди по TTL + отдельная таблица `commented_deviations`
- Экспорт логов / удобная аналитика в UI
