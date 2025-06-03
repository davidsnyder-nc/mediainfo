import os
import logging
import uuid
import requests
from flask import Flask, render_template, request, flash, redirect, url_for, session, jsonify, Response, send_from_directory
from config import ConfigManager
from media_tracker import MediaTracker
from models import api_key_manager, require_api_key
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import atexit
import pytz
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")

# Initialize configuration manager
config_manager = ConfigManager()

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.start()

# Register shutdown handler
atexit.register(lambda: scheduler.shutdown())

# Initialize scheduler on startup
def init_scheduler():
    """Initialize scheduler with current configuration on app startup"""
    try:
        update_scheduler()
    except Exception as e:
        logging.error(f"Error initializing scheduler: {e}")

# Initialize scheduler after all functions are defined

def scheduled_sync():
    """Function to run scheduled daily sync"""
    try:
        logging.info("Running scheduled daily sync...")
        config = config_manager.get_config()
        tracker = MediaTracker(config)
        results = tracker.run_daily_sync()
        
        if results['success']:
            logging.info(f"Scheduled sync completed! Found {results['movies_count']} movies and {results['shows_count']} TV shows.")
        else:
            logging.error(f"Scheduled sync failed: {results['error']}")
    except Exception as e:
        logging.error(f"Error in scheduled sync: {str(e)}")

def update_scheduler():
    """Update scheduler based on current configuration"""
    config = config_manager.get_config()
    
    # Set Eastern timezone
    eastern = pytz.timezone('US/Eastern')
    
    # Remove existing job if it exists
    try:
        scheduler.remove_job('media_sync')
    except:
        pass
    
    # Add new job if scheduling is enabled
    if config.get('scheduler_enabled', False):
        schedule_type = config.get('schedule_type', 'daily')
        
        if schedule_type == 'daily':
            hour = config.get('scheduler_hour', 19)
            minute = config.get('scheduler_minute', 55)
            
            scheduler.add_job(
                func=scheduled_sync,
                trigger=CronTrigger(hour=hour, minute=minute, timezone=eastern),
                id='media_sync',
                name='Daily Media Sync',
                replace_existing=True
            )
            logging.info(f"Scheduled daily sync for {hour:02d}:{minute:02d} Eastern")
            
        elif schedule_type == 'hourly':
            interval_hours = config.get('interval_hours', 1)
            
            # Create hourly schedule that runs at the top of each hour
            if interval_hours == 1:
                # Every hour at minute 0
                hour_schedule = '*'
            else:
                # Every X hours starting at midnight, at minute 0
                hour_schedule = f'*/{interval_hours}'
            
            scheduler.add_job(
                func=scheduled_sync,
                trigger=CronTrigger(hour=hour_schedule, minute=0, timezone=eastern),
                id='media_sync',
                name=f'Hourly Media Sync (every {interval_hours}h at :00)',
                replace_existing=True
            )
            logging.info(f"Scheduled sync every {interval_hours} hour(s) at the top of the hour (Eastern)")

@app.route('/')
def index():
    """Main configuration page"""
    config = config_manager.get_config()
    return render_template('index.html', config=config)

