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
            plex_url = self.config.get('plex_url', '').strip()
            plex_token = self.config.get('plex_token', '').strip()
            
            if not plex_url or not plex_token:
                logging.error("Plex URL or token not configured")
                return False
            
            # Ensure URL has protocol
            if not plex_url.startswith(('http://', 'https://')):
                plex_url = 'http://' + plex_url
            
            url = urljoin(plex_url, '/identity')
            headers = {'X-Plex-Token': plex_token}
            
            response = self.session.get(url, headers=headers, timeout=2)
            response.raise_for_status()
            
            logging.info("Plex connection successful")
            return True
            
        except Exception as e:
            logging.error(f"Plex connection failed: {str(e)}")
            return False
    
    def test_sonarr_connection(self):
        """Test connection to Sonarr API"""
        try:
            sonarr_url = self.config.get('sonarr_url', '').strip()
            sonarr_api_key = self.config.get('sonarr_api_key', '').strip()
            
            logging.info(f"Testing Sonarr connection - URL: {sonarr_url}, API Key: {'***' if sonarr_api_key else 'None'}")
            
            if not sonarr_url or not sonarr_api_key:
                logging.error("Sonarr URL or API key not configured")
                return False
            
            # Ensure URL has protocol
            if not sonarr_url.startswith(('http://', 'https://')):
                sonarr_url = 'http://' + sonarr_url
            
            url = urljoin(sonarr_url, '/api/v3/system/status')
            headers = {'X-Api-Key': sonarr_api_key}
            
            logging.info(f"Making request to: {url}")
            response = self.session.get(url, headers=headers, timeout=2)
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
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S') if self.config.get('include_timestamps', True) else ''
            
            # Get custom formats
            movie_format = self.config.get('movie_format', 'Title: {title}\nYear: {year}\nAdded: {added_date}\n{separator}')
            tv_format = self.config.get('tv_format', 'Title: {title}\nYear: {year}\nAdded: {added_date}\n{separator}')
            schedule_format = self.config.get('schedule_format', 'Series: {series_title}\nEpisode: S{season:02d}E{episode:02d} - {episode_title}\nAir Date: {air_date}\n{separator}')
            file_naming = self.config.get('file_naming', 'date_suffix')
            
            # Single output file
            if file_naming == 'custom':
                output_file = os.path.join(output_dir, self.config.get('single_output_file', 'media_tracker.txt'))
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
                
                logging.info(f"Writing file with: {len(movies)} movies, {len(tv_shows)} TV shows, {len(scheduled_shows)} scheduled shows")
                logging.info(f"Section toggles - Movies: {self.config.get('include_movies', True)}, TV: {self.config.get('include_tv_shows', True)}, Schedule: {self.config.get('include_tv_calendar', True)}")
                
                # Movies section
                if self.config.get('include_movies', True):
                    movies_title = self.config.get('movies_title', 'PLEX MOVIES ADDED')
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
                    tv_shows_title = self.config.get('tv_shows_title', 'PLEX TV SHOWS ADDED')
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
                    tv_calendar_title = self.config.get('tv_calendar_title', 'TV SHOWS AIRING TODAY')
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
                
            owner = self.config.get('github_owner', '')
            repo = self.config.get('github_repo', '')
            token = self.config.get('github_token', '')
            
            if not owner or not repo or not token:
                return False
            
            # Test by getting repository info
            full_repo = f"{owner}/{repo}"
            url = f"https://api.github.com/repos/{full_repo}"
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
            owner = self.config.get('github_owner', '')
            repo = self.config.get('github_repo', '')
            token = self.config.get('github_token', '')
            branch = self.config.get('github_branch', 'main')
            
            if not owner or not repo or not token:
                logging.error("GitHub owner, repository, or token not configured")
                return False
            
            full_repo = f"{owner}/{repo}"
            
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
                check_url = f"https://api.github.com/repos/{full_repo}/contents/{filename}"
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
                upload_url = f"https://api.github.com/repos/{full_repo}/contents/{filename}"
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
            plex_url = self.config.get('plex_url', '').strip()
            plex_token = self.config.get('plex_token', '').strip()
            
            if not plex_url or not plex_token:
                logging.error("Plex URL or token not configured")
                return movies, tv_shows
            
            # Ensure URL has protocol
            if not plex_url.startswith(('http://', 'https://')):
                plex_url = 'http://' + plex_url
            
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            start_timestamp = int(start_date.timestamp())
            
            # Get recently added content
            url = urljoin(plex_url, '/library/recentlyAdded')
            headers = {'X-Plex-Token': plex_token}
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
    
    def get_plex_all_content(self):
        """Get all movies and TV shows from Plex library"""
        movies = []
        tv_shows = []
        
        try:
            plex_url = self.config.get('plex_url', '').strip()
            plex_token = self.config.get('plex_token', '').strip()
            
            if not plex_url or not plex_token:
                logging.error("Plex URL or token not configured")
                return movies, tv_shows
            
            # Ensure URL has protocol
            if not plex_url.startswith(('http://', 'https://')):
                plex_url = 'http://' + plex_url
            
            # Get all libraries
            url = urljoin(plex_url, '/library/sections')
            headers = {'X-Plex-Token': plex_token}
            
            response = self.session.get(url, headers=headers)
            response.raise_for_status()
            
            # Parse XML response (Plex returns XML)
            import xml.etree.ElementTree as ET
            root = ET.fromstring(response.content)
            
            # Helper function to get full artwork URL
            def get_artwork_url(thumb_path):
                if not thumb_path:
                    return None
                if thumb_path.startswith('http'):
                    return thumb_path
                return urljoin(plex_url, f'{thumb_path}?X-Plex-Token={plex_token}')
            
            # Iterate through each library section
            for section in root.findall('.//Directory'):
                section_type = section.get('type')
                section_key = section.get('key')
                section_title = section.get('title', 'Unknown')
                
                if section_type == 'movie':
                    # Get all movies from this section
                    section_url = urljoin(plex_url, f'/library/sections/{section_key}/all')
                    section_response = self.session.get(section_url, headers=headers)
                    section_response.raise_for_status()
                    
                    section_root = ET.fromstring(section_response.content)
                    for item in section_root.findall('.//Video'):
                        thumb = item.get('thumb', '')
                        art = item.get('art', '')
                        
                        content_item = {
                            'title': item.get('title', 'Unknown'),
                            'year': item.get('year', 'Unknown'),
                            'rating': item.get('rating', 'Not Rated'),
                            'duration': int(item.get('duration', 0)) if item.get('duration') else 0,
                            'duration_formatted': self._format_duration(int(item.get('duration', 0)) if item.get('duration') else 0),
                            'summary': item.get('summary', ''),
                            'added_date': datetime.fromtimestamp(int(item.get('addedAt', 0))).strftime('%Y-%m-%d') if item.get('addedAt') else 'Unknown',
                            'studio': item.get('studio', ''),
                            'content_rating': item.get('contentRating', ''),
                            'thumb': get_artwork_url(thumb),
                            'art': get_artwork_url(art),
                            'genres': [genre.get('tag', '') for genre in item.findall('.//Genre')],
                            'plex_key': item.get('key', ''),
                            'guid': item.get('guid', ''),
                            'director': [director.get('tag', '') for director in item.findall('.//Director')],
                            'writers': [writer.get('tag', '') for writer in item.findall('.//Writer')],
                            'actors': [{'name': actor.get('tag', ''), 'role': actor.get('role', '')} for actor in item.findall('.//Role')[:10]],
                            'country': [country.get('tag', '') for country in item.findall('.//Country')],
                            'tagline': item.get('tagline', ''),
                            'originally_available_at': item.get('originallyAvailableAt', '')
                        }
                        movies.append(content_item)
                
                elif section_type == 'show':
                    # For TV shows, we need to use the correct endpoint
                    section_url = urljoin(plex_url, f'/library/sections/{section_key}/all')
                    section_response = self.session.get(section_url, headers=headers)
                    section_response.raise_for_status()
                    
                    section_root = ET.fromstring(section_response.content)
                    for show in section_root.findall('.//Directory'):
                        # Get the show's rating key for detailed info
                        rating_key = show.get('ratingKey')
                        if rating_key:
                            # Get detailed show info using the rating key
                            show_url = urljoin(plex_url, f'/library/metadata/{rating_key}')
                            show_response = self.session.get(show_url, headers=headers)
                            show_response.raise_for_status()
                            
                            show_root = ET.fromstring(show_response.content)
                            show_item = show_root.find('.//Directory')
                            
                            if show_item is not None:
                                thumb = show_item.get('thumb', '')
                                art = show_item.get('art', '')
                                
                                # Get season count
                                seasons_url = urljoin(plex_url, f'/library/metadata/{rating_key}/children')
                                seasons_response = self.session.get(seasons_url, headers=headers)
                                seasons_response.raise_for_status()
                                seasons_root = ET.fromstring(seasons_response.content)
                                season_count = len(seasons_root.findall('.//Directory'))
                                
                                # Get episode count
                                episodes_url = urljoin(plex_url, f'/library/metadata/{rating_key}/allLeaves')
                                episodes_response = self.session.get(episodes_url, headers=headers)
                                episodes_response.raise_for_status()
                                episodes_root = ET.fromstring(episodes_response.content)
                                episode_count = len(episodes_root.findall('.//Video'))
                                
                                content_item = {
                                    'title': show_item.get('title', 'Unknown'),
                                    'year': show_item.get('year', 'Unknown'),
                                    'rating': show_item.get('rating', 'Not Rated'),
                                    'summary': show_item.get('summary', ''),
                                    'added_date': datetime.fromtimestamp(int(show_item.get('addedAt', 0))).strftime('%Y-%m-%d') if show_item.get('addedAt') else 'Unknown',
                                    'studio': show_item.get('studio', ''),
                                    'content_rating': show_item.get('contentRating', ''),
                                    'thumb': get_artwork_url(thumb),
                                    'art': get_artwork_url(art),
                                    'genres': [genre.get('tag', '') for genre in show_item.findall('.//Genre')],
                                    'plex_key': show_item.get('key', ''),
                                    'guid': show_item.get('guid', ''),
                                    'episode_count': episode_count,
                                    'season_count': season_count,
                                    'originally_available_at': show_item.get('originallyAvailableAt', ''),
                                    'network': show_item.get('network', ''),
                                    'status': show_item.get('status', '')
                                }
                                tv_shows.append(content_item)
            
        except Exception as e:
            logging.error(f"Error getting all Plex content: {str(e)}")
            logging.exception("Full traceback:")
        
        return movies, tv_shows
    
    def get_sonarr_calendar_extended(self, days=7):
        """Get TV shows from Sonarr calendar for the next N days with extended metadata"""
        scheduled_shows = []
        
        try:
            sonarr_url = self.config.get('sonarr_url', '').strip()
            sonarr_api_key = self.config.get('sonarr_api_key', '').strip()
            
            if not sonarr_url or not sonarr_api_key:
                logging.error("Sonarr URL or API key not configured")
                return scheduled_shows
            
            # Ensure URL has protocol
            if not sonarr_url.startswith(('http://', 'https://')):
                sonarr_url = 'http://' + sonarr_url
            
            # Get date range
            start_date = datetime.now().strftime('%Y-%m-%d')
            end_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
            
            # Get calendar data
            url = urljoin(sonarr_url, '/api/v3/calendar')
            headers = {'X-Api-Key': sonarr_api_key}
            params = {'start': start_date, 'end': end_date}
            
            response = self.session.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            episodes = response.json()
            
            # Get series data for additional metadata
            series_url = urljoin(sonarr_url, '/api/v3/series')
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
        """Get comprehensive Plex library statistics (reuse logic from get_plex_all_content)"""
        stats = {
            'libraries': [],
            'total_movies': 0,
            'total_shows': 0,
            'total_episodes': 0,
            'total_music': 0
        }
        
        try:
            plex_url = self.config.get('plex_url', '').strip()
            plex_token = self.config.get('plex_token', '').strip()
            
            if not plex_url or not plex_token:
                logging.error("Plex URL or token not configured")
                return stats
            
            # Ensure URL has protocol
            if not plex_url.startswith(('http://', 'https://')):
                plex_url = 'http://' + plex_url
            
            # Get all libraries
            url = urljoin(plex_url, '/library/sections')
            headers = {'X-Plex-Token': plex_token}
            
            response = self.session.get(url, headers=headers)
            response.raise_for_status()
            
            import xml.etree.ElementTree as ET
            root = ET.fromstring(response.content)
            
            for section in root.findall('.//Directory'):
                section_type = section.get('type')
                section_key = section.get('key')
                section_title = section.get('title', 'Unknown')
                library_info = {
                    'key': section_key,
                    'title': section_title,
                    'type': section_type,
                    'count': 0
                }
                if section_type == 'movie':
                    section_url = urljoin(plex_url, f'/library/sections/{section_key}/all')
                    section_response = self.session.get(section_url, headers=headers)
                    section_response.raise_for_status()
                    section_root = ET.fromstring(section_response.content)
                    count = len(section_root.findall('.//Video'))
                    stats['total_movies'] += count
                    library_info['count'] = count
                elif section_type == 'show':
                    section_url = urljoin(plex_url, f'/library/sections/{section_key}/all')
                    section_response = self.session.get(section_url, headers=headers)
                    section_response.raise_for_status()
                    section_root = ET.fromstring(section_response.content)
                    shows = [d for d in section_root.findall('.//Directory') if d.get('type') == 'show']
                    count = len(shows)
                    stats['total_shows'] += count
                    library_info['count'] = count
                    # Count episodes for each show
                    for show in shows:
                        show_key = show.get('ratingKey')
                        if show_key:
                            episodes_url = urljoin(plex_url, f'/library/metadata/{show_key}/allLeaves')
                            episodes_response = self.session.get(episodes_url, headers=headers)
                            episodes_response.raise_for_status()
                            episodes_root = ET.fromstring(episodes_response.content)
                            episode_count = len(episodes_root.findall('.//Video'))
                            stats['total_episodes'] += episode_count
                elif section_type == 'artist':
                    section_url = urljoin(plex_url, f'/library/sections/{section_key}/all')
                    section_response = self.session.get(section_url, headers=headers)
                    section_response.raise_for_status()
                    section_root = ET.fromstring(section_response.content)
                    count = len(section_root.findall('.//Directory'))
                    stats['total_music'] += count
                    library_info['count'] = count
                else:
                    library_info['count'] = 0
                stats['libraries'].append(library_info)
            return stats
        except Exception as e:
            logging.error(f"Error getting Plex library stats: {str(e)}")
            logging.exception("Full traceback:")
            return stats

    def run_daily_sync(self):
        """Run the complete daily sync process"""
        try:
            logging.info("Starting daily sync...")
            
            # Get data from APIs with error handling
            try:
                movies, tv_shows = self.get_plex_recent_content()
            except Exception as e:
                logging.warning(f"Plex data retrieval failed: {str(e)}")
                movies, tv_shows = [], []
            
            try:
                scheduled_shows = self.get_sonarr_today_schedule()
            except Exception as e:
                logging.warning(f"Sonarr data retrieval failed: {str(e)}")
                scheduled_shows = []
            
            # Debug logging
            logging.info(f"Daily sync found: {len(movies)} movies, {len(tv_shows)} TV shows, {len(scheduled_shows)} scheduled shows")
            if scheduled_shows:
                logging.info(f"Scheduled shows data: {scheduled_shows}")
            
            # Always write to files locally first
            file_success = self.write_to_files(movies, tv_shows, scheduled_shows)
            
            result = {
                'success': file_success,
                'movies_count': len(movies),
                'shows_count': len(tv_shows),
                'scheduled_count': len(scheduled_shows),
                'files_written': file_success
            }
            
            # Try to upload to GitHub if enabled and configured
            if file_success and self.config.get('github_enabled', False):
                try:
                    # Get the file paths that were written
                    output_dir = self.config.get('output_directory', './output')
                    file_paths = []
                    
                    # Add files based on what was written
                    if len(movies) > 0:
                        file_paths.append(f"{output_dir}/movies_today.txt")
                    if len(tv_shows) > 0:
                        file_paths.append(f"{output_dir}/tv_shows_today.txt")
                    if len(scheduled_shows) > 0:
                        file_paths.append(f"{output_dir}/tv_schedule_today.txt")
                    
                    if file_paths and self.upload_to_github(file_paths):
                        result['github_uploaded'] = True
                        logging.info("Files uploaded to GitHub successfully")
                    else:
                        result['github_uploaded'] = False
                        logging.warning("GitHub upload failed, but files saved locally")
                except Exception as e:
                    result['github_uploaded'] = False
                    logging.warning(f"GitHub upload failed: {str(e)}, but files saved locally")
            else:
                result['github_uploaded'] = False
            
            if file_success:
                logging.info("Daily sync completed successfully")
                return result
            else:
                return {'success': False, 'error': 'Failed to write output files'}
                
        except Exception as e:
            logging.error(f"Daily sync failed: {str(e)}")
            return {'success': False, 'error': str(e)}

    def get_dashboard_content(self, dashboard_config=None):
        """Get movies and TV shows for the dashboard with configurable date range"""
        movies = []
        tv_shows = []
        
        try:
            # Use provided dashboard config or fall back to main config
            config = dashboard_config or self.config
            plex_url = config.get('plex_url', '').strip()
            plex_token = config.get('plex_token', '').strip()
            
            if not plex_url or not plex_token:
                logging.error("Plex URL or token not configured")
                return movies, tv_shows
            
            # Ensure URL has protocol
            if not plex_url.startswith(('http://', 'https://')):
                plex_url = 'http://' + plex_url
            
            # Get date range from config
            days = config.get('dashboard_days', 3650)  # Default to showing all content
            max_items = config.get('dashboard_max_items', 100)  # Default to 100 items
            
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            start_timestamp = int(start_date.timestamp())
            
            # Get recently added content
            url = urljoin(plex_url, '/library/recentlyAdded')
            headers = {'X-Plex-Token': plex_token}
            params = {
                'X-Plex-Container-Start': '0',
                'X-Plex-Container-Size': str(max_items)
            }
            
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
                            'duration_formatted': self._format_duration(item.get('duration', 0)),
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
            logging.error(f"Error getting dashboard content: {str(e)}")
        
        return movies, tv_shows

    def _format_duration(self, duration_ms):
        """Format duration in milliseconds to human-readable format"""
        if not duration_ms:
            return 'Unknown'
        
        seconds = duration_ms // 1000
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
