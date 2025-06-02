# Media Tracker

**Media Tracker** is a Flask-based application that unifies your home media APIs (Plex, Sonarr, and more) into a single, modern API and dashboard.  
It acts as a "one API to rule them all," aggregating, normalizing, and exposing your media data through a single endpoint and a beautiful web interface.

---

## Why Media Tracker?

- **One API, One Dashboard:**  
  No more juggling multiple apps and endpoints. Media Tracker collects, merges, and presents all your media data in one place.
- **Meta-API:**  
  Query your entire media ecosystem (Plex, Sonarr, etc.) through a single, consistent API.
- **Customizable Reports:**  
  Generate daily/weekly reports, text files, and more—locally or to GitHub.
- **Modern Dashboard:**  
  See your entire media universe at a glance: movies, TV shows, schedules, stats, and more.

---

## Features

### 🛠 Unified API Layer
- Aggregates data from Plex, Sonarr, and other media APIs.
- Exposes a single `/internal/all_content` endpoint for all movies, TV shows, and schedules.
- Normalizes metadata (titles, artwork, genres, ratings, etc.) across sources.
- Extensible: add more media sources as plugins.

### 📊 Modern Dashboard
- Recently added movies and TV shows (with artwork, metadata, and filters).
- TV schedule (from Sonarr and other sources).
- System status (Plex, Sonarr, GitHub, Scheduler).
- Library statistics (movies, shows, episodes, libraries).
- Auto-refresh, display customization, and more.

### 📝 Customizable Reports
- Generate daily/weekly text reports of new content and schedules.
- Customizable output format for each section.
- Save reports locally or upload to GitHub.

### 🔄 Automated Scheduling
- Built-in APScheduler for daily or hourly syncs (Eastern timezone support).
- Manual sync available from the web interface.

### ☁️ GitHub Integration (Optional)
- Automatically upload generated reports to a GitHub repository.
- Supports personal access tokens and branch selection.

### ⚙️ Configuration Web UI
- Easy-to-use web interface for all settings:
  - API details for each service (Plex, Sonarr, etc.)
  - GitHub integration
  - Scheduler options
  - Output formatting
  - Dashboard display options

### 🔒 Security
- Sensitive configuration (API keys, tokens) stored locally and excluded from git.
- OAuth support for secure Plex authentication.
- Environment variable support for secrets.

---

## Installation

1. **Clone the repository:**
   ```sh
   git clone https://github.com/davidsnyder-nc/mediainfo.git
   cd mediainfo
   ```
2. **Create a virtual environment:**
   ```sh
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. **Install dependencies:**
   ```sh
   pip install flask apscheduler requests pytz
   ```

---

## Usage

1. **Run the application:**
   ```sh
   python app.py
   ```
2. **Open your browser to:**  
   [http://localhost:3038](http://localhost:3038)
3. **Configure your settings:**  
   - Enter API details for Plex, Sonarr, and any other supported services.
   - Optionally configure GitHub and scheduler.
4. **Dashboard:**  
   - View your unified media library, schedule, and stats in real time.
5. **Unified API:**  
   - Query `/internal/all_content` for a normalized JSON of all your movies, TV shows, and schedules.
6. **Manual & Automated Sync:**  
   - Click "Run Daily Sync" or enable the scheduler for automatic updates.

---

## API Endpoints

- `/internal/all_content`  
  Returns a normalized JSON object with all movies, TV shows, and schedules from all connected services.
- `/internal/schedule`  
  Returns upcoming TV schedules (from Sonarr and others).
- `/internal/library_stats`  
  Returns statistics for all libraries.
- `/internal/status`  
  Returns system and API connection status.

*See the code or API docs for more endpoints and details.*

---

## Output & Reports

- Reports are saved in the `output/` directory (excluded from git).
- Customizable format for movies, TV shows, and schedule.
- Optionally upload reports to GitHub.

---

## Security & Best Practices

- **Never commit your `config.json` or API keys to git.**
- `.gitignore` is pre-configured to exclude sensitive files.
- Use environment variables for secrets if deploying to production.

---

## Troubleshooting

- Ensure all media servers are accessible from the app server.
- Verify API keys and tokens are correct.
- Check logs for detailed error messages.
- For GitHub uploads, ensure your token has `repo` scope.

---

## License

MIT License

---

## About

Media Tracker is an open-source project by [davidsnyder-nc](https://github.com/davidsnyder-nc/mediainfo) for home media enthusiasts who want a single API and dashboard for their entire media universe.

---

**Want to add more integrations or features? Fork the project or open an issue!**