@app.route('/save_config', methods=['POST'])
def save_config():
    """Save configuration settings"""
    try:
        config_data = {
            'plex_url': request.form.get('plex_url', '').strip(),
            'plex_token': request.form.get('plex_token', '').strip(),
            'sonarr_url': request.form.get('sonarr_url', '').strip(),
            'sonarr_api_key': request.form.get('sonarr_api_key', '').strip(),
            'output_directory': request.form.get('output_directory', './output').strip(),
            'include_movies': request.form.get('include_movies') == 'on',
            'include_tv_shows': request.form.get('include_tv_shows') == 'on',
            'include_tv_calendar': request.form.get('include_tv_calendar') == 'on',
            'report_title': request.form.get('report_title', 'Media Tracker Report').strip(),
            'movies_title': request.form.get('movies_title', 'PLEX MOVIES ADDED').strip(),
            'tv_shows_title': request.form.get('tv_shows_title', 'PLEX TV SHOWS ADDED').strip(),
            'tv_calendar_title': request.form.get('tv_calendar_title', 'TV SHOWS AIRING TODAY').strip(),
            'no_movies_text': request.form.get('no_movies_text', 'No movies added recently.').strip(),
            'no_tv_text': request.form.get('no_tv_text', 'No TV shows added recently.').strip(),
            'no_schedule_text': request.form.get('no_schedule_text', 'No shows scheduled for today.').strip(),
            'github_enabled': request.form.get('github_enabled') == 'on',
            'github_owner': request.form.get('github_owner', '').strip(),
            'github_repo': request.form.get('github_repo', '').strip(),
            'github_token': request.form.get('github_token', '').strip(),
            'github_branch': request.form.get('github_branch', 'main').strip(),
            'scheduler_enabled': request.form.get('scheduler_enabled') == 'on',
            'schedule_type': request.form.get('schedule_type', 'daily'),
            'scheduler_hour': int(request.form.get('scheduler_hour', 19)),
            'scheduler_minute': int(request.form.get('scheduler_minute', 55)),
            'interval_hours': int(request.form.get('interval_hours', 1)),
            # Output format fields
            'movie_format': request.form.get('movie_format', 'Title: {title}\nYear: {year}\nAdded: {added_date}\n{separator}').strip(),
            'tv_format': request.form.get('tv_format', 'Title: {title}\nYear: {year}\nAdded: {added_date}\n{separator}').strip(),
            'schedule_format': request.form.get('schedule_format', 'Series: {series_title}\nEpisode: S{season:02d}E{episode:02d} - {episode_title}\nAir Date: {air_date}\n{separator}').strip(),
            'section_separator': request.form.get('section_separator', '=' * 50).strip(),
            'include_timestamps': request.form.get('include_timestamps') == 'on',
            'file_naming': request.form.get('file_naming', 'date_suffix'),
            'single_output_file': request.form.get('single_output_file', 'media_tracker.txt').strip(),
            # Dashboard configuration
            'dashboard_days': int(request.form.get('dashboard_days', 3650)),  # Default to showing all content
            'dashboard_max_items': int(request.form.get('dashboard_max_items', 100))  # Default to 100 items
        }
        
        # Load existing config and merge with new data (allows partial updates)
        existing_config = config_manager.get_config()
        
        # Debug logging
        logging.info(f"Form data received: {dict(request.form)}")
        logging.info(f"Config data parsed: {config_data}")
        
        # Update all configuration fields since we now have a single form
        for key, value in config_data.items():
            existing_config[key] = value
        
        # Validate GitHub fields only if GitHub is being enabled
        if config_data['github_enabled']:
            github_required = ['github_owner', 'github_repo', 'github_token']
            missing_github = [field for field in github_required if not existing_config.get(field)]
            if missing_github:
                flash(f"GitHub enabled but missing: {', '.join(missing_github)}", 'warning')
                # Don't return here - allow saving other fields
        
        # Save configuration
        config_manager.save_config(existing_config)
        
        # Update scheduler with new settings
        update_scheduler()
        
        flash('Configuration saved successfully!', 'success')
        
    except Exception as e:
        logging.error(f"Error saving configuration: {str(e)}")
        flash(f'Error saving configuration: {str(e)}', 'error')
    
    return redirect(url_for('index'))

@app.route('/test_connection')
def test_connection():
    """Test API connections"""
    try:
        config = config_manager.get_config()
        tracker = MediaTracker(config)
        
        # Test both APIs
        plex_status = tracker.test_plex_connection()
        sonarr_status = tracker.test_sonarr_connection()
        github_status = tracker.test_github_connection() if config.get('github_enabled', False) else True
        
        return jsonify({
            'success': True,
            'plex': plex_status,
            'sonarr': sonarr_status,
            'github': github_status,
            'message': f'Connection test completed. Plex: {"✓" if plex_status else "✗"}, Sonarr: {"✓" if sonarr_status else "✗"}, GitHub: {"✓" if github_status else "✗"}'
        })
            
    except Exception as e:
        logging.error(f"Error testing connections: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': f'Error testing connections: {str(e)}'
        })

