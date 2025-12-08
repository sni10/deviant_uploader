# DeviantArt Image Uploader

> **Language**: [Русский](README.md)

[![CI](https://img.shields.io/github/actions/workflow/status/sni10/deviant_uploader/ci.yml?style=for-the-badge&logo=github&label=CI)](https://github.com/sni10/deviant_uploader/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/actions/workflow/status/sni10/deviant_uploader/release.yml?style=for-the-badge&logo=github&label=Release)](https://github.com/sni10/deviant_uploader/actions/workflows/release.yml)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge&logo=opensourceinitiative&logoColor=white)](https://github.com/sni10/deviant_uploader/blob/main/LICENSE)
[![Latest Release](https://img.shields.io/github/v/release/sni10/deviant_uploader?style=for-the-badge&logo=github)](https://github.com/sni10/deviant_uploader/releases/latest)
[![Tests](https://img.shields.io/badge/tests-66%20passed-brightgreen?style=for-the-badge&logo=pytest&logoColor=white)](https://github.com/sni10/deviant_uploader/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-47%25-brightgreen?style=for-the-badge&logo=codecov&logoColor=white)](https://github.com/sni10/deviant_uploader/actions/workflows/ci.yml)

Simple synchronous Python app for uploading images to DeviantArt via the OAuth2 API. The code follows DDD, SOLID, OOP, DRY, and KISS with clear separation of concerns.

## Features

### Core Functions
- **OAuth2 authentication**: automatic token handling with refresh
- **Token validation**: uses DeviantArt placebo endpoint
- **Automatic token refresh**: renews expired tokens
- **Gallery management**: fetch, sync, and manage DeviantArt galleries
- **Template-based uploads**: configure upload parameters via JSON template
- **Image upload**: publish via stash/publish endpoint
- **Gallery assignment**: publish to selected galleries automatically
- **DB tracking**: SQLite/PostgreSQL database tracks uploads and galleries
- **File handling**: moves successful uploads to the `done` folder
- **Logging**: detailed logs with rotation
- **Configuration**: environment-driven settings
- **Recovery**: restores stuck uploads after failures

### Web Interfaces
- **Stats Dashboard**: web dashboard for viewing current deviation stats, daily snapshots, and watcher history with auto-sync across all galleries
- **Charts Dashboard**: interactive charts and statistics visualization with deviation filtering and time period selection
- **Upload Admin Interface**: full-featured web interface for batch upload management with drag-and-drop support

### Advanced Features
- **Upload Presets**: savable presets system for quick upload configuration (tags, galleries, mature flags, etc.)
- **Batch Operations**: batch stash, publish, and delete deviations through web interface
- **Rate Limiting**: automatic DeviantArt API rate limit handling with exponential backoff
- **Database Abstraction**: SQLite and PostgreSQL support through unified interface
- **Responsive UI**: Bootstrap 5 adaptive interface for any device

## Architecture

The project follows Domain-Driven Design (DDD):

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

## Requirements

- Python 3.10+
- DeviantArt Developer account
- Registered DeviantArt application

## Setup

### 1. Register the application

1. Go to https://www.deviantart.com/developers/
2. Register a new application
3. Set redirect URI to `http://localhost:8080/callback`
4. Note your `client_id` and `client_secret`

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:
```env
DA_CLIENT_ID=your_client_id
DA_CLIENT_SECRET=your_client_secret
```

### 4. Prepare the upload folder

Place images you want to upload into `upload/`. Supported formats:
- JPG/JPEG
- PNG
- GIF
- BMP

## Usage

### Basic usage

Run the main app:

```bash
python main.py
```

On first run:
1. Browser opens for DeviantArt authorization
2. Sign in and authorize the app
3. App receives OAuth token
4. Images in `upload/` are processed

### User management

Fetch and store the authenticated DeviantArt user in the local DB.

#### Fetch user info

```bash
python fetch_user.py
```

This performs:
1. Authentication
2. `/user/whoami`
3. `/user/profile/{username}`
4. Persistence in DB
5. Console output

**Stored data:** username, user ID, avatar, account type; profile fields (real name, tagline, country, website, bio); artist info; stats (deviations, favourites, comments, profile views/comments).

### Gallery management

Sync DeviantArt galleries and publish directly into them.

#### Step 1: Fetch galleries

```bash
python fetch_galleries.py
```

- Authenticates
- Fetches all gallery folders
- Saves to DB with UUIDs
- Prints list with DB IDs

#### Step 2: Configure upload template

```bash
cp upload_template.json.example upload_template.json
```

Edit `upload_template.json`:

```json
{
  "title_template": "My artwork title",
  "tags": ["art", "digital", "fantasy"],
  "is_mature": false,
  "is_ai_generated": true,
  "gallery_id": 2
}
```

**Important**: `gallery_id` is the DB ID (the `[ID: X]` value), not the DeviantArt UUID.

#### Step 3: Prepare images

Drop files into `upload/`. Files are uploaded to Stash automatically.

Optional per-file metadata (`upload/art.png.json`):
```json
{ "itemid": 123456789 }
```

#### Step 4: Run upload

```bash
python main.py
```

The app:
1. Loads `upload_template.json`
2. Processes each image
3. Applies template settings
4. Uploads to Stash via `/stash/submit` if `itemid` is missing
5. Reads `itemid` from response
6. Resolves gallery UUID from DB
7. Publishes via `/stash/publish`
8. Saves to DB
9. Moves successful files to `upload/done/`

### Automatic Stash upload

- Fully automated: uploads to Stash (`/stash/submit`), gets `itemid`, publishes, and moves files to `done`.
- Optional: if you already have an `itemid`, place it in the sidecar JSON to skip uploading.

**Programmatic single-file upload**

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

uploader.upload_single(
    filename="my_image.jpg",
    itemid=123456789,
    title="My artwork title",
    is_mature=False,
    tags=["digital", "art", "illustration"],
)

token_repo.close()
```

### DeviantArt Manager Web Interface

The app provides three web interfaces for managing your DeviantArt content.

**Start the web server:**
1. Ensure base setup is done (`.env`, `python fetch_user.py`, `python fetch_galleries.py`)
2. Start the unified server:

```bash
python run_stats.py
```

3. Open `http://localhost:5000` in your browser

Three interfaces are available with a responsive navbar for switching between them.

#### Stats Dashboard (`http://localhost:5000/`)

Dashboard for viewing and syncing statistics of your deviations.

**Features:**
- View current views, favourites, and comments for all deviations
- Daily deltas (growth/decline) for each metric
- Thumbnails, titles, publication dates, mature flags
- Display user watcher count and daily change
- **Automatic sync across all galleries** - Sync button iterates through all galleries with 3-second intervals
- Sort by any column (views, favourites, comments, publication date)
- Combined Score (views + favourites × 10) for quick popularity assessment

**API endpoints:**
- `GET /api/stats` — current stats with daily deltas
- `POST /api/stats/sync` — sync stats for a gallery
- `GET /api/options` — users and galleries list
- `GET /api/user_stats/latest?username=...` — latest watcher snapshot

#### Charts Dashboard (`http://localhost:5000/charts.html`)

Interactive charts and statistics visualization.

**Features:**
- Visualize aggregated statistics (views, favourites, comments) for selected period
- Filter by specific deviations (select from list with thumbnails)
- Flexible time periods (7, 14, 30 days)
- User watcher history with change graphs
- Interactive Chart.js charts with zoom capabilities

**API endpoints:**
- `GET /api/charts/deviations` — list of all deviations for filtering
- `GET /api/charts/aggregated?period=7&deviation_ids=...` — aggregated stats
- `GET /api/charts/user-watchers?username=...&period=7` — watcher history

#### Upload Admin Interface (`http://localhost:5000/upload_admin.html`)

Full-featured web interface for batch upload management to DeviantArt.

**Features:**
- Scan `upload/` folder and display files with thumbnails
- **Upload Presets** - create and manage presets with settings (tags, galleries, mature flags, artist comments)
- Apply presets to selected deviations with one click
- **Batch Operations:**
  - Stash - batch upload files to DeviantArt Stash
  - Publish - batch publish stash items
  - Upload - combined operation (stash + publish)
  - Delete - delete files and database records
- Filter by status (new, stashed, published)
- Display upload statuses with icons and colors
- Responsive design for tablets and desktops

**API endpoints:**
- `POST /api/admin/scan` — scan upload folder
- `GET /api/admin/drafts` — get all deviations from DB
- `GET /api/admin/galleries` — galleries list
- `GET /api/admin/presets` — presets list
- `POST /api/admin/presets` — save preset
- `POST /api/admin/apply-preset` — apply preset to deviations
- `POST /api/admin/stash` — batch upload to stash
- `POST /api/admin/publish` — batch publish
- `POST /api/admin/upload` — combined upload (stash+publish)
- `POST /api/admin/delete` — delete files and records
- `GET /api/admin/thumbnail/<id>` — deviation thumbnail

**Rate Limiting:**
All sync operations respect DeviantArt API rate limits. On `429 user_api_threshold` response, the service performs multiple attempts with exponential backoff and safely stops the current run without blocking the token.

## Configuration

All configuration is via environment variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DA_CLIENT_ID` | Yes | - | DeviantArt client ID |
| `DA_CLIENT_SECRET` | Yes | - | DeviantArt client secret |
| `DA_REDIRECT_URI` | No | `http://localhost:8080/callback` | OAuth redirect URI |
| `DA_SCOPES` | No | `browse stash publish` | OAuth scopes |
| `DATABASE_TYPE` | No | `sqlite` | Database type (`sqlite` or `postgresql`) |
| `DATABASE_PATH` | No | `data/deviant.db` | SQLite path (for DATABASE_TYPE=sqlite) |
| `DATABASE_URL` | No | - | PostgreSQL URL (for DATABASE_TYPE=postgresql) |
| `UPLOAD_DIR` | No | `upload` | Upload directory |
| `DONE_DIR` | No | `upload/done` | Folder for uploaded files |
| `LOG_DIR` | No | `logs` | Log directory |
| `LOG_LEVEL` | No | `INFO` | Log level |

## Database abstraction level

Supports SQLite (default) and PostgreSQL (via SQLAlchemy) through a unified interface.

- `DBConnection` protocol with `execute`, `commit`, `close`
- `SQLiteAdapter` for the current schema
- `SQLAlchemyAdapter` for PostgreSQL via SQLAlchemy ORM
- Factory helpers pick the backend from config

Switching databases:

SQLite (default):
```env
DATABASE_TYPE=sqlite
DATABASE_PATH=data/deviant.db
```

PostgreSQL:
```env
DATABASE_TYPE=postgresql
DATABASE_URL=postgresql://username:password@localhost:5432/deviant
```

Repositories work unchanged.

## Project structure

```
deviant/
├── API.md                      # DeviantArt API docs
├── README.md                   # This file (Russian)
├── README_EN.md                # English copy
├── main.py                     # Template-based upload entry point
├── fetch_user.py               # User sync script
├── fetch_galleries.py          # Gallery sync script
├── run_stats.py                # Flask stats dashboard
├── requirements.txt            # Python deps
├── .env.example                # Env config sample
├── upload_template.json.example # Upload template sample
├── upload_template.json        # Your upload config (gitignored)
├── data/                       # SQLite DB storage
├── logs/                       # App logs
├── static/                     # Stats dashboard UI (stats.html)
├── upload/                     # Images to upload
│   ├── *.png                   # Image files
│   ├── *.png.json              # Per-file metadata (itemid)
│   └── done/                   # Uploaded files
├── tests/                      # Pytest suite
│   ├── __init__.py
│   ├── test_domain_models.py   # Domain model tests
│   └── test_stats_service.py   # Stats service rate-limit tests
└── src/
    ├── config/
    │   ├── __init__.py
    │   └── settings.py         # Config singleton
    ├── domain/
    │   ├── __init__.py
    │   └── models.py           # Domain entities
    ├── api/
    │   ├── __init__.py
    │   └── stats_api.py        # Flask stats API
    ├── storage/
    │   ├── __init__.py
    │   ├── database.py         # DB schema
    │   ├── base_repository.py  # Base repo
    │   ├── user_repository.py  # Users
    │   ├── oauth_token_repository.py  # OAuth tokens
    │   ├── gallery_repository.py      # Galleries
    │   ├── deviation_repository.py    # Deviations
    │   └── stats_repository.py        # Stats and snapshots
    ├── service/
    │   ├── __init__.py
    │   ├── auth_service.py     # OAuth2 auth
    │   ├── user_service.py     # Users
    │   ├── gallery_service.py  # Galleries
    │   ├── uploader.py         # Template uploads
    │   └── stats_service.py    # DeviantArt stats aggregation
    ├── log/
    │   ├── __init__.py
    │   └── logger.py           # Logging setup
    └── fs/
        ├── __init__.py
        └── utils.py            # File utils
```

## Database schema

### users
- `id` (PK)
- `userid` (DeviantArt UUID, unique)
- `username`
- `usericon`
- `type`
- Profile: real_name, tagline, country, website, bio
- Artist info: artist_level, artist_specialty
- Stats: user_deviations, user_favourites, user_comments, profile_pageviews, profile_comments
- Timestamps: `created_at`, `updated_at`

### oauth_tokens
- `user_id` (FK users)
- access_token, refresh_token, expires_at
- Timestamps: `created_at`, `updated_at`

### galleries
- `id` (DB ID for templates)
- `user_id` (FK users)
- `folderid` (DeviantArt UUID, unique)
- `name`
- `parent`
- `size`
- Timestamps

### deviations
- `user_id` (FK users)
- File info: filename, title, file_path
- Status: new, uploading, done, failed
- DeviantArt params: mature, tags, AI-generated, etc.
- Stash params: artist_comments, original_url, stack, etc.
- Gallery link: `gallery_id` (FK galleries)
- Results: URL, deviation ID, itemid
- Errors
- Timestamps: `created_at`, `uploaded_at`, `published_time`

### deviation_stats
- `id`
- `deviationid` (DeviantArt UUID, unique)
- `title`
- `thumb_url`
- `is_mature`
- Metrics: `views`, `favourites`, `comments`
- `gallery_folderid`
- `url`
- Timestamps

### stats_snapshots
- `id`
- `deviationid`
- `snapshot_date` (YYYY-MM-DD)
- Metrics: `views`, `favourites`, `comments`
- Timestamps

### user_stats_snapshots
- `id`
- `user_id` (FK users)
- `username`
- `snapshot_date`
- `watchers`
- `friends`
- Timestamps

### deviation_metadata
- `id`
- `deviationid` (unique)
- Core: `title`, `description`, `license`, `allows_comments`
- Flags: `is_favourited`, `is_watching`, `is_mature`, `mature_level`, `mature_classification`
- Author/attributes: `author`, `creation_time`, `category`, `file_size`, `resolution`, `camera`
- Transport/collections: `submitted_with`, `collections`, `galleries`
- Rights/interactions: `can_post_comment`
- Detailed stats: `stats_views_today`, `stats_downloads_today`, `stats_downloads`, `stats_views`, `stats_favourites`, `stats_comments`
- Timestamps

## Design principles

- **DDD**: clear domain model (User, Gallery, Deviation)
- **SOLID**: single responsibility, dependency injection, explicit interfaces
- **OOP**: proper encapsulation and abstraction
- **DRY**: reusable components and services
- **KISS**: straightforward implementation
- **Separation of concerns**: layered architecture (domain, storage, service)

## Logging

Logs go to stdout and `logs/app.log` (rotation: 10 files, 10MB each).

Format:
```
2025-11-12 20:56:00 | INFO     | deviant | Message
```

## Error handling

Handles missing/invalid config, auth errors, token expiry/refresh, API errors, filesystem errors, database errors. All errors are logged with context.

## Limitations

1. **Automatic Stash upload**: fully automated via `/stash/submit` then `/stash/publish`.
2. **Synchronous only**: processes one image at a time.
3. **Local callback server**: OAuth callback uses localhost:8080; ensure the port is free.

## Troubleshooting

- Port 8080 busy: update `DA_REDIRECT_URI` and your DeviantArt app whitelist.
- Auth failure: check client_id/client_secret; ensure redirect_uri matches; required scopes include stash and publish.
- Upload failure: verify itemid; ensure token is valid; check logs; ensure mature flags are correct.

## API documentation

See `API.md` for full DeviantArt API details: OAuth2 flow, token handling, stash/publish specs, error codes.

## License

MIT, provided as-is for educational and personal use.

## Contributing

This is a purpose-built project; feel free to adapt it for your needs.
