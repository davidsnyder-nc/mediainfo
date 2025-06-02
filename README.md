# Media Tracker

A Flask-based media tracking application that integrates with Plex and Sonarr APIs to generate customizable daily content reports with automated scheduling capabilities.

## Features

- **Plex Integration**: Track movies and TV shows added to your Plex server
- **Sonarr Integration**: Monitor TV show schedules and upcoming episodes
- **Automated Scheduling**: Built-in APScheduler with Eastern timezone support
- **Flexible Scheduling**: Choose between daily or hourly sync options
- **Custom Output**: Configurable text file generation with custom formatting
- **GitHub Integration**: Optional automatic upload of reports to GitHub repository
- **Web Interface**: Easy-to-use configuration interface
- **OAuth Support**: Secure Plex authentication using OAuth flow

## Installation

1. Clone this repository:
```bash
git clone https://github.com/davidsnyder-nc/mediainfo.git
cd mediainfo
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install flask apscheduler requests pytz
```

## Configuration

1. Run the application:
```bash
python app.py
```

2. Open your browser to `http://localhost:3038`

3. Configure your API settings:
   - **Plex**: Use the OAuth authentication or manually enter your Plex URL and token
   - **Sonarr**: Enter your Sonarr URL and API key
   - **GitHub** (optional): Configure repository upload settings
   - **Scheduler**: Enable automated daily or hourly syncing

## Usage

### Manual Sync
Click "Run Daily Sync" to manually trigger content collection from your configured APIs.

### Automated Scheduling
Enable the scheduler in the configuration to automatically run syncs:
- **Daily**: Run at a specific time each day (Eastern timezone)
- **Hourly**: Run every X hours at the top of the hour

### Output Customization
Customize the output format for movies, TV shows, and schedules using template variables:
- `{title}`, `{year}`, `{added_date}` for movies/shows
- `{series_title}`, `{episode_title}`, `{season}`, `{episode}`, `{air_date}` for schedules

## API Requirements

### Plex
- Plex Media Server with network access
- Valid Plex account for OAuth authentication

### Sonarr
- Sonarr instance with API access enabled
- API key from Sonarr settings

### GitHub (Optional)
- GitHub repository for report uploads
- Personal access token with 'repo' permissions

## File Structure

- `app.py` - Main Flask application with scheduler
- `config.py` - Configuration management
- `media_tracker.py` - API integration logic
- `templates/` - Web interface templates
- `output/` - Generated report files (excluded from git)

## Security

- All sensitive configuration is stored locally in `config.json` (excluded from git)
- OAuth flow for secure Plex authentication
- Environment variable support for secrets

## Troubleshooting

- Ensure your Plex server is accessible from the application
- Verify Sonarr API key has proper permissions
- Check that GitHub token has 'repo' scope if using repository uploads
- Review application logs for detailed error messages

## License

This project is open source and available under the MIT License.