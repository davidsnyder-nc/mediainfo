import json
import os
import logging

class ConfigManager:
    """Manages configuration settings for the media tracker"""
    
    def __init__(self, config_file='config.json'):
        self.config_file = config_file
        self.default_config = {
            'plex_url': '',
            'plex_token': '',
            'sonarr_url': '',
            'sonarr_api_key': '',
            'output_directory': './output',
            'github_enabled': False,
            'github_repo': '',
            'github_token': '',
            'github_branch': 'main',
            'output_format': {
                'movie_format': 'Title: {title}\nYear: {year}\nAdded: {added_date}\n{separator}',
                'tv_format': 'Title: {title}\nYear: {year}\nAdded: {added_date}\n{separator}',
                'schedule_format': 'Series: {series_title}\nEpisode: S{season:02d}E{episode:02d} - {episode_title}\nAir Date: {air_date}\n{separator}',
                'include_timestamps': True,
                'include_descriptions': False,
                'file_naming': 'date_suffix',
                'single_output_file': 'media_tracker.txt'
            }
        }
    
    def get_config(self):
        """Load configuration from file or return defaults"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                # Merge with defaults to ensure all keys exist
                merged_config = self.default_config.copy()
                merged_config.update(config)
                return merged_config
            else:
                return self.default_config.copy()
        except Exception as e:
            logging.error(f"Error loading config: {str(e)}")
            return self.default_config.copy()
    
    def save_config(self, config_data):
        """Save configuration to file"""
        try:
            # Ensure output directory exists
            output_dir = config_data.get('output_directory', './output')
            os.makedirs(output_dir, exist_ok=True)
            
            with open(self.config_file, 'w') as f:
                json.dump(config_data, f, indent=2)
            logging.info("Configuration saved successfully")
        except Exception as e:
            logging.error(f"Error saving config: {str(e)}")
            raise
