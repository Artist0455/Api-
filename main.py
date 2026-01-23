import os
import re
import json
import requests
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from urllib.parse import urlparse, parse_qs
import time
import base64

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
    
    def get_instagram_page(self, url):
        """Fetch Instagram page content"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"Error fetching page: {str(e)}")
            return None
    
    def extract_shortcode(self, url):
        """Extract shortcode from Instagram URL"""
        patterns = [
            r'instagram\.com/reel/([^/?]+)',
            r'instagram\.com/p/([^/?]+)',
            r'instagram\.com/stories/([^/?]+)',
            r'instagram\.com/tv/([^/?]+)',
            r'reel/([^/?]+)',
            r'p/([^/?]+)',
            r'stories/([^/?]+)',
            r'tv/([^/?]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    def find_highest_quality_video(self, video_data):
        """Find highest quality video from available video URLs"""
        if not video_data:
            return None
        
        # If video_data is a string (single URL)
        if isinstance(video_data, str):
            return video_data
        
        # If video_data is a list
        if isinstance(video_data, list):
            # Sort by quality indicators
            quality_order = ['1080', '720', '480', '360', '240']
            for quality in quality_order:
                for video in video_data:
                    if isinstance(video, str) and quality in video:
                        return video
            
            # Return first video if no quality found
            for video in video_data:
                if isinstance(video, str):
                    return video
        
        # If video_data is a dict with quality options
        if isinstance(video_data, dict):
            # Check for specific quality keys
            quality_keys = ['hd', 'high', '1080', '720', 'sd', 'low']
            for key in quality_keys:
                if key in video_data:
                    return video_data[key]
            
            # Return first value
            for key, value in video_data.items():
                if value:
                    return value
        
        return None
    
    def find_highest_quality_image(self, image_data):
        """Find highest quality image from available image URLs"""
        if not image_data:
            return None
        
        # If image_data is a string (single URL)
        if isinstance(image_data, str):
            return image_data
        
        # If image_data is a list
        if isinstance(image_data, list):
            # Sort by size indicators
            size_order = ['1080', '2048', '1536', '1280', '1024', '800', '640', '480', '320']
            for size in size_order:
                for img in image_data:
                    if isinstance(img, str) and size in img:
                        return img
            
            # Return largest image by looking at dimensions in URL
            max_size = 0
            best_image = None
            for img in image_data:
                if isinstance(img, str):
                    # Try to extract dimensions from URL
                    size_match = re.search(r'(\d{3,4})x(\d{3,4})', img)
                    if size_match:
                        size = int(size_match.group(1)) * int(size_match.group(2))
                        if size > max_size:
                            max_size = size
                            best_image = img
            
            if best_image:
                return best_image
            
            # Return first image
            for img in image_data:
                if isinstance(img, str):
                    return img
        
        # If image_data is a dict
        if isinstance(image_data, dict):
            # Check for specific size keys
            size_keys = ['hd', 'high', '1080', '720', 'large', 'medium', 'small']
            for key in size_keys:
                if key in image_data:
                    return image_data[key]
            
            # Return first value
            for key, value in image_data.items():
                if value:
                    return value
        
        return None
    
    def extract_from_shared_data(self, html_content):
        """Extract media data from Instagram's shared data"""
        try:
            # Look for the shared data script
            pattern = r'<script[^>]*>window\._sharedData\s*=\s*({.*?});</script>'
            match = re.search(pattern, html_content, re.DOTALL)
            
            if match:
                shared_data = json.loads(match.group(1))
                
                # Navigate through the data structure
                post_data = None
                
                # Check entry data
                if 'entry_data' in shared_data:
                    for key, data in shared_data['entry_data'].items():
                        if isinstance(data, list) and len(data) > 0:
                            post_data = data[0]
                            break
                
                if not post_data:
                    return None
                
                # Extract from GraphQL
                if 'graphql' in post_data:
                    media_data = post_data['graphql'].get('shortcode_media', {})
                    return self.extract_from_graphql(media_data)
                
                # Extract from PostPage
                elif 'PostPage' in post_data:
                    for page in post_data['PostPage']:
                        if 'graphql' in page:
                            media_data = page['graphql'].get('shortcode_media', {})
                            return self.extract_from_graphql(media_data)
            
            return None
            
        except Exception as e:
            print(f"Error extracting shared data: {str(e)}")
            return None
    
    def extract_from_graphql(self, media_data):
        """Extract media from GraphQL data structure"""
        try:
            result = {
                'type': None,
                'urls': [],
                'is_video': False,
                'is_carousel': False,
                'caption': None,
                'dimensions': None,
                'display_url': None
            }
            
            if not media_data:
                return None
            
            # Get media type
            result['type'] = media_data.get('__typename')
            result['is_video'] = media_data.get('is_video', False)
            result['caption'] = media_data.get('edge_media_to_caption', {}).get('edges', [{}])[0].get('node', {}).get('text', '')
            result['dimensions'] = media_data.get('dimensions', {})
            
            # Handle single image/video
            if result['type'] == 'GraphImage':
                # Get display URL
                display_url = media_data.get('display_url')
                if display_url:
                    result['display_url'] = display_url
                    result['urls'].append({
                        'url': display_url,
                        'type': 'image',
                        'quality': 'display'
                    })
                
                # Get high quality images
                if 'display_resources' in media_data:
                    for resource in media_data['display_resources']:
                        if 'src' in resource:
                            result['urls'].append({
                                'url': resource['src'],
                                'type': 'image',
                                'quality': f"{resource.get('config_width', 0)}x{resource.get('config_height', 0)}"
                            })
                
                # Get original image
                if 'thumbnail_resources' in media_data:
                    for resource in media_data['thumbnail_resources']:
                        if 'src' in resource and 'original' in resource['src']:
                            result['urls'].append({
                                'url': resource['src'],
                                'type': 'image',
                                'quality': 'original'
                            })
            
            # Handle video
            elif result['type'] == 'GraphVideo':
                result['is_video'] = True
                
                # Get video URL
                video_url = media_data.get('video_url')
                if video_url:
                    result['display_url'] = video_url
                    result['urls'].append({
                        'url': video_url,
                        'type': 'video',
                        'quality': 'video_url'
                    })
                
                # Get display URL for thumbnail
                display_url = media_data.get('display_url')
                if display_url:
                    result['urls'].append({
                        'url': display_url,
                        'type': 'image',
                        'quality': 'thumbnail'
                    })
            
            # Handle carousel (multiple images/videos)
            elif result['type'] == 'GraphSidecar':
                result['is_carousel'] = True
                
                edges = media_data.get('edge_sidecar_to_children', {}).get('edges', [])
                for edge in edges:
                    node = edge.get('node', {})
                    node_type = node.get('__typename')
                    
                    if node_type == 'GraphImage':
                        # Get display URL
                        display_url = node.get('display_url')
                        if display_url:
                            result['urls'].append({
                                'url': display_url,
                                'type': 'image',
                                'quality': 'display'
                            })
                        
                        # Get high quality images
                        if 'display_resources' in node:
                            for resource in node['display_resources']:
                                if 'src' in resource:
                                    result['urls'].append({
                                        'url': resource['src'],
                                        'type': 'image',
                                        'quality': f"{resource.get('config_width', 0)}x{resource.get('config_height', 0)}"
                                    })
                    
                    elif node_type == 'GraphVideo':
                        # Get video URL
                        video_url = node.get('video_url')
                        if video_url:
                            result['urls'].append({
                                'url': video_url,
                                'type': 'video',
                                'quality': 'video_url'
                            })
            
            return result if result['urls'] else None
            
        except Exception as e:
            print(f"Error extracting from GraphQL: {str(e)}")
            return None
    
    def extract_from_alternative_sources(self, html_content):
        """Extract media from alternative sources in HTML"""
        try:
            # Look for JavaScript data
            patterns = [
                r'"display_url":"([^"]+)"',
                r'"displayUrl":"([^"]+)"',
                r'"video_url":"([^"]+)"',
                r'"videoUrl":"([^"]+)"',
                r'"thumbnail_src":"([^"]+)"',
                r'"thumbnailSrc":"([^"]+)"',
                r'"src":"([^"]+\.(?:jpg|jpeg|png|mp4)[^"]*)"',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, html_content)
                for match in matches:
                    if match and ('instagram.com' in match or 'cdninstagram.com' in match):
                        return match
            
            return None
            
        except Exception as e:
            print(f"Error extracting from alternative sources: {str(e)}")
            return None
    
    def extract_high_quality_media(self, html_content):
        """Extract high quality media using multiple methods"""
        # Method 1: Extract from shared data (best quality)
        print("Trying Method 1: Shared Data...")
        graphql_data = self.extract_from_shared_data(html_content)
        
        if graphql_data and graphql_data['urls']:
            print(f"Found media via GraphQL: {len(graphql_data['urls'])} items")
            return graphql_data
        
        # Method 2: Extract from meta tags
        print("Trying Method 2: Meta Tags...")
        
        # Look for Open Graph meta tags (usually good quality)
        meta_patterns = {
            'og:image': r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"',
            'og:video': r'<meta[^>]*property="og:video"[^>]*content="([^"]+)"',
            'og:video:secure_url': r'<meta[^>]*property="og:video:secure_url"[^>]*content="([^"]+)"',
            'twitter:image': r'<meta[^>]*name="twitter:image"[^>]*content="([^"]+)"',
            'twitter:player:stream': r'<meta[^>]*name="twitter:player:stream"[^>]*content="([^"]+)"',
        }
        
        media_urls = []
        is_video = False
        
        for meta_type, pattern in meta_patterns.items():
            matches = re.findall(pattern, html_content)
            for match in matches:
                if match:
                    media_type = 'video' if 'video' in meta_type else 'image'
                    if 'video' in meta_type:
                        is_video = True
                    
                    media_urls.append({
                        'url': match,
                        'type': media_type,
                        'quality': meta_type
                    })
        
        if media_urls:
            return {
                'type': 'MetaTags',
                'urls': media_urls,
                'is_video': is_video,
                'is_carousel': False,
                'caption': None,
                'dimensions': None,
                'display_url': media_urls[0]['url'] if media_urls else None
            }
        
        # Method 3: Extract from JSON-LD
        print("Trying Method 3: JSON-LD...")
        json_ld_pattern = r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>'
        matches = re.findall(json_ld_pattern, html_content, re.DOTALL)
        
        for json_str in matches:
            try:
                data = json.loads(json_str)
                if isinstance(data, dict) and 'video' in data:
                    video_data = data['video']
                    if isinstance(video_data, dict):
                        video_url = video_data.get('contentUrl') or video_data.get('embedUrl')
                        if video_url:
                            return {
                                'type': 'JSON-LD',
                                'urls': [{
                                    'url': video_url,
                                    'type': 'video',
                                    'quality': 'json-ld'
                                }],
                                'is_video': True,
                                'is_carousel': False,
                                'caption': None,
                                'dimensions': None,
                                'display_url': video_url
                            }
            except:
                continue
        
        return None
    
    def get_best_quality_url(self, media_data):
        """Get the best quality URL from media data"""
        if not media_data or not media_data.get('urls'):
            return None
        
        urls = media_data['urls']
        
        # For videos, prioritize video URLs
        if media_data.get('is_video'):
            video_urls = [u for u in urls if u['type'] == 'video']
            if video_urls:
                # Sort by quality indicators
                quality_order = ['video_url', 'hd', '1080', '720', '480', '360']
                for quality in quality_order:
                    for url_info in video_urls:
                        if quality in url_info['quality'].lower():
                            return url_info['url']
                
                # Return first video URL
                return video_urls[0]['url']
        
        # For images, prioritize display URLs
        image_urls = [u for u in urls if u['type'] == 'image']
        if image_urls:
            # Sort by quality indicators
            quality_order = ['display', 'original', '2048', '1536', '1080', 'hd', 'high', 'large']
            for quality in quality_order:
                for url_info in image_urls:
                    if quality in url_info['quality'].lower():
                        return url_info['url']
            
            # Return first image URL
            return image_urls[0]['url']
        
        # Return first URL
        return urls[0]['url'] if urls else None
    
    def fix_url_formatting(self, url):
        """Fix URL formatting issues"""
        if not url:
            return None
        
        # Fix escaped characters
        url = url.replace('\\/', '/').replace('\\\\/', '/')
        url = url.replace('\\u0026', '&').replace('\\u002F', '/')
        url = url.replace('\\u003D', '=').replace('\\u003F', '?')
        
        # Ensure proper protocol
        if url.startswith('//'):
            url = 'https:' + url
        elif not url.startswith('http'):
            url = 'https://' + url
        
        return url
    
    def download_media(self, url):
        """Main function to download media"""
        print(f"Processing URL: {url}")
        
        # Get HTML content
        html_content = self.get_instagram_page(url)
        if not html_content:
            return {
                'success': False,
                'error': 'Failed to fetch Instagram page'
            }
        
        # Extract media data
        media_data = self.extract_high_quality_media(html_content)
        
        if media_data:
            # Get best quality URL
            best_url = self.get_best_quality_url(media_data)
            
            if best_url:
                best_url = self.fix_url_formatting(best_url)
                
                return {
                    'success': True,
                    'media_type': 'video' if media_data['is_video'] else 'image',
                    'media_url': best_url,
                    'all_urls': media_data['urls'],
                    'is_carousel': media_data.get('is_carousel', False),
                    'caption': media_data.get('caption'),
                    'dimensions': media_data.get('dimensions'),
                    'method': media_data.get('type', 'unknown')
                }
        
        # Fallback: Try alternative extraction
        print("Trying fallback methods...")
        fallback_url = self.extract_from_alternative_sources(html_content)
        
        if fallback_url:
            fallback_url = self.fix_url_formatting(fallback_url)
            
            # Determine media type
            is_video = '.mp4' in fallback_url.lower()
            
            return {
                'success': True,
                'media_type': 'video' if is_video else 'image',
                'media_url': fallback_url,
                'method': 'fallback'
            }
        
        return {
            'success': False,
            'error': 'Could not extract media. The post might be private or require login.'
        }

