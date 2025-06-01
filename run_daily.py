#!/usr/bin/env python3
"""
Daily media tracker script for cron job execution.
This script runs the daily sync without starting the web server.
"""

import sys
import logging
from config import ConfigManager
from media_tracker import MediaTracker

def main():
    """Main function for daily sync execution"""
    # Configure logging for cron job
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('media_tracker.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    try:
        # Load configuration
        config_manager = ConfigManager()
        config = config_manager.get_config()
        
        # Validate configuration
        required_fields = ['plex_url', 'plex_token', 'sonarr_url', 'sonarr_api_key']
        missing_fields = [field for field in required_fields if not config.get(field)]
        
        if missing_fields:
            logging.error(f"Missing configuration fields: {', '.join(missing_fields)}")
            logging.error("Please configure the application using the web interface first.")
            sys.exit(1)
        
        # Initialize tracker and run sync
        tracker = MediaTracker(config)
        results = tracker.run_daily_sync()
        
        if results['success']:
            logging.info(f"Daily sync completed successfully!")
            logging.info(f"Movies found: {results.get('movies_count', 0)}")
            logging.info(f"TV shows found: {results.get('shows_count', 0)}")
            logging.info(f"Scheduled shows: {results.get('scheduled_count', 0)}")
            sys.exit(0)
        else:
            logging.error(f"Daily sync failed: {results['error']}")
            sys.exit(1)
            
    except Exception as e:
        logging.error(f"Unexpected error during daily sync: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()
