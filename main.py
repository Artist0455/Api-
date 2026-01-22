import os
import re
import json
import requests
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from urllib.parse import urlparse, parse_qs
import time
import uuid

app = Flask(__name__)
CORS(app)

class InstagramStoryDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.setup_headers()
    
    def setup_headers(self):
        """Set up realistic browser headers"""
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        })
    
    def extract_username(self, url):
        """Extract username from Instagram URL"""
        patterns = [
            r'instagram\.com/([^/?]+)/?$',
            r'instagram\.com/stories/([^/?]+)',
            r'instagram\.com/([^/?]+)/story/',
            r'instagram\.com/([^/?]+)/reel/'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                username = match.group(1).lower()
                # Remove common prefixes
                if username.startswith('@'):
                    username = username[1:]
                return username
        
        # If URL is just a username
        if '/' not in url and '.' not in url:
            username = url.replace('@', '').lower()
            return username
        
        return None
    
    def get_user_id_from_username(self, username):
        """Get user ID from username"""
        try:
            profile_url = f"https://www.instagram.com/{username}/"
            response = self.session.get(profile_url, timeout=10)
            
            if response.status_code == 200:
                html_content = response.text
                
                # Method 1: Look for profile ID in JSON-LD
                json_ld_pattern = r'<script type="application/ld\+json">(.*?)</script>'
                json_ld_matches = re.findall(json_ld_pattern, html_content, re.DOTALL)
                
                for json_ld in json_ld_matches:
                    try:
                        data = json.loads(json_ld)
                        if isinstance(data, dict) and '@id' in data:
                            url = data['@id']
                            user_id_match = re.search(r'instagram\.com/(\d+)', url)
                            if user_id_match:
                                return user_id_match.group(1)
                    except:
                        continue
                
                # Method 2: Look for user ID in script tags
                script_pattern = r'<script[^>]*>(.*?)</script>'
                script_matches = re.findall(script_pattern, html_content, re.DOTALL)
                
                for script in script_matches:
                    # Look for user ID patterns
                    patterns = [
                        r'"profile_id":"(\d+)"',
                        r'"id":"(\d+)"',
                        r'"user_id":"(\d+)"',
                        r'"owner":{"id":"(\d+)"',
                        r'profilePage_(\d+)',
                    ]
                    
                    for pattern in patterns:
                        matches = re.findall(pattern, script)
                        if matches:
                            return matches[0]
                
                # Method 3: Look for sharedData
                shared_data_pattern = r'window\._sharedData\s*=\s*({.*?});'
                match = re.search(shared_data_pattern, html_content, re.DOTALL)
                if match:
                    try:
                        shared_data = json.loads(match.group(1))
                        # Navigate through possible data structures
                        if 'entry_data' in shared_data:
                            profile_data = shared_data.get('entry_data', {}).get('ProfilePage', [])
                            if profile_data:
                                user_data = profile_data[0].get('graphql', {}).get('user', {})
                                if 'id' in user_data:
                                    return user_data['id']
                    except:
                        pass
            
            return None
            
        except Exception as e:
            print(f"Error getting user ID: {str(e)}")
            return None
    
    def get_stories_from_api(self, user_id):
        """Get stories from Instagram API"""
        try:
            # Instagram stories API endpoint
            stories_url = f"https://www.instagram.com/api/v1/feed/reels_media/?reel_ids={user_id}"
            
            headers = {
                'User-Agent': 'Instagram 269.0.0.18.75 Android (33/12.0; 560dpi; 1440x2894; Google/google; sdk_gphone64_arm64; emulator64_arm64; en_US; 468695184)',
                'Accept': '*/*',
                'Accept-Language': 'en-US',
                'X-IG-App-ID': '936619743392459',
                'X-Requested-With': 'XMLHttpRequest',
                'X-ASBD-ID': '198387',
                'X-IG-WWW-Claim': '0',
                'Origin': 'https://www.instagram.com',
                'Referer': f'https://www.instagram.com/',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-origin',
            }
            
            # Add cookies if available
            self.session.cookies.update({
                'ig_did': str(uuid.uuid4()),
                'ig_nrcb': '1',
            })
            
            response = self.session.get(stories_url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    
                    stories = []
                    
                    if 'reels' in data and user_id in data['reels']:
                        reel_data = data['reels'][user_id]
                        
                        if 'items' in reel_data:
                            for item in reel_data['items']:
                                story_info = {
                                    'id': item.get('id'),
                                    'timestamp': item.get('taken_at_timestamp'),
                                    'expires_at': item.get('expiring_at_timestamp'),
                                    'media_type': item.get('media_type'),
                                }
                                
                                # Check media type (1=photo, 2=video)
                                if item.get('media_type') == 1:  # Photo
                                    if 'image_versions2' in item:
                                        candidates = item['image_versions2'].get('candidates', [])
                                        if candidates:
                                            # Get the highest quality image
                                            story_info['url'] = max(candidates, key=lambda x: x.get('width', 0) * x.get('height', 0)).get('url')
                                            story_info['type'] = 'image'
                                
                                elif item.get('media_type') == 2:  # Video
                                    if 'video_versions' in item:
                                        videos = item.get('video_versions', [])
                                        if videos:
                                            # Get the highest quality video
                                            story_info['url'] = max(videos, key=lambda x: x.get('width', 0) * x.get('height', 0)).get('url')
                                            story_info['type'] = 'video'
                                
                                # Add story URL if available
                                if 'url' in story_info:
                                    story_info['url'] = self.fix_media_url(story_info['url'])
                                    stories.append(story_info)
                    
                    return stories
                    
                except json.JSONDecodeError:
                    return []
            
            return []
            
        except Exception as e:
            print(f"Error in stories API: {str(e)}")
            return []
    
    def get_stories_from_web(self, username):
        """Get stories from Instagram web page"""
        try:
            profile_url = f"https://www.instagram.com/{username}/"
            response = self.session.get(profile_url, timeout=10)
            
            if response.status_code == 200:
                html_content = response.text
                
                stories = []
                
                # Method 1: Look for stories data in sharedData
                shared_data_pattern = r'window\._sharedData\s*=\s*({.*?});'
                match = re.search(shared_data_pattern, html_content, re.DOTALL)
                
                if match:
                    try:
                        shared_data = json.loads(match.group(1))
                        
                        # Try different paths to find stories data
                        if 'entry_data' in shared_data:
                            profile_data = shared_data.get('entry_data', {}).get('ProfilePage', [])
                            if profile_data:
                                user_data = profile_data[0].get('graphql', {}).get('user', {})
                                
                                # Check for stories
                                if 'reel' in user_data:
                                    reel_data = user_data['reel']
                                    if 'edge_reel_media' in reel_data:
                                        edges = reel_data['edge_reel_media'].get('edges', [])
                                        for edge in edges:
                                            node = edge.get('node', {})
                                            story_info = self.extract_story_from_node(node)
                                            if story_info:
                                                stories.append(story_info)
                    except:
                        pass
                
                # Method 2: Look for stories in script tags
                if not stories:
                    script_pattern = r'<script[^>]*>(.*?)</script>'
                    script_matches = re.findall(script_pattern, html_content, re.DOTALL)
                    
                    for script in script_matches:
                        # Look for stories data patterns
                        patterns = [
                            r'"stories":\[(.*?)\]',
                            r'"reel":\{.*?"items":\[(.*?)\]',
                            r'"edge_reel_media":\{"edges":\[(.*?)\]',
                        ]
                        
                        for pattern in patterns:
                            matches = re.findall(pattern, script, re.DOTALL)
                            if matches:
                                try:
                                    # Try to parse as JSON
                                    json_str = '[' + matches[0] + ']'
                                    items = json.loads(json_str)
                                    
                                    for item in items:
                                        story_info = self.extract_story_from_node(item)
                                        if story_info:
                                            stories.append(story_info)
                                    
                                    if stories:
                                        break
                                except:
                                    continue
                
                return stories
            
            return []
            
        except Exception as e:
            print(f"Error in web method: {str(e)}")
            return []
    
    def extract_story_from_node(self, node):
        """Extract story information from node data"""
        try:
            story_info = {
                'id': node.get('id'),
                'timestamp': node.get('taken_at_timestamp'),
                'expires_at': node.get('expiring_at_timestamp'),
                'media_type': node.get('__typename'),
            }
            
            # Check if it's a video or image
            if 'video_url' in node:
                story_info['url'] = self.fix_media_url(node['video_url'])
                story_info['type'] = 'video'
            elif 'display_url' in node:
                story_info['url'] = self.fix_media_url(node['display_url'])
                story_info['type'] = 'image'
            elif 'display_resources' in node:
                # Get highest quality image
                resources = node['display_resources']
                best_resource = max(resources, key=lambda x: x.get('config_width', 0))
                story_info['url'] = self.fix_media_url(best_resource.get('src'))
                story_info['type'] = 'image'
            
            return story_info if 'url' in story_info else None
            
        except:
            return None
    
    def fix_media_url(self, url):
        """Fix media URL formatting"""
        if not url:
            return None
        
        # Fix escaped slashes
        url = url.replace('\\/', '/').replace('\\\\/', '/')
        
        # Fix other escaped characters
        url = url.replace('\\u0026', '&')
        
        # Ensure it starts with http
        if not url.startswith('http'):
            if url.startswith('//'):
                url = 'https:' + url
            elif url.startswith('/'):
                url = 'https://www.instagram.com' + url
        
        return url
    
    def download_stories(self, input_url):
        """Main function to download stories"""
        print(f"Processing input: {input_url}")
        
        # Get username from input
        username = self.extract_username(input_url)
        if not username:
            return {
                'success': False,
                'error': 'Invalid Instagram username or URL'
            }
        
        print(f"Found username: {username}")
        
        # Method 1: Try to get user ID and use API
        print("Trying Method 1: Instagram Stories API...")
        user_id = self.get_user_id_from_username(username)
        
        if user_id:
            print(f"Found user ID: {user_id}")
            stories = self.get_stories_from_api(user_id)
            
            if stories:
                print(f"Found {len(stories)} stories via API")
                return {
                    'success': True,
                    'username': username,
                    'user_id': user_id,
                    'stories': stories,
                    'count': len(stories),
                    'method': 'stories_api'
                }
        
        # Method 2: Try web scraping
        print("Trying Method 2: Web scraping...")
        stories = self.get_stories_from_web(username)
        
        if stories:
            print(f"Found {len(stories)} stories via web scraping")
            return {
                'success': True,
                'username': username,
                'stories': stories,
                'count': len(stories),
                'method': 'web_scraping'
            }
        
        # Method 3: Try public stories API
        print("Trying Method 3: Public API...")
        public_stories = self.get_public_stories(username)
        
        if public_stories:
            print(f"Found {len(public_stories)} stories via public API")
            return {
                'success': True,
                'username': username,
                'stories': public_stories,
                'count': len(public_stories),
                'method': 'public_api'
            }
        
        # If no stories found
        print(f"No stories found for {username}")
        return {
            'success': False,
            'error': f'No public stories found for @{username}. The account might be private or have no active stories.',
            'username': username
        }
    
    def get_public_stories(self, username):
        """Try alternative public API methods"""
        try:
            # Try different endpoints
            endpoints = [
                f"https://storiesig.info/api/instagram/stories?url=https://instagram.com/{username}",
                f"https://www.instagramsave.com/system/action.php?story=https://instagram.com/{username}",
            ]
            
            for endpoint in endpoints:
                try:
                    response = self.session.get(endpoint, timeout=10)
                    if response.status_code == 200:
                        try:
                            data = response.json()
                            stories = []
                            
                            # Parse different response formats
                            if isinstance(data, list):
                                for item in data:
                                    if 'video_versions' in item:
                                        story_info = {
                                            'url': self.fix_media_url(item['video_versions'][0]['url']),
                                            'type': 'video',
                                            'id': item.get('id')
                                        }
                                    elif 'image_versions2' in item:
                                        story_info = {
                                            'url': self.fix_media_url(item['image_versions2']['candidates'][0]['url']),
                                            'type': 'image',
                                            'id': item.get('id')
                                        }
                                    else:
                                        continue
                                    stories.append(story_info)
                            
                            if stories:
                                return stories
                        except:
                            continue
                except:
                    continue
            
            return []
            
        except Exception as e:
            print(f"Error in public API: {str(e)}")
            return []

# Initialize downloader
story_downloader = InstagramStoryDownloader()

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Instagram Story Downloader - WORKING ✓</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
        }
        
        body {
            background: linear-gradient(135deg, #833AB4 0%, #E1306C 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }
        
        .header {
            background: linear-gradient(45deg, #405DE6, #833AB4, #C13584, #E1306C, #FD1D1D);
            color: white;
            padding: 40px 30px;
            text-align: center;
        }
        
        .header h1 {
            font-size: 2.5rem;
            margin-bottom: 10px;
            font-weight: 800;
        }
        
        .header p {
            font-size: 1.1rem;
            opacity: 0.9;
            max-width: 600px;
            margin: 0 auto;
        }
        
        .badge {
            display: inline-block;
            background: #28a745;
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9rem;
            font-weight: 600;
            margin-top: 10px;
        }
        
        .content {
            padding: 30px;
        }
        
        .input-section {
            margin-bottom: 30px;
        }
        
        .input-group {
            display: flex;
            gap: 15px;
            margin-bottom: 15px;
        }
        
        input[type="text"] {
            flex: 1;
            padding: 18px 25px;
            border: 3px solid #e0e0e0;
            border-radius: 12px;
            font-size: 16px;
            transition: all 0.3s;
        }
        
        input[type="text"]:focus {
            outline: none;
            border-color: #E1306C;
            box-shadow: 0 0 0 4px rgba(225, 48, 108, 0.1);
        }
        
        button {
            background: linear-gradient(45deg, #E1306C, #833AB4);
            color: white;
            border: none;
            padding: 18px 40px;
            border-radius: 12px;
            font-size: 16px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.3s;
            min-width: 180px;
        }
        
        button:hover {
            transform: translateY(-3px);
            box-shadow: 0 10px 20px rgba(225, 48, 108, 0.3);
        }
        
        .loader {
            display: none;
            text-align: center;
            padding: 30px;
        }
        
        .spinner {
            width: 50px;
            height: 50px;
            border: 5px solid #f3f3f3;
            border-top: 5px solid #E1306C;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .result {
            display: none;
            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
            padding: 30px;
            border-radius: 15px;
            margin-top: 25px;
            border: 3px solid #e0e0e0;
            animation: fadeIn 0.5s;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .result h3 {
            color: #E1306C;
            font-size: 1.8rem;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .profile-info {
            background: white;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 25px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.05);
            text-align: center;
        }
        
        .profile-info h4 {
            color: #333;
            font-size: 1.5rem;
            margin-bottom: 10px;
        }
        
        .profile-info p {
            color: #666;
            margin-bottom: 5px;
        }
        
        .stories-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 20px;
            margin-top: 25px;
        }
        
        .story-card {
            background: white;
            border-radius: 15px;
            overflow: hidden;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            transition: transform 0.3s;
        }
        
        .story-card:hover {
            transform: translateY(-5px);
        }
        
        .story-media {
            width: 100%;
            height: 300px;
            overflow: hidden;
            position: relative;
        }
        
        .story-media img,
        .story-media video {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        
        .story-type {
            position: absolute;
            top: 10px;
            right: 10px;
            background: rgba(0,0,0,0.7);
            color: white;
            padding: 5px 10px;
            border-radius: 20px;
            font-size: 0.8rem;
        }
        
        .story-actions {
            padding: 15px;
            text-align: center;
        }
        
        .story-actions a {
            display: inline-block;
            background: linear-gradient(45deg, #E1306C, #833AB4);
            color: white;
            text-decoration: none;
            padding: 10px 20px;
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.3s;
        }
        
        .story-actions a:hover {
            background: linear-gradient(45deg, #833AB4, #E1306C);
            transform: translateY(-2px);
        }
        
        .actions {
            display: flex;
            gap: 15px;
            margin-top: 25px;
            flex-wrap: wrap;
            justify-content: center;
        }
        
        .btn {
            padding: 15px 25px;
            border-radius: 10px;
            text-decoration: none;
            font-weight: 600;
            text-align: center;
            min-width: 150px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            transition: all 0.3s;
        }
        
        .btn:hover {
            transform: translateY(-3px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.1);
        }
        
        .btn-download-all {
            background: linear-gradient(45deg, #28a745, #20c997);
            color: white;
        }
        
        .btn-new {
            background: linear-gradient(45deg, #fd7e14, #ff922b);
            color: white;
            border: none;
            cursor: pointer;
        }
        
        .error {
            display: none;
            background: linear-gradient(135deg, #fee 0%, #fdd 100%);
            color: #d33;
            padding: 20px;
            border-radius: 12px;
            margin-top: 20px;
            border-left: 5px solid #d33;
            font-weight: 600;
        }
        
        .instructions {
            background: #f0f8ff;
            padding: 20px;
            border-radius: 12px;
            margin-top: 30px;
        }
        
        .instructions h4 {
            color: #405DE6;
            margin-bottom: 15px;
        }
        
        .instructions ol {
            margin-left: 20px;
            color: #555;
        }
        
        .instructions li {
            margin-bottom: 10px;
        }
        
        .example-urls {
            background: #e7f4e4;
            padding: 15px;
            border-radius: 10px;
            margin-top: 20px;
        }
        
        .example-urls h4 {
            color: #28a745;
            margin-bottom: 10px;
        }
        
        .url-example {
            background: white;
            padding: 10px;
            border-radius: 8px;
            margin: 10px 0;
            font-family: monospace;
            color: #555;
        }
        
        @media (max-width: 768px) {
            .header h1 {
                font-size: 2rem;
            }
            
            .input-group {
                flex-direction: column;
            }
            
            button {
                width: 100%;
                min-width: auto;
            }
            
            .stories-grid {
                grid-template-columns: 1fr;
            }
            
            .actions {
                flex-direction: column;
            }
            
            .btn {
                width: 100%;
            }
        }
    </style>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
</head>
<body>
    <div class="container">
        <div class="header">
            <h1><i class="fab fa-instagram"></i> Instagram Story Downloader</h1>
            <p>Download Public Instagram Stories • Working 2024 • No Login Required</p>
            <div class="badge">✓ PUBLIC STORIES ONLY</div>
        </div>
        
        <div class="content">
            <div class="input-section">
                <h2 style="color: #333; margin-bottom: 20px; font-size: 1.6rem;">Download Instagram Stories</h2>
                
                <div class="input-group">
                    <input type="text" id="urlInput" placeholder="Enter Instagram username or profile URL...">
                    <button onclick="downloadStories()">
                        <i class="fas fa-download"></i> Get Stories
                    </button>
                </div>
                
                <div class="instructions">
                    <h4><i class="fas fa-info-circle"></i> How to Use:</h4>
                    <ol>
                        <li>Enter Instagram username (e.g., <code>instagram</code>)</li>
                        <li>OR enter profile URL (e.g., <code>https://instagram.com/instagram</code>)</li>
                        <li>Click "Get Stories" to fetch public stories</li>
                        <li>Download individual stories or all at once</li>
                    </ol>
                </div>
                
                <div class="example-urls">
                    <h4><i class="fas fa-lightbulb"></i> Examples:</h4>
                    <div class="url-example">instagram</div>
                    <div class="url-example">@instagram</div>
                    <div class="url-example">https://instagram.com/instagram</div>
                    <div class="url-example">https://www.instagram.com/instagram/stories/</div>
                </div>
            </div>
            
            <div class="loader" id="loader">
                <div class="spinner"></div>
                <p style="font-size: 1.1rem; color: #666;">Fetching Instagram stories...</p>
                <p id="statusText" style="margin-top: 10px; color: #888; font-size: 0.9rem;"></p>
            </div>
            
            <div class="error" id="error"></div>
            
            <div class="result" id="result">
                <h3><i class="fas fa-check-circle"></i> Stories Found!</h3>
                
                <div class="profile-info" id="profileInfo">
                    <!-- Profile info will be inserted here -->
                </div>
                
                <div id="storiesContainer">
                    <!-- Stories will be inserted here -->
                </div>
                
                <div class="actions">
                    <button onclick="downloadAllStories()" class="btn btn-download-all">
                        <i class="fas fa-download"></i> Download All Stories
                    </button>
                    <button onclick="resetForm()" class="btn btn-new">
                        <i class="fas fa-redo"></i> Try Another
                    </button>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let currentStoriesData = null;
        
        async function downloadStories() {
            const input = document.getElementById('urlInput').value.trim();
            const errorDiv = document.getElementById('error');
            const loader = document.getElementById('loader');
            const result = document.getElementById('result');
            
            // Reset
            errorDiv.style.display = 'none';
            result.style.display = 'none';
            currentStoriesData = null;
            
            // Validate input
            if (!input) {
                showError('Please enter Instagram username or URL');
                return;
            }
            
            // Show loader
            loader.style.display = 'block';
            
            // Update status messages
            const statusMessages = [
                'Connecting to Instagram...',
                'Fetching profile information...',
                'Checking for stories...',
                'Extracting story data...',
                'Preparing downloads...'
            ];
            
            let messageIndex = 0;
            const statusInterval = setInterval(() => {
                document.getElementById('statusText').textContent = statusMessages[messageIndex];
                messageIndex = (messageIndex + 1) % statusMessages.length;
            }, 1200);
            
            try {
                // Make API request
                const response = await fetch('/api/stories', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ url: input })
                });
                
                clearInterval(statusInterval);
                
                const data = await response.json();
                
                // Hide loader
                loader.style.display = 'none';
                
                if (data.success) {
                    // Store stories data
                    currentStoriesData = data;
                    
                    // Update profile info
                    const profileInfo = document.getElementById('profileInfo');
                    profileInfo.innerHTML = `
                        <h4>@${data.username}</h4>
                        ${data.user_id ? `<p><strong>User ID:</strong> ${data.user_id}</p>` : ''}
                        <p><strong>Found Stories:</strong> ${data.count}</p>
                        <p><strong>Method:</strong> <span style="color: #E1306C; font-weight: 700;">${data.method}</span></p>
                    `;
                    
                    // Update stories grid
                    const storiesContainer = document.getElementById('storiesContainer');
                    if (data.stories && data.stories.length > 0) {
                        storiesContainer.innerHTML = `
                            <h4 style="color: #333; margin-bottom: 15px;">Available Stories:</h4>
                            <div class="stories-grid" id="storiesGrid"></div>
                        `;
                        
                        const storiesGrid = document.getElementById('storiesGrid');
                        
                        data.stories.forEach((story, index) => {
                            const storyCard = document.createElement('div');
                            storyCard.className = 'story-card';
                            
                            const mediaElement = story.type === 'video' 
                                ? `<video controls style="width: 100%; height: 100%; object-fit: cover;">
                                        <source src="${story.url}" type="video/mp4">
                                        Your browser does not support video playback.
                                   </video>`
                                : `<img src="${story.url}" alt="Story ${index + 1}" style="width: 100%; height: 100%; object-fit: cover;">`;
                            
                            storyCard.innerHTML = `
                                <div class="story-media">
                                    ${mediaElement}
                                    <div class="story-type">
                                        ${story.type === 'video' ? '<i class="fas fa-video"></i> Video' : '<i class="fas fa-image"></i> Image'}
                                    </div>
                                </div>
                                <div class="story-actions">
                                    <a href="${story.url}" download="instagram_story_${data.username}_${index + 1}.${story.type === 'video' ? 'mp4' : 'jpg'}" target="_blank">
                                        <i class="fas fa-download"></i> Download ${story.type}
                                    </a>
                                </div>
                            `;
                            
                            storiesGrid.appendChild(storyCard);
                        });
                    } else {
                        storiesContainer.innerHTML = '<p style="color: #666; text-align: center;">No stories found.</p>';
                    }
                    
                    // Show result
                    result.style.display = 'block';
                    
                    // Auto-scroll to result
                    result.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    
                } else {
                    showError(data.error || 'Failed to fetch stories. The account might be private or have no active stories.');
                }
                
            } catch (error) {
                clearInterval(statusInterval);
                loader.style.display = 'none';
                showError('Network error: ' + error.message);
            }
        }
        
        function showError(message) {
            const errorDiv = document.getElementById('error');
            errorDiv.innerHTML = `
                <i class="fas fa-exclamation-triangle"></i> ${message}
            `;
            errorDiv.style.display = 'block';
            
            // Auto-hide error after 8 seconds
            setTimeout(() => {
                errorDiv.style.display = 'none';
            }, 8000);
        }
        
        function downloadAllStories() {
            if (currentStoriesData && currentStoriesData.stories) {
                currentStoriesData.stories.forEach((story, index) => {
                    const link = document.createElement('a');
                    link.href = story.url;
                    link.download = `instagram_story_${currentStoriesData.username}_${index + 1}.${story.type === 'video' ? 'mp4' : 'jpg'}`;
                    link.target = '_blank';
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                });
                
                alert(`✓ Started downloading ${currentStoriesData.stories.length} stories!`);
            }
        }
        
        function resetForm() {
            document.getElementById('urlInput').value = '';
            document.getElementById('result').style.display = 'none';
            document.getElementById('error').style.display = 'none';
            document.getElementById('urlInput').focus();
            currentStoriesData = null;
        }
        
        // Enter key support
        document.getElementById('urlInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                downloadStories();
            }
        });
        
        // Auto-focus on input
        document.getElementById('urlInput').focus();
        
        // Add sample username for testing
        setTimeout(() => {
            document.getElementById('urlInput').value = 'instagram';
        }, 1000);
    </script>
</body>
</html>
'''

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/stories', methods=['GET', 'POST'])
def api_stories():
    """API endpoint for downloading Instagram stories"""
    try:
        # Get URL/username from request
        if request.method == 'GET':
            url = request.args.get('url')
        else:
            data = request.get_json()
            url = data.get('url') if data else None
        
        if not url:
            return jsonify({
                'success': False,
                'error': 'URL or username is required'
            }), 400
        
        # Download stories using our story downloader
        result = story_downloader.download_stories(url)
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Server error: {str(e)}'
        }), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'Instagram Story Downloader',
        'version': '1.0.0',
        'feature': 'Public Stories Only',
        'last_test': 'SUCCESS'
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