@app.route('/plex_auth')
def plex_auth():
    """Start Plex OAuth flow"""
    try:
        # Generate a unique identifier for this auth request
        client_identifier = str(uuid.uuid4())
        session['plex_client_id'] = client_identifier
        
        # Use the same method as your working implementation
        headers = {
            'Accept': 'application/json',
            'X-Plex-Product': 'Media Tracker',
            'X-Plex-Client-Identifier': client_identifier
        }
        
        # Request PIN using .json endpoint like your working code
        response = requests.post('https://plex.tv/api/v2/pins.json', headers=headers)
        
        if response.status_code == 201:
            pin_info = response.json()
            logging.debug(f"Plex PIN response: {pin_info}")
            session['plex_pin_id'] = pin_info['id']
            session['plex_pin_code'] = pin_info['code']
            
            # Return the PIN code to display to user
            return render_template('plex_auth.html', pin_code=pin_info['code'])
        else:
            flash('Failed to get Plex authentication code', 'error')
            
    except Exception as e:
        logging.error(f"Error starting Plex auth: {str(e)}")
        flash(f'Error starting Plex authentication: {str(e)}', 'error')
    
    return redirect(url_for('index'))

@app.route('/plex_auth_check')
def plex_auth_check():
    """Check if Plex authentication is complete"""
    try:
        pin_id = session.get('plex_pin_id')
        client_id = session.get('plex_client_id')
        
        if not pin_id or not client_id:
            flash('Authentication session expired', 'error')
            return redirect(url_for('index'))
        
        # Check if the PIN has been authorized using .json endpoint
        response = requests.get(f'https://plex.tv/api/v2/pins/{pin_id}.json', headers={
            'Accept': 'application/json',
            'X-Plex-Product': 'Media Tracker',
            'X-Plex-Client-Identifier': client_id
        })
        
        logging.debug(f"PIN check response status: {response.status_code}")
        if response.status_code == 200:
            pin_data = response.json()
            logging.debug(f"PIN check data: {pin_data}")
            if pin_data.get('authToken'):
                # Save the token directly like your working implementation
                config = config_manager.get_config()
                config['plex_token'] = pin_data['authToken']
                config_manager.save_config(config)
                
                # Clear session data
                session.pop('plex_pin_id', None)
                session.pop('plex_pin_code', None)
                session.pop('plex_client_id', None)
                
                flash('Plex authentication successful! Token saved.', 'success')
                return redirect(url_for('index'))
            else:
                flash('Authentication not yet complete. Please enter the code in Plex and try again.', 'warning')
        else:
            flash('Error checking authentication status', 'error')
            
    except Exception as e:
        logging.error(f"Error checking Plex auth: {str(e)}")
        flash(f'Error checking Plex authentication: {str(e)}', 'error')
    
    return redirect(url_for('index'))

@app.route('/run_daily_sync', methods=['POST'])
def run_daily_sync():
    """Manually trigger daily sync"""
    try:
        config = config_manager.get_config()
        tracker = MediaTracker(config)
        
        # Run the daily sync
        results = tracker.run_daily_sync()
        
        if results['success']:
            return jsonify({
                'success': True,
                'message': f"Daily sync completed! Found {results['movies_count']} movies, {results['shows_count']} TV shows, and {results['scheduled_count']} scheduled episodes."
            })
        else:
            return jsonify({
                'success': False,
                'message': f"Daily sync failed: {results['error']}"
            })
            
    except Exception as e:
        logging.error(f"Error running daily sync: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error running daily sync: {str(e)}'
        })

@app.route('/save_output_format', methods=['POST'])
def save_output_format():
    """Save custom output format settings"""
    try:
        config = config_manager.get_config()
        
        # Save output format preferences
        config['output_format'] = {
            'movie_format': request.form.get('movie_format', '').strip(),
            'tv_format': request.form.get('tv_format', '').strip(),
            'schedule_format': request.form.get('schedule_format', '').strip(),
            'include_timestamps': request.form.get('include_timestamps') == 'on',
            'include_descriptions': request.form.get('include_descriptions') == 'on',
            'file_naming': request.form.get('file_naming', 'date_suffix').strip(),
            'single_output_file': request.form.get('single_output_file', 'media_tracker.txt').strip()
        }
        
        config_manager.save_config(config)
        flash('Output format saved successfully!', 'success')
        
    except Exception as e:
        logging.error(f"Error saving output format: {str(e)}")
        flash(f'Error saving output format: {str(e)}', 'error')
    
    return redirect(url_for('index'))

