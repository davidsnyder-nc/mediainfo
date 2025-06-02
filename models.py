import json
import os
import secrets
import string
from datetime import datetime
from functools import wraps
from flask import request, jsonify


class APIKeyManager:
    """Simple file-based API key management"""
    
    def __init__(self, keys_file='api_keys.json'):
        self.keys_file = keys_file
        self.keys = self._load_keys()
    
    def _load_keys(self):
        """Load API keys from file"""
        if os.path.exists(self.keys_file):
            try:
                with open(self.keys_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def _save_keys(self):
        """Save API keys to file"""
        with open(self.keys_file, 'w') as f:
            json.dump(self.keys, f, indent=2, default=str)
    
    @staticmethod
    def generate_key():
        """Generate a secure API key"""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(32))
    
    def create_key(self, name):
        """Create a new API key"""
        key = self.generate_key()
        self.keys[key] = {
            'name': name,
            'is_active': True,
            'created_at': datetime.now().isoformat(),
            'last_used': None,
            'usage_count': 0
        }
        self._save_keys()
        return key
    
    def validate_key(self, key):
        """Validate an API key and update usage stats"""
        if key in self.keys and self.keys[key]['is_active']:
            self.keys[key]['last_used'] = datetime.now().isoformat()
            self.keys[key]['usage_count'] += 1
            self._save_keys()
            return True
        return False
    
    def deactivate_key(self, key):
        """Deactivate an API key"""
        if key in self.keys:
            self.keys[key]['is_active'] = False
            self._save_keys()
            return True
        return False
    
    def list_keys(self):
        """List all API keys with their details"""
        return [
            {
                'key': key,
                'name': data['name'],
                'is_active': data['is_active'],
                'created_at': data['created_at'],
                'last_used': data['last_used'],
                'usage_count': data['usage_count']
            }
            for key, data in self.keys.items()
        ]


# Global API key manager instance
api_key_manager = APIKeyManager()


def require_api_key(f):
    """Decorator to require API key for API endpoints"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get API key from header or query parameter
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        
        if not api_key:
            return jsonify({
                'error': 'API key required',
                'message': 'Provide API key in X-API-Key header or api_key parameter'
            }), 401
        
        if not api_key_manager.validate_key(api_key):
            return jsonify({
                'error': 'Invalid API key',
                'message': 'The provided API key is invalid or inactive'
            }), 403
        
        return f(*args, **kwargs)
    
    return decorated_function