import os
import logging
from flask import Flask, render_template, request, flash, redirect, url_for
from config import ConfigManager
from media_tracker import MediaTracker

# Configure logging
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")

# Initialize configuration manager
config_manager = ConfigManager()

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
            'output_directory': request.form.get('output_directory', './output').strip()
        }
        
        # Validate required fields
        required_fields = ['plex_url', 'plex_token', 'sonarr_url', 'sonarr_api_key']
        missing_fields = [field for field in required_fields if not config_data[field]]
        
        if missing_fields:
            flash(f"Missing required fields: {', '.join(missing_fields)}", 'error')
            return redirect(url_for('index'))
        
        # Save configuration
        config_manager.save_config(config_data)
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
        
        if plex_status and sonarr_status:
            flash('Both API connections successful!', 'success')
        elif plex_status:
            flash('Plex connection successful, Sonarr connection failed!', 'warning')
        elif sonarr_status:
            flash('Sonarr connection successful, Plex connection failed!', 'warning')
        else:
            flash('Both API connections failed!', 'error')
            
    except Exception as e:
        logging.error(f"Error testing connections: {str(e)}")
        flash(f'Error testing connections: {str(e)}', 'error')
    
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
