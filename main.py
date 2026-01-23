import os
import re
import json
import requests
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from urllib.parse import urlparse, parse_qs, unquote
import time
import mimetypes

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
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/heic,image/heif,*/*;q=0.8',
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
    
    def detect_media_type_from_url(self, url):
        """Detect media type from URL"""
        if not url:
            return 'unknown'
        
        url_lower = url.lower()
        
        # Video formats
        video_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv']
        for ext in video_extensions:
            if ext in url_lower:
                return 'video'
        
        # Image formats (including HEIC/HEIF)
        image_extensions = [
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', 
            '.heic', '.heif', '.tiff', '.svg'
        ]
        for ext in image_extensions:
            if ext in url_lower:
                return 'image'
        
        # Check URL patterns
        if '/reel/' in url or '/tv/' in url:
            return 'video'
        elif 'video' in url_lower:
            return 'video'
        elif 'image' in url_lower or 'jpg' in url_lower or 'png' in url_lower:
            return 'image'
        
        # Check query parameters
        parsed_url = urlparse(url)
        if 'heic' in parsed_url.path.lower():
            return 'image'
        
        return 'unknown'
    
    def convert_heic_to_jpg_url(self, url):
        """Convert HEIC URL to JPG URL if possible"""
        if not url:
            return url
        
        # If it's already a HEIC URL, try to convert to JPG
        if '.heic' in url.lower():
            # Try different conversions
            jpg_url = url.replace('.heic', '.jpg').replace('.HEIC', '.jpg')
            
            # Also try to remove format parameters
            parsed_url = urlparse(url)
            path = parsed_url.path
            
            # Check if path ends with .heic
            if path.lower().endswith('.heic'):
                # Try with .jpg extension
                base_path = path[:-5]  # Remove .heic
                new_path = base_path + '.jpg'
                
                # Reconstruct URL
                jpg_url = parsed_url._replace(path=new_path).geturl()
                
                # Try both variations
                return jpg_url
        
        return url
    
    def get_best_image_url(self, url):
        """Get the best quality image URL"""
        if not url:
            return url
        
        # Try to get higher quality versions
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        
        # Remove size limitations
        for param in ['stp', 'width', 'height', 'size', 'w', 'h']:
            if param in query_params:
                del query_params[param]
        
        # Reconstruct URL without size limits
        new_query = '&'.join([f"{k}={v[0]}" for k, v in query_params.items()])
        best_url = parsed_url._replace(query=new_query).geturl()
        
        # Try to remove quality parameters that might limit resolution
        patterns_to_remove = [
            r'&w=\d+',
            r'&h=\d+',
            r'&size=\d+',
            r'&stp=[^&]*',
            r'c\d+\.\d+\.\d+\.\d+',  # Crop patterns like c288.0.864.864
        ]
        
        for pattern in patterns_to_remove:
            best_url = re.sub(pattern, '', best_url)
        
        # For HEIC, try to get JPG version
        if '.heic' in best_url.lower():
            jpg_url = self.convert_heic_to_jpg_url(best_url)
            return jpg_url
        
        return best_url
    
    def extract_media_urls_from_html(self, html_content):
        """Extract all media URLs from HTML"""
        urls = []
        
        # Look for all possible media URLs
        patterns = [
            r'"display_url":"([^"]+)"',
            r'"displayUrl":"([^"]+)"',
            r'"video_url":"([^"]+)"',
            r'"videoUrl":"([^"]+)"',
            r'"thumbnail_src":"([^"]+)"',
            r'"thumbnailSrc":"([^"]+)"',
            r'"src":"([^"]+)"',
            r'content="([^"]+\.(?:mp4|jpg|jpeg|png|gif|webp|heic|heif))"',
            r'src="([^"]+\.(?:mp4|jpg|jpeg|png|gif|webp|heic|heif))"',
            r'url="([^"]+\.(?:mp4|jpg|jpeg|png|gif|webp|heic|heif))"',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            for match in matches:
                if match and ('instagram.com' in match or 'cdninstagram.com' in match or 'fbcdn.net' in match):
                    # Clean URL
                    clean_url = match.replace('\\/', '/').replace('\\u0026', '&')
                    
                    # Detect media type
                    media_type = self.detect_media_type_from_url(clean_url)
                    
                    # Get quality indicator
                    quality = self.get_quality_indicator(clean_url)
                    
                    urls.append({
                        'url': clean_url,
                        'type': media_type,
                        'quality': quality,
                        'original_url': clean_url
                    })
        
        # Remove duplicates
        unique_urls = []
        seen_urls = set()
        for url_info in urls:
            if url_info['url'] not in seen_urls:
                seen_urls.add(url_info['url'])
                unique_urls.append(url_info)
        
        return unique_urls
    
    def get_quality_indicator(self, url):
        """Get quality indicator from URL"""
        if not url:
            return 'unknown'
        
        url_lower = url.lower()
        
        # Check for size indicators
        if '1080' in url_lower:
            return '1080p'
        elif '720' in url_lower:
            return '720p'
        elif '480' in url_lower:
            return '480p'
        elif '360' in url_lower:
            return '360p'
        elif 'hd' in url_lower:
            return 'hd'
        elif 'high' in url_lower:
            return 'high'
        elif 'low' in url_lower:
            return 'low'
        
        # Check for image size patterns
        size_match = re.search(r'(\d{3,4})x(\d{3,4})', url_lower)
        if size_match:
            width = int(size_match.group(1))
            height = int(size_match.group(2))
            if width >= 1920 or height >= 1080:
                return 'full_hd'
            elif width >= 1280 or height >= 720:
                return 'hd'
            else:
                return f"{width}x{height}"
        
        return 'standard'
    
    def sort_urls_by_quality(self, urls):
        """Sort URLs by quality (highest first)"""
        quality_order = {
            'full_hd': 10,
            '1080p': 9,
            'hd': 8,
            '720p': 7,
            'high': 6,
            'standard': 5,
            '480p': 4,
            '360p': 3,
            'low': 2,
            'unknown': 1
        }
        
        def quality_score(url_info):
            quality = url_info.get('quality', 'unknown').lower()
            # Get base score
            score = quality_order.get(quality, 0)
            
            # Bonus for larger images
            if url_info['type'] == 'image':
                size_match = re.search(r'(\d{3,4})x(\d{3,4})', url_info['url'].lower())
                if size_match:
                    width = int(size_match.group(1))
                    height = int(size_match.group(2))
                    score += (width * height) / 1000000  # Add based on megapixels
            
            return score
        
        return sorted(urls, key=quality_score, reverse=True)
    
    def get_direct_media_from_url(self, url):
        """Get direct media URL from Instagram CDN link"""
        try:
            # If it's already a direct CDN link
            if 'cdninstagram.com' in url or 'fbcdn.net' in url:
                # Clean up the URL
                parsed_url = urlparse(url)
                
                # Remove tracking parameters
                clean_params = {}
                for key, value in parse_qs(parsed_url.query).items():
                    if key not in ['_nc_cat', '_nc_sid', '_nc_ohc', '_nc_oc', 
                                  '_nc_zt', '_nc_ht', '_nc_gid', 'oh', 'oe']:
                        clean_params[key] = value[0]
                
                # Reconstruct URL
                new_query = '&'.join([f"{k}={v}" for k, v in clean_params.items()])
                clean_url = parsed_url._replace(query=new_query).geturl()
                
                # Detect media type
                media_type = self.detect_media_type_from_url(clean_url)
                
                # For HEIC images, try to get JPG version
                if media_type == 'image' and '.heic' in clean_url.lower():
                    jpg_url = self.convert_heic_to_jpg_url(clean_url)
                    if jpg_url != clean_url:
                        return {
                            'url': jpg_url,
                            'type': 'image',
                            'quality': 'converted_jpg',
                            'original_heic': clean_url
                        }
                
                return {
                    'url': clean_url,
                    'type': media_type,
                    'quality': self.get_quality_indicator(clean_url),
                    'is_direct': True
                }
            
            return None
            
        except Exception as e:
            print(f"Error processing direct URL: {str(e)}")
            return None
    
    def extract_from_shared_data(self, html_content):
        """Extract media from shared data"""
        try:
            pattern = r'<script[^>]*>window\._sharedData\s*=\s*({.*?});</script>'
            match = re.search(pattern, html_content, re.DOTALL)
            
            if match:
                shared_data = json.loads(match.group(1))
                
                # Navigate to get media URLs
                entry_data = shared_data.get('entry_data', {})
                
                for page_type, pages in entry_data.items():
                    if isinstance(pages, list) and pages:
                        for page in pages:
                            if 'graphql' in page:
                                media_data = page['graphql'].get('shortcode_media', {})
                                
                                # Get display URL
                                display_url = media_data.get('display_url')
                                if display_url:
                                    return [{
                                        'url': display_url,
                                        'type': 'image',
                                        'quality': 'display',
                                        'from_graphql': True
                                    }]
                                
                                # Get video URL
                                video_url = media_data.get('video_url')
                                if video_url:
                                    return [{
                                        'url': video_url,
                                        'type': 'video',
                                        'quality': 'video',
                                        'from_graphql': True
                                    }]
                
            return None
            
        except Exception as e:
            print(f"Error extracting shared data: {str(e)}")
            return None
    
    def process_media_url(self, url_info):
        """Process and enhance media URL"""
        processed = url_info.copy()
        
        # Clean URL
        url = processed['url']
        url = url.replace('\\/', '/').replace('\\u0026', '&').replace('\\u003D', '=')
        
        # Ensure proper protocol
        if url.startswith('//'):
            url = 'https:' + url
        elif not url.startswith('http'):
            url = 'https://' + url
        
        processed['url'] = url
        
        # For images, try to get best quality
        if processed['type'] == 'image':
            best_url = self.get_best_image_url(url)
            if best_url != url:
                processed['url'] = best_url
                processed['quality'] = 'optimized'
        
        return processed
    
    def download_media(self, input_url):
        """Main function to download media"""
        print(f"Processing URL: {input_url}")
        
        # Check if it's already a direct CDN link
        direct_media = self.get_direct_media_from_url(input_url)
        if direct_media:
            print(f"Direct CDN link detected: {direct_media['type']}")
            return {
                'success': True,
                'media_type': direct_media['type'],
                'media_url': direct_media['url'],
                'all_urls': [direct_media],
                'is_direct': True,
                'method': 'direct_cdn'
            }
        
        # Otherwise, fetch Instagram page
        html_content = self.get_instagram_page(input_url)
        if not html_content:
            return {
                'success': False,
                'error': 'Failed to fetch Instagram page'
            }
        
        # Try multiple extraction methods
        all_urls = []
        
        # Method 1: Extract from shared data
        shared_data_urls = self.extract_from_shared_data(html_content)
        if shared_data_urls:
            all_urls.extend(shared_data_urls)
        
        # Method 2: Extract from HTML
        html_urls = self.extract_media_urls_from_html(html_content)
        all_urls.extend(html_urls)
        
        # Method 3: Look for meta tags
        meta_patterns = [
            r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"',
            r'<meta[^>]*property="og:video"[^>]*content="([^"]+)"',
            r'<meta[^>]*property="og:video:secure_url"[^>]*content="([^"]+)"',
            r'<meta[^>]*name="twitter:image"[^>]*content="([^"]+)"',
        ]
        
        for pattern in meta_patterns:
            matches = re.findall(pattern, html_content)
            for match in matches:
                if match and ('instagram.com' in match or 'cdninstagram.com' in match):
                    media_type = 'video' if 'video' in pattern else 'image'
                    all_urls.append({
                        'url': match,
                        'type': media_type,
                        'quality': 'meta_tag'
                    })
        
        if not all_urls:
            return {
                'success': False,
                'error': 'No media found on this page'
            }
        
        # Process all URLs
        processed_urls = []
        for url_info in all_urls:
            processed = self.process_media_url(url_info)
            processed_urls.append(processed)
        
        # Remove duplicates
        unique_urls = []
        seen_urls = set()
        for url_info in processed_urls:
            if url_info['url'] not in seen_urls:
                seen_urls.add(url_info['url'])
                unique_urls.append(url_info)
        
        # Sort by quality
        sorted_urls = self.sort_urls_by_quality(unique_urls)
        
        if not sorted_urls:
            return {
                'success': False,
                'error': 'Could not extract media URLs'
            }
        
        # Get best URL
        best_url_info = sorted_urls[0]
        
        return {
            'success': True,
            'media_type': best_url_info['type'],
            'media_url': best_url_info['url'],
            'all_urls': sorted_urls,
            'is_direct': False,
            'method': 'html_parsing',
            'total_found': len(sorted_urls)
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
        
        .note {
            background: #e7f3ff;
            padding: 15px;
            border-radius: 10px;
            margin-top: 20px;
            border-left: 4px solid #405DE6;
        }
        
        .note h4 {
            color: #405DE6;
            margin-bottom: 8px;
        }
        
        .note p {
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
                
                <div class="note">
                    <h4><i class="fas fa-lightbulb"></i> Pro Tip:</h4>
                    <p>You can also paste direct Instagram CDN links (like HEIC images) and we'll convert them to downloadable formats!</p>
                </div>
                
                <div class="feature-list">
                    <div class="feature-card">
                        <i class="fas fa-images"></i>
                        <h4>All Formats</h4>
                        <p>JPG, PNG, HEIC, MP4, and more</p>
                    </div>
                    
                    <div class="feature-card">
                        <i class="fas fa-compress-alt"></i>
                        <h4>HEIC Support</h4>
                        <p>Converts HEIC images to JPG</p>
                    </div>
                    
                    <div class="feature-card">
                        <i class="fas fa-expand-arrows-alt"></i>
                        <h4>Full Size</h4>
                        <p>Gets original resolution media</p>
                    </div>
                    
                    <div class="feature-card">
                        <i class="fas fa-bolt"></i>
                        <h4>Direct Links</h4>
                        <p>Works with direct CDN URLs too</p>
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
                    <p id="urlsFoundInfo" style="display: none;">
                        <strong>Found:</strong> 
                        <span id="urlsFound"></span> URLs
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
            
            // Show loader
            loader.style.display = 'block';
            
            // Update status messages
            const statusMessages = [
                'Processing URL...',
                'Checking media type...',
                'Extracting highest quality...',
                'Optimizing for download...',
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
                    
                    // Show URLs found count
                    if (data.total_found) {
                        document.getElementById('urlsFound').textContent = data.total_found;
                        document.getElementById('urlsFoundInfo').style.display = 'block';
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
                        // For HEIC images, show special note
                        let heicNote = '';
                        if (data.media_url.toLowerCase().includes('.heic')) {
                            heicNote = `
                                <div class="note" style="margin-top: 10px;">
                                    <p><i class="fas fa-exclamation-triangle"></i> HEIC format detected. Right-click and "Save as" to download.</p>
                                </div>
                            `;
                        }
                        
                        mediaPreview.innerHTML = `
                            <div style="background: #000; border-radius: 10px; padding: 10px; margin-bottom: 15px;">
                                <img src="${data.media_url}" 
                                     style="max-width: 100%; max-height: 500px; border-radius: 8px;"
                                     alt="Instagram Media Preview"
                                     onerror="this.onerror=null; this.src='https://via.placeholder.com/500x500?text=Image+Loading+Error'">
                            </div>
                            <p style="color: #666; font-size: 0.9rem;">
                                <i class="fas fa-info-circle"></i> High quality media preview
                            </p>
                            ${heicNote}
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
                    <div style="font-weight: 600;">${urlInfo.quality || 'standard'}</div>
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
            
            // Update quality type display
            document.getElementById('qualityType').textContent = (urlInfo.quality || 'STANDARD').toUpperCase();
            
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
                        <i class="fas fa-info-circle"></i> ${urlInfo.quality || 'Standard'} quality
                    </p>
                `;
            } else {
                // For HEIC images, show special note
                let heicNote = '';
                if (urlInfo.url.toLowerCase().includes('.heic')) {
                    heicNote = `
                        <div class="note" style="margin-top: 10px;">
                            <p><i class="fas fa-exclamation-triangle"></i> HEIC format detected. Right-click and "Save as" to download.</p>
                        </div>
                    `;
                }
                
                mediaPreview.innerHTML = `
                    <div style="background: #000; border-radius: 10px; padding: 10px; margin-bottom: 15px;">
                        <img src="${urlInfo.url}" 
                             style="max-width: 100%; max-height: 500px; border-radius: 8px;"
                             alt="Instagram Media Preview"
                             onerror="this.onerror=null; this.src='https://via.placeholder.com/500x500?text=Image+Loading+Error'">
                    </div>
                    <p style="color: #666; font-size: 0.9rem;">
                        <i class="fas fa-info-circle"></i> ${urlInfo.quality || 'Standard'} quality
                    </p>
                    ${heicNote}
                `;
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
            // Test with your HEIC URL
            document.getElementById('urlInput').value = 'https://scontent-den2-1.cdninstagram.com/v/t51.29350-15/472284890_576877441799553_5127931670163329588_n.heic?stp=c288.0.864.864a_dst-jpg_e35_s640x640_tt6&amp;_nc_cat=110&amp;ccb=7-5&amp;_nc_sid=18de74&amp;efg=eyJlZmdfdGFnIjoiQ0FST1VTRUxfSVRFTS5iZXN0X2ltYWdlX3VybGdlbi5DMyJ9&amp;_nc_ohc=OaSsbNblbxAQ7kNvwGH1acV&amp;_nc_oc=AdmA2uDrdA6--3xd9LHQM6cvy5_PC7Z6ffE3Ki8gkUHiz2XnOKJu4nZAQbEpI1yKH6g&amp;_nc_zt=23&amp;_nc_ht=scontent-den2-1.cdninstagram.com&amp;_nc_gid=XJRpi0e4VkALdtWVDt9HUQ&amp;oh=00_Afr_YTCZg5wiDawhSFAh-4wtK8TXE5se2ELZJPJuPxU1xQ&amp;oe=69797F97';
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
        
        # Clean URL - remove HTML entities
        url = url.replace('&amp;', '&')
        
        # Download media using our downloader
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
        'service': 'Instagram High Quality Downloader',
        'version': '3.0.0',
        'features': ['HEIC Support', 'Direct CDN Links', 'All Formats', 'High Quality'],
        'working': 'YES'
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
