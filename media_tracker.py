import requests
import json
import os
import logging
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
                
                if library_type in ['movie', 'show']:
                    # Get recently added items from this library
                    recent_url = urljoin(self.config['plex_url'], f'/library/sections/{library_key}/recentlyAdded')
                    recent_response = self.session.get(recent_url, headers=headers)
                    recent_response.raise_for_status()
                    
                    recent_root = ET.fromstring(recent_response.content)
                    
                    for item in recent_root.findall('.//Video'):
                        added_at = item.get('addedAt')
                        if added_at:
                            added_date = datetime.fromtimestamp(int(added_at)).date()
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
        
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
            
            url = urljoin(self.config['sonarr_url'], f'/api/v3/calendar?start={today}&end={tomorrow}')
            headers = {'X-Api-Key': self.config['sonarr_api_key']}
            
            response = self.session.get(url, headers=headers)
            response.raise_for_status()
            
            calendar_data = response.json()
            
            for episode in calendar_data:
                air_date = episode.get('airDate', '')
                if air_date == today:
                    scheduled_shows.append({
                        'series_title': episode.get('series', {}).get('title', 'Unknown Series'),
                        'episode_title': episode.get('title', 'Unknown Episode'),
                        'season': episode.get('seasonNumber', 'Unknown'),
                        'episode': episode.get('episodeNumber', 'Unknown'),
                        'air_date': air_date
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
            
            # Determine file names
            if file_naming == 'date_prefix':
                movies_file = os.path.join(output_dir, f'{today_str}_plex_movies.txt')
                tv_file = os.path.join(output_dir, f'{today_str}_plex_tv_shows.txt')
                schedule_file = os.path.join(output_dir, f'{today_str}_sonarr_schedule.txt')
            else:  # date_suffix (default)
                movies_file = os.path.join(output_dir, f'plex_movies_{today_str}.txt')
                tv_file = os.path.join(output_dir, f'plex_tv_shows_{today_str}.txt')
                schedule_file = os.path.join(output_dir, f'sonarr_schedule_{today_str}.txt')
            
            # Write movies file
            with open(movies_file, 'w') as f:
                header = f"Plex Movies Added - {today_str}"
                if timestamp:
                    header += f" (Generated: {timestamp})"
                f.write(header + "\n")
                f.write("=" * len(header) + "\n\n")
                
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
                    f.write("No movies added today.\n")
            
            # Write TV shows file
            with open(tv_file, 'w') as f:
                header = f"Plex TV Shows Added - {today_str}"
                if timestamp:
                    header += f" (Generated: {timestamp})"
                f.write(header + "\n")
                f.write("=" * len(header) + "\n\n")
                
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
                    f.write("No TV shows added today.\n")
            
            # Write scheduled shows file
            with open(schedule_file, 'w') as f:
                header = f"Sonarr TV Schedule - {today_str}"
                if timestamp:
                    header += f" (Generated: {timestamp})"
                f.write(header + "\n")
                f.write("=" * len(header) + "\n\n")
                
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
                    f.write("No shows scheduled for today.\n")
            
            logging.info(f"Files written successfully to {output_dir}")
            return True
            
        except Exception as e:
            logging.error(f"Error writing files: {str(e)}")
            return False
    
    def run_daily_sync(self):
        """Run the complete daily sync process"""
        try:
            logging.info("Starting daily sync...")
            
            # Test connections first
            if not self.test_plex_connection():
                return {'success': False, 'error': 'Plex connection failed'}
            
            if not self.test_sonarr_connection():
                return {'success': False, 'error': 'Sonarr connection failed'}
            
            # Get data from APIs
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
