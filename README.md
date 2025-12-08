# Загрузчик изображений на DeviantArt

[![CI](https://github.com/sni10/deviant_uploader/workflows/CI/badge.svg)](https://github.com/sni10/deviant_uploader/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/tests-passed-brightgreen.svg)](https://github.com/sni10/deviant_uploader/actions/workflows/ci.yml)
[![Release](https://github.com/sni10/deviant_uploader/workflows/Release/badge.svg)](https://github.com/sni10/deviant_uploader/releases)
[![Python Version](https://img.shields.io/badge/python-3.10-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/sni10/deviant_uploader/blob/main/LICENSE)
[![Latest Release](https://img.shields.io/github/v/release/sni10/deviant_uploader)](https://github.com/sni10/deviant_uploader/releases/latest)
[![Code Coverage](https://img.shields.io/badge/coverage-85%25-brightgreen.svg)](https://github.com/sni10/deviant_uploader/actions/workflows/ci.yml)

Простое синхронное Python-приложение для загрузки изображений на DeviantArt через OAuth2 API. Приложение следует принципам DDD, SOLID, OOP, DRY и KISS с четким разделением ответственности.

## Возможности

- **OAuth2 Аутентификация**: Автоматическое управление токенами с возможностью обновления
- **Валидация токенов**: Использует endpoint placebo от DeviantArt для проверки токенов
- **Автоматическое обновление токенов**: Автоматически обновляет просроченные токены
- **Управление галереями**: Получение, синхронизация и управление галереями DeviantArt
- **Загрузка на основе шаблонов**: Настройка параметров загрузки через JSON-шаблон
- **Загрузка изображений**: Публикует изображения на DeviantArt через endpoint stash/publish
- **Назначение галерей**: Автоматическая публикация в указанные галереи
- **Отслеживание в БД**: База данных SQLite для отслеживания загрузок и галерей
- **Управление файлами**: Автоматически перемещает успешно загруженные файлы в папку done
- **Файлы метаданных**: Настройка каждого изображения через JSON-файлы
- **Логирование**: Подробное логирование с ротацией
- **Конфигурация**: Настройка через переменные окружения
- **Восстановление**: Восстанавливает застрявшие загрузки после сбоев
- **Панель статистики**: Веб-дашборд на Flask с API для просмотра текущей статистики девиаций, дневных снэпшотов и истории вотчеров, а также расширенных метаданных по работам.

## Архитектура

Проект следует принципам Domain-Driven Design (DDD):

```
deviant_uploader/
├── .github/
│   └── workflows/
│       ├── ci.yml           # CI workflow (tests)
│       └── release.yml      # Auto-versioning & releases
├── src/
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py      # Configuration management (Singleton)
│   ├── domain/
│   │   ├── __init__.py
│   │   └── models.py        # Domain entities (User, Gallery, Deviation, UploadStatus)
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── database.py      # SQLite schema initialization
│   │   ├── base_repository.py
│   │   ├── user_repository.py
│   │   ├── oauth_token_repository.py
│   │   ├── gallery_repository.py
│   │   └── deviation_repository.py
│   ├── service/
│   │   ├── __init__.py
│   │   ├── auth_service.py  # OAuth2 authentication
│   │   ├── user_service.py  # User management
│   │   ├── gallery_service.py
│   │   └── uploader.py      # Upload orchestration
│   ├── log/
│   │   ├── __init__.py
│   │   └── logger.py        # Centralized logging
│   └── fs/
│       ├── __init__.py
│       └── utils.py         # File system utilities
├── tests/
│   ├── __init__.py
│   └── test_domain_models.py
├── data/                    # SQLite database (auto-created)
├── logs/                    # Application logs (auto-created)
├── upload/                  # Source images directory
│   └── done/                # Successfully uploaded images
├── main.py                  # Main application entry point
├── fetch_user.py            # User synchronization script
├── fetch_galleries.py       # Gallery synchronization script
├── requirements.txt         # Python dependencies
├── LICENSE                  # MIT License
├── .env.example             # Environment variables template
└── upload_template.json.example  # Upload settings template
```

## Требования

- Python 3.10+
- Учетная запись DeviantArt Developer
- Зарегистрированное приложение DeviantArt

## Настройка

### 1. Регистрация приложения

1. Перейдите на https://www.deviantart.com/developers/
2. Зарегистрируйте новое приложение
3. Установите redirect URI в `http://localhost:8080/callback`
4. Запишите ваши `client_id` и `client_secret`

### 2. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 3. Настройка переменных окружения

Скопируйте `.env.example` в `.env` и заполните свои учетные данные:

```bash
cp .env.example .env
```

Отредактируйте `.env`:
```env
DA_CLIENT_ID=ваш_client_id
DA_CLIENT_SECRET=ваш_client_secret
```

### 4. Подготовка папки для загрузки

Поместите изображения, которые хотите загрузить, в папку `upload/`. Поддерживаемые форматы:
- JPG/JPEG
- PNG
- GIF
- BMP

## Использование

### Базовое использование

Запустите основное приложение:

```bash
python main.py
```

При первом запуске:
1. Откроется браузер для авторизации на DeviantArt
2. Войдите и авторизуйте приложение
3. Приложение получит OAuth токен
4. Изображения будут обработаны из папки `upload/`

### Управление пользователем

Приложение позволяет получить и сохранить информацию об аутентифицированном пользователе DeviantArt в локальной базе данных.

#### Получение информации о пользователе

Запустите скрипт синхронизации пользователя:

```bash
python fetch_user.py
```

Это выполнит:
1. Аутентификацию с DeviantArt
2. Получение базовой информации через `/user/whoami`
3. Получение расширенного профиля через `/user/profile/{username}`
4. Сохранение информации в базе данных
5. Отображение информации о пользователе

**Какая информация сохраняется:**
- Основные данные: username, user ID, avatar, тип аккаунта
- Профиль: настоящее имя, tagline, страна, вебсайт, биография
- Информация об артисте: уровень, специализация
- Статистика: количество девиаций, избранного, комментариев, просмотров профиля

**Пример вывода:**
```
================================================================================
User Information
================================================================================
Username: YourUsername
User ID: 09A4052C-88B2-65CB-CEC5-B1E31C18B940
Type: regular
Real Name: Your Name
Profile: https://www.deviantart.com/yourusername
Country: Your Country

Artist Info:
  Level: Professional
  Specialty: Digital Art

Statistics:
  Deviations: 150
  Favourites: 320
  Comments: 89
  Profile Views: 5234
  Profile Comments: 45

Database ID: 1
================================================================================
```

**Зачем это нужно:**
- Информация о пользователе связана с токенами, галереями и девиациями в базе данных
- Позволяет отслеживать, какому пользователю принадлежат загрузки
- Полезно для приложений с поддержкой нескольких аккаунтов DeviantArt

### Управление галереями

Приложение поддерживает автоматическое управление галереями, позволяя публиковать девиации непосредственно в указанные галереи.

#### Шаг 1: Получение списка галерей

Запустите скрипт синхронизации галерей, чтобы получить все ваши галереи DeviantArt и сохранить их в локальной базе данных:

```bash
python fetch_galleries.py
```

Это выполнит:
1. Аутентификацию с DeviantArt
2. Получение всех ваших папок галерей
3. Сохранение их в базе данных с UUID
4. Отображение списка галерей с их ID в базе данных

**Пример вывода:**
```
[ID: 1] Featured - 10 элементов
  UUID: 47D47436-5683-8DF2-EEBF-2A6760BE1336
[ID: 2] Bloom, garden and body - 5 элементов
  UUID: E431BAFB-7A00-7EA1-EED7-2EF9FA0F04CE
```

#### Шаг 2: Настройка шаблона загрузки

Создайте `upload_template.json` из примера:

```bash
cp upload_template.json.example upload_template.json
```

Отредактируйте `upload_template.json` с вашими настройками:

```json
{
  "title_template": "Название моей работы",
  "tags": ["art", "digital", "fantasy"],
  "is_mature": false,
  "is_ai_generated": true,
  "gallery_id": 2
}
```

**Важно**: Установите `gallery_id` в ID базы данных (значение `[ID: X]`) из списка галерей, НЕ UUID.

#### Шаг 3: Подготовка изображений

Просто поместите изображения в папку `upload/`. Файлы будут автоматически загружены в Stash!

**Опциональные JSON-метаданные:**
Если у вас уже есть файлы в Stash или нужно переопределить настройки шаблона:

- `upload/artwork.png`
- `upload/artwork.png.json` (опционально):
  ```json
  {
    "itemid": 123456789
  }
  ```

Все настройки (название, теги, галерея и т.д.) берутся из `upload_template.json`.

#### Шаг 4: Запуск загрузки

```bash
python main.py
```

Приложение выполнит:
1. Загрузку настроек из `upload_template.json`
2. Обработку каждого изображения в `upload/`
3. Применение настроек из шаблона к каждому файлу
4. **Автоматическую загрузку файла в Stash** через `/stash/submit` (если itemid не указан)
5. Получение `itemid` из ответа API
6. Получение UUID галереи из базы данных
7. **Публикацию на DeviantArt** через `/stash/publish` с полученным itemid
8. Сохранение информации в базу данных
9. Перемещение успешно загруженных файлов в `upload/done/`

### Автоматическая загрузка в Stash

✅ **Полностью автоматизировано**: Приложение теперь автоматически загружает файлы в DeviantArt Stash через endpoint `/stash/submit` и получает `itemid` без ручного вмешательства.

**Как это работает:**
1. Поместите изображения в папку `upload/`
2. Настройте параметры в `upload_template.json`
3. Запустите `python main.py`
4. Приложение автоматически:
   - Загрузит файл в Stash DeviantArt
   - Получит `itemid` из ответа API
   - Опубликует девиацию с полученным `itemid`
   - Переместит файл в `upload/done/`

**Опционально**: Если у вас уже есть файлы в Stash с известным `itemid`, вы можете поместить его в `.json` файл рядом с изображением, чтобы пропустить загрузку

**Альтернатива: Программная загрузка одного файла**

```python
from src.config import get_config
from src.log.logger import setup_logger
from src.storage import create_repositories
from src.service.auth_service import AuthService
from src.service.uploader import UploaderService

config = get_config()
logger = setup_logger()
token_repo, gallery_repo, deviation_repo = create_repositories(config.database_path)
auth_service = AuthService(token_repo, logger)
uploader = UploaderService(deviation_repo, gallery_repo, auth_service, logger)

# Загрузка одного файла с stash itemid
uploader.upload_single(
    filename="my_image.jpg",
    itemid=123456789,  # Ваш stash item ID
    title="Название моей работы",
    is_mature=False,
    tags=["digital", "art", "illustration"]
)

token_repo.close()
```

### Панель статистики DeviantArt

Панель статистики предоставляет веб-интерфейс и REST API для просмотра актуальных метрик по девиациям и истории вотчеров.

**Что умеет дашборд:**
- Показывает текущие просмотры, избранное и комментарии по всем девиациям в выбранной галерее
- Строит дневные дельты (рост/падение) по просмотрам, избранному и комментариям
- Отображает расширенные метаданные (миниатюра, заголовок, дата публикации)
- Показывает в шапке количество вотчеров пользователя и изменение за последний день

**Как запустить панель статистики:**
1. Убедитесь, что уже выполнена базовая настройка (`.env`, `python main.py`, `python fetch_user.py`, `python fetch_galleries.py`) и база данных содержит пользователя, галереи и девиации.
2. Установите зависимости (Flask уже прописан в `requirements.txt`).
3. Запустите сервер статистики:

```bash
python run_stats.py
```

4. Откройте в браузере `http://localhost:5000` — отобразится страница `static/stats.html`.

**Доступные HTTP‑endpoint'ы:**
- `GET /api/stats` — текущая статистика девиаций с дневными дельтами
- `POST /api/stats/sync` — принудительная синхронизация статистики для выбранной галереи
- `GET /api/options` — список пользователей и галерей для заполнения выпадающих списков на дашборде
- `GET /api/user_stats/latest?username=...` — последние снэпшоты статистики пользователя (в том числе вотчеры и их дельта)

Синхронизация работает через `AuthService` и `StatsService` и учитывает rate limit DeviantArt: при получении ответа `429 user_api_threshold` сервис делает несколько попыток с экспоненциальным backoff и безопасно останавливает текущий прогон, не «забанивая» токен.

## Конфигурация

Вся конфигурация выполняется через переменные окружения:

| Переменная | Обязательна | По умолчанию | Описание |
|----------|----------|---------|-------------|
| `DA_CLIENT_ID` | Да | - | Client ID приложения DeviantArt |
| `DA_CLIENT_SECRET` | Да | - | Client secret приложения DeviantArt |
| `DA_REDIRECT_URI` | Нет | `http://localhost:8080/callback` | URI для OAuth redirect |
| `DA_SCOPES` | Нет | `browse stash publish` | OAuth scopes |
| `DATABASE_PATH` | Нет | `data/deviant.db` | Путь к базе данных SQLite |
| `UPLOAD_DIR` | Нет | `upload` | Директория для загрузки изображений |
| `DONE_DIR` | Нет | `upload/done` | Директория для загруженных изображений |
| `LOG_DIR` | Нет | `logs` | Директория для лог-файлов |
| `LOG_LEVEL` | Нет | `INFO` | Уровень логирования |

## Структура проекта

```
deviant/
├── API.md                      # Документация API DeviantArt
├── README.md                   # Этот файл
├── main.py                     # Точка входа приложения (загрузка с шаблоном)
├── fetch_user.py               # Скрипт синхронизации информации о пользователе
├── fetch_galleries.py          # Скрипт синхронизации галерей из DeviantArt
├── run_stats.py                # Запуск веб-дашборда статистики (Flask)
├── requirements.txt            # Python зависимости
├── .env.example                # Пример конфигурации окружения
├── upload_template.json.example # Пример шаблона загрузки
├── upload_template.json        # Ваши настройки загрузки (в .gitignore)
├── data/                       # Хранилище базы данных SQLite
├── logs/                       # Логи приложения
├── static/                     # Веб-интерфейс дашборда статистики (stats.html)
├── upload/                     # Изображения для загрузки (источник)
│   ├── *.png                  # Файлы изображений
│   ├── *.png.json             # Метаданные для каждого изображения (itemid)
│   └── done/                  # Успешно загруженные изображения
├── tests/                      # Тесты (pytest)
│   ├── __init__.py
│   ├── test_domain_models.py   # Тесты доменных моделей
│   └── test_stats_service.py   # Тесты сервиса статистики и обработки rate limit
└── src/
    ├── config/
    │   ├── __init__.py
    │   └── settings.py         # Singleton конфигурации
    ├── domain/
    │   ├── __init__.py
     │   └── models.py           # Доменные сущности (User, Gallery, Deviation)
    ├── api/
    │   ├── __init__.py
    │   └── stats_api.py        # Flask API для дашборда статистики
    ├── storage/
    │   ├── __init__.py
    │   ├── database.py         # Схема базы данных
    │   ├── base_repository.py  # Базовый репозиторий
    │   ├── user_repository.py  # Репозиторий пользователей
    │   ├── oauth_token_repository.py  # Репозиторий OAuth токенов
     │   ├── gallery_repository.py      # Репозиторий галерей
    │   ├── deviation_repository.py    # Репозиторий девиаций
    │   └── stats_repository.py        # Репозиторий статистики и снэпшотов
    ├── service/
    │   ├── __init__.py
    │   ├── auth_service.py     # OAuth2 аутентификация
    │   ├── user_service.py     # Управление пользователями
    │   ├── gallery_service.py  # Управление галереями
    │   ├── uploader.py         # Сервис загрузки с поддержкой шаблонов
    │   └── stats_service.py    # Сервис сбора и агрегации статистики DeviantArt
    ├── log/
    │   ├── __init__.py
    │   └── logger.py           # Конфигурация логирования
    └── fs/
        ├── __init__.py
        └── utils.py            # Утилиты файловой системы
```

## Схема базы данных

### users
Хранит информацию о пользователях DeviantArt:
- `id` - Внутренний ID базы данных
- `userid` - UUID пользователя DeviantArt (уникальный)
- `username` - Имя пользователя
- `usericon` - URL аватара
- `type` - Тип аккаунта (regular, premium и т.д.)
- Профиль: real_name, tagline, country, website, bio
- Информация об артисте: artist_level, artist_specialty
- Статистика: user_deviations, user_favourites, user_comments, profile_pageviews, profile_comments
- Временные метки: `created_at`, `updated_at`

### oauth_tokens
Хранит OAuth access и refresh токены:
- `user_id` - Связь с таблицей users (какому пользователю принадлежит токен)
- access_token, refresh_token, expires_at
- Временные метки: `created_at`, `updated_at`

### galleries
Хранит папки галерей DeviantArt:
- `id` - Внутренний ID базы данных (используется в шаблонах)
- `user_id` - Связь с таблицей users (владелец галереи)
- `folderid` - UUID галереи DeviantArt (уникальный)
- `name` - Название галереи
- `parent` - UUID родительской галереи (для вложенных галерей)
- `size` - Количество элементов в галерее
- Временные метки: `created_at`, `updated_at`

### deviations
Отслеживает все загруженные девиации:
- `user_id` - Связь с таблицей users (автор девиации)
- Информация о файле: filename, title, file_path
- Статус загрузки: new, uploading, done, failed
- Параметры DeviantArt: mature, tags, AI-generated и т.д.
- Параметры Stash: artist_comments, original_url, stack и т.д.
- Ссылка на галерею: `gallery_id` (связь с таблицей galleries)
- Результаты загрузки: URL, deviation ID, itemid
- Сообщения об ошибках
- Временные метки: `created_at`, `uploaded_at`, а также удалённое время публикации девиации на DeviantArt (`published_time`)

### deviation_stats
Хранит текущую агрегированную статистику девиаций:
- `id` - Внутренний ID базы данных
- `deviationid` - UUID девиации DeviantArt (уникальный)
- `title` - Заголовок девиации
- `thumb_url` - URL превью
- `is_mature` - Флаг контента для взрослых
- Метрики отклика: `views`, `favourites`, `comments`
- `gallery_folderid` - UUID папки галереи на DeviantArt
- `url` - Публичный URL девиации
- Временные метки: `created_at`, `updated_at`

### stats_snapshots
Хранит дневные снэпшоты статистики девиаций:
- `id` - Внутренний ID базы данных
- `deviationid` - UUID девиации DeviantArt
- `snapshot_date` - Дата снэпшота (YYYY-MM-DD)
- Метрики отклика на дату: `views`, `favourites`, `comments`
- Временные метки: `created_at`, `updated_at`

### user_stats_snapshots
Хранит историю количества вотчеров и друзей пользователя:
- `id` - Внутренний ID базы данных
- `user_id` - Связь с таблицей users (к какому пользователю относится снэпшот)
- `username` - Имя пользователя DeviantArt
- `snapshot_date` - Дата снэпшота (YYYY-MM-DD)
- `watchers` - Количество вотчеров на дату снэпшота
- `friends` - Количество друзей на дату снэпшота
- Временные метки: `created_at`, `updated_at`

### deviation_metadata
Хранит расширенные метаданные и детальную статистику по девиации:
- `id` - Внутренний ID базы данных
- `deviationid` - UUID девиации DeviantArt (уникальный)
- Основные поля: `title`, `description`, `license`, `allows_comments`
- Флаги и статус: `is_favourited`, `is_watching`, `is_mature`, `mature_level`, `mature_classification`
- Автор и атрибуты: `author`, `creation_time`, `category`, `file_size`, `resolution`, `camera`
- Транспорт и коллекции: `submitted_with`, `collections`, `galleries`
- Права и взаимодействие: `can_post_comment`
- Детальная статистика: `stats_views_today`, `stats_downloads_today`, `stats_downloads`, `stats_views`, `stats_favourites`, `stats_comments`
- Временные метки: `created_at`, `updated_at`

## Принципы проектирования

- **DDD (Domain-Driven Design)**: Четкая доменная модель (сущности User, Gallery, Deviation)
- **SOLID**: Единственная ответственность, внедрение зависимостей, интерфейсы
- **OOP**: Правильная инкапсуляция и абстракция
- **DRY**: Переиспользуемые компоненты и сервисы
- **KISS**: Простая, понятная реализация
- **Разделение ответственности**: Четкие слои (domain, storage, service)

## Логирование

Логи записываются в:
- Консоль (stdout)
- Файл: `logs/app.log` (с ротацией, максимум 10 файлов по 10MB каждый)

Формат логов:
```
2025-11-12 20:56:00 | INFO     | deviant | Сообщение
```

## Обработка ошибок

Приложение обрабатывает:
- Отсутствующую/недействительную конфигурацию
- Ошибки аутентификации
- Истечение срока действия токенов и их обновление
- Ошибки API запросов
- Ошибки файловой системы
- Ошибки базы данных

Все ошибки логируются с подробными сообщениями.

## Ограничения

1. **Автоматическая загрузка в Stash**: ✅ Полностью автоматизировано! Приложение загружает файлы через `/stash/submit`, затем публикует через `/stash/publish`. Ручная загрузка больше не требуется.

2. **Только синхронный режим**: Приложение спроектировано как синхронное и простое, обрабатывает по одному изображению за раз.

3. **Локальный сервер для callback**: OAuth callback использует локальный HTTP сервер на порту 8080. Убедитесь, что этот порт доступен.

## Устранение неполадок

### Порт 8080 занят
Измените `DA_REDIRECT_URI` в `.env` и обновите whitelist redirect URI вашего приложения DeviantArt.

### Ошибка аутентификации
- Проверьте ваши client_id и client_secret
- Убедитесь, что redirect_uri соответствует настройкам вашего приложения
- Проверьте, что у вас есть необходимые scopes (stash, publish)

### Ошибка загрузки
- Проверьте, что itemid действителен
- Проверьте, что токен не истек
- Просмотрите логи для подробных сообщений об ошибках
- Убедитесь, что контент для взрослых правильно помечен

## Документация API

См. `API.md` для полной документации API DeviantArt, включая:
- Детали OAuth2 flow
- Управление токенами
- Спецификации endpoint stash/publish
- Коды ошибок и их обработка

## Лицензия

Этот проект предоставляется как есть для образовательных и личных целей.

## Вклад в проект

Это простой проект, следующий конкретным требованиям. Не стесняйтесь адаптировать его под свои нужды.
