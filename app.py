import os
import logging
import uuid
import requests
from flask import Flask, render_template, request, flash, redirect, url_for, session
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
            'output_directory': request.form.get('output_directory', './output').strip(),
            'github_enabled': request.form.get('github_enabled') == 'on',
            'github_repo': request.form.get('github_repo', '').strip(),
            'github_token': request.form.get('github_token', '').strip(),
            'github_branch': request.form.get('github_branch', 'main').strip()
        }
        
        # Validate required fields
        required_fields = ['plex_url', 'plex_token', 'sonarr_url', 'sonarr_api_key']
        missing_fields = [field for field in required_fields if not config_data[field]]
        
        # Validate GitHub fields if enabled
        if config_data['github_enabled']:
            github_required = ['github_repo', 'github_token']
            missing_github = [field for field in github_required if not config_data[field]]
            if missing_github:
                flash(f"GitHub enabled but missing: {', '.join(missing_github)}", 'error')
                return redirect(url_for('index'))
        
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
        
        # Use the same method as device pairing for 4-digit codes
        headers = {
            'Accept': 'application/json',
            'X-Plex-Product': 'Media Tracker',
            'X-Plex-Version': '1.0',
            'X-Plex-Client-Identifier': client_identifier,
            'X-Plex-Platform': 'Linux',
            'X-Plex-Model': 'bundled'
        }
        
        # Request PIN without strong parameter to get shorter code
        response = requests.post('https://plex.tv/api/v2/pins', headers=headers)
        
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
        
        # Check if the PIN has been authorized
        response = requests.get(f'https://plex.tv/api/v2/pins/{pin_id}', headers={
            'Accept': 'application/json',
            'X-Plex-Client-Identifier': client_id
        })
        
        if response.status_code == 200:
            pin_data = response.json()
            if pin_data.get('authToken'):
                # Get user's Plex servers
                servers_response = requests.get('https://plex.tv/api/v2/resources', headers={
                    'Accept': 'application/json',
                    'X-Plex-Token': pin_data['authToken']
                })
                
                if servers_response.status_code == 200:
                    servers = servers_response.json()
                    plex_servers = [s for s in servers if s.get('product') == 'Plex Media Server' and s.get('owned') == '1']
                    
                    if plex_servers:
                        # Use the first owned server
                        server = plex_servers[0]
                        connections = server.get('connections', [])
                        local_connection = next((c for c in connections if c.get('local') == '1'), connections[0] if connections else None)
                        
                        if local_connection:
                            plex_url = f"{local_connection['protocol']}://{local_connection['address']}:{local_connection['port']}"
                            
                            # Save the configuration
                            config = config_manager.get_config()
                            config['plex_url'] = plex_url
                            config['plex_token'] = pin_data['authToken']
                            config_manager.save_config(config)
                            
                            # Clear session data
                            session.pop('plex_pin_id', None)
                            session.pop('plex_pin_code', None)
                            session.pop('plex_client_id', None)
                            
                            flash('Plex authentication successful!', 'success')
                            return redirect(url_for('index'))
                
                flash('Could not find accessible Plex server', 'error')
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3038, debug=True)