@app.route('/clear_config')
def clear_config():
    """Clear all saved configuration"""
    try:
        import os
        config_file = 'config.json'
        if os.path.exists(config_file):
            os.remove(config_file)
            flash('Configuration cleared successfully! You can now reconfigure from scratch.', 'success')
        else:
            flash('No configuration file found to clear.', 'info')
    except Exception as e:
        logging.error(f"Error clearing configuration: {str(e)}")
        flash(f'Error clearing configuration: {str(e)}', 'error')
    
    return redirect(url_for('index'))

# JSON API Endpoints for external interfaces
@app.route('/api/status')
def api_status():
    """Get current status of all services"""
    config = config_manager.get_config()
    tracker = MediaTracker(config)
    
    status = {
        'plex': {
            'configured': bool(config.get('plex_url') and config.get('plex_token')),
            'connected': False
        },
        'sonarr': {
            'configured': bool(config.get('sonarr_url') and config.get('sonarr_api_key')),
            'connected': False
        },
        'github': {
            'configured': bool(config.get('github_enabled') and config.get('github_token')),
            'connected': False
        },
        'scheduler': {
            'enabled': config.get('scheduler_enabled', False),
            'type': config.get('schedule_type', 'daily'),
            'next_run': None
        }
    }
    
    # Test connections
    if status['plex']['configured']:
        try:
            result = tracker.test_plex_connection()
            status['plex']['connected'] = result and result.get('success', False)
        except:
            pass
    
    if status['sonarr']['configured']:
        try:
            result = tracker.test_sonarr_connection()
            status['sonarr']['connected'] = result and result.get('success', False)
        except:
            pass
    
    if status['github']['configured']:
        try:
            result = tracker.test_github_connection()
            status['github']['connected'] = result and result.get('success', False)
        except:
            pass
    
    # Get next scheduled run
    if scheduler.get_jobs():
        next_job = scheduler.get_jobs()[0]
        status['scheduler']['next_run'] = next_job.next_run_time.isoformat() if next_job.next_run_time else None
    
    return jsonify(status)

