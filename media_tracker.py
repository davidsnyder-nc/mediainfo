import requests
import json
import os
import logging
import base64
from datetime import datetime, timedelta
from urllib.parse import urljoin

class MediaTracker:
    """Handles API connections and data processing for Plex and Sonarr"""
    
    def __init__(self, config):
        self.config = config
        self.session = requests.Session()
    
    def test_plex_connection(self):
        """Test connection to Plex API"""
        try:
            url = urljoin(self.config['plex_url'], '/identity')
            headers = {'X-Plex-Token': self.config['plex_token']}
            
            response = self.session.get(url, headers=headers)
            response.raise_for_status()
            
            logging.info("Plex connection successful")
            return True
            
        except Exception as e:
            logging.error(f"Plex connection failed: {str(e)}")
            return False
    
    def test_sonarr_connection(self):
        """Test connection to Sonarr API"""
        try:
            url = urljoin(self.config['sonarr_url'], '/api/v3/system/status')
            headers = {'X-Api-Key': self.config['sonarr_api_key']}
            
            response = self.session.get(url, headers=headers)
            response.raise_for_status()
            
            logging.info("Sonarr connection successful")
            return True
            
        except Exception as e:
            logging.error(f"Sonarr connection failed: {str(e)}")
            return False
    
    def get_plex_recent_content(self):
        """Get movies and TV shows added to Plex today"""
        movies = []
        tv_shows = []
        
        # Check if Plex is configured
        if not self.config.get('plex_url') or not self.config.get('plex_token'):
            return movies, tv_shows
        
        try:
            # Get all libraries
            url = urljoin(self.config['plex_url'], '/library/sections')
            headers = {'X-Plex-Token': self.config['plex_token']}
            
            response = self.session.get(url, headers=headers)
            response.raise_for_status()
            
            # Parse XML response (Plex returns XML)
            import xml.etree.ElementTree as ET
            root = ET.fromstring(response.content)
            
            today = datetime.now().date()
            yesterday = today - timedelta(days=1)
            
            for library in root.findall('.//Directory'):
                library_key = library.get('key')
                library_type = library.get('type')
                library_title = library.get('title', 'Unknown Library')
                
                logging.info(f"Checking library: {library_title} (type: {library_type})")
                
                if library_type in ['movie', 'show']:
                    # Get recently added items from this library
                    recent_url = urljoin(self.config['plex_url'], f'/library/sections/{library_key}/recentlyAdded')
                    recent_response = self.session.get(recent_url, headers=headers, timeout=30)
                    recent_response.raise_for_status()
                    
                    recent_root = ET.fromstring(recent_response.content)
                    all_items = recent_root.findall('.//Video')
                    logging.info(f"Found {len(all_items)} total items in {library_title}")
                    
                    for item in all_items:
                        added_at = item.get('addedAt')
                        if added_at:
                            added_date = datetime.fromtimestamp(int(added_at)).date()
                            # Only show content from yesterday and today
                            if added_date >= yesterday:
                                title = item.get('title', 'Unknown Title')
                                year = item.get('year', 'Unknown Year')
                                
                                if library_type == 'movie':
                                    movies.append({
                                        'title': title,
                                        'year': year,
                                        'added_date': added_date.strftime('%Y-%m-%d')
                                    })
                                elif library_type == 'show':
                                    tv_shows.append({
                                        'title': title,
                                        'year': year,
                                        'added_date': added_date.strftime('%Y-%m-%d')
                                    })
        
        except Exception as e:
            logging.error(f"Error getting Plex content: {str(e)}")
        
        return movies, tv_shows
    
    def get_sonarr_today_schedule(self):
        """Get TV shows scheduled for today from Sonarr"""
        scheduled_shows = []
        
        # Check if Sonarr is configured
        if not self.config.get('sonarr_url') or not self.config.get('sonarr_api_key'):
            return scheduled_shows
        
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
            
            # First get all series to create a lookup table
            series_url = urljoin(self.config['sonarr_url'], '/api/v3/series')
            headers = {'X-Api-Key': self.config['sonarr_api_key']}
            
            series_response = self.session.get(series_url, headers=headers)
            series_response.raise_for_status()
            all_series = series_response.json()
            
            # Create a lookup dictionary for series ID to title
            series_lookup = {series['id']: series['title'] for series in all_series}
            
            # Now get the calendar data
            calendar_url = urljoin(self.config['sonarr_url'], f'/api/v3/calendar?start={today}&end={tomorrow}')
            
            calendar_response = self.session.get(calendar_url, headers=headers)
            calendar_response.raise_for_status()
            
            calendar_data = calendar_response.json()
            logging.debug(f"Sonarr calendar response sample: {calendar_data[:1] if calendar_data else 'No data'}")
            
            for episode in calendar_data:
                air_date = episode.get('airDate', episode.get('airDateUtc', ''))
                if air_date and air_date.startswith(today):
                    # Get series title from lookup table using seriesId
                    series_id = episode.get('seriesId')
                    series_title = series_lookup.get(series_id, 'Unknown Series')
                    
                    scheduled_shows.append({
                        'series_title': series_title,
                        'episode_title': episode.get('title', 'Unknown Episode'),
                        'season': episode.get('seasonNumber', 'Unknown'),
                        'episode': episode.get('episodeNumber', 'Unknown'),
                        'air_date': air_date.split('T')[0] if 'T' in air_date else air_date
                    })
        
        except Exception as e:
            logging.error(f"Error getting Sonarr schedule: {str(e)}")
        
        return scheduled_shows
    
    def write_to_files(self, movies, tv_shows, scheduled_shows):
        """Write collected data to text files using custom format"""
        try:
            output_dir = self.config['output_directory']
            os.makedirs(output_dir, exist_ok=True)
            
            today_str = datetime.now().strftime('%Y-%m-%d')
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S') if self.config.get('output_format', {}).get('include_timestamps', True) else ''
            
            # Get custom formats
            output_format = self.config.get('output_format', {})
            movie_format = output_format.get('movie_format', 'Title: {title}\nYear: {year}\nAdded: {added_date}\n{separator}')
            tv_format = output_format.get('tv_format', 'Title: {title}\nYear: {year}\nAdded: {added_date}\n{separator}')
            schedule_format = output_format.get('schedule_format', 'Series: {series_title}\nEpisode: S{season:02d}E{episode:02d} - {episode_title}\nAir Date: {air_date}\n{separator}')
            file_naming = output_format.get('file_naming', 'date_suffix')
            
            # Single output file
            if file_naming == 'custom':
                output_file = os.path.join(output_dir, output_format.get('single_output_file', 'media_tracker.txt'))
            elif file_naming == 'date_prefix':
                output_file = os.path.join(output_dir, f'{today_str}_media_tracker.txt')
            else:  # date_suffix (default)
                output_file = os.path.join(output_dir, f'media_tracker_{today_str}.txt')
            
            # Write all data to single file
            with open(output_file, 'w') as f:
                # Header
                report_title = self.config.get('report_title', 'Media Tracker Report')
                header = f"{report_title} - {today_str}"
                if timestamp:
                    header += f" (Generated: {timestamp})"
                f.write(header + "\n")
                f.write("=" * len(header) + "\n\n")
                
                # Movies section
                if self.config.get('include_movies', True):
                    movies_title = self.config.get('movies_section_title', 'PLEX MOVIES ADDED')
                    f.write(f"{movies_title}\n")
                    f.write("=" * len(movies_title) + "\n")
                    if movies:
                        for movie in movies:
                            content = movie_format.format(
                                title=movie['title'],
                                year=movie['year'],
                                added_date=movie['added_date'],
                                separator="-" * 30
                            )
                            f.write(content + "\n")
                    else:
                        no_movies_text = self.config.get('no_movies_text', 'No movies added recently.')
                        f.write(f"{no_movies_text}\n\n")
                
                # TV Shows section
                if self.config.get('include_tv_shows', True):
                    tv_shows_title = self.config.get('tv_shows_section_title', 'PLEX TV SHOWS ADDED')
                    f.write(f"\n{tv_shows_title}\n")
                    f.write("=" * len(tv_shows_title) + "\n")
                    if tv_shows:
                        for show in tv_shows:
                            content = tv_format.format(
                                title=show['title'],
                                year=show['year'],
                                added_date=show['added_date'],
                                separator="-" * 30
                            )
                            f.write(content + "\n")
                    else:
                        no_tv_text = self.config.get('no_tv_text', 'No TV shows added recently.')
                        f.write(f"{no_tv_text}\n\n")
                
                # Schedule section
                if self.config.get('include_tv_calendar', True):
                    tv_calendar_title = self.config.get('tv_calendar_section_title', 'SONARR TV SCHEDULE')
                    f.write(f"\n{tv_calendar_title}\n")
                    f.write("=" * len(tv_calendar_title) + "\n")
                    if scheduled_shows:
                        for show in scheduled_shows:
                            content = schedule_format.format(
                                series_title=show['series_title'],
                                episode_title=show['episode_title'],
                                season=show['season'],
                                episode=show['episode'],
                                air_date=show['air_date'],
                                separator="-" * 30
                            )
                            f.write(content + "\n")
                    else:
                        no_schedule_text = self.config.get('no_schedule_text', 'No shows scheduled for today.')
                        f.write(f"{no_schedule_text}\n")
            
            logging.info(f"Files written successfully to {output_dir}")
            
            # Upload to GitHub if enabled
            if self.config.get('github_enabled', False):
                self.upload_to_github([output_file])
            
            return True
            
        except Exception as e:
            logging.error(f"Error writing files: {str(e)}")
            return False
    
    def test_github_connection(self):
        """Test GitHub API connection"""
        try:
            if not self.config.get('github_enabled', False):
                return False
                
            repo = self.config.get('github_repo', '')
            token = self.config.get('github_token', '')
            
            if not repo or not token:
                return False
            
            # Test by getting repository info
            url = f"https://api.github.com/repos/{repo}"
            headers = {
                'Authorization': f'token {token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            response = self.session.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            logging.info("GitHub connection successful")
            return True
            
        except Exception as e:
            logging.error(f"GitHub connection failed: {str(e)}")
            return False
    
    def upload_to_github(self, file_paths):
        """Upload files to GitHub repository"""
        try:
            repo = self.config.get('github_repo', '')
            token = self.config.get('github_token', '')
            branch = self.config.get('github_branch', 'main')
            
            if not repo or not token:
                logging.error("GitHub repository or token not configured")
                return False
            
            headers = {
                'Authorization': f'token {token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            for file_path in file_paths:
                if not os.path.exists(file_path):
                    continue
                    
                # Read file content
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Encode content to base64
                content_encoded = base64.b64encode(content.encode('utf-8')).decode('utf-8')
                
                # Get just the filename for GitHub
                filename = os.path.basename(file_path)
                
                # Check if file already exists to get SHA
                check_url = f"https://api.github.com/repos/{repo}/contents/{filename}"
                check_params = {'ref': branch}
                check_response = self.session.get(check_url, headers=headers, params=check_params, timeout=30)
                
                # Prepare the commit data
                commit_data = {
                    'message': f'Update media tracker: {filename}',
                    'content': content_encoded,
                    'branch': branch
                }
                
                # If file exists, include the SHA for update
                if check_response.status_code == 200:
                    existing_file = check_response.json()
                    commit_data['sha'] = existing_file['sha']
                
                # Upload/update the file
                upload_url = f"https://api.github.com/repos/{repo}/contents/{filename}"
                response = self.session.put(upload_url, headers=headers, json=commit_data, timeout=30)
                
                if response.status_code in [200, 201]:
                    logging.info(f"Successfully uploaded {filename} to GitHub")
                else:
                    logging.error(f"Failed to upload {filename} to GitHub: {response.status_code} - {response.text}")
            
            return True
            
        except Exception as e:
            logging.error(f"Error uploading to GitHub: {str(e)}")
            return False
    
    def get_plex_recent_content_extended(self, days=7):
        """Get movies and TV shows added to Plex in the last N days with extended metadata"""
        movies = []
        tv_shows = []
        
        try:
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            start_timestamp = int(start_date.timestamp())
            
            # Get recently added content
            url = urljoin(self.config['plex_url'], '/library/recentlyAdded')
            headers = {'X-Plex-Token': self.config['plex_token']}
            params = {'X-Plex-Container-Start': '0', 'X-Plex-Container-Size': '100'}
            
            response = self.session.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if 'MediaContainer' in data and 'Metadata' in data['MediaContainer']:
                for item in data['MediaContainer']['Metadata']:
                    added_at = item.get('addedAt', 0)
                    
                    if int(added_at) >= start_timestamp:
                        # Enhanced metadata extraction
                        base_item = {
                            'title': item.get('title', 'Unknown'),
                            'year': item.get('year', 'Unknown'),
                            'added_date': datetime.fromtimestamp(int(added_at)).strftime('%Y-%m-%d'),
                            'added_timestamp': int(added_at),
                            'rating': item.get('rating', 'Not Rated'),
                            'summary': item.get('summary', ''),
                            'duration': item.get('duration', 0),
                            'thumb': item.get('thumb', ''),
                            'art': item.get('art', ''),
                            'genres': [genre.get('tag', '') for genre in item.get('Genre', [])],
                            'studio': item.get('studio', ''),
                            'content_rating': item.get('contentRating', ''),
                            'plex_key': item.get('key', ''),
                            'guid': item.get('guid', '')
                        }
                        
                        if item.get('type') == 'movie':
                            # Movie-specific fields
                            movie_item = base_item.copy()
                            movie_item.update({
                                'director': [director.get('tag', '') for director in item.get('Director', [])],
                                'writers': [writer.get('tag', '') for writer in item.get('Writer', [])],
                                'actors': [{'name': actor.get('tag', ''), 'role': actor.get('role', '')} for actor in item.get('Role', [])[:10]],  # Limit to top 10
                                'country': [country.get('tag', '') for country in item.get('Country', [])],
                                'tagline': item.get('tagline', ''),
                                'originally_available_at': item.get('originallyAvailableAt', '')
                            })
                            movies.append(movie_item)
                            
                        elif item.get('type') == 'show':
                            # TV Show-specific fields
                            tv_item = base_item.copy()
                            tv_item.update({
                                'episode_count': item.get('leafCount', 0),
                                'season_count': item.get('childCount', 0),
                                'originally_available_at': item.get('originallyAvailableAt', ''),
                                'network': item.get('network', ''),
                                'status': item.get('status', '')
                            })
                            tv_shows.append(tv_item)
        
        except Exception as e:
            logging.error(f"Error getting extended Plex content: {str(e)}")
        
        return movies, tv_shows
    
    def get_sonarr_calendar_extended(self, days=7):
        """Get TV shows from Sonarr calendar for the next N days with extended metadata"""
        scheduled_shows = []
        
        try:
            # Get date range
            start_date = datetime.now().strftime('%Y-%m-%d')
            end_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
            
            # Get calendar data
            url = urljoin(self.config['sonarr_url'], '/api/v3/calendar')
            headers = {'X-Api-Key': self.config['sonarr_api_key']}
            params = {'start': start_date, 'end': end_date}
            
            response = self.session.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            episodes = response.json()
            
            # Get series data for additional metadata
            series_url = urljoin(self.config['sonarr_url'], '/api/v3/series')
            series_response = self.session.get(series_url, headers=headers)
            series_response.raise_for_status()
            series_data = series_response.json()
            
            # Create series lookup
            series_lookup = {series['id']: series for series in series_data}
            
            for episode in episodes:
                series_id = episode.get('seriesId')
                series = series_lookup.get(series_id, {})
                air_date = episode.get('airDateUtc', '')
                
                if air_date:
                    episode_data = {
                        'series_title': series.get('title', 'Unknown Series'),
                        'episode_title': episode.get('title', 'Unknown Episode'),
                        'season': episode.get('seasonNumber', 'Unknown'),
                        'episode': episode.get('episodeNumber', 'Unknown'),
                        'air_date': air_date.split('T')[0] if 'T' in air_date else air_date,
                        'air_time': air_date.split('T')[1].split('.')[0] if 'T' in air_date else '',
                        'overview': episode.get('overview', ''),
                        'series_overview': series.get('overview', ''),
                        'network': series.get('network', ''),
                        'status': series.get('status', ''),
                        'genres': series.get('genres', []),
                        'year': series.get('year', 0),
                        'runtime': series.get('runtime', 0),
                        'certification': series.get('certification', ''),
                        'image_url': series.get('images', [{}])[0].get('url', '') if series.get('images') else '',
                        'imdb_id': series.get('imdbId', ''),
                        'tvdb_id': series.get('tvdbId', ''),
                        'series_type': series.get('seriesType', ''),
                        'language': series.get('languageProfileId', ''),
                        'quality_profile': series.get('qualityProfileId', ''),
                        'monitored': series.get('monitored', False),
                        'episode_monitored': episode.get('monitored', False),
                        'has_file': episode.get('hasFile', False),
                        'episode_id': episode.get('id', 0),
                        'series_id': series_id
                    }
                    scheduled_shows.append(episode_data)
        
        except Exception as e:
            logging.error(f"Error getting extended Sonarr calendar: {str(e)}")
        
        return scheduled_shows
    
    def get_plex_library_stats(self):
        """Get comprehensive Plex library statistics"""
        stats = {
            'libraries': [],
            'total_movies': 0,
            'total_shows': 0,
            'total_episodes': 0,
            'total_music': 0
        }
        
        try:
            # Get library sections
            url = urljoin(self.config['plex_url'], '/library/sections')
            headers = {'X-Plex-Token': self.config['plex_token']}
            
            response = self.session.get(url, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            
            if 'MediaContainer' in data and 'Directory' in data['MediaContainer']:
                for library in data['MediaContainer']['Directory']:
                    library_info = {
                        'key': library.get('key', ''),
                        'title': library.get('title', ''),
                        'type': library.get('type', ''),
                        'count': 0,
                        'size': 0
                    }
                    
                    # Get library contents count
                    lib_url = urljoin(self.config['plex_url'], f'/library/sections/{library.get("key")}/all')
                    lib_response = self.session.get(lib_url, headers=headers, params={'X-Plex-Container-Size': '0'})
                    
                    if lib_response.status_code == 200:
                        lib_data = lib_response.json()
                        if 'MediaContainer' in lib_data:
                            library_info['count'] = lib_data['MediaContainer'].get('totalSize', 0)
                    
                    stats['libraries'].append(library_info)
                    
                    # Update totals
                    if library.get('type') == 'movie':
                        stats['total_movies'] += library_info['count']
                    elif library.get('type') == 'show':
                        stats['total_shows'] += library_info['count']
                    elif library.get('type') == 'artist':
                        stats['total_music'] += library_info['count']
        
        except Exception as e:
            logging.error(f"Error getting Plex library stats: {str(e)}")
        
        return stats

    def run_daily_sync(self):
        """Run the complete daily sync process"""
        try:
            logging.info("Starting daily sync...")
            
            # Test connections first
            if not self.test_plex_connection():
                return {'success': False, 'error': 'Plex connection failed'}
            
            if not self.test_sonarr_connection():
                return {'success': False, 'error': 'Sonarr connection failed'}
            
            # Get data from APIs (keeping original methods for text file output)
            movies, tv_shows = self.get_plex_recent_content()
            scheduled_shows = self.get_sonarr_today_schedule()
            
            # Write to files
            if self.write_to_files(movies, tv_shows, scheduled_shows):
                logging.info("Daily sync completed successfully")
                return {
                    'success': True,
                    'movies_count': len(movies),
                    'shows_count': len(tv_shows),
                    'scheduled_count': len(scheduled_shows)
                }
            else:
                return {'success': False, 'error': 'Failed to write output files'}
                
        except Exception as e:
            logging.error(f"Daily sync failed: {str(e)}")
            return {'success': False, 'error': str(e)}
