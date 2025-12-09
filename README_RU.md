# DeviantArt Manager

> **Language**: [EN](README.md)

[![CI](https://img.shields.io/github/actions/workflow/status/sni10/deviant_uploader/ci.yml?style=for-the-badge&logo=github&label=CI)](https://github.com/sni10/deviant_uploader/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/actions/workflow/status/sni10/deviant_uploader/release.yml?style=for-the-badge&logo=github&label=Release)](https://github.com/sni10/deviant_uploader/actions/workflows/release.yml)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge&logo=opensourceinitiative&logoColor=white)](https://github.com/sni10/deviant_uploader/blob/main/LICENSE)
[![Latest Release](https://img.shields.io/github/v/release/sni10/deviant_uploader?style=for-the-badge&logo=github)](https://github.com/sni10/deviant_uploader/releases/latest)
[![Tests](https://img.shields.io/badge/tests-66%20passed-brightgreen?style=for-the-badge&logo=pytest&logoColor=white)](https://github.com/sni10/deviant_uploader/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-47%25-brightgreen?style=for-the-badge&logo=codecov&logoColor=white)](https://github.com/sni10/deviant_uploader/actions/workflows/ci.yml)

Веб-приложение для управления контентом на DeviantArt: пакетная загрузка, статистика, графики.

## Возможности

### 📊 Stats Dashboard
- Просмотр статистики всех девиаций (просмотры, избранное, комментарии)
- Дневные дельты и история изменений
- Автосинхронизация всех галерей с DeviantArt
- Отслеживание вотчеров и их прироста
- Сортировка и фильтрация

### 📈 Charts Dashboard
- Интерактивные графики статистики за выбранный период
- Фильтрация по конкретным девиациям
- История вотчеров с визуализацией
- Экспорт данных

### 🚀 Upload Admin
- Пакетная загрузка изображений на DeviantArt
- Система пресетов (теги, галереи, настройки)
- Batch-операции: stash, publish, delete
- Предпросмотр с миниатюрами
- Управление статусами загрузок

### Технические особенности
- OAuth2 аутентификация с автообновлением токенов
- Поддержка SQLite и PostgreSQL
- Rate limiting с exponential backoff
- Responsive UI (Bootstrap 5)
- REST API для всех операций

---------
## _Screenshots_

- Statistics
- Charts
- Mas.uploader

<details>
  <summary> --== Open views image ==-- </summary>

![DeviantArt-Stats-Dashboard-12-09-2025_09_54_AM.png](doc/img/DeviantArt-Stats-Dashboard-12-09-2025_09_54_AM.png)
![Statistics-Charts-DeviantArt-Dashboard-12-09-2025_09_54_AM.png](doc/img/Statistics-Charts-DeviantArt-Dashboard-12-09-2025_09_54_AM.png)
![DeviantArt-Upload-Admin-12-09-2025_09_54_AM.png](doc/img/DeviantArt-Upload-Admin-12-09-2025_09_54_AM.png)

</details>
---------

## Быстрый старт

### 1. Установка

```bash
# Клонировать репозиторий
git clone https://github.com/sni10/deviant_uploader.git
cd deviant_uploader

# Установить зависимости
pip install -r requirements.txt
```

### 2. Конфигурация

Создайте `.env` файл:

```bash
cp .env.example .env
```

Заполните обязательные параметры:

```env
DA_CLIENT_ID=ваш_client_id
DA_CLIENT_SECRET=ваш_client_secret
```

Получить credentials: https://www.deviantart.com/developers/

### 3. Первоначальная настройка

```bash
# Получить информацию о пользователе
python fetch_user.py

# Синхронизировать галереи
python fetch_galleries.py
```

### 4. Запуск веб-интерфейса

```bash
python run_stats.py
```

Откройте браузер: `http://localhost:5000`

## Веб-интерфейсы

### Stats Dashboard (`http://localhost:5000/`)

Мониторинг статистики ваших работ.

**Основные функции:**
- Таблица всех девиаций с метриками
- Прирост/падение за последние сутки
- Синхронизация всех галерей (кнопка Sync)
- Счетчик вотчеров
- Сортировка по столбцам

### Charts Dashboard (`http://localhost:5000/charts.html`)

Визуализация статистики.

**Основные функции:**
- Графики просмотров, избранного, комментариев
- Выбор периода (7/14/30 дней)
- Фильтрация по девиациям
- График истории вотчеров

### Upload Admin (`http://localhost:5000/upload_admin.html`)

Управление загрузками.

**Основные функции:**
- Сканирование папки `upload/`
- Создание пресетов настроек
- Применение пресетов к выбранным файлам
- Batch Stash - загрузка файлов в DeviantArt Stash
- Batch Publish - публикация работ
- Batch Upload - загрузка и публикация одной командой
- Удаление файлов

**Workflow:**
1. Поместите изображения в папку `upload/`
2. Нажмите "Scan Files"
3. Создайте или выберите пресет с настройками
4. Примените пресет к выбранным файлам
5. Нажмите "Upload Selected" для загрузки и публикации

## Конфигурация

| Переменная | Обязательна | По умолчанию | Описание |
|----------|----------|---------|-------------|
| `DA_CLIENT_ID` | Да | - | DeviantArt Client ID |
| `DA_CLIENT_SECRET` | Да | - | DeviantArt Client Secret |
| `DA_REDIRECT_URI` | Нет | `http://localhost:8080/callback` | OAuth redirect URI |
| `DATABASE_TYPE` | Нет | `sqlite` | `sqlite` или `postgresql` |
| `DATABASE_PATH` | Нет | `data/deviant.db` | Путь к SQLite БД |
| `DATABASE_URL` | Нет | - | PostgreSQL connection string |
| `UPLOAD_DIR` | Нет | `upload` | Папка для загружаемых файлов |
| `LOG_LEVEL` | Нет | `INFO` | Уровень логирования |

## Структура проекта

```
deviant/
├── src/
│   ├── api/                    # Flask REST API
│   │   ├── stats_api.py       # Stats & Charts API + Upload Admin API
│   │   └── upload_admin_api.py # (deprecated, merged into stats_api)
│   ├── config/                # Конфигурация
│   │   └── settings.py        # Настройки из .env
│   ├── domain/                # Доменные модели
│   │   └── models.py          # User, Gallery, Deviation, UploadPreset
│   ├── service/               # Бизнес-логика
│   │   ├── auth_service.py    # OAuth2 аутентификация
│   │   ├── stats_service.py   # Синхронизация статистики DeviantArt
│   │   ├── uploader.py        # Загрузка и публикация девиаций
│   │   ├── gallery_service.py # Управление галереями
│   │   └── user_service.py    # Управление пользователями
│   ├── storage/               # Репозитории и БД
│   │   ├── adapters/          # DB адаптеры (SQLite, PostgreSQL)
│   │   ├── models.py          # SQLAlchemy модели
│   │   ├── *_repository.py    # Репозитории для каждой сущности
│   │   └── database.py        # Схема БД
│   ├── log/
│   │   └── logger.py          # Централизованное логирование
│   └── fs/
│       └── utils.py           # Утилиты для работы с файлами
├── static/                    # Веб-интерфейсы
│   ├── stats.html             # Stats Dashboard
│   ├── stats.js
│   ├── charts.html            # Charts Dashboard
│   ├── charts.js
│   ├── upload_admin.html      # Upload Admin Interface
│   └── upload_admin.js
├── tests/                     # Тесты
├── data/                      # База данных SQLite
├── upload/                    # Папка для загрузки изображений
│   └── done/                  # Загруженные файлы
├── logs/                      # Логи приложения
├── run_stats.py               # Запуск веб-сервера
├── fetch_user.py              # Синхронизация пользователя
├── fetch_galleries.py         # Синхронизация галерей
├── requirements.txt           # Зависимости Python
└── .env                       # Конфигурация (создать из .env.example)
```

## База данных

По умолчанию используется SQLite:

```env
DATABASE_TYPE=sqlite
DATABASE_PATH=data/deviant.db
```

Для использования PostgreSQL:

```env
DATABASE_TYPE=postgresql
DATABASE_URL=postgresql://user:password@localhost:5432/deviant
```

## Архитектура

Приложение следует принципам DDD, SOLID, OOP:

- **Domain Layer**: модели User, Gallery, Deviation
- **Storage Layer**: репозитории с единым интерфейсом (SQLite/PostgreSQL)
- **Service Layer**: бизнес-логика (Auth, Stats, Upload)
- **API Layer**: Flask REST API
- **Presentation Layer**: Bootstrap 5 веб-интерфейсы

## Лицензия

MIT License - см. [LICENSE](LICENSE)

## Вклад в проект

Issues и Pull Requests приветствуются!

