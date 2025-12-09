# DeviantArt Manager

[![CI](https://img.shields.io/github/actions/workflow/status/sni10/deviant_uploader/ci.yml?style=for-the-badge&logo=github&label=CI)](https://github.com/sni10/deviant_uploader/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/actions/workflow/status/sni10/deviant_uploader/release.yml?style=for-the-badge&logo=github&label=Release)](https://github.com/sni10/deviant_uploader/actions/workflows/release.yml)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge&logo=opensourceinitiative&logoColor=white)](https://github.com/sni10/deviant_uploader/blob/main/LICENSE)
[![Latest Release](https://img.shields.io/github/v/release/sni10/deviant_uploader?style=for-the-badge&logo=github)](https://github.com/sni10/deviant_uploader/releases/latest)
[![Tests](https://img.shields.io/badge/tests-66%20passed-brightgreen?style=for-the-badge&logo=pytest&logoColor=white)](https://github.com/sni10/deviant_uploader/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-47%25-brightgreen?style=for-the-badge&logo=codecov&logoColor=white)](https://github.com/sni10/deviant_uploader/actions/workflows/ci.yml)

Web app for managing DeviantArt content: batch uploads, statistics, charts.

## Features

### 📊 Stats Dashboard
- View statistics for all deviations (views, favourites, comments)
- Daily deltas and change history
- Auto-sync across all galleries
- Watcher tracking with growth metrics
- Sorting and filtering

### 📈 Charts Dashboard
- Interactive statistics charts for selected periods
- Filter by specific deviations
- Watcher history visualization
- Data export

### 🚀 Upload Admin
- Batch image uploads to DeviantArt
- Preset system (tags, galleries, settings)
- Batch operations: stash, publish, delete
- Thumbnail previews
- Upload status management

### Technical Features
- OAuth2 authentication with auto-refresh
- SQLite and PostgreSQL support
- Rate limiting with exponential backoff
- Responsive UI (Bootstrap 5)
- REST API for all operations

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

## Quick Start

### 1. Installation

```bash
# Clone repository
git clone https://github.com/sni10/deviant_uploader.git
cd deviant_uploader

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

Create `.env` file:

```bash
cp .env.example .env
```

Fill required parameters:

```env
DA_CLIENT_ID=your_client_id
DA_CLIENT_SECRET=your_client_secret
```

Get credentials: https://www.deviantart.com/developers/

### 3. Initial Setup

```bash
# Fetch user information
python fetch_user.py

# Sync galleries
python fetch_galleries.py
```

### 4. Start Web Interface

```bash
python run_stats.py
```

Open browser: `http://localhost:5000`

## Web Interfaces

### Stats Dashboard (`http://localhost:5000/`)

Monitor your artwork statistics.

**Key Functions:**
- Table of all deviations with metrics
- Daily growth/decline indicators
- Sync all galleries (Sync button)
- Watcher counter
- Column sorting

### Charts Dashboard (`http://localhost:5000/charts.html`)

Statistics visualization.

**Key Functions:**
- Charts for views, favourites, comments
- Period selection (7/14/30 days)
- Deviation filtering
- Watcher history graph

### Upload Admin (`http://localhost:5000/upload_admin.html`)

Upload management.

**Key Functions:**
- Scan `upload/` folder
- Create setting presets
- Apply presets to selected files
- Batch Stash - upload files to DeviantArt Stash
- Batch Publish - publish artworks
- Batch Upload - upload and publish in one command
- Delete files

**Workflow:**
1. Place images in `upload/` folder
2. Click "Scan Files"
3. Create or select preset with settings
4. Apply preset to selected files
5. Click "Upload Selected" to upload and publish

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DA_CLIENT_ID` | Yes | - | DeviantArt Client ID |
| `DA_CLIENT_SECRET` | Yes | - | DeviantArt Client Secret |
| `DA_REDIRECT_URI` | No | `http://localhost:8080/callback` | OAuth redirect URI |
| `DATABASE_TYPE` | No | `sqlite` | `sqlite` or `postgresql` |
| `DATABASE_PATH` | No | `data/deviant.db` | SQLite database path |
| `DATABASE_URL` | No | - | PostgreSQL connection string |
| `UPLOAD_DIR` | No | `upload` | Upload folder path |
| `LOG_LEVEL` | No | `INFO` | Logging level |

## Project Structure

```
deviant/
├── src/
│   ├── api/                    # Flask REST API
│   │   ├── stats_api.py       # Stats & Charts API + Upload Admin API
│   │   └── upload_admin_api.py # (deprecated, merged into stats_api)
│   ├── config/                # Configuration
│   │   └── settings.py        # Settings from .env
│   ├── domain/                # Domain models
│   │   └── models.py          # User, Gallery, Deviation, UploadPreset
│   ├── service/               # Business logic
│   │   ├── auth_service.py    # OAuth2 authentication
│   │   ├── stats_service.py   # DeviantArt stats sync
│   │   ├── uploader.py        # Deviation upload & publish
│   │   ├── gallery_service.py # Gallery management
│   │   └── user_service.py    # User management
│   ├── storage/               # Repositories & DB
│   │   ├── adapters/          # DB adapters (SQLite, PostgreSQL)
│   │   ├── models.py          # SQLAlchemy models
│   │   ├── *_repository.py    # Repositories for each entity
│   │   └── database.py        # DB schema
│   ├── log/
│   │   └── logger.py          # Centralized logging
│   └── fs/
│       └── utils.py           # File utilities
├── static/                    # Web interfaces
│   ├── stats.html             # Stats Dashboard
│   ├── stats.js
│   ├── charts.html            # Charts Dashboard
│   ├── charts.js
│   ├── upload_admin.html      # Upload Admin Interface
│   └── upload_admin.js
├── tests/                     # Tests
├── data/                      # SQLite database
├── upload/                    # Upload folder
│   └── done/                  # Uploaded files
├── logs/                      # Application logs
├── run_stats.py               # Web server launcher
├── fetch_user.py              # User sync
├── fetch_galleries.py         # Galleries sync
├── requirements.txt           # Python dependencies
└── .env                       # Configuration (create from .env.example)
```

## Database

SQLite is used by default:

```env
DATABASE_TYPE=sqlite
DATABASE_PATH=data/deviant.db
```

To use PostgreSQL:

```env
DATABASE_TYPE=postgresql
DATABASE_URL=postgresql://user:password@localhost:5432/deviant
```

## Architecture

The app follows DDD, SOLID, OOP principles:

- **Domain Layer**: User, Gallery, Deviation models
- **Storage Layer**: repositories with unified interface (SQLite/PostgreSQL)
- **Service Layer**: business logic (Auth, Stats, Upload)
- **API Layer**: Flask REST API
- **Presentation Layer**: Bootstrap 5 web interfaces

## License

MIT License - see [LICENSE](LICENSE)


## Contributing

Issues and Pull Requests are welcome!

> **Additional Language**: [RU](README_RU.md)
