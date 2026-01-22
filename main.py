import os
import re
import json
import requests
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from urllib.parse import urlparse, parse_qs
import time
import html

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
        # Remove @ symbol if present
        url = url.replace('@', '')
        
        patterns = [
            r'instagram\.com/([^/?]+)/?$',
            r'instagram\.com/stories/([^/?]+)',
            r'instagram\.com/([^/?]+)/story/',
            r'instagram\.com/([^/?]+)/reel/',
            r'instagram\.com/([^/?]+)/p/',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                username = match.group(1).lower()
                # Remove query parameters
                username = username.split('?')[0]
                return username
        
        # If URL is just a username
        if '/' not in url and '.' not in url:
            return url.lower()
        
        return None
    
    def get_user_id_public(self, username):
        """Get user ID from public Instagram page"""
        try:
            profile_url = f"https://www.instagram.com/{username}/"
            print(f"Fetching profile: {profile_url}")
            
            response = self.session.get(profile_url, timeout=15)
            
            if response.status_code == 200:
                html_content = response.text
                
                # Save HTML for debugging
                with open(f"debug_{username}.html", "w", encoding="utf-8") as f:
                    f.write(html_content)
                
                # Method 1: Look for user ID in shared data
                shared_data_pattern = r'window\._sharedData\s*=\s*({.*?});'
                match = re.search(shared_data_pattern, html_content, re.DOTALL)
                
                if match:
                    try:
                        shared_data = json.loads(match.group(1))
                        
                        # Try multiple paths to get user ID
                        if 'entry_data' in shared_data:
                            profile_data = shared_data.get('entry_data', {}).get('ProfilePage', [])
                            if profile_data:
                                user_data = profile_data[0].get('graphql', {}).get('user', {})
                                if 'id' in user_data:
                                    print(f"Found user ID via sharedData: {user_data['id']}")
                                    return user_data['id']
                    except Exception as e:
                        print(f"Error parsing sharedData: {e}")
                
                # Method 2: Look for additional data
                additional_data_pattern = r'window\.__additionalDataLoaded\s*\([^,]+,({.*?})\);'
                match = re.search(additional_data_pattern, html_content, re.DOTALL)
                
                if match:
                    try:
                        additional_data = json.loads(match.group(1))
                        user_data = additional_data.get('graphql', {}).get('user', {})
                        if 'id' in user_data:
                            print(f"Found user ID via additionalData: {user_data['id']}")
                            return user_data['id']
                    except:
                        pass
                
                # Method 3: Look for profile ID directly in HTML
                profile_id_patterns = [
                    r'"profile_id":"(\d+)"',
                    r'"user_id":"(\d+)"',
                    r'"owner":{"id":"(\d+)"',
                    r'profilePage_(\d+)',
                    r'"id":"(\d+)"',
                ]
                
                for pattern in profile_id_patterns:
                    matches = re.findall(pattern, html_content)
                    if matches:
                        print(f"Found user ID via pattern {pattern}: {matches[0]}")
                        return matches[0]
                
                # Method 4: Look for user ID in JSON-LD
                json_ld_pattern = r'<script type="application/ld\+json">(.*?)</script>'
                json_ld_matches = re.findall(json_ld_pattern, html_content, re.DOTALL)
                
                for json_ld in json_ld_matches:
                    try:
                        data = json.loads(json_ld)
                        if isinstance(data, dict) and '@id' in data:
                            url = data['@id']
                            user_id_match = re.search(r'instagram\.com/(\d+)', url)
                            if user_id_match:
                                print(f"Found user ID via JSON-LD: {user_id_match.group(1)}")
                                return user_id_match.group(1)
                    except:
                        continue
                
                print("Could not find user ID in HTML")
                return None
            else:
                print(f"HTTP Error {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Error getting user ID: {str(e)}")
            return None
    
    def get_stories_via_graphql(self, user_id):
        """Get stories using GraphQL endpoint"""
        try:
            # Instagram's GraphQL endpoint for stories
            graphql_url = "https://www.instagram.com/graphql/query/"
            
            # Query hash for stories (this might need to be updated)
            query_hash = "de8017ee0a7c9c45ec4260733d81ea31"  # Stories query hash
            
            variables = {
                'reel_ids': [user_id],
                'tag_names': [],
                'location_ids': [],
                'highlight_reel_ids': [],
                'precomposed_overlay': False,
                'show_story_viewer_list': True,
                'story_viewer_fetch_count': 50,
                'story_viewer_cursor': "",
                'stories_video_dash_manifest': False
            }
            
            params = {
                'query_hash': query_hash,
                'variables': json.dumps(variables)
            }
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'X-IG-App-ID': '936619743392459',
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': 'https://www.instagram.com/',
                'Accept': 'application/json',
            }
            
            response = self.session.get(graphql_url, params=params, headers=headers, timeout=15)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    
                    stories = []
                    
                    # Parse response for stories
                    if 'data' in data:
                        reels_media = data['data'].get('reels_media', [])
                        
                        for reel in reels_media:
                            if 'items' in reel:
                                for item in reel['items']:
                                    story_info = self.extract_story_info(item)
                                    if story_info:
                                        stories.append(story_info)
                    
                    return stories
                except json.JSONDecodeError:
                    return []
            
            return []
            
        except Exception as e:
            print(f"Error in GraphQL method: {str(e)}")
            return []
    
    def get_stories_via_embed(self, username):
        """Get stories via Instagram embed API"""
        try:
            embed_url = f"https://www.instagram.com/{username}/?__a=1&__d=dis"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Referer': f'https://www.instagram.com/{username}/',
            }
            
            response = self.session.get(embed_url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    stories = []
                    
                    # Parse the JSON response
                    user_data = data.get('graphql', {}).get('user', {})
                    
                    if 'reel' in user_data:
                        reel_data = user_data['reel']
                        if 'edge_reel_media' in reel_data:
                            edges = reel_data['edge_reel_media'].get('edges', [])
                            for edge in edges:
                                node = edge.get('node', {})
                                story_info = self.extract_story_from_node(node)
                                if story_info:
                                    stories.append(story_info)
                    
                    return stories
                except:
                    return []
            
            return []
            
        except Exception as e:
            print(f"Error in embed method: {str(e)}")
            return []
    
    def get_stories_via_public_api(self, username):
        """Get stories via public Instagram API"""
        try:
            # Try different public API endpoints
            endpoints = [
                f"https://www.instagram.com/{username}/channel/?__a=1",
                f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}",
                f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}",
            ]
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'X-IG-App-ID': '936619743392459',
                'X-Requested-With': 'XMLHttpRequest',
            }
            
            for endpoint in endpoints:
                try:
                    response = self.session.get(endpoint, headers=headers, timeout=10)
                    
                    if response.status_code == 200:
                        try:
                            data = response.json()
                            stories = []
                            
                            # Parse different response formats
                            if 'data' in data:
                                user_data = data['data'].get('user', {})
                                if 'reel' in user_data:
                                    items = user_data['reel'].get('items', [])
                                    for item in items:
                                        story_info = self.extract_story_info(item)
                                        if story_info:
                                            stories.append(story_info)
                            
                            elif 'graphql' in data:
                                user_data = data['graphql'].get('user', {})
                                if 'reel' in user_data:
                                    items = user_data['reel'].get('items', [])
                                    for item in items:
                                        story_info = self.extract_story_info(item)
                                        if story_info:
                                            stories.append(story_info)
                            
                            if stories:
                                return stories
                                
                        except:
                            continue
                except:
                    continue
            
            return []
            
        except Exception as e:
            print(f"Error in public API method: {str(e)}")
            return []
    
    def extract_story_info(self, item):
        """Extract story information from item data"""
        try:
            story_info = {
                'id': item.get('id'),
                'timestamp': item.get('taken_at_timestamp'),
                'media_type': item.get('__typename'),
            }
            
            # Check media type
            if item.get('__typename') == 'GraphStoryVideo':
                # Video story
                if 'video_resources' in item:
                    videos = item['video_resources']
                    if videos:
                        # Get highest quality video
                        best_video = max(videos, key=lambda x: x.get('config_height', 0))
                        story_info['url'] = self.fix_url(best_video.get('src'))
                        story_info['type'] = 'video'
                elif 'video_url' in item:
                    story_info['url'] = self.fix_url(item['video_url'])
                    story_info['type'] = 'video'
                    
            else:
                # Image story
                if 'display_resources' in item:
                    resources = item['display_resources']
                    if resources:
                        # Get highest quality image
                        best_image = max(resources, key=lambda x: x.get('config_width', 0))
                        story_info['url'] = self.fix_url(best_image.get('src'))
                        story_info['type'] = 'image'
                elif 'display_url' in item:
                    story_info['url'] = self.fix_url(item['display_url'])
                    story_info['type'] = 'image'
            
            return story_info if 'url' in story_info else None
            
        except Exception as e:
            print(f"Error extracting story info: {e}")
            return None
    
    def extract_story_from_node(self, node):
        """Extract story from node data"""
        try:
            story_info = {
                'id': node.get('id'),
                'timestamp': node.get('taken_at_timestamp'),
                'media_type': node.get('__typename'),
            }
            
            if node.get('is_video'):
                # Video story
                if 'video_url' in node:
                    story_info['url'] = self.fix_url(node['video_url'])
                    story_info['type'] = 'video'
                elif 'video_versions' in node:
                    videos = node['video_versions']
                    if videos:
                        best_video = max(videos, key=lambda x: x.get('height', 0))
                        story_info['url'] = self.fix_url(best_video.get('url'))
                        story_info['type'] = 'video'
            else:
                # Image story
                if 'display_resources' in node:
                    resources = node['display_resources']
                    if resources:
                        best_image = max(resources, key=lambda x: x.get('config_width', 0))
                        story_info['url'] = self.fix_url(best_image.get('src'))
                        story_info['type'] = 'image'
                elif 'display_url' in node:
                    story_info['url'] = self.fix_url(node['display_url'])
                    story_info['type'] = 'image'
            
            return story_info if 'url' in story_info else None
            
        except Exception as e:
            print(f"Error extracting from node: {e}")
            return None
    
    def fix_url(self, url):
        """Fix URL formatting"""
        if not url:
            return None
        
        # Fix escaped slashes
        url = url.replace('\\/', '/').replace('\\\\/', '/')
        
        # Fix other escaped characters
        url = url.replace('\\u0026', '&').replace('\\u002F', '/')
        
        # Ensure it starts with http
        if not url.startswith('http'):
            if url.startswith('//'):
                url = 'https:' + url
        
        return url
    
    def download_stories(self, input_url):
        """Main function to download stories"""
        print(f"\n{'='*50}")
        print(f"Processing input: {input_url}")
        
        # Get username from input
        username = self.extract_username(input_url)
        if not username:
            return {
                'success': False,
                'error': 'Invalid Instagram username or URL format'
            }
        
        print(f"Username extracted: {username}")
        
        # Method 1: Get user ID and try GraphQL
        print("\nMethod 1: Getting user ID...")
        user_id = self.get_user_id_public(username)
        
        if user_id:
            print(f"Found user ID: {user_id}")
            print("Trying GraphQL method...")
            stories = self.get_stories_via_graphql(user_id)
            
            if stories:
                print(f"✓ Found {len(stories)} stories via GraphQL")
                return {
                    'success': True,
                    'username': username,
                    'user_id': user_id,
                    'stories': stories,
                    'count': len(stories),
                    'method': 'graphql'
                }
        
        # Method 2: Try embed API
        print("\nMethod 2: Trying embed API...")
        stories = self.get_stories_via_embed(username)
        
        if stories:
            print(f"✓ Found {len(stories)} stories via embed API")
            return {
                'success': True,
                'username': username,
                'stories': stories,
                'count': len(stories),
                'method': 'embed_api'
            }
        
        # Method 3: Try public API
        print("\nMethod 3: Trying public API...")
        stories = self.get_stories_via_public_api(username)
        
        if stories:
            print(f"✓ Found {len(stories)} stories via public API")
            return {
                'success': True,
                'username': username,
                'stories': stories,
                'count': len(stories),
                'method': 'public_api'
            }
        
        # Method 4: Try direct HTML parsing as last resort
        print("\nMethod 4: Trying direct HTML parsing...")
        stories = self.get_stories_from_html(username)
        
        if stories:
            print(f"✓ Found {len(stories)} stories via HTML parsing")
            return {
                'success': True,
                'username': username,
                'stories': stories,
                'count': len(stories),
                'method': 'html_parsing'
            }
        
        # If all methods fail
        print(f"\n✗ No stories found for @{username}")
        return {
            'success': False,
            'error': f'No public stories found for @{username}. Possible reasons:\n1. Account is private\n2. No active stories at the moment\n3. Instagram API restrictions\n4. Account doesn\'t exist',
            'username': username,
            'note': 'Try checking manually if the account has public stories visible on Instagram.'
        }
    
    def get_stories_from_html(self, username):
        """Direct HTML parsing as fallback"""
        try:
            profile_url = f"https://www.instagram.com/{username}/"
            response = self.session.get(profile_url, timeout=15)
            
            if response.status_code == 200:
                html_content = response.text
                stories = []
                
                # Look for story URLs in HTML
                story_patterns = [
                    r'"video_url":"([^"]+)"',
                    r'"display_url":"([^"]+)"',
                    r'"src":"([^"]+\.(mp4|jpg|jpeg|png))"',
                    r'https://[^"]+\.(mp4|jpg|jpeg|png)[^"]*',
                ]
                
                for pattern in story_patterns:
                    matches = re.findall(pattern, html_content)
                    for match in matches:
                        if isinstance(match, tuple):
                            url = match[0]
                        else:
                            url = match
                        
                        if 'stories' in url.lower() or 'story' in url.lower():
                            story_info = {
                                'url': self.fix_url(url),
                                'type': 'video' if url.endswith('.mp4') else 'image',
                            }
                            stories.append(story_info)
                
                return stories[:10]  # Return max 10 stories
            
            return []
            
        except Exception as e:
            print(f"Error in HTML parsing: {e}")
            return []

