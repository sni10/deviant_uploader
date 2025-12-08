# Уровень абстракции базы данных

## Обзор

В этом документе описывается реализация уровня абстракции базы данных, которая позволяет легко переключаться между бэкендами SQLite и PostgreSQL без изменения кода приложения.

## Архитектура

Уровень абстракции следует **шаблону адаптера на основе протокола** с тремя основными компонентами:

### 1. Протокол DBConnection (`src/storage/base_repository.py`)

Определяет минимальный интерфейс, который должны реализовывать все соединения с базой данных:
- `execute(sql, parameters)` - выполнение SQL-операторов
- `commit()` - фиксация транзакций
- `close()` - закрытие соединений

Все репозитории зависят от этого протокола, а не от конкретных реализаций.

### 2. Адаптеры баз данных (`src/storage/adapters/`)

**Базовый протокол** (`base.py`):
- `DatabaseAdapter` - определение интерфейса адаптера протокола
- `initialize()` - создание схемы и запуск миграций
- `get_connection()` - возврат соединения, совместимого с DBConnection

**Адаптер SQLite** (`sqlite_adapter.py`):
- `SQLiteConnection` - обёртка `sqlite3.Connection` для реализации `DBConnection`
- `SQLiteAdapter` - фабрика для подключений SQLite
- использование существующей схемы из `database.py`
- выполнение существующей логики миграции
- отсутствие внешних зависимостей, помимо стандартной библиотеки Python

**Адаптер SQLAlchemy** (`sqlalchemy_adapter.py`):
- `SQLAlchemyConnection` - обёртка `Session` SQLAlchemy для реализации `DBConnection`
- `SQLAlchemyAdapter` — фабрика для подключений к PostgreSQL через SQLAlchemy
  — использует декларативные модели из `models.py`
  — создаёт схему с помощью `Base.metadata.create_all()`
  — требует пакеты `sqlalchemy` и `psycopg2`

**Модели SQLAlchemy** (`src/storage/models.py`):
— декларативные модели ORM, соответствующие схеме SQLite
— таблицы: users, oauth_tokens, gallery, Deviations, Deviation_stats, stats_snapshots, user_stats_snapshots, Deviation_metadata

### 3. Функции фабрики (`src/storage/database.py`)

**`get_database_adapter()`**:
— считывает `DATABASE_TYPE` из конфигурации
— возвращает соответствующий адаптер (SQLiteAdapter или SQLAlchemyAdapter)
- Проверяет конфигурацию (например, DATABASE_URL требуется для PostgreSQL)

**`get_connection()`**:
- Удобная функция, которая создаёт адаптер и возвращает подключение
- Рекомендуемая точка входа для всего кода приложения

**`init_database(db_path)`**:
- Устаревшая функция сохранена для обратной совместимости
- В новом коде вместо неё следует использовать `get_connection()`

## Конфигурация

### Переменные окружения

Добавьте в файл `.env`:

```bash
# Выбор бэкэнда базы данных
DATABASE_TYPE=sqlite # или 'postgresql'

# Конфигурация SQLite (используется, когда DATABASE_TYPE=sqlite)
DATABASE_PATH=data/deviant.db

# Конфигурация PostgreSQL (требуется, когда DATABASE_TYPE=postgresql)
DATABASE_URL=postgresql://username:password@localhost:5432/deviant
```

### Переключение между базами данных

**Для использования SQLite** (по умолчанию):
```bash
DATABASE_TYPE=sqlite
DATABASE_PATH=data/deviant.db
```

**Для использования PostgreSQL**:
```bash
DATABASE_TYPE=postgresql
DATABASE_URL=postgresql://deviant_user:mypassword@localhost:5432/deviant
```

Изменение кода не требуется — просто обновите конфигурацию и перезапустите приложение.

## Использование

### Код приложения

Все точки входа обновлены для использования функции фабрики:

```python
from src.storage import create_repositories

# Автоматически использует настроенную базу данных
user_repo, token_repo, gallery_repo, Deviation_repo, stats_repo = create_repositories()

# Использовать репозитории как обычно
user = user_repo.get_user_by_userid('12345')

# Закрыть по завершении (все репозитории используют одно соединение)
token_repo.close()
```

### Прямой доступ к соединению

Для расширенных вариантов использования:

```python
from src.storage import get_connection, get_database_adapter

# Получить соединение напрямую
conn = get_connection()
cursor = conn.execute("SELECT * FROM пользователи")
conn.close()

# Или работайте с адаптером
adapter = get_database_adapter()
adapter.initialize() # Убедитесь, что схема существует
conn = adapter.get_connection()
```

## Подробности реализации

### Как репозитории остаются неизменными

Репозитории используют только три метода из соединений:
1. `execute(sql, parameters)` — поддерживают и SQLite, и SQLAlchemy
2. `commit()` — Стандартная фиксация транзакции
3. `close()` — Очистка

Оба класса: `SQLiteConnection` и `SQLAlchemyConnection` реализуют эти методы, обёртывая соответствующие собственные объекты соединения/сеанса.

### Совместимость с SQL

В текущей реализации используются **сырые SQL-запросы** в репозиториях, что работает благодаря:
- SQLite и PostgreSQL используют схожие диалекты SQL для используемых нами операций;
- В запросах используются плейсхолдеры `?`, которые поддерживаются обеими сторонами (SQLAlchemy преобразует их при необходимости);
- Не используются специфичные для базы данных функции (например, функции, доступные только SQLite);

### Управление схемой

**SQLite**:
- Схема определена как SQL-строка в `database.py`;
- Миграции обрабатываются функцией `_migrate_database()`;
- Использует `PRAGMA table_info` для обнаружения отсутствующих столбцов;

**PostgreSQL**:
- Схема определена как модели SQLAlchemy в `models.py`;
- В настоящее время для миграций используется `Base.metadata.create_all()` (создаёт все таблицы);
- В будущем: следует использовать Alembic fo