# Initialize downloader
downloader = InstagramSelfDownloader()

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Instagram Downloader - High Quality ✓</title>
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
        
        .media-info p {
            margin-bottom: 8px;
            color: #333;
        }
        
        .media-info span {
            color: #405DE6;
            font-weight: 700;
            background: #eef2ff;
            padding: 3px 8px;
            border-radius: 4px;
        }
        
        .media-preview {
            margin: 20px 0;
            text-align: center;
        }
        
        .media-preview img,
        .media-preview video {
            max-width: 100%;
            max-height: 500px;
            border-radius: 12px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        }
        
        .quality-options {
            background: white;
            padding: 15px;
            border-radius: 10px;
            margin-top: 20px;
            border-left: 4px solid #405DE6;
        }
        
        .quality-options h4 {
            color: #333;
            margin-bottom: 10px;
        }
        
        .quality-list {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 10px;
        }
        
        .quality-item {
            padding: 8px 15px;
            background: #f8f9fa;
            border-radius: 6px;
            border: 1px solid #dee2e6;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .quality-item:hover {
            background: #e9ecef;
            border-color: #405DE6;
        }
        
        .quality-item.active {
            background: #405DE6;
            color: white;
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
        
        .feature-list {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 15px;
            margin-top: 30px;
        }
        
        .feature-card {
            background: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            box-shadow: 0 5px 15px rgba(0,0,0,0.05);
            border-top: 4px solid #405DE6;
        }
        
        .feature-card i {
            font-size: 2rem;
            color: #405DE6;
            margin-bottom: 10px;
        }
        
        .feature-card h4 {
            color: #333;
            margin-bottom: 8px;
        }
        
        .feature-card p {
            color: #666;
            font-size: 0.9rem;
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
            
            .feature-list {
                grid-template-columns: 1fr;
            }
        }
    </style>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
</head>
<body>
    <div class="container">
        <div class="header">
            <h1><i class="fab fa-instagram"></i> Instagram Downloader</h1>
            <p>Download Posts, Reels, Stories in Highest Quality • No Watermark</p>
            <div class="badge">✓ HIGH QUALITY DOWNLOAD</div>
        </div>
        
        <div class="content">
            <div class="input-section">
                <h2 style="color: #333; margin-bottom: 20px; font-size: 1.6rem;">Download Instagram Media</h2>
                
                <div class="input-group">
                    <input type="text" id="urlInput" placeholder="Paste Instagram Post/Reel/Story URL here...">
                    <button onclick="downloadMedia()">
                        <i class="fas fa-download"></i> Download
                    </button>
                </div>
                
                <div class="feature-list">
                    <div class="feature-card">
                        <i class="fas fa-images"></i>
                        <h4>HD Photos</h4>
                        <p>Download images in original high resolution</p>
                    </div>
                    
                    <div class="feature-card">
                        <i class="fas fa-video"></i>
                        <h4>Full HD Videos</h4>
                        <p>Get videos in highest available quality</p>
                    </div>
                    
                    <div class="feature-card">
                        <i class="fas fa-layer-group"></i>
                        <h4>Carousel Posts</h4>
                        <p>Download multiple images/videos from posts</p>
                    </div>
                    
                    <div class="feature-card">
                        <i class="fas fa-expand-arrows-alt"></i>
                        <h4>Full Size</h4>
                        <p>Get media in original dimensions</p>
                    </div>
                </div>
            </div>
            
            <div class="loader" id="loader">
                <div class="spinner"></div>
                <p style="font-size: 1.1rem; color: #666;">Extracting highest quality media...</p>
                <p id="statusText" style="margin-top: 10px; color: #888; font-size: 0.9rem;"></p>
            </div>
            
            <div class="error" id="error"></div>
            
            <div class="result" id="result">
                <h3><i class="fas fa-check-circle"></i> Media Found!</h3>
                
                <div class="media-info">
                    <p>
                        <strong>Type:</strong> 
                        <span id="mediaType" style="text-transform: uppercase;"></span>
                    </p>
                    <p>
                        <strong>Quality:</strong> 
                        <span id="qualityType">HIGHEST</span>
                    </p>
                    <p>
                        <strong>Method:</strong> 
                        <span id="methodName"></span>
                    </p>
                    <p id="dimensionsInfo" style="display: none;">
                        <strong>Dimensions:</strong> 
                        <span id="dimensions"></span>
                    </p>
                    <p id="captionInfo" style="display: none;">
                        <strong>Caption:</strong> 
                        <span id="caption"></span>
                    </p>
                </div>
                
                <div class="media-preview" id="mediaPreview">
                    <!-- Media will be inserted here -->
                </div>
                
                <div class="quality-options" id="qualityOptions" style="display: none;">
                    <h4><i class="fas fa-sliders-h"></i> Available Qualities</h4>
                    <div class="quality-list" id="qualityList">
                        <!-- Quality options will be inserted here -->
                    </div>
                </div>
                
                <div class="actions">
                    <a href="#" id="downloadLink" class="btn btn-download" target="_blank">
                        <i class="fas fa-download"></i> Download Now
                    </a>
                    <button onclick="copyUrl()" class="btn btn-copy">
                        <i class="fas fa-copy"></i> Copy URL
                    </button>
                    <button onclick="resetForm()" class="btn btn-new">
                        <i class="fas fa-redo"></i> Try Another
                    </button>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let currentMediaData = null;
        let currentQualityIndex = 0;
        
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
                'Fetching Instagram page...',
                'Analyzing media content...',
                'Extracting highest quality...',
                'Preparing download...',
                'Almost ready...'
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
                    document.getElementById('mediaType').textContent = data.media_type;
                    document.getElementById('methodName').textContent = data.method;
                    document.getElementById('downloadLink').href = data.media_url;
                    
                    // Show dimensions if available
                    if (data.dimensions) {
                        document.getElementById('dimensions').textContent = 
                            `${data.dimensions.width} × ${data.dimensions.height}`;
                        document.getElementById('dimensionsInfo').style.display = 'block';
                    }
                    
                    // Show caption if available
                    if (data.caption) {
                        const caption = data.caption.length > 100 ? 
                            data.caption.substring(0, 100) + '...' : data.caption;
                        document.getElementById('caption').textContent = caption;
                        document.getElementById('captionInfo').style.display = 'block';
                    }
                    
                    // Update media preview
                    const mediaPreview = document.getElementById('mediaPreview');
                    
                    if (data.media_type === 'video') {
                        mediaPreview.innerHTML = `
                            <div style="background: #000; border-radius: 10px; padding: 10px; margin-bottom: 15px;">
                                <video controls style="width: 100%; max-width: 500px; border-radius: 8px;">
                                    <source src="${data.media_url}" type="video/mp4">
                                    Your browser does not support video playback.
                                </video>
                            </div>
                            <p style="color: #666; font-size: 0.9rem;">
                                <i class="fas fa-info-circle"></i> Click play to preview the video
                            </p>
                        `;
                    } else {
                        mediaPreview.innerHTML = `
                            <div style="background: #000; border-radius: 10px; padding: 10px; margin-bottom: 15px;">
                                <img src="${data.media_url}" 
                                     style="max-width: 100%; max-height: 500px; border-radius: 8px;"
                                     alt="Instagram Image Preview"
                                     onerror="this.onerror=null; this.src='https://via.placeholder.com/500x500?text=Image+Loading+Error'">
                            </div>
                            <p style="color: #666; font-size: 0.9rem;">
                                <i class="fas fa-info-circle"></i> High quality image preview
                            </p>
                        `;
                    }
                    
                    // Show quality options if multiple URLs available
                    if (data.all_urls && data.all_urls.length > 1) {
                        showQualityOptions(data.all_urls);
                    }
                    
                    // Show result
                    result.style.display = 'block';
                    
                    // Auto-scroll to result
                    result.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    
                } else {
                    showError(data.error || 'Failed to extract media. The post might be private or restricted.');
                }
                
            } catch (error) {
                clearInterval(statusInterval);
                loader.style.display = 'none';
                showError('Network error: ' + error.message);
            }
        }
        
        function showQualityOptions(urls) {
            const qualityOptions = document.getElementById('qualityOptions');
            const qualityList = document.getElementById('qualityList');
            
            qualityList.innerHTML = '';
            
            urls.forEach((urlInfo, index) => {
                const qualityDiv = document.createElement('div');
                qualityDiv.className = `quality-item ${index === 0 ? 'active' : ''}`;
                qualityDiv.innerHTML = `
                    <div style="font-weight: 600;">${urlInfo.quality}</div>
                    <div style="font-size: 0.8rem; color: #666;">${urlInfo.type}</div>
                `;
                
                qualityDiv.onclick = () => selectQuality(urlInfo, index);
                qualityList.appendChild(qualityDiv);
            });
            
            qualityOptions.style.display = 'block';
        }
        
        function selectQuality(urlInfo, index) {
            if (!currentMediaData) return;
            
            // Update active class
            document.querySelectorAll('.quality-item').forEach((item, i) => {
                item.classList.toggle('active', i === index);
            });
            
            // Update current URL
            currentQualityIndex = index;
            
            // Update download link
            document.getElementById('downloadLink').href = urlInfo.url;
            
            // Update preview
            const mediaPreview = document.getElementById('mediaPreview');
            
            if (urlInfo.type === 'video') {
                mediaPreview.innerHTML = `
                    <div style="background: #000; border-radius: 10px; padding: 10px; margin-bottom: 15px;">
                        <video controls style="width: 100%; max-width: 500px; border-radius: 8px;">
                            <source src="${urlInfo.url}" type="video/mp4">
                            Your browser does not support video playback.
                        </video>
                    </div>
                    <p style="color: #666; font-size: 0.9rem;">
                        <i class="fas fa-info-circle"></i> ${urlInfo.quality} quality
                    </p>
                `;
            } else {
                mediaPreview.innerHTML = `
                    <div style="background: #000; border-radius: 10px; padding: 10px; margin-bottom: 15px;">
                        <img src="${urlInfo.url}" 
                             style="max-width: 100%; max-height: 500px; border-radius: 8px;"
                             alt="Instagram Image Preview"
                             onerror="this.onerror=null; this.src='https://via.placeholder.com/500x500?text=Image+Loading+Error'">
                    </div>
                    <p style="color: #666; font-size: 0.9rem;">
                        <i class="fas fa-info-circle"></i> ${urlInfo.quality} quality
                    </p>
                `;
            }
            
            // Update quality type display
            document.getElementById('qualityType').textContent = urlInfo.quality.toUpperCase();
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
        
        function copyUrl() {
            if (currentMediaData && currentMediaData.media_url) {
                const urlToCopy = currentMediaData.all_urls && currentMediaData.all_urls[currentQualityIndex] ?
                    currentMediaData.all_urls[currentQualityIndex].url : currentMediaData.media_url;
                
                navigator.clipboard.writeText(urlToCopy)
                    .then(() => {
                        alert('✓ Media URL copied to clipboard!');
                    })
                    .catch(err => {
                        console.error('Copy failed:', err);
                        alert('Failed to copy URL. Please try again.');
                    });
            }
        }
        
        function resetForm() {
            document.getElementById('urlInput').value = '';
            document.getElementById('result').style.display = 'none';
            document.getElementById('error').style.display = 'none';
            document.getElementById('urlInput').focus();
            currentMediaData = null;
            currentQualityIndex = 0;
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
        
        # Download media using our downloader
        result = downloader.download_media(url)
        
        # Fix URL formatting before returning
        if result.get('success') and 'media_url' in result:
            result['media_url'] = downloader.fix_url_formatting(result['media_url'])
            
            # Fix all URLs
            if 'all_urls' in result:
                for url_info in result['all_urls']:
                    if 'url' in url_info:
                        url_info['url'] = downloader.fix_url_formatting(url_info['url'])
        
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
        'service': 'Instagram High Quality Downloader',
        'version': '2.0.0',
        'features': ['HD Images', 'Full HD Videos', 'Carousel Posts', 'High Quality'],
        'working': 'YES'
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
[file content end]
