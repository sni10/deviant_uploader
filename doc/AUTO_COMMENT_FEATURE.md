# Auto-Comment Feature Backlog

## Overview

Реализация автоматического комментирования девиаций с использованием шаблонизатора-синонимайзера. Аналогично Profile Broadcast, но комментарии отправляются под девиации вместо профилей пользователей.

## Core Concept

**Profile Broadcast** (текущий) → комментарии на стены профилей подписчиков
**Auto-Comment** (новый) → комментарии под девиации из двух источников

## Источники девиаций

### 1. Feed (Лента подписок)
- Девиации из ленты пользователей, на которых я подписан
- Аналогично текущему `feed auto-fave` механизму
- API endpoint: `/feed` (browse endpoint with user filtering)

### 2. Browse (Живая лента)
- Общий поток новых девиаций DeviantArt
- Фильтрация по категориям/тегам (опционально)
- API endpoint: `/browse/newest`

## Architecture Components

### Database Layer

#### Таблицы

**1. `comment_queue` - Очередь девиаций для комментирования**
```sql
CREATE TABLE comment_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deviationid TEXT NOT NULL UNIQUE,
    deviation_url TEXT,
    title TEXT,
    author_username TEXT,
    author_userid TEXT,
    source TEXT NOT NULL,  -- 'feed' or 'browse'
    ts BIGINT NOT NULL,    -- timestamp from feed/browse
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, commented, failed
    attempts INTEGER DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_comment_queue_status ON comment_queue(status);
CREATE INDEX idx_comment_queue_deviationid ON comment_queue(deviationid);
CREATE INDEX idx_comment_queue_source ON comment_queue(source);
CREATE INDEX idx_comment_queue_status_ts ON comment_queue(status, ts DESC);
```

**2. `comment_templates` - Шаблоны комментариев**
```sql
CREATE TABLE comment_templates (
    template_id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    body TEXT NOT NULL,  -- Текст с синонимами в формате {word1|word2|word3}
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**3. `comment_logs` - Лог отправленных комментариев**
```sql
CREATE TABLE comment_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER,
    deviationid TEXT NOT NULL,
    deviation_url TEXT,
    author_username TEXT,
    commentid TEXT,  -- DeviantArt comment UUID
    comment_text TEXT,  -- Финальный текст после рендера синонимов
    status TEXT NOT NULL,  -- 'sent', 'failed'
    error_message TEXT,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (template_id) REFERENCES comment_templates(template_id)
);

CREATE INDEX idx_comment_logs_deviationid ON comment_logs(deviationid);
CREATE INDEX idx_comment_logs_status ON comment_logs(status);
CREATE INDEX idx_comment_logs_template_id ON comment_logs(template_id);
```

**4. `comment_state` - Состояние коллекторов**
```sql
CREATE TABLE comment_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Repository Layer

**1. `CommentQueueRepository`**
```python
class CommentQueueRepository(BaseRepository):
    """Управление очередью девиаций для комментирования."""

    def add_deviation(deviationid, title, author, source, ts, url=None)
    def get_one_pending() -> dict | None
    def mark_commented(deviationid, commentid)
    def mark_failed(deviationid, error)
    def bump_attempt(deviationid, error)
    def get_stats() -> dict  # {pending, commented, failed, total}
    def clear_queue(status=None)
    def reset_failed_to_pending()
    def get_recent_commented(limit=50)
```

**2. `CommentTemplateRepository`**
```python
class CommentTemplateRepository(BaseRepository):
    """Управление шаблонами комментариев."""

    def create_template(title, body) -> int
    def get_template_by_id(template_id) -> CommentTemplate | None
    def get_all_templates() -> list[CommentTemplate]
    def get_active_templates() -> list[CommentTemplate]
    def get_random_active_template() -> CommentTemplate | None
    def update_template(template_id, title=None, body=None, is_active=None)
    def delete_template(template_id)
    def toggle_active(template_id)
```

**3. `CommentLogRepository`**
```python
class CommentLogRepository(BaseRepository):
    """Лог отправленных комментариев."""

    def log_comment(template_id, deviationid, deviation_url, author_username,
                   commentid, comment_text, status, error_message=None)
    def get_logs(limit=100, status=None) -> list[dict]
    def get_commented_deviations() -> set[str]  # deviationids для дедупликации
    def get_stats_by_template() -> dict
```

### Service Layer