# Initialize downloader
story_downloader = InstagramStoryDownloader()

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Instagram Story Downloader - PUBLIC ACCOUNTS ONLY</title>
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
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }
        
        .header {
            background: linear-gradient(45deg, #405DE6, #833AB4, #C13584, #E1306C, #FD1D1D);
            color: white;
            padding: 30px;
            text-align: center;
        }
        
        .header h1 {
            font-size: 2.2rem;
            margin-bottom: 10px;
            font-weight: 800;
        }
        
        .header p {
            font-size: 1rem;
            opacity: 0.9;
            margin: 5px 0;
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
        
        .warning {
            background: #fff3cd;
            color: #856404;
            padding: 15px;
            margin: 0 30px;
            border-radius: 10px;
            border-left: 4px solid #ffc107;
            text-align: center;
            font-weight: 600;
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
            margin-bottom: 20px;
        }
        
        input[type="text"] {
            flex: 1;
            padding: 15px 20px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            font-size: 16px;
            transition: all 0.3s;
        }
        
        input[type="text"]:focus {
            outline: none;
            border-color: #E1306C;
            box-shadow: 0 0 0 3px rgba(225, 48, 108, 0.1);
        }
        
        button {
            background: linear-gradient(45deg, #E1306C, #833AB4);
            color: white;
            border: none;
            padding: 15px 30px;
            border-radius: 10px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            min-width: 150px;
        }
        
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(225, 48, 108, 0.2);
        }
        
        button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        
        .loader {
            display: none;
            text-align: center;
            padding: 30px;
        }
        
        .spinner {
            width: 40px;
            height: 40px;
            border: 4px solid #f3f3f3;
            border-top: 4px solid #E1306C;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 15px;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .result {
            display: none;
            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
            padding: 25px;
            border-radius: 15px;
            margin-top: 20px;
            border: 2px solid #e0e0e0;
            animation: fadeIn 0.5s;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
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
            white-space: pre-line;
        }
        
        .profile-info {
            background: white;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.05);
            text-align: center;
        }
        
        .profile-info h4 {
            color: #333;
            font-size: 1.4rem;
            margin-bottom: 10px;
        }
        
        .stories-container {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }
        
        .story-card {
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            transition: transform 0.3s;
        }
        
        .story-card:hover {
            transform: translateY(-3px);
        }
        
        .story-media {
            width: 100%;
            height: 250px;
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
            padding: 4px 8px;
            border-radius: 15px;
            font-size: 0.7rem;
        }
        
        .story-actions {
            padding: 12px;
            text-align: center;
        }
        
        .story-actions a {
            display: inline-block;
            background: linear-gradient(45deg, #28a745, #20c997);
            color: white;
            text-decoration: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-weight: 600;
            font-size: 0.9rem;
            transition: all 0.3s;
        }
        
        .story-actions a:hover {
            background: linear-gradient(45deg, #20c997, #28a745);
            transform: translateY(-2px);
        }
        
        .no-stories {
            text-align: center;
            padding: 40px;
            color: #666;
        }
        
        .no-stories i {
            font-size: 3rem;
            color: #ccc;
            margin-bottom: 15px;
        }
        
        .actions {
            display: flex;
            gap: 10px;
            margin-top: 20px;
            flex-wrap: wrap;
            justify-content: center;
        }
        
        .btn {
            padding: 12px 20px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            text-align: center;
            min-width: 140px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            transition: all 0.3s;
            border: none;
            cursor: pointer;
            font-size: 0.9rem;
        }
        
        .btn-download-all {
            background: linear-gradient(45deg, #28a745, #20c997);
            color: white;
        }
        
        .btn-new {
            background: linear-gradient(45deg, #fd7e14, #ff922b);
            color: white;
        }
        
        .examples {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 10px;
            margin-top: 20px;
        }
        
        .examples h4 {
            color: #555;
            margin-bottom: 10px;
            font-size: 0.9rem;
        }
        
        .example-item {
            display: inline-block;
            background: white;
            padding: 8px 12px;
            margin: 5px;
            border-radius: 6px;
            font-size: 0.85rem;
            color: #E1306C;
            cursor: pointer;
            border: 1px solid #e0e0e0;
        }
        
        .example-item:hover {
            background: #f8f8f8;
        }
        
        @media (max-width: 768px) {
            .container {
                border-radius: 15px;
            }
            
            .header {
                padding: 20px;
            }
            
            .header h1 {
                font-size: 1.8rem;
            }
            
            .input-group {
                flex-direction: column;
            }
            
            button {
                width: 100%;
                min-width: auto;
            }
            
            .stories-container {
                grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
            }
            
            .story-media {
                height: 200px;
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
            <p>Download Public Instagram Stories • No Login Required</p>
            <div class="badge">PUBLIC ACCOUNTS ONLY</div>
        </div>
        
        <div class="warning">
            <i class="fas fa-exclamation-triangle"></i> 
            This tool works only with PUBLIC Instagram accounts. Private accounts require login.
        </div>
        
        <div class="content">
            <div class="input-section">
                <h2 style="color: #333; margin-bottom: 15px; font-size: 1.4rem;">Enter Instagram Details</h2>
                
                <div class="input-group">
                    <input type="text" id="urlInput" placeholder="Enter username (e.g., instagram) or profile URL...">
                    <button onclick="downloadStories()" id="downloadBtn">
                        <i class="fas fa-download"></i> Get Stories
                    </button>
                </div>
                
                <div class="examples">
                    <h4>Try these public accounts:</h4>
                    <div class="example-item" onclick="useExample('instagram')">instagram</div>
                    <div class="example-item" onclick="useExample('natgeo')">natgeo</div>
                    <div class="example-item" onclick="useExample('nasa')">nasa</div>
                    <div class="example-item" onclick="useExample('netflix')">netflix</div>
                    <div class="example-item" onclick="useExample('instagram')">@instagram</div>
                </div>
            </div>
            
            <div class="loader" id="loader">
                <div class="spinner"></div>
                <p style="font-size: 1rem; color: #666; margin-top: 10px;">Fetching stories...</p>
                <p id="statusText" style="margin-top: 5px; color: #888; font-size: 0.85rem;"></p>
            </div>
            
            <div class="error" id="error"></div>
            
            <div class="result" id="result">
                <!-- Results will be inserted here -->
            </div>
        </div>
    </div>
    
    <script>
        let currentStoriesData = null;
        let isProcessing = false;
        
        function useExample(username) {
            document.getElementById('urlInput').value = username;
            downloadStories();
        }
        
        async function downloadStories() {
            if (isProcessing) return;
            
            const input = document.getElementById('urlInput').value.trim();
            const errorDiv = document.getElementById('error');
            const loader = document.getElementById('loader');
            const resultDiv = document.getElementById('result');
            const downloadBtn = document.getElementById('downloadBtn');
            
            // Reset
            errorDiv.style.display = 'none';
            resultDiv.style.display = 'none';
            currentStoriesData = null;
            isProcessing = true;
            downloadBtn.disabled = true;
            downloadBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
            
            // Validate input
            if (!input) {
                showError('Please enter Instagram username or URL');
                resetButton();
                return;
            }
            
            // Show loader
            loader.style.display = 'block';
            
            // Status messages
            const statusMessages = [
                'Checking account...',
                'Fetching profile data...',
                'Looking for stories...',
                'Extracting media...',
                'Almost done...'
            ];
            
            let messageIndex = 0;
            const statusInterval = setInterval(() => {
                document.getElementById('statusText').textContent = statusMessages[messageIndex];
                messageIndex = (messageIndex + 1) % statusMessages.length;
            }, 1000);
            
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
                    currentStoriesData = data;
                    displayResults(data);
                } else {
                    showError(data.error || 'Failed to fetch stories. Make sure the account is public.');
                }
                
            } catch (error) {
                clearInterval(statusInterval);
                loader.style.display = 'none';
                showError('Network error: ' + error.message);
            } finally {
                resetButton();
            }
        }
        
        function displayResults(data) {
            const resultDiv = document.getElementById('result');
            
            let storiesHTML = '';
            
            if (data.stories && data.stories.length > 0) {
                storiesHTML = `
                    <div class="profile-info">
                        <h4><i class="fab fa-instagram"></i> @${data.username}</h4>
                        <p><strong>Stories Found:</strong> ${data.count} | <strong>Method:</strong> ${data.method}</p>
                    </div>
                    
                    <div class="stories-container" id="storiesGrid">
                        ${data.stories.map((story, index) => `
                            <div class="story-card">
                                <div class="story-media">
                                    ${story.type === 'video' 
                                        ? `<video controls style="width: 100%; height: 100%; object-fit: cover;">
                                            <source src="${story.url}" type="video/mp4">
                                          </video>`
                                        : `<img src="${story.url}" alt="Story ${index + 1}" 
                                             onerror="this.src='https://via.placeholder.com/300x300?text=Image+Not+Available'" 
                                             style="width: 100%; height: 100%; object-fit: cover;">`
                                    }
                                    <div class="story-type">
                                        ${story.type === 'video' ? '<i class="fas fa-video"></i> Video' : '<i class="fas fa-image"></i> Image'}
                                    </div>
                                </div>
                                <div class="story-actions">
                                    <a href="${story.url}" 
                                       download="instagram_story_${data.username}_${index + 1}.${story.type === 'video' ? 'mp4' : 'jpg'}" 
                                       target="_blank">
                                        <i class="fas fa-download"></i> Download ${story.type}
                                    </a>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                    
                    <div class="actions">
                        <button onclick="downloadAllStories()" class="btn btn-download-all">
                            <i class="fas fa-download"></i> Download All (${data.count})
                        </button>
                        <button onclick="resetForm()" class="btn btn-new">
                            <i class="fas fa-redo"></i> Try Another
                        </button>
                    </div>
                `;
            } else {
                storiesHTML = `
                    <div class="no-stories">
                        <i class="fas fa-images"></i>
                        <h3>No Stories Found</h3>
                        <p>@${data.username} doesn't have any active stories right now.</p>
                        <button onclick="resetForm()" class="btn btn-new" style="margin-top: 20px;">
                            <i class="fas fa-search"></i> Try Another Account
                        </button>
                    </div>
                `;
            }
            
            resultDiv.innerHTML = storiesHTML;
            resultDiv.style.display = 'block';
            resultDiv.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
        
        function showError(message) {
            const errorDiv = document.getElementById('error');
            errorDiv.innerHTML = `
                <i class="fas fa-exclamation-triangle"></i> ${message}
            `;
            errorDiv.style.display = 'block';
            errorDiv.scrollIntoView({ behavior: 'smooth', block: 'start' });
            
            setTimeout(() => {
                errorDiv.style.display = 'none';
            }, 10000);
        }
        
        function downloadAllStories() {
            if (!currentStoriesData || !currentStoriesData.stories) return;
            
            currentStoriesData.stories.forEach((story, index) => {
                setTimeout(() => {
                    const link = document.createElement('a');
                    link.href = story.url;
                    link.download = `instagram_${currentStoriesData.username}_story_${index + 1}.${story.type === 'video' ? 'mp4' : 'jpg'}`;
                    link.target = '_blank';
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                }, index * 500); // Stagger downloads
            });
            
            alert(`Downloading ${currentStoriesData.stories.length} stories... Check your downloads folder.`);
        }
        
        function resetForm() {
            document.getElementById('urlInput').value = '';
            document.getElementById('result').style.display = 'none';
            document.getElementById('error').style.display = 'none';
            document.getElementById('urlInput').focus();
            currentStoriesData = null;
        }
        
        function resetButton() {
            const downloadBtn = document.getElementById('downloadBtn');
            downloadBtn.disabled = false;
            downloadBtn.innerHTML = '<i class="fas fa-download"></i> Get Stories';
            isProcessing = false;
        }
        
        // Enter key support
        document.getElementById('urlInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter' && !isProcessing) {
                downloadStories();
            }
        });
        
        // Auto-focus on input
        document.getElementById('urlInput').focus();
        
        // Add sample for testing
        setTimeout(() => {
            document.getElementById('urlInput').value = 'instagram';
        }, 500);
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
        
        # Download stories
        result = story_downloader.download_stories(url)
        
        return jsonify(result)
    
    except Exception as e:
        import traceback
        print(f"Server error: {e}")
        print(traceback.format_exc())
        
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
        'version': '2.0.0',
        'feature': 'Public Accounts Only',
        'note': 'For private accounts, login is required'
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True, threaded=True)
