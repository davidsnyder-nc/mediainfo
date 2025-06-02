import os
import logging
import uuid
import requests
from flask import Flask, render_template, request, flash, redirect, url_for, session, jsonify
from config import ConfigManager
from media_tracker import MediaTracker
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
            'movies_section_title': request.form.get('movies_section_title', 'PLEX MOVIES ADDED').strip(),
            'tv_shows_section_title': request.form.get('tv_shows_section_title', 'PLEX TV SHOWS ADDED').strip(),
            'tv_calendar_section_title': request.form.get('tv_calendar_section_title', 'SONARR TV SCHEDULE').strip(),
            'no_movies_text': request.form.get('no_movies_text', 'No movies added recently.').strip(),
            'no_tv_text': request.form.get('no_tv_text', 'No TV shows added recently.').strip(),
            'no_schedule_text': request.form.get('no_schedule_text', 'No shows scheduled for today.').strip(),
            'github_enabled': request.form.get('github_enabled') == 'on',
            'github_repo': request.form.get('github_repo', '').strip(),
            'github_token': request.form.get('github_token', '').strip(),
            'github_branch': request.form.get('github_branch', 'main').strip(),
            'scheduler_enabled': request.form.get('scheduler_enabled') == 'on',
            'schedule_type': request.form.get('schedule_type', 'daily'),
            'scheduler_hour': int(request.form.get('scheduler_hour', 19)),
            'scheduler_minute': int(request.form.get('scheduler_minute', 55)),
            'interval_hours': int(request.form.get('interval_hours', 1))
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
            github_required = ['github_repo', 'github_token']
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
        
        success_count = sum([plex_status, sonarr_status, github_status])
        total_tests = 2 + (1 if config.get('github_enabled', False) else 0)
        
        if success_count == total_tests:
            flash('All API connections successful!', 'success')
        elif success_count > 0:
            status_msgs = []
            if plex_status:
                status_msgs.append('Plex: OK')
            else:
                status_msgs.append('Plex: Failed')
            if sonarr_status:
                status_msgs.append('Sonarr: OK')
            else:
                status_msgs.append('Sonarr: Failed')
            if config.get('github_enabled', False):
                if github_status:
                    status_msgs.append('GitHub: OK')
                else:
                    status_msgs.append('GitHub: Failed')
            flash(f"Connection status: {' | '.join(status_msgs)}", 'warning')
        else:
            flash('All API connections failed!', 'error')
            
    except Exception as e:
        logging.error(f"Error testing connections: {str(e)}")
        flash(f'Error testing connections: {str(e)}', 'error')
    
    return redirect(url_for('index'))

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

@app.route('/run_daily_sync')
def run_daily_sync():
    """Manually trigger daily sync"""
    try:
        config = config_manager.get_config()
        tracker = MediaTracker(config)
        
        # Run the daily sync
        results = tracker.run_daily_sync()
        
        if results['success']:
            flash(f"Daily sync completed! Found {results['movies_count']} movies and {results['shows_count']} TV shows.", 'success')
        else:
            flash(f"Daily sync failed: {results['error']}", 'error')
            
    except Exception as e:
        logging.error(f"Error running daily sync: {str(e)}")
        flash(f'Error running daily sync: {str(e)}', 'error')
    
    return redirect(url_for('index'))

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

@app.route('/api/schedule')
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

# Initialize scheduler now that all functions are defined
init_scheduler()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3038, debug=True)