**1. `CommentCollectorService`**
```python
class CommentCollectorService:
    """Сборщик девиаций из Feed и Browse."""

    def __init__(http_client, comment_queue_repo, comment_log_repo)

    def collect_from_feed(limit=50) -> int:
        """Собрать девиации из feed (лента подписок)."""
        # - Получить offset из comment_state
        # - Запрос к /feed
        # - Фильтровать уже обработанные (check comment_logs)
        # - Добавить в comment_queue с source='feed'
        # - Обновить offset в comment_state
        # - Вернуть количество добавленных

    def collect_from_browse(limit=50) -> int:
        """Собрать девиации из browse (живая лента)."""
        # - Получить offset из comment_state
        # - Запрос к /browse/newest
        # - Фильтровать уже обработанные
        # - Добавить в comment_queue с source='browse'
        # - Обновить offset в comment_state
        # - Вернуть количество добавленных
```

**2. `CommentPosterService`**
```python
class CommentPosterService:
    """Сервис отправки комментариев."""

    def __init__(http_client, template_repo, queue_repo, log_repo)

    def post_comment(deviationid: str, template_id: int = None) -> dict:
        """Отправить комментарий под девиацию.

        Returns:
            {
                'success': bool,
                'commentid': str | None,
                'comment_text': str,
                'error': str | None
            }
        """
        # - Получить/выбрать шаблон (random.choice() если не указан)
        # - Рендерить синонимы через message_randomizer.randomize_template()
        # - POST /comments?deviationid={uuid} с body=comment_text
        # - Залогировать в comment_logs
        # - Вернуть результат

    def process_next() -> dict:
        """Обработать следующую девиацию из очереди."""
        # - Получить один pending из queue
        # - Вызвать post_comment()
        # - Обновить статус в queue (commented/failed)
        # - Вернуть результат
```

**3. `TemplateRenderer` (уже существует)**
```python
class TemplateRenderer:
    """Рендеринг шаблонов с синонимами."""

    def render(template: str) -> str:
        """Заменить {word1|word2|word3} на случайный выбор."""
        # Уже реализовано в profile_message_service.py
```

### API Layer

**`src/api/comment_api.py`** (новый)

```python
from flask import Blueprint, request, jsonify

comment_bp = Blueprint('comment', __name__, url_prefix='/api/comment')

# === Templates ===
@comment_bp.route('/templates', methods=['GET'])
def get_templates():
    """Получить все шаблоны."""

@comment_bp.route('/templates', methods=['POST'])
def create_template():
    """Создать новый шаблон."""
    # body: {title, body}

@comment_bp.route('/templates/<int:template_id>', methods=['PUT'])
def update_template(template_id):
    """Обновить шаблон."""

@comment_bp.route('/templates/<int:template_id>', methods=['DELETE'])
def delete_template(template_id):
    """Удалить шаблон."""

@comment_bp.route('/templates/<int:template_id>/toggle', methods=['POST'])
def toggle_template(template_id):
    """Переключить активность шаблона."""

# === Queue Management ===
@comment_bp.route('/queue/stats', methods=['GET'])
def get_queue_stats():
    """Статистика очереди."""

@comment_bp.route('/queue/collect/feed', methods=['POST'])
def collect_from_feed():
    """Собрать девиации из feed."""
    # body: {limit: 50}

@comment_bp.route('/queue/collect/browse', methods=['POST'])
def collect_from_browse():
    """Собрать девиации из browse."""
    # body: {limit: 50}

@comment_bp.route('/queue/clear', methods=['POST'])
def clear_queue():
    """Очистить очередь."""
    # body: {status: 'pending' | 'commented' | 'failed' | null}

@comment_bp.route('/queue/reset-failed', methods=['POST'])
def reset_failed():
    """Сбросить failed → pending."""

# === Worker Control ===
@comment_bp.route('/worker/status', methods=['GET'])
def get_worker_status():
    """Статус воркера (running/stopped)."""

@comment_bp.route('/worker/start', methods=['POST'])
def start_worker():
    """Запустить воркер."""
    # body: {template_id: int | null, delay_seconds: 30}

@comment_bp.route('/worker/stop', methods=['POST'])
def stop_worker():
    """Остановить воркер."""

# === Logs ===
@comment_bp.route('/logs', methods=['GET'])
def get_logs():
    """Получить лог комментариев."""
    # query: ?limit=100&status=sent

@comment_bp.route('/logs/stats', methods=['GET'])
def get_log_stats():
    """Статистика по шаблонам."""
```

### Worker

**`comment_worker.py`** (новый скрипт)

