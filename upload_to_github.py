#!/usr/bin/env python3
"""
Upload media tracker files to GitHub repository using GitHub API
"""
import os
import base64
import json
import requests

def upload_file_to_github(file_path, repo_owner, repo_name, github_token):
    """Upload a single file to GitHub repository"""
    
    # Read file content
    with open(file_path, 'rb') as f:
        content = f.read()
    
    # Encode content as base64
    encoded_content = base64.b64encode(content).decode('utf-8')
    
    # GitHub API URL
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"
    
    # Headers
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    # Check if file exists to get SHA
    response = requests.get(url, headers=headers)
    sha = None
    if response.status_code == 200:
        sha = response.json()['sha']
    
    # Prepare data
    data = {
        'message': f'Update {file_path}',
        'content': encoded_content,
        'branch': 'main'
    }
    
    if sha:
        data['sha'] = sha
    
    # Upload file
    response = requests.put(url, headers=headers, json=data)
    
    if response.status_code in [200, 201]:
        print(f"✓ Uploaded {file_path}")
        return True
    else:
        print(f"✗ Failed to upload {file_path}: {response.status_code}")
        print(response.json())
        return False

def main():
    github_token = os.environ.get('GITHUB_TOKEN')
    if not github_token:
        print("Error: GITHUB_TOKEN environment variable not set")
        return False
    
    repo_owner = 'davidsnyder-nc'
    repo_name = 'mediainfo'
    
    # Files to upload (excluding personal config files)
    files_to_upload = [
        'app.py',
        'config.py', 
        'media_tracker.py',
        'main.py',
        'run_daily.py',
        'pyproject.toml',
        'uv.lock',
        '.gitignore',
        'README.md',
        'templates/index.html',
        'templates/plex_auth.html'
    ]
    
    success_count = 0
    total_files = len(files_to_upload)
    
    print(f"Uploading {total_files} files to {repo_owner}/{repo_name}...")
    
    for file_path in files_to_upload:
        if os.path.exists(file_path):
            if upload_file_to_github(file_path, repo_owner, repo_name, github_token):
                success_count += 1
        else:
            print(f"✗ File not found: {file_path}")
    
    print(f"\nUpload complete: {success_count}/{total_files} files uploaded successfully")
    
    if success_count == total_files:
        print("🎉 All files uploaded successfully to GitHub!")
        return True
    else:
        print("⚠️  Some files failed to upload")
        return False

if __name__ == '__main__':
    main()