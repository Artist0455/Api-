[file name]: main.py
[file content begin]
import os
import re
import json
import requests
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from urllib.parse import urlparse, parse_qs, urlencode
import time

app = Flask(__name__)
CORS(app)

class InstagramSelfDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.setup_headers()
    
    def setup_headers(self):
        """Set up realistic browser headers"""
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
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
    
    def extract_shortcode(self, url):
        """Extract shortcode from Instagram URL"""
        patterns = [
            r'instagram\.com/reel/([^/?]+)',
            r'instagram\.com/p/([^/?]+)',
            r'instagram\.com/tv/([^/?]+)',
            r'instagram\.com/stories/[^/]+/([^/?]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    def get_instagram_page(self, url):
        """Fetch Instagram page content"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"Error fetching page: {str(e)}")
            return None
    
    def extract_media_from_html(self, html_content):
        """Extract all media URLs (images and videos) from HTML with highest quality"""
        media_data = {
            'images': [],  # Multiple images for carousel posts
            'videos': [],  # Videos with quality info
            'is_video': False,
            'is_carousel': False,
            'caption': '',
            'username': ''
        }
        
        try:
            # Method 1: Extract from JSON-LD structured data
            json_ld_pattern = r'<script type="application/ld\+json">(.*?)</script>'
            json_ld_matches = re.findall(json_ld_pattern, html_content, re.DOTALL)
            
            for json_ld in json_ld_matches:
                try:
                    data = json.loads(json_ld)
                    if isinstance(data, dict):
                        if 'video' in data:
                            video_info = data['video']
                            if isinstance(video_info, dict):
                                if 'contentUrl' in video_info:
                                    video_url = video_info['contentUrl']
                                    media_data['videos'].append({
                                        'url': video_url,
                                        'quality': 'high',
                                        'type': 'video/mp4'
                                    })
                                    media_data['is_video'] = True
                        elif 'image' in data:
                            image_info = data['image']
                            if isinstance(image_info, dict):
                                if 'url' in image_info:
                                    media_data['images'].append(image_info['url'])
                except:
                    continue
            
            # Method 2: Look for window.__additionalDataLoaded or window._sharedData
            script_patterns = [
                r'window\.__additionalDataLoaded\([^,]+,\s*({.*?})\);',
                r'window\._sharedData\s*=\s*({.*?});',
                r'<script[^>]*>window\._sharedData\s*=\s*({.*?});</script>'
            ]
            
            for pattern in script_patterns:
                matches = re.findall(pattern, html_content, re.DOTALL)
                for match in matches:
                    try:
                        data = json.loads(match)
                        # Navigate through possible data structures
                        if 'entry_data' in data:
                            for entry in data['entry_data'].get('PostPage', []):
                                media = entry.get('graphql', {}).get('shortcode_media', {})
                                self.extract_from_graphql(media, media_data)
                        elif 'graphql' in data:
                            media = data['graphql'].get('shortcode_media', {})
                            self.extract_from_graphql(media, media_data)
                    except:
                        continue
            
            # Method 3: Look for video URLs directly in HTML
            video_patterns = [
                r'"video_url":"([^"]+)"',
                r'"videoUrl":"([^"]+)"',
                r'"contentUrl":"([^"]+)"',
                r'<source[^>]*src="([^"]+)"[^>]*type="video/mp4"',
                r'<video[^>]*src="([^"]+)"',
            ]
            
            for pattern in video_patterns:
                matches = re.findall(pattern, html_content)
                for match in matches:
                    if '.mp4' in match or 'video' in match.lower():
                        video_url = match.replace('\\/', '/').replace('\\u0026', '&')
                        # Check if this is highest quality
                        if any(q in video_url.lower() for q in ['1080', '720', 'hd', 'high']):
                            media_data['videos'].insert(0, {
                                'url': video_url,
                                'quality': 'high',
                                'type': 'video/mp4'
                            })
                        else:
                            media_data['videos'].append({
                                'url': video_url,
                                'quality': 'standard',
                                'type': 'video/mp4'
                            })
                        media_data['is_video'] = True
            
            # Method 4: Look for image URLs (highest resolution)
            image_patterns = [
                r'"display_url":"([^"]+)"',
                r'"displayUrl":"([^"]+)"',
                r'<meta property="og:image" content="([^"]+)"',
                r'<meta property="og:image:secure_url" content="([^"]+)"',
                r'"thumbnail_src":"([^"]+)"',
                r'"thumbnail_url":"([^"]+)"',
            ]
            
            for pattern in image_patterns:
                matches = re.findall(pattern, html_content)
                for match in matches:
                    image_url = match.replace('\\/', '/').replace('\\u0026', '&')
                    # Get highest resolution by removing size parameters
                    base_url = re.sub(r'(\?|&)ig_cache_key[^&]*', '', image_url)
                    base_url = re.sub(r'(\?|&)se=\d+', '', base_url)
                    base_url = re.sub(r'(\?|&)s=\w+', '', base_url)
                    
                    # Try to get original quality by removing resizing parameters
                    original_url = re.sub(r'/s\d+x\d+/', '/', base_url)
                    original_url = re.sub(r'/c\d+\.[\d.]+:\d+,\d+/', '/', original_url)
                    
                    if original_url not in media_data['images']:
                        media_data['images'].append(original_url)
            
            # Method 5: Check for carousel posts
            carousel_patterns = [
                r'"edge_sidecar_to_children".*?"edges".*?\[(.*?)\]',
                r'"carousel_media".*?\[(.*?)\]'
            ]
            
            for pattern in carousel_patterns:
                matches = re.findall(pattern, html_content, re.DOTALL)
                for match in matches:
                    # Extract individual media items
                    item_patterns = [
                        r'"video_url":"([^"]+)"',
                        r'"display_url":"([^"]+)"',
                        r'"image_versions2".*?"candidates".*?\[(.*?)\]'
                    ]
                    
                    for item_pattern in item_patterns:
                        items = re.findall(item_pattern, match, re.DOTALL)
                        for item in items:
                            if item:
                                if '"video_url"' in pattern:
                                    media_data['videos'].append({
                                        'url': item.replace('\\/', '/'),
                                        'quality': 'high',
                                        'type': 'video/mp4'
                                    })
                                    media_data['is_video'] = True
                                else:
                                    # Parse JSON for image candidates
                                    try:
                                        candidates = json.loads(f'[{item}]')
                                        if candidates and len(candidates) > 0:
                                            # Get the highest resolution (usually first)
                                            best_image = candidates[0].get('url', '')
                                            if best_image:
                                                media_data['images'].append(best_image.replace('\\/', '/'))
                                    except:
                                        media_data['images'].append(item.replace('\\/', '/'))
                    
                    if len(media_data['images']) > 1 or len(media_data['videos']) > 0:
                        media_data['is_carousel'] = True
            
            # Remove duplicates
            media_data['images'] = list(dict.fromkeys(media_data['images']))
            
            # Extract caption and username
            caption_patterns = [
                r'"edge_media_to_caption".*?"edges".*?"text":"([^"]+)"',
                r'"caption":"([^"]+)"',
                r'<meta property="og:title" content="([^"]+)"',
                r'<meta property="og:description" content="([^"]+)"'
            ]
            
            for pattern in caption_patterns:
                matches = re.findall(pattern, html_content, re.DOTALL)
                if matches:
                    media_data['caption'] = matches[0].replace('\\n', '\n').replace('\\/', '/')
                    break
            
            username_patterns = [
                r'"owner".*?"username":"([^"]+)"',
                r'"username":"([^"]+)"',
                r'<meta property="og:site_name" content="Instagram video by ([^"]+)"',
                r'content="instagram://user\?username=([^"]+)"'
            ]
            
            for pattern in username_patterns:
                matches = re.findall(pattern, html_content)
                if matches:
                    media_data['username'] = matches[0]
                    break
            
            return media_data
            
        except Exception as e:
            print(f"Error extracting media from HTML: {str(e)}")
            return media_data
    
    def extract_from_graphql(self, media_data, result):
        """Extract media from GraphQL data structure"""
        try:
            # Check if it's a video
            if media_data.get('is_video'):
                video_url = media_data.get('video_url')
                if video_url:
                    # Get best quality video
                    result['videos'].append({
                        'url': video_url,
                        'quality': 'high',
                        'type': 'video/mp4',
                        'duration': media_data.get('video_duration'),
                        'dimensions': media_data.get('dimensions', {})
                    })
                    result['is_video'] = True
            
            # Check for carousel media
            elif media_data.get('__typename') == 'GraphSidecar':
                edges = media_data.get('edge_sidecar_to_children', {}).get('edges', [])
                for edge in edges:
                    node = edge.get('node', {})
                    if node.get('is_video'):
                        video_url = node.get('video_url')
                        if video_url:
                            result['videos'].append({
                                'url': video_url,
                                'quality': 'high',
                                'type': 'video/mp4'
                            })
                            result['is_video'] = True
                    else:
                        display_url = node.get('display_url')
                        if display_url:
                            result['images'].append(display_url)
                if len(edges) > 1:
                    result['is_carousel'] = True
            
            # Single image
            else:
                display_url = media_data.get('display_url')
                if display_url:
                    result['images'].append(display_url)
            
            # Get caption
            caption_edges = media_data.get('edge_media_to_caption', {}).get('edges', [])
            if caption_edges:
                result['caption'] = caption_edges[0].get('node', {}).get('text', '')
            
            # Get username
            owner = media_data.get('owner', {})
            if owner:
                result['username'] = owner.get('username', '')
                
        except Exception as e:
            print(f"Error in extract_from_graphql: {str(e)}")
    
    def get_media_from_api(self, shortcode):
        """Try to get media from Instagram's internal APIs"""
        try:
            # Try GraphQL endpoint
            api_url = "https://www.instagram.com/graphql/query/"
            
            # Different query hashes for different media types
            query_hashes = {
                'post': "2b0673e0dc4580674a88d426fe00ea90",
                'reel': "b3055c01b4b222b8a47d12a2d933b233",
                'story': "45246d3fe16ccc6577e0bd297a5db1ab"
            }
            
            for media_type, query_hash in query_hashes.items():
                try:
                    params = {
                        'query_hash': query_hash,
                        'variables': json.dumps({
                            'shortcode': shortcode,
                            'child_comment_count': 3,
                            'fetch_comment_count': 40,
                            'parent_comment_count': 24,
                            'has_threaded_comments': False
                        })
                    }
                    
                    headers = {
                        'User-Agent': 'Instagram 269.0.0.18.75 Android',
                        'Accept': '*/*',
                        'X-IG-App-ID': '936619743392459',
                        'X-Requested-With': 'XMLHttpRequest',
                        'Referer': f'https://www.instagram.com/p/{shortcode}/',
                    }
                    
                    response = self.session.get(api_url, params=params, headers=headers, timeout=15)
                    
                    if response.status_code == 200:
                        data = response.json()
                        # Try to extract media from response
                        media_data = self.extract_from_api_response(data)
                        if media_data and (media_data['images'] or media_data['videos']):
                            return media_data
                except:
                    continue
            
            return None
            
        except Exception as e:
            print(f"Error in API method: {str(e)}")
            return None
    
    def extract_from_api_response(self, data):
        """Extract media from API response"""
        media_data = {
            'images': [],
            'videos': [],
            'is_video': False,
            'is_carousel': False,
            'caption': '',
            'username': ''
        }
        
        try:
            # Navigate through response structure
            response_data = data.get('data', {})
            
            # Try different possible structures
            possible_paths = [
                ['shortcode_media'],
                ['media'],
                ['items', 0],
                ['graphql', 'shortcode_media'],
                ['edge_owner_to_timeline_media', 'edges', 0, 'node']
            ]
            
            for path in possible_paths:
                current = response_data
                valid = True
                for key in path:
                    if isinstance(current, dict) and key in current:
                        current = current[key]
                    elif isinstance(current, list) and isinstance(key, int) and key < len(current):
                        current = current[key]
                    else:
                        valid = False
                        break
                
                if valid and current:
                    self.extract_from_graphql(current, media_data)
                    if media_data['images'] or media_data['videos']:
                        break
            
            return media_data
            
        except Exception as e:
            print(f"Error extracting from API response: {str(e)}")
            return media_data
    
    def get_best_quality_video(self, videos):
        """Select the highest quality video from available options"""
        if not videos:
            return None
        
        # Sort by quality indicators
        quality_scores = {
            '1080': 4,
            '720': 3,
            'hd': 2,
            'high': 2,
            'standard': 1,
            'low': 0
        }
        
        best_video = videos[0]
        best_score = 0
        
        for video in videos:
            score = 0
            url_lower = video['url'].lower()
            
            for quality, points in quality_scores.items():
                if quality in url_lower:
                    score = max(score, points)
            
            # Check for resolution patterns
            res_match = re.search(r'(\d{3,4})[pP]', url_lower)
            if res_match:
                res = int(res_match.group(1))
                score = max(score, res / 100)
            
            if score > best_score:
                best_score = score
                best_video = video
        
        return best_video['url']
    
    def download_media(self, url):
        """Main function to download Instagram media"""
        print(f"Processing URL: {url}")
        
        # Get shortcode
        shortcode = self.extract_shortcode(url)
        if not shortcode:
            return {
                'success': False,
                'error': 'Invalid Instagram URL format'
            }
        
        results = []
        
        # Method 1: Direct HTML parsing
        print("Method 1: HTML parsing...")
        html_content = self.get_instagram_page(url)
        if html_content:
            media_data = self.extract_media_from_html(html_content)
            if media_data['images'] or media_data['videos']:
                result = self.format_result(media_data, 'html_parsing')
                results.append(result)
                print(f"Found {len(media_data['images'])} images, {len(media_data['videos'])} videos via HTML")
        
        # Method 2: API extraction
        print("Method 2: API extraction...")
        api_data = self.get_media_from_api(shortcode)
        if api_data and (api_data['images'] or api_data['videos']):
            result = self.format_result(api_data, 'instagram_api')
            results.append(result)
            print(f"Found {len(api_data['images'])} images, {len(api_data['videos'])} videos via API")
        
        # Method 3: Try embed page
        print("Method 3: Embed page...")
        try:
            embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
            embed_html = self.get_instagram_page(embed_url)
            if embed_html:
                embed_data = self.extract_media_from_html(embed_html)
                if embed_data['images'] or embed_data['videos']:
                    result = self.format_result(embed_data, 'embed_page')
                    results.append(result)
                    print(f"Found {len(embed_data['images'])} images, {len(embed_data['videos'])} videos via embed")
        except:
            pass
        
        # Select best result
        if results:
            # Prioritize results with videos
            video_results = [r for r in results if r['is_video']]
            if video_results:
                best_result = video_results[0]
                # Get highest quality video
                if best_result['videos']:
                    best_video_url = self.get_best_quality_video(best_result['videos'])
                    best_result['video_url'] = best_video_url
            else:
                best_result = results[0]
            
            best_result['success'] = True
            return best_result
        
        # If all methods fail
        return {
            'success': False,
            'error': 'Could not extract media. The post might be private or require login.'
        }
    
    def format_result(self, media_data, method):
        """Format media data for response"""
        result = {
            'success': True,
            'method': method,
            'is_video': media_data['is_video'],
            'is_carousel': media_data['is_carousel'],
            'images': media_data['images'],
            'videos': media_data['videos'],
            'username': media_data['username'],
            'caption': media_data['caption'][:200] + '...' if len(media_data['caption']) > 200 else media_data['caption']
        }
        
        # Add video_url for single videos
        if media_data['videos'] and not media_data['is_carousel']:
            result['video_url'] = self.get_best_quality_video(media_data['videos'])
        
        return result

# Initialize downloader
downloader = InstagramSelfDownloader()

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Instagram Downloader - HQ Photos & Videos</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
        }
        
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
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
            border-color: #405DE6;
            box-shadow: 0 0 0 4px rgba(64, 93, 230, 0.1);
        }
        
        button {
            background: linear-gradient(45deg, #405DE6, #833AB4);
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
            box-shadow: 0 10px 20px rgba(64, 93, 230, 0.3);
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
            border-top: 5px solid #405DE6;
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
            color: #28a745;
            font-size: 1.8rem;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .media-info {
            background: white;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 25px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.05);
        }
        
        .media-preview {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        
        .media-item {
            position: relative;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            background: #000;
        }
        
        .media-item img, .media-item video {
            width: 100%;
            height: 250px;
            object-fit: cover;
            display: block;
        }
        
        .media-item video {
            background: #000;
        }
        
        .media-badge {
            position: absolute;
            top: 10px;
            right: 10px;
            background: rgba(0,0,0,0.7);
            color: white;
            padding: 5px 10px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 600;
        }
        
        .caption {
            background: white;
            padding: 15px;
            border-radius: 10px;
            margin: 15px 0;
            border-left: 4px solid #405DE6;
            font-style: italic;
        }
        
        .actions {
            display: flex;
            gap: 15px;
            margin-top: 25px;
            flex-wrap: wrap;
        }
        
        .btn {
            padding: 15px 25px;
            border-radius: 10px;
            text-decoration: none;
            font-weight: 600;
            text-align: center;
            flex: 1;
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
        
        .btn-download {
            background: linear-gradient(45deg, #28a745, #20c997);
            color: white;
        }
        
        .btn-copy {
            background: linear-gradient(45deg, #6c757d, #495057);
            color: white;
            border: none;
            cursor: pointer;
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
        
        .working-example {
            background: #e7f4e4;
            padding: 15px;
            border-radius: 10px;
            margin-top: 20px;
            border-left: 4px solid #28a745;
        }
        
        .working-example h4 {
            color: #28a745;
            margin-bottom: 10px;
        }
        
        .features {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-top: 30px;
        }
        
        .feature-card {
            background: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            box-shadow: 0 5px 15px rgba(0,0,0,0.05);
            border-top: 4px solid #405DE6;
            transition: transform 0.3s;
        }
        
        .feature-card:hover {
            transform: translateY(-5px);
        }
        
        .feature-card i {
            font-size: 2.5rem;
            color: #405DE6;
            margin-bottom: 15px;
        }
        
        .feature-card h4 {
            color: #333;
            margin-bottom: 10px;
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
            
            .actions {
                flex-direction: column;
            }
            
            .btn {
                width: 100%;
            }
            
            .features {
                grid-template-columns: 1fr;
            }
            
            .media-preview {
                grid-template-columns: 1fr;
            }
        }
    </style>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
</head>
<body>
    <div class="container">
        <div class="header">
            <h1><i class="fab fa-instagram"></i> Instagram HQ Downloader</h1>
            <p>Download Photos & Videos in Original Quality • No Watermark • No Login</p>
            <div class="badge">✓ FULL RESOLUTION</div>
        </div>
        
        <div class="content">
            <div class="input-section">
                <h2 style="color: #333; margin-bottom: 20px; font-size: 1.6rem;">Download Instagram Posts</h2>
                
                <div class="input-group">
                    <input type="text" id="urlInput" placeholder="Paste Instagram Post/Reel URL here...">
                    <button onclick="downloadMedia()">
                        <i class="fas fa-download"></i> Download
                    </button>
                </div>
                
                <div class="working-example">
                    <h4><i class="fas fa-check-circle"></i> Supports All Formats</h4>
                    <p>• Single Photos • Multiple Photos (Carousel) • Videos • Reels</p>
                    <p style="margin-top: 10px; font-size: 0.9rem; color: #555;">
                        <strong>Quality:</strong> Downloads in original Instagram quality
                    </p>
                </div>
            </div>
            
            <div class="loader" id="loader">
                <div class="spinner"></div>
                <p style="font-size: 1.1rem; color: #666;">Extracting media from Instagram...</p>
                <p id="statusText" style="margin-top: 10px; color: #888; font-size: 0.9rem;"></p>
            </div>
            
            <div class="error" id="error"></div>
            
            <div class="result" id="result">
                <h3><i class="fas fa-check-circle"></i> Media Found!</h3>
                
                <div class="media-info">
                    <p style="margin-bottom: 10px;">
                        <strong>Type:</strong> 
                        <span id="mediaType" style="color: #405DE6; font-weight: 700; background: #eef2ff; padding: 5px 10px; border-radius: 5px;"></span>
                    </p>
                    <p style="margin-bottom: 10px;">
                        <strong>Method:</strong> 
                        <span id="methodName" style="color: #833AB4; font-weight: 700; background: #f8f0ff; padding: 5px 10px; border-radius: 5px;"></span>
                    </p>
                    <p style="margin-bottom: 10px;">
                        <strong>Quality:</strong> 
                        <span style="color: #28a745; font-weight: 700;">
                            <i class="fas fa-check"></i> Original Resolution
                        </span>
                    </p>
                    <div id="caption" class="caption"></div>
                </div>
                
                <div id="mediaPreview" class="media-preview">
                    <!-- Media will be inserted here -->
                </div>
                
                <div class="actions" id="downloadActions">
                    <!-- Download buttons will be inserted here -->
                </div>
            </div>
            
            <div class="features">
                <div class="feature-card">
                    <i class="fas fa-image"></i>
                    <h4>High Quality Photos</h4>
                    <p style="color: #666; font-size: 0.9rem;">Download images in full resolution</p>
                </div>
                
                <div class="feature-card">
                    <i class="fas fa-video"></i>
                    <h4>HD Videos</h4>
                    <p style="color: #666; font-size: 0.9rem;">1080p/720p video downloads</p>
                </div>
                
                <div class="feature-card">
                    <i class="fas fa-layer-group"></i>
                    <h4>Carousel Posts</h4>
                    <p style="color: #666; font-size: 0.9rem;">Download multiple photos/videos</p>
                </div>
                
                <div class="feature-card">
                    <i class="fas fa-bolt"></i>
                    <h4>Fast Extraction</h4>
                    <p style="color: #666; font-size: 0.9rem;">Multiple methods for reliability</p>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let currentMediaData = null;
        
        async function downloadMedia() {
            const url = document.getElementById('urlInput').value.trim();
            const errorDiv = document.getElementById('error');
            const loader = document.getElementById('loader');
            const result = document.getElementById('result');
            
            // Reset
            errorDiv.style.display = 'none';
            result.style.display = 'none';
            currentMediaData = null;
            
            // Validate URL
            if (!url) {
                showError('Please enter an Instagram URL');
                return;
            }
            
            if (!url.includes('instagram.com')) {
                showError('Please enter a valid Instagram URL');
                return;
            }
            
            // Show loader
            loader.style.display = 'block';
            
            // Update status messages
            const statusMessages = [
                'Connecting to Instagram...',
                'Loading media content...',
                'Extracting high quality files...',
                'Finding best resolution...',
                'Preparing downloads...'
            ];
            
            let messageIndex = 0;
            const statusInterval = setInterval(() => {
                document.getElementById('statusText').textContent = statusMessages[messageIndex];
                messageIndex = (messageIndex + 1) % statusMessages.length;
            }, 1200);
            
            try {
                // Make API request
                const response = await fetch('/api/download', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ url: url })
                });
                
                clearInterval(statusInterval);
                
                const data = await response.json();
                
                // Hide loader
                loader.style.display = 'none';
                
                if (data.success) {
                    // Store media data
                    currentMediaData = data;
                    
                    // Update UI
                    let mediaType = 'Single Photo';
                    if (data.is_video) mediaType = 'Video';
                    if (data.is_carousel && data.is_video) mediaType = 'Carousel with Videos';
                    else if (data.is_carousel) mediaType = 'Photo Carousel';
                    
                    document.getElementById('mediaType').textContent = mediaType;
                    document.getElementById('methodName').textContent = data.method;
                    
                    // Update caption
                    if (data.caption) {
                        document.getElementById('caption').innerHTML = `
                            <strong><i class="fas fa-comment"></i> Caption:</strong>
                            <p style="margin-top: 8px;">${data.caption}</p>
                        `;
                    } else {
                        document.getElementById('caption').innerHTML = '';
                    }
                    
                    // Update media preview
                    const mediaPreview = document.getElementById('mediaPreview');
                    mediaPreview.innerHTML = '';
                    
                    // Show images
                    if (data.images && data.images.length > 0) {
                        data.images.forEach((imgUrl, index) => {
                            const mediaItem = document.createElement('div');
                            mediaItem.className = 'media-item';
                            mediaItem.innerHTML = `
                                <img src="${imgUrl}" alt="Instagram Image ${index + 1}" onerror="this.src='https://via.placeholder.com/250x250?text=Image+Not+Loaded'">
                                <div class="media-badge">Photo ${index + 1}</div>
                            `;
                            mediaPreview.appendChild(mediaItem);
                        });
                    }
                    
                    // Show videos
                    if (data.videos && data.videos.length > 0) {
                        data.videos.forEach((video, index) => {
                            const mediaItem = document.createElement('div');
                            mediaItem.className = 'media-item';
                            mediaItem.innerHTML = `
                                <video controls>
                                    <source src="${video.url}" type="${video.type || 'video/mp4'}">
                                    Your browser does not support video playback.
                                </video>
                                <div class="media-badge">
                                    <i class="fas fa-video"></i> ${video.quality || 'HD'}
                                </div>
                            `;
                            mediaPreview.appendChild(mediaItem);
                        });
                    } else if (data.video_url) {
                        const mediaItem = document.createElement('div');
                        mediaItem.className = 'media-item';
                        mediaItem.innerHTML = `
                            <video controls>
                                <source src="${data.video_url}" type="video/mp4">
                                Your browser does not support video playback.
                            </video>
                            <div class="media-badge">
                                <i class="fas fa-video"></i> HD Video
                            </div>
                        `;
                        mediaPreview.appendChild(mediaItem);
                    }
                    
                    // Update download actions
                    const downloadActions = document.getElementById('downloadActions');
                    downloadActions.innerHTML = '';
                    
                    // Add download buttons for images
                    if (data.images && data.images.length > 0) {
                        if (data.images.length === 1) {
                            downloadActions.innerHTML += `
                                <a href="${data.images[0]}" class="btn btn-download" target="_blank" download>
                                    <i class="fas fa-download"></i> Download Photo
                                </a>
                            `;
                        } else {
                            data.images.forEach((imgUrl, index) => {
                                downloadActions.innerHTML += `
                                    <a href="${imgUrl}" class="btn btn-download" target="_blank" download style="flex: 0 1 auto;">
                                        <i class="fas fa-download"></i> Photo ${index + 1}
                                    </a>
                                `;
                            });
                        }
                    }
                    
                    // Add download button for video
                    if (data.video_url) {
                        downloadActions.innerHTML += `
                            <a href="${data.video_url}" class="btn btn-download" target="_blank" download>
                                <i class="fas fa-download"></i> Download Video
                            </a>
                        `;
                    } else if (data.videos && data.videos.length > 0) {
                        data.videos.forEach((video, index) => {
                            downloadActions.innerHTML += `
                                <a href="${video.url}" class="btn btn-download" target="_blank" download style="flex: 0 1 auto;">
                                    <i class="fas fa-download"></i> Video ${index + 1}
                                </a>
                            `;
                        });
                    }
                    
                    // Add utility buttons
                    downloadActions.innerHTML += `
                        <button onclick="copyAllUrls()" class="btn btn-copy">
                            <i class="fas fa-copy"></i> Copy All URLs
                        </button>
                        <button onclick="resetForm()" class="btn btn-new">
                            <i class="fas fa-redo"></i> Try Another
                        </button>
                    `;
                    
                    // Show result
                    result.style.display = 'block';
                    
                    // Auto-scroll to result
                    result.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    
                } else {
                    showError(data.error || 'Failed to extract media. The post might be private.');
                }
                
            } catch (error) {
                clearInterval(statusInterval);
                loader.style.display = 'none';
                showError('Network error: ' + error.message);
            }
        }
        
        function copyAllUrls() {
            if (!currentMediaData) return;
            
            let urls = [];
            
            // Collect image URLs
            if (currentMediaData.images && currentMediaData.images.length > 0) {
                urls.push(...currentMediaData.images);
            }
            
            // Collect video URLs
            if (currentMediaData.video_url) {
                urls.push(currentMediaData.video_url);
            } else if (currentMediaData.videos && currentMediaData.videos.length > 0) {
                urls.push(...currentMediaData.videos.map(v => v.url));
            }
            
            if (urls.length > 0) {
                navigator.clipboard.writeText(urls.join('\n'))
                    .then(() => {
                        alert(`✓ ${urls.length} URL(s) copied to clipboard!`);
                    })
                    .catch(err => {
                        console.error('Copy failed:', err);
                        alert('Failed to copy URLs. Please try again.');
                    });
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
        
        function resetForm() {
            document.getElementById('urlInput').value = '';
            document.getElementById('result').style.display = 'none';
            document.getElementById('error').style.display = 'none';
            document.getElementById('urlInput').focus();
            currentMediaData = null;
        }
        
        // Enter key support
        document.getElementById('urlInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                downloadMedia();
            }
        });
        
        // Auto-focus on input
        document.getElementById('urlInput').focus();
        
        // Add sample URL for testing
        setTimeout(() => {
            document.getElementById('urlInput').value = 'https://www.instagram.com/p/C1AZAMgLwT9/';
        }, 1000);
    </script>
</body>
</html>
'''

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/download', methods=['GET', 'POST'])
def api_download():
    """API endpoint for downloading Instagram media"""
    try:
        # Get URL from request
        if request.method == 'GET':
            url = request.args.get('url')
        else:
            data = request.get_json()
            url = data.get('url') if data else None
        
        if not url:
            return jsonify({
                'success': False,
                'error': 'URL parameter is required'
            }), 400
        
        # Validate Instagram URL
        if 'instagram.com' not in url:
            return jsonify({
                'success': False,
                'error': 'Invalid Instagram URL'
            }), 400
        
        # Download media using our self-made downloader
        result = downloader.download_media(url)
        
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
        'service': 'Instagram HQ Media Downloader',
        'version': '2.0.0',
        'features': ['photos', 'videos', 'carousels', 'full_resolution'],
        'working': 'YES'
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
[file content end]