```python
#!/usr/bin/env python3
"""Background worker для отправки комментариев."""

import time
import signal
import sys
from src.service.comment_poster_service import CommentPosterService

class CommentWorker:
    def __init__(self, delay_seconds=30, template_id=None):
        self.delay_seconds = delay_seconds
        self.template_id = template_id
        self.running = False

    def start(self):
        """Запустить воркер."""
        self.running = True
        signal.signal(signal.SIGINT, self._handle_stop)
        signal.signal(signal.SIGTERM, self._handle_stop)

        print(f"🚀 Comment Worker started (delay={self.delay_seconds}s)")

        while self.running:
            try:
                result = comment_poster_service.process_next()

                if result['success']:
                    print(f"✓ Comment sent: {result['deviationid']}")
                else:
                    print(f"✗ Failed: {result['error']}")

                time.sleep(self.delay_seconds)

            except Exception as e:
                print(f"Error: {e}")
                time.sleep(self.delay_seconds)

    def _handle_stop(self, signum, frame):
        print("\n🛑 Stopping worker...")
        self.running = False
        sys.exit(0)

if __name__ == '__main__':
    worker = CommentWorker(delay_seconds=30)
    worker.start()
```

### Frontend

**`static/auto_comment.html`** (новый)

Структура аналогична `profile_broadcast.html`:

```
┌─────────────────────────────────────────┐
│ Auto Comment Dashboard                   │
├─────────────────────────────────────────┤
│                                          │
│ ┌─ Templates ────────────────────────┐  │
│ │ [+ Add Template]                   │  │
│ │                                     │  │
│ │ Template 1  [Edit] [Toggle] [Del]  │  │
│ │ Template 2  [Edit] [Toggle] [Del]  │  │
│ └─────────────────────────────────────┘  │
│                                          │
│ ┌─ Queue Management ─────────────────┐  │
│ │ Source:                             │  │
│ │ ○ Feed (subscriptions)              │  │
│ │ ○ Browse (live stream)              │  │
│ │                                     │  │
│ │ [Collect 50 Deviations]             │  │
│ │                                     │  │
│ │ Stats:                              │  │
│ │ Pending: 125 | Commented: 43        │  │
│ │ Failed: 2    | Total: 170           │  │
│ │                                     │  │
│ │ [Clear Pending] [Reset Failed]      │  │
│ └─────────────────────────────────────┘  │
│                                          │
│ ┌─ Worker Control ───────────────────┐  │
│ │ Status: ⚫ Stopped                  │  │
│ │                                     │  │
│ │ Template: [Random ▼]                │  │
│ │ Delay: [30] seconds                 │  │
│ │                                     │  │
│ │ [▶ Start Worker] [⏹ Stop Worker]   │  │
│ └─────────────────────────────────────┘  │
│                                          │
│ ┌─ Recent Comments ──────────────────┐  │
│ │ ✓ Deviation A | Template 1 | 2m ago│  │
│ │ ✗ Deviation B | Template 2 | 5m ago│  │
│ │ ✓ Deviation C | Template 1 | 8m ago│  │
│ │ ... [View All Logs]                 │  │
│ └─────────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

### Domain Models

**`src/domain/models.py`** (дополнить)

```python
@dataclass
class CommentTemplate:
    """Шаблон комментария."""
    template_id: int
    title: str
    body: str  # Текст с {synonym1|synonym2}
    is_active: bool
    created_at: datetime
    updated_at: datetime

@dataclass
class CommentQueueItem:
    """Элемент очереди комментирования."""
    id: int
    deviationid: str
    deviation_url: str
    title: str
    author_username: str
    author_userid: str
    source: str  # 'feed' | 'browse'
    ts: int
    status: str  # 'pending' | 'commented' | 'failed'
    attempts: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime

@dataclass
class CommentLog:
    """Лог отправленного комментария."""
    log_id: int
    template_id: int
    deviationid: str
    deviation_url: str
    author_username: str
    commentid: str | None
    comment_text: str
    status: str  # 'sent' | 'failed'
    error_message: str | None
    sent_at: datetime