@app.route('/api/recent')
@require_api_key
def api_recent():
    """Get recent movies and TV shows with detailed information"""
    config = config_manager.get_config()
    tracker = MediaTracker(config)
    
    try:
        # Get days parameter, default to 7
        days = request.args.get('days', 7, type=int)
        if days < 1 or days > 30:
            days = 7
        
        movies, tv_shows = tracker.get_plex_recent_content_extended(days=days)
        return jsonify({
            'success': True,
            'days': days,
            'movies': movies,
            'tv_shows': tv_shows,
            'movies_count': len(movies),
            'tv_shows_count': len(tv_shows),
            'timestamp': datetime.now(pytz.timezone(config.get('timezone', 'US/Eastern'))).isoformat()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/all_content')
@require_api_key
def api_all_content():
    """Get all movies and TV shows from Plex library"""
    config = config_manager.get_config()
    tracker = MediaTracker(config)
    
    try:
        movies, tv_shows = tracker.get_plex_all_content()
        return jsonify({
            'success': True,
            'movies': movies,
            'tv_shows': tv_shows,
            'movies_count': len(movies),
            'tv_shows_count': len(tv_shows),
            'timestamp': datetime.now(pytz.timezone(config.get('timezone', 'US/Eastern'))).isoformat()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/schedule')
@require_api_key
def api_schedule():
    """Get TV schedule with detailed information"""
    config = config_manager.get_config()
    tracker = MediaTracker(config)
    
    try:
        # Get days parameter, default to 7
        days = request.args.get('days', 7, type=int)
        if days < 1 or days > 30:
            days = 7
        
        scheduled_shows = tracker.get_sonarr_calendar_extended(days=days)
        return jsonify({
            'success': True,
            'days': days,
            'scheduled_shows': scheduled_shows,
            'scheduled_count': len(scheduled_shows),
            'timestamp': datetime.now(pytz.timezone(config.get('timezone', 'US/Eastern'))).isoformat()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/full_sync')
@require_api_key
def api_full_sync():
    """Get all data in one call - recent content and schedule"""
    config = config_manager.get_config()
    tracker = MediaTracker(config)
    
    try:
        # Get days parameter, default to 7
        days = request.args.get('days', 7, type=int)
        if days < 1 or days > 30:
            days = 7
        
        movies, tv_shows = tracker.get_plex_recent_content_extended(days=days)
        scheduled_shows = tracker.get_sonarr_calendar_extended(days=days)
        
        # Get library stats
        library_stats = tracker.get_plex_library_stats()
        
        return jsonify({
            'success': True,
            'days': days,
            'data': {
                'movies': movies,
                'tv_shows': tv_shows,
                'scheduled_shows': scheduled_shows,
                'library_stats': library_stats
            },
            'counts': {
                'movies': len(movies),
                'tv_shows': len(tv_shows),
                'scheduled_shows': len(scheduled_shows)
            },
            'timestamp': datetime.now(pytz.timezone(config.get('timezone', 'US/Eastern'))).isoformat(),
            'timezone': config.get('timezone', 'US/Eastern')
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/library_stats')
@require_api_key
def api_library_stats():
    """Get Plex library statistics"""
    config = config_manager.get_config()
    tracker = MediaTracker(config)
    
    try:
        library_stats = tracker.get_plex_library_stats()
        return jsonify({
            'success': True,
            'library_stats': library_stats,
            'timestamp': datetime.now(pytz.timezone(config.get('timezone', 'US/Eastern'))).isoformat()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/config')
@require_api_key
def api_config():
    """Get current configuration (excluding sensitive data)"""
    config = config_manager.get_config()
    
    # Return config without sensitive information
    safe_config = {
        'plex_url': config.get('plex_url'),
        'sonarr_url': config.get('sonarr_url'),
        'filename': config.get('filename'),
        'timezone': config.get('timezone'),
        'movie_format': config.get('movie_format'),
        'tv_format': config.get('tv_format'),
        'schedule_format': config.get('schedule_format'),
        'scheduler_enabled': config.get('scheduler_enabled'),
        'schedule_type': config.get('schedule_type'),
        'schedule_hour': config.get('schedule_hour'),
        'schedule_minute': config.get('schedule_minute'),
        'schedule_interval': config.get('schedule_interval'),
        'github_enabled': config.get('github_enabled'),
        'github_owner': config.get('github_owner'),
        'github_repo': config.get('github_repo')
    }
    
    return jsonify(safe_config)

@app.route('/dashboard')
def dashboard():
    """Sample dashboard that demonstrates API usage"""
    return render_template('dashboard.html')

# Internal dashboard endpoints (no API key required)
@app.route('/internal/status')
def internal_status():
    """Internal status endpoint for dashboard"""
    try:
        config = config_manager.get_config()
        tracker = MediaTracker(config)
        
        plex_connected = tracker.test_plex_connection()
        sonarr_connected = tracker.test_sonarr_connection()
        github_connected = tracker.test_github_connection()
        
        return jsonify({
            'plex': {
                'configured': bool(config.get('plex_url') and config.get('plex_token')),
                'connected': plex_connected
            },
            'sonarr': {
                'configured': bool(config.get('sonarr_url') and config.get('sonarr_api_key')),
                'connected': sonarr_connected
            },
            'github': {
                'configured': bool(config.get('github_token') and config.get('github_repo')),
                'connected': github_connected
            },
            'scheduler': {
                'enabled': config.get('scheduler_enabled', False),
                'type': config.get('schedule_type', 'daily'),
                'next_run': None
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/internal/all_content')
def internal_all_content():
    """Internal endpoint to get all Plex content for dashboard"""
    try:
        config = config_manager.get_config()
        tracker = MediaTracker(config)
        
        # Try to get content, but handle connection gracefully
        movies = []
        tv_shows = []
        
        try:
            # Use get_plex_all_content to get all movies and TV shows
            movies, tv_shows = tracker.get_plex_all_content()
            
            # Add debug logging
            logging.info(f"Retrieved {len(movies)} movies and {len(tv_shows)} TV shows")
            if movies:
                logging.info(f"Sample movie: {movies[0]}")
            if tv_shows:
                logging.info(f"Sample TV show: {tv_shows[0]}")
            
            # Ensure we have valid data structures
            movies = movies if movies else []
            tv_shows = tv_shows if tv_shows else []
            
        except Exception as e:
            logging.error(f"Dashboard Plex connection error: {str(e)}")
            # Return empty but valid data structure
            movies = []
            tv_shows = []
            
        response_data = {
            'success': True,
            'movies': movies,
            'tv_shows': tv_shows,
            'movies_count': len(movies),
            'tv_shows_count': len(tv_shows),
            'timestamp': datetime.now(pytz.timezone(config.get('timezone', 'US/Eastern'))).isoformat()
        }
        
        logging.info(f"Sending response with {len(movies)} movies and {len(tv_shows)} TV shows")
        return jsonify(response_data)
        
    except Exception as e:
        logging.error(f"Internal all_content error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/internal/schedule')
def internal_schedule():
    """Internal endpoint to get TV schedule for dashboard"""
    try:
        config = config_manager.get_config()
        tracker = MediaTracker(config)
        
        # Get days parameter, default to 7
        days = request.args.get('days', 7, type=int)
        if days < 1 or days > 30:
            days = 7
            
        scheduled_shows = tracker.get_sonarr_calendar_extended(days=days)
        return jsonify({
            'success': True,
            'days': days,
            'scheduled_shows': scheduled_shows,
            'count': len(scheduled_shows),
            'timestamp': datetime.now(pytz.timezone(config.get('timezone', 'US/Eastern'))).isoformat()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/internal/library_stats')
def internal_library_stats():
    """Internal endpoint to get library stats for dashboard"""
    try:
        config = config_manager.get_config()
        tracker = MediaTracker(config)
        
        # Use the same successful inline approach
        movies = []
        tv_shows = []
        
        config = config_manager.get_config()
        if config.get('plex_url') and config.get('plex_token'):
            try:
                from urllib.parse import urljoin
                import xml.etree.ElementTree as ET
                import requests
                
                # Use same session setup as working text file generation
                session = requests.Session()
                session.headers.update({'Accept': 'application/xml'})
                
                url = urljoin(config['plex_url'], '/library/sections')
                headers = {'X-Plex-Token': config['plex_token']}
                
                response = session.get(url, headers=headers, timeout=30)
                response.raise_for_status()
                
                root = ET.fromstring(response.content)
                
                for library in root.findall('.//Directory'):
                    library_key = library.get('key')
                    library_type = library.get('type')
                    
                    if library_type in ['movie', 'show']:
                        all_url = urljoin(config['plex_url'], f'/library/sections/{library_key}/all')
                        all_response = requests.get(all_url, headers=headers)
                        all_response.raise_for_status()
                        
                        all_root = ET.fromstring(all_response.content)
                        items = all_root.findall('.//Video')
                        
                        if library_type == 'movie':
                            movies.extend(items)
                        elif library_type == 'show':
                            tv_shows.extend(items)
            except Exception as e:
                logging.error(f"Error getting Plex stats: {str(e)}")
        
        stats = {
            'total_movies': len(movies),
            'total_shows': len(tv_shows)
        }
        return jsonify({
            'success': True,
            'stats': stats,
            'timestamp': datetime.now(pytz.timezone(config.get('timezone', 'US/Eastern'))).isoformat()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/dashboard/download')
def download_dashboard_html():
    """Generate and download dashboard HTML code"""
    from datetime import datetime
    from flask import make_response
    
    # Get the current dashboard HTML template
    dashboard_html = render_template('dashboard.html')
    
    # Create response with HTML content
    response = make_response(dashboard_html)
    response.headers['Content-Type'] = 'text/html'
    response.headers['Content-Disposition'] = f'attachment; filename="media_tracker_dashboard_{datetime.now().strftime("%Y%m%d_%H%M%S")}.html"'
    
    return response

@app.route('/api/documentation/download')
def download_api_documentation():
    """Generate and download comprehensive API documentation"""
    from datetime import datetime
    import io
    
    # Generate comprehensive API documentation
    doc_content = f"""MEDIA TRACKER API DOCUMENTATION
=================================

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Base URL: {request.url_root}

OVERVIEW
--------
The Media Tracker API provides programmatic access to your Plex media library and Sonarr TV schedule data. All endpoints return JSON responses and support CORS for web applications.

AUTHENTICATION
--------------
All API endpoints require a valid API key for access. You can manage API keys through the web interface at /api_keys.

Include your API key in requests using one of these methods:
1. Header (Recommended): X-API-Key: YOUR_API_KEY
2. Query Parameter: ?api_key=YOUR_API_KEY

Example:
curl -H "X-API-Key: YOUR_API_KEY" {request.url_root}api/recent
curl "{request.url_root}api/recent?api_key=YOUR_API_KEY"

Unauthorized requests will receive a 401 or 403 error response.

ENDPOINTS
---------

1. GET /api/status
   Description: Get current connection status of all configured services
   Parameters: None
   
   Response Format:
   {{
     "plex": {{
       "configured": boolean,
       "connected": boolean
     }},
     "sonarr": {{
       "configured": boolean,
       "connected": boolean
     }},
     "github": {{
       "configured": boolean,
       "connected": boolean
     }},
     "scheduler": {{
       "enabled": boolean,
       "type": string,
       "next_run": string (ISO format)
     }}
   }}

2. GET /api/recent
   Description: Get recently added movies and TV shows with extended metadata
   Parameters: 
     - days (optional): Number of days to look back (1-30, default: 7)
   
   Example: /api/recent?days=14

3. GET /api/all_content
   Description: Get all movies and TV shows from your Plex library (no time restrictions)
   Parameters: None
   
   Example: /api/all_content
   
   Response Format:
   {{
     "success": boolean,
     "movies": [
       {{
         "title": string,
         "year": number,
         "rating": string,
         "summary": string,
         "duration": number (milliseconds),
         "genres": [string],
         "directors": [string],
         "actors": [string],
         "poster_url": string,
         "content_rating": string,
         "added_date": string,
         "library": string
       }}
     ],
     "tv_shows": [
       {{
         "title": string,
         "year": number,
         "rating": string,
         "summary": string,
         "episode_count": number,
         "genres": [string],
         "actors": [string],
         "poster_url": string,
         "content_rating": string,
         "added_date": string,
         "library": string
       }}
     ],
     "timestamp": string (ISO format),
     "timezone": string
   }}

3. GET /api/schedule
   Description: Get TV show schedule with extended metadata
   Parameters:
     - days (optional): Number of days to look ahead (1-30, default: 7)
   
   Example: /api/schedule?days=3
   
   Response Format:
   {{
     "success": boolean,
     "scheduled_shows": [
       {{
         "series_title": string,
         "episode_title": string,
         "season": number,
         "episode": number,
         "air_date": string,
         "overview": string,
         "series_id": number,
         "episode_id": number
       }}
     ],
     "timestamp": string (ISO format),
     "timezone": string
   }}

4. GET /api/full_sync
   Description: Get all data in one call - recent content and schedule
   Parameters:
     - days (optional): Number of days for both recent content and schedule (1-30, default: 7)
   
   Example: /api/full_sync?days=5
   
   Response Format:
   {{
     "success": boolean,
     "data": {{
       "movies": [...], // Same format as /api/recent
       "tv_shows": [...], // Same format as /api/recent
       "scheduled_shows": [...] // Same format as /api/schedule
     }},
     "timestamp": string (ISO format),
     "timezone": string
   }}

5. GET /api/library_stats
   Description: Get comprehensive Plex library statistics
   Parameters: None
   
   Response Format:
   {{
     "success": boolean,
     "library_stats": {{
       "total_movies": number,
       "total_shows": number,
       "total_episodes": number,
       "libraries": [
         {{
           "title": string,
           "type": string,
           "count": number
         }}
       ]
     }},
     "timestamp": string (ISO format)
   }}

6. GET /api/config
   Description: Get current configuration settings (sensitive data excluded)
   Parameters: None
   
   Response Format:
   {{
     "success": boolean,
     "config": {{
       "plex_configured": boolean,
       "sonarr_configured": boolean,
       "github_configured": boolean,
       "scheduler_enabled": boolean,
       "timezone": string,
       "output_format": {{
         "movies_header": string,
         "tv_header": string,
         "schedule_header": string,
         "movie_format": string,
         "tv_format": string,
         "schedule_format": string
       }}
     }}
   }}

ERROR HANDLING
--------------
All endpoints return appropriate HTTP status codes:
- 200: Success
- 400: Bad Request (invalid parameters)
- 500: Internal Server Error

Error responses include details:
{{
  "success": false,
  "error": "Error description",
  "timestamp": "ISO formatted timestamp"
}}

USAGE EXAMPLES
--------------

JavaScript (Fetch API):
```javascript
// Get recent content from last 7 days
fetch('/api/recent?days=7')
  .then(response => response.json())
  .then(data => {{
    if (data.success) {{
      console.log('Movies:', data.movies);
      console.log('TV Shows:', data.tv_shows);
    }}
  }});

// Get all data in one call
fetch('/api/full_sync?days=3')
  .then(response => response.json())
  .then(data => {{
    if (data.success) {{
      const {{ movies, tv_shows, scheduled_shows }} = data.data;
      // Process your data here
    }}
  }});
```

Python (requests library):
```python
import requests

# Get status of all services
response = requests.get('http://your-server:5000/api/status')
status_data = response.json()

# Get recent content
response = requests.get('http://your-server:5000/api/recent?days=14')
content_data = response.json()

if content_data['success']:
    for movie in content_data['movies']:
        print(f"{{movie['title']}} ({{movie['year']}})")
```

curl:
```bash
# Test connection status
curl http://your-server:5000/api/status

# Get recent content with pretty formatting
curl -s http://your-server:5000/api/recent?days=7 | python -m json.tool

# Get schedule for next 3 days
curl http://your-server:5000/api/schedule?days=3
```

INTEGRATION NOTES
-----------------
- All timestamps are returned in ISO format with timezone information
- The API respects the timezone configured in your Media Tracker settings
- Large responses may take a few seconds depending on your Plex library size
- The API supports CORS for cross-origin requests from web applications
- Content is cached for optimal performance - data updates every few minutes

RATE LIMITING
-------------
Currently no rate limiting is implemented, but it's recommended to:
- Cache responses when possible
- Avoid excessive polling (consider webhooks or scheduled checks instead)
- Use the /api/full_sync endpoint for efficiency when you need multiple data types

TROUBLESHOOTING
---------------
If endpoints return errors:
1. Check /api/status to verify service connections
2. Ensure Plex and Sonarr are properly configured and accessible
3. Verify the Media Tracker has proper permissions to access your services
4. Check the Media Tracker logs for detailed error messages

SAMPLE DASHBOARD
---------------
A sample dashboard demonstrating API usage is available at: {request.url_root}dashboard

This dashboard shows how to integrate the API endpoints into a web application with real-time data display and interactive features.

You can also download the complete dashboard HTML code from: {request.url_root}dashboard/download
This provides a ready-to-use template that you can customize for your own applications.

For support and updates, visit the Media Tracker configuration page.

---
End of Documentation
"""
    
    # Create a text file response
    output = io.StringIO()
    output.write(doc_content)
    output.seek(0)
    
    response = Response(
        output.getvalue(),
        mimetype='text/plain',
        headers={
            'Content-Disposition': f'attachment; filename=media-tracker-api-docs-{datetime.now().strftime("%Y%m%d")}.txt',
            'Content-Type': 'text/plain; charset=utf-8'
        }
    )
    
    return response

@app.route('/api_keys')
def api_keys():
    """API key management page"""
    return render_template('api_keys.html', api_keys=api_key_manager.list_keys())

@app.route('/create_api_key', methods=['POST'])
def create_api_key():
    """Create a new API key"""
    name = request.form.get('name', '').strip()
    if not name:
        flash('API key name is required', 'error')
        return redirect(url_for('api_keys'))
    
    try:
        key = api_key_manager.create_key(name)
        flash(f'API key created successfully: {key}', 'success')
    except Exception as e:
        flash(f'Error creating API key: {str(e)}', 'error')
    
    return redirect(url_for('api_keys'))

@app.route('/deactivate_api_key/<key>')
def deactivate_api_key(key):
    """Deactivate an API key"""
    if api_key_manager.deactivate_key(key):
        flash('API key deactivated successfully', 'success')
    else:
        flash('API key not found', 'error')
    
    return redirect(url_for('api_keys'))

@app.route('/help')
def help_page():
    """Comprehensive help documentation"""
    return render_template('help.html')

@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files"""
    return send_from_directory('static', filename)

# Initialize scheduler now that all functions are defined
init_scheduler()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3038, debug=True)
