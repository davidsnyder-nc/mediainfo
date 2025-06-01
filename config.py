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
            'output_directory': './output'
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