```

## Implementation Plan

### Phase 1: Database & Repositories
- [ ] Создать SQL схему таблиц
- [ ] Реализовать `CommentQueueRepository`
- [ ] Реализовать `CommentTemplateRepository`
- [ ] Реализовать `CommentLogRepository`
- [ ] Написать тесты для репозиториев

### Phase 2: Services
- [ ] Реализовать `CommentCollectorService`
  - [ ] Метод `collect_from_feed()`
  - [ ] Метод `collect_from_browse()`
- [ ] Реализовать `CommentPosterService`
  - [ ] Метод `post_comment()`
  - [ ] Метод `process_next()`
- [ ] Интегрировать `TemplateRenderer` из profile_message
- [ ] Написать тесты для сервисов

### Phase 3: API Layer
- [ ] Создать `comment_api.py` blueprint
- [ ] Реализовать endpoints для шаблонов
- [ ] Реализовать endpoints для очереди
- [ ] Реализовать endpoints для воркера
- [ ] Реализовать endpoints для логов
- [ ] Зарегистрировать blueprint в `run_stats.py`

### Phase 4: Worker
- [ ] Создать `comment_worker.py`
- [ ] Реализовать основной цикл обработки
- [ ] Добавить graceful shutdown
- [ ] Добавить rate limiting (Retry-After headers)
- [ ] Добавить логирование

### Phase 5: Frontend
- [ ] Создать `auto_comment.html`
- [ ] Создать `auto_comment.js`
- [ ] Реализовать UI для управления шаблонами
- [ ] Реализовать UI для управления очередью
- [ ] Реализовать UI для управления воркером
- [ ] Реализовать отображение логов
- [ ] Добавить ссылку в главное меню

### Phase 6: Testing & Documentation
- [ ] Integration тесты
- [ ] E2E тесты UI
- [ ] Обновить README.md
- [ ] Создать user guide
- [ ] Добавить screenshots

## Technical Considerations

### Rate Limiting
- Использовать `Retry-After` header из ответов DA API
- Exponential backoff при ошибках
- Configurable delay между комментариями (default: 30s)

### Deduplication
- Проверять `comment_logs.deviationid` перед добавлением в queue
- Unique constraint на `comment_queue.deviationid`

### Error Handling
- Максимум 3 попытки (`attempts < 3`)
- После 3 неудач → status = 'failed'
- Возможность reset failed → pending

### Template System
- Поддержка синонимов: `{word1|word2|word3}` (как в Profile Broadcast)
- Функция рендера: `message_randomizer.randomize_template()`
- Случайный выбор активного шаблона через `random.choice()`
- Только активные шаблоны (`is_active=1`) участвуют в выборе
- Preview рендера перед отправкой (опционально в UI)

### Data Sources
**Feed:**
- Endpoint: `/feed`
- Cursor-based pagination (offset)
- Только девиации от подписок

**Browse:**
- Endpoint: `/browse/newest`
- Offset pagination
- Все новые девиации DA

## Dependencies

### Existing Components to Reuse
- `src/service/http_client.py` - HTTP client с retry
- `src/service/profile_message_service.py` - TemplateRenderer
- `src/storage/adapters/` - Database adapters
- `static/profile_broadcast.html` - UI reference

### New Dependencies
- None (все есть в текущем проекте)

## Success Criteria

- [ ] Можно создавать/редактировать шаблоны комментариев
- [ ] Можно собирать девиации из Feed
- [ ] Можно собирать девиации из Browse
- [ ] Воркер отправляет комментарии с заданным интервалом
- [ ] Нет дублирования комментариев на одной девиации
- [ ] Логи сохраняются с commentid
- [ ] UI позволяет управлять всеми операциями
- [ ] Rate limiting работает корректно
- [ ] Failed комментарии можно сбросить в pending

## Future Enhancements

- [ ] Фильтрация по категориям в Browse
- [ ] Blacklist авторов (не комментировать определенных)
- [ ] Whitelist авторов (комментировать только их)
- [ ] Scheduled commenting (только в определенное время)
- [ ] Statistics dashboard (comments per day, success rate)
- [ ] Multiple workers с разными шаблонами
- [ ] Comment variations (A/B testing шаблонов)

## References

Аналогичные компоненты в проекте:
- **Profile Broadcast**: `src/service/profile_message_service.py` - выбор шаблона, воркер, отправка
- **Template Randomizer**: `src/service/message_randomizer.py` - `randomize_template()` функция
- **Auto-Fave**: `src/service/mass_fave_service.py` - работа с очередью, воркер
- **Feed Collection**: `src/storage/feed_deviation_repository.py` - очереди, статусы
- **Profile Tables**: `src/storage/profile_message_tables.py` - таблицы шаблонов и логов

## Notes

- Комментарии отправляются через DeviantArt API: `POST /comments?deviationid={uuid}`
- Нужен scope `comment.post` в OAuth токене
- CommentID возвращается в ответе API (сохранять в logs)
- Соблюдать rate limits DeviantArt (30-60s между комментариями рекомендуется)
