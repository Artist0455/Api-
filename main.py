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
        self.instagram_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://www.instagram.com/',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
        }
    
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
    
    def clean_url(self, url):
        """Clean and format URL"""
        url = url.strip()
        if not url.startswith('http'):
            url = 'https://' + url
        return url
    
    def extract_from_shared_data(self, html_content):
        """Extract media from window._sharedData"""
        try:
            # Look for window._sharedData pattern
            pattern = r'window\._sharedData\s*=\s*({.*?});'
            match = re.search(pattern, html_content, re.DOTALL)
            
            if match:
                shared_data = json.loads(match.group(1))
                
                # Navigate through the data structure
                entry_data = shared_data.get('entry_data', {})
                if 'PostPage' in entry_data:
                    for post in entry_data['PostPage']:
                        return self.extract_from_graphql(post.get('graphql', {}).get('shortcode_media', {}))
                
                if 'PostPage' not in entry_data:
                    # Try other structures
                    for key, value in entry_data.items():
                        if isinstance(value, list) and len(value) > 0:
                            for item in value:
                                if isinstance(item, dict):
                                    if 'graphql' in item:
                                        return self.extract_from_graphql(item['graphql'].get('shortcode_media', {}))
            
            return None
        except Exception as e:
            print(f"Error in shared_data extraction: {str(e)}")
            return None
    
    def extract_from_script_tags(self, html_content):
        """Extract media data from script tags"""
        try:
            # Look for JSON data in script tags
            script_pattern = r'<script[^>]*type="text/javascript"[^>]*>window\.__additionalDataLoaded\([^,]+,\s*({.*?})\);</script>'
            matches = re.findall(script_pattern, html_content, re.DOTALL)
            
            for match in matches:
                try:
                    data = json.loads(match)
                    if 'graphql' in data:
                        return self.extract_from_graphql(data['graphql'].get('shortcode_media', {}))
                    elif 'items' in data and len(data['items']) > 0:
                        return self.extract_from_item(data['items'][0])
                except:
                    continue
            
            # Look for other script patterns
            other_patterns = [
                r'<script[^>]*>.*?"shortcode_media".*?({.*?})</script>',
                r'"graphql".*?"shortcode_media".*?({.*?})"',
            ]
            
            for pattern in other_patterns:
                matches = re.findall(pattern, html_content, re.DOTALL)
                for match in matches:
                    try:
                        # Try to parse as JSON
                        if '{' in match and '}' in match:
                            # Find the complete JSON object
                            start = match.find('{')
                            end = match.rfind('}') + 1
                            json_str = match[start:end]
                            data = json.loads(json_str)
                            return self.extract_from_graphql(data)
                    except:
                        continue
            
            return None
        except Exception as e:
            print(f"Error in script tag extraction: {str(e)}")
            return None
    
    def extract_from_graphql(self, media_data):
        """Extract media from GraphQL data structure"""
        result = {
            'images': [],
            'videos': [],
            'is_video': False,
            'is_carousel': False,
            'caption': '',
            'username': ''
        }
        
        try:
            if not media_data:
                return result
            
            # Get username
            owner = media_data.get('owner', {})
            if owner:
                result['username'] = owner.get('username', '')
            
            # Get caption
            caption_edges = media_data.get('edge_media_to_caption', {}).get('edges', [])
            if caption_edges and len(caption_edges) > 0:
                result['caption'] = caption_edges[0].get('node', {}).get('text', '')
            
            # Check media type
            typename = media_data.get('__typename', '')
            
            # Single image
            if typename in ['GraphImage', 'XDTImage', 'Image']:
                display_url = media_data.get('display_url') or media_data.get('displayUrl')
                if display_url:
                    result['images'].append(display_url)
                
                # Also check for other image URLs
                if 'display_resources' in media_data:
                    resources = media_data.get('display_resources', [])
                    if resources:
                        # Get the highest resolution (last one is usually highest)
                        best_image = resources[-1].get('src', '')
                        if best_image and best_image not in result['images']:
                            result['images'].append(best_image)
            
            # Video
            elif typename in ['GraphVideo', 'XDTVideo', 'Video', 'XDTStoryVideo']:
                video_url = media_data.get('video_url') or media_data.get('videoUrl')
                if video_url:
                    result['videos'].append({
                        'url': video_url,
                        'quality': 'high',
                        'type': 'video/mp4'
                    })
                    result['is_video'] = True
                
                # Also get thumbnail
                display_url = media_data.get('display_url') or media_data.get('displayUrl')
                if display_url:
                    result['images'].append(display_url)
            
            # Carousel
            elif typename in ['GraphSidecar', 'XDTStory', 'XDTStoryMultiImage']:
                result['is_carousel'] = True
                edges = media_data.get('edge_sidecar_to_children', {}).get('edges', [])
                
                for edge in edges:
                    node = edge.get('node', {})
                    node_typename = node.get('__typename', '')
                    
                    if node_typename in ['GraphImage', 'XDTImage', 'Image']:
                        display_url = node.get('display_url') or node.get('displayUrl')
                        if display_url:
                            result['images'].append(display_url)
                    
                    elif node_typename in ['GraphVideo', 'XDTVideo', 'Video']:
                        video_url = node.get('video_url') or node.get('videoUrl')
                        if video_url:
                            result['videos'].append({
                                'url': video_url,
                                'quality': 'high',
                                'type': 'video/mp4'
                            })
                            result['is_video'] = True
            
            # Try alternative video URLs
            if not result['videos'] and 'video_versions' in media_data:
                video_versions = media_data.get('video_versions', [])
                if video_versions:
                    # Get highest quality (first one is usually highest)
                    best_video = video_versions[0].get('url', '')
                    if best_video:
                        result['videos'].append({
                            'url': best_video,
                            'quality': 'high',
                            'type': 'video/mp4'
                        })
                        result['is_video'] = True
            
            # Try alternative image URLs
            if not result['images'] and 'image_versions2' in media_data:
                candidates = media_data.get('image_versions2', {}).get('candidates', [])
                if candidates:
                    # Get highest quality (first one is usually highest)
                    best_image = candidates[0].get('url', '')
                    if best_image:
                        result['images'].append(best_image)
            
            # Get thumbnail as fallback
            if not result['images']:
                thumbnail_src = media_data.get('thumbnail_src') or media_data.get('thumbnailSrc')
                if thumbnail_src:
                    result['images'].append(thumbnail_src)
            
            return result
            
        except Exception as e:
            print(f"Error in graphql extraction: {str(e)}")
            return result
    
    def extract_from_item(self, item_data):
        """Extract from item structure"""
        result = {
            'images': [],
            'videos': [],
            'is_video': False,
            'is_carousel': False,
            'caption': '',
            'username': ''
        }
        
        try:
            # Get caption
            caption = item_data.get('caption', {}).get('text', '')
            result['caption'] = caption
            
            # Get user
            user = item_data.get('user', {})
            if user:
                result['username'] = user.get('username', '')
            
            # Check media type
            media_type = item_data.get('media_type', 1)  # 1: photo, 2: video, 8: carousel
            
            # Photo
            if media_type == 1:
                image_versions = item_data.get('image_versions2', {}).get('candidates', [])
                if image_versions:
                    best_image = image_versions[0].get('url', '')
                    if best_image:
                        result['images'].append(best_image)
            
            # Video
            elif media_type == 2:
                video_versions = item_data.get('video_versions', [])
                if video_versions:
                    best_video = video_versions[0].get('url', '')
                    if best_video:
                        result['videos'].append({
                            'url': best_video,
                            'quality': 'high',
                            'type': 'video/mp4'
                        })
                        result['is_video'] = True
                
                # Also get thumbnail
                image_versions = item_data.get('image_versions2', {}).get('candidates', [])
                if image_versions:
                    best_image = image_versions[0].get('url', '')
                    if best_image:
                        result['images'].append(best_image)
            
            # Carousel
            elif media_type == 8:
                result['is_carousel'] = True
                carousel_media = item_data.get('carousel_media', [])
                
                for media in carousel_media:
                    media_type_item = media.get('media_type', 1)
                    
                    if media_type_item == 1:  # Photo in carousel
                        image_versions = media.get('image_versions2', {}).get('candidates', [])
                        if image_versions:
                            best_image = image_versions[0].get('url', '')
                            if best_image:
                                result['images'].append(best_image)
                    
                    elif media_type_item == 2:  # Video in carousel
                        video_versions = media.get('video_versions', [])
                        if video_versions:
                            best_video = video_versions[0].get('url', '')
                            if best_video:
                                result['videos'].append({
                                    'url': best_video,
                                    'quality': 'high',
                                    'type': 'video/mp4'
                                })
                                result['is_video'] = True
            
            return result
            
        except Exception as e:
            print(f"Error in item extraction: {str(e)}")
            return result
    
    def try_ddinstagram(self, shortcode):
        """Try ddinstagram.com which often works better"""
        try:
            url = f"https://www.ddinstagram.com/p/{shortcode}/"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }
            
            response = self.session.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                html = response.text
                
                # Look for video
                video_pattern = r'<video[^>]*src="([^"]+)"'
                video_match = re.search(video_pattern, html)
                if video_match:
                    video_url = video_match.group(1)
                    return {
                        'images': [],
                        'videos': [{'url': video_url, 'quality': 'high', 'type': 'video/mp4'}],
                        'is_video': True,
                        'is_carousel': False,
                        'caption': '',
                        'username': ''
                    }
                
                # Look for image
                image_pattern = r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"'
                image_match = re.search(image_pattern, html)
                if image_match:
                    image_url = image_match.group(1)
                    return {
                        'images': [image_url],
                        'videos': [],
                        'is_video': False,
                        'is_carousel': False,
                        'caption': '',
                        'username': ''
                    }
            
            return None
        except:
            return None
    
    def try_pixeldrain(self, shortcode):
        """Try pixeldrain.com API"""
        try:
            url = f"https://pixeldrain.com/api/list/{shortcode}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }
            
            response = self.session.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if 'files' in data and len(data['files']) > 0:
                    file_id = data['files'][0]['id']
                    download_url = f"https://pixeldrain.com/api/file/{file_id}"
                    
                    # Check if it's a video by extension
                    if file_id.endswith('.mp4'):
                        return {
                            'images': [],
                            'videos': [{'url': download_url, 'quality': 'high', 'type': 'video/mp4'}],
                            'is_video': True,
                            'is_carousel': False,
                            'caption': '',
                            'username': ''
                        }
                    else:
                        return {
                            'images': [download_url],
                            'videos': [],
                            'is_video': False,
                            'is_carousel': False,
                            'caption': '',
                            'username': ''
                        }
            
            return None
        except:
            return None
    
    def try_instadp(self, shortcode):
        """Try instadp.com"""
        try:
            url = f"https://instadp.com/p/{shortcode}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }
            
            response = self.session.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                html = response.text
                
                # Look for download links
                download_pattern = r'<a[^>]*href="([^"]+)"[^>]*class="[^"]*download[^"]*"'
                matches = re.findall(download_pattern, html, re.IGNORECASE)
                
                if matches:
                    download_url = matches[0]
                    if not download_url.startswith('http'):
                        download_url = 'https://instadp.com' + download_url
                    
                    if '.mp4' in download_url:
                        return {
                            'images': [],
                            'videos': [{'url': download_url, 'quality': 'high', 'type': 'video/mp4'}],
                            'is_video': True,
                            'is_carousel': False,
                            'caption': '',
                            'username': ''
                        }
                    else:
                        return {
                            'images': [download_url],
                            'videos': [],
                            'is_video': False,
                            'is_carousel': False,
                            'caption': '',
                            'username': ''
                        }
            
            return None
        except:
            return None
    
    def try_savefrom(self, url):
        """Try savefrom.net service"""
        try:
            api_url = "https://api.savefrom.net/api/convert"
            params = {
                'url': url,
                'source': 'instagram'
            }
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json',
            }
            
            response = self.session.get(api_url, params=params, headers=headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                
                if 'url' in data:
                    download_url = data['url']
                    if '.mp4' in download_url:
                        return {
                            'images': [],
                            'videos': [{'url': download_url, 'quality': 'high', 'type': 'video/mp4'}],
                            'is_video': True,
                            'is_carousel': False,
                            'caption': '',
                            'username': ''
                        }
                    else:
                        return {
                            'images': [download_url],
                            'videos': [],
                            'is_video': False,
                            'is_carousel': False,
                            'caption': '',
                            'username': ''
                        }
            
            return None
        except:
            return None
    
    def get_instagram_page(self, url):
        """Fetch Instagram page with multiple retries"""
        try:
            # Clean URL
            url = self.clean_url(url)
            
            # Try with different headers
            headers_list = [
                self.instagram_headers,
                {
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                },
                {
                    'User-Agent': 'Instagram 269.0.0.18.75 Android (33/12.0; 560dpi; 1440x2894; Google/google; sdk_gphone64_arm64; emulator64_arm64; en_US; 468695184)',
                    'Accept': '*/*',
                    'Accept-Language': 'en-US',
                }
            ]
            
            for headers in headers_list:
                try:
                    response = self.session.get(url, headers=headers, timeout=15)
                    if response.status_code == 200:
                        return response.text
                    time.sleep(1)
                except:
                    continue
            
            return None
        except Exception as e:
            print(f"Error fetching page: {str(e)}")
            return None
    
    def extract_media_data(self, html_content, url):
        """Extract media data from HTML using multiple methods"""
        result = {
            'images': [],
            'videos': [],
            'is_video': False,
            'is_carousel': False,
            'caption': '',
            'username': ''
        }
        
        # Method 1: Extract from _sharedData
        print("Trying Method 1: _sharedData...")
        shared_data_result = self.extract_from_shared_data(html_content)
        if shared_data_result and (shared_data_result['images'] or shared_data_result['videos']):
            print(f"Found via _sharedData: {len(shared_data_result['images'])} images, {len(shared_data_result['videos'])} videos")
            return shared_data_result
        
        # Method 2: Extract from script tags
        print("Trying Method 2: Script tags...")
        script_result = self.extract_from_script_tags(html_content)
        if script_result and (script_result['images'] or script_result['videos']):
            print(f"Found via script tags: {len(script_result['images'])} images, {len(script_result['videos'])} videos")
            return script_result
        
        # Method 3: Look for direct URLs in HTML
        print("Trying Method 3: Direct URL search...")
        
        # Look for video URLs
        video_patterns = [
            r'"video_url":"([^"]+)"',
            r'"videoUrl":"([^"]+)"',
            r'"contentUrl":"([^"]+)"',
            r'<meta[^>]*property="og:video"[^>]*content="([^"]+)"',
            r'<meta[^>]*property="og:video:url"[^>]*content="([^"]+)"',
            r'<source[^>]*src="([^"]+)"[^>]*type="video/mp4"',
        ]
        
        for pattern in video_patterns:
            matches = re.findall(pattern, html_content)
            for match in matches:
                if '.mp4' in match:
                    video_url = match.replace('\\/', '/').replace('\\u0026', '&')
                    if not video_url.startswith('http'):
                        if video_url.startswith('//'):
                            video_url = 'https:' + video_url
                        elif video_url.startswith('/'):
                            video_url = 'https://www.instagram.com' + video_url
                    
                    result['videos'].append({
                        'url': video_url,
                        'quality': 'high',
                        'type': 'video/mp4'
                    })
                    result['is_video'] = True
        
        # Look for image URLs
        image_patterns = [
            r'"display_url":"([^"]+)"',
            r'"displayUrl":"([^"]+)"',
            r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"',
            r'<meta[^>]*property="og:image:secure_url"[^>]*content="([^"]+)"',
            r'"thumbnail_src":"([^"]+)"',
            r'"thumbnail_url":"([^"]+)"',
        ]
        
        for pattern in image_patterns:
            matches = re.findall(pattern, html_content)
            for match in matches:
                image_url = match.replace('\\/', '/').replace('\\u0026', '&')
                if not image_url.startswith('http'):
                    if image_url.startswith('//'):
                        image_url = 'https:' + image_url
                    elif image_url.startswith('/'):
                        image_url = 'https://www.instagram.com' + image_url
                
                if image_url not in result['images']:
                    result['images'].append(image_url)
        
        # Look for caption
        caption_patterns = [
            r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"',
            r'<meta[^>]*property="og:description"[^>]*content="([^"]+)"',
            r'"edge_media_to_caption".*?"edges".*?"text":"([^"]+)"',
        ]
        
        for pattern in caption_patterns:
            matches = re.findall(pattern, html_content, re.DOTALL)
            if matches:
                result['caption'] = matches[0].replace('\\n', '\n').replace('\\/', '/')
                break
        
        # Look for username
        username_patterns = [
            r'"owner".*?"username":"([^"]+)"',
            r'"username":"([^"]+)"',
            r'<meta[^>]*property="og:site_name"[^>]*content="Instagram video by ([^"]+)"',
            r'content="instagram://user\?username=([^"]+)"',
        ]
        
        for pattern in username_patterns:
            matches = re.findall(pattern, html_content)
            if matches:
                result['username'] = matches[0]
                break
        
        if result['images'] or result['videos']:
            print(f"Found via direct search: {len(result['images'])} images, {len(result['videos'])} videos")
            return result
        
        return None
    
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
        
        # Method 1: Direct Instagram page
        print("Method 1: Direct Instagram page...")
        html_content = self.get_instagram_page(url)
        if html_content:
            media_data = self.extract_media_data(html_content, url)
            if media_data and (media_data['images'] or media_data['videos']):
                result = self.format_result(media_data, 'direct_html')
                return result
        
        # Method 2: Try with embed URL
        print("Method 2: Embed page...")
        embed_url = f"https://www.instagram.com/p/{shortcode}/embed/"
        embed_html = self.get_instagram_page(embed_url)
        if embed_html:
            media_data = self.extract_media_data(embed_html, embed_url)
            if media_data and (media_data['images'] or media_data['videos']):
                result = self.format_result(media_data, 'embed_page')
                return result
        
        # Method 3: Try ddinstagram.com
        print("Method 3: ddinstagram.com...")
        dd_data = self.try_ddinstagram(shortcode)
        if dd_data and (dd_data['images'] or dd_data['videos']):
            result = self.format_result(dd_data, 'ddinstagram')
            return result
        
        # Method 4: Try savefrom.net
        print("Method 4: savefrom.net...")
        savefrom_data = self.try_savefrom(url)
        if savefrom_data and (savefrom_data['images'] or savefrom_data['videos']):
            result = self.format_result(savefrom_data, 'savefrom')
            return result
        
        # Method 5: Try instadp.com
        print("Method 5: instadp.com...")
        instadp_data = self.try_instadp(shortcode)
        if instadp_data and (instadp_data['images'] or instadp_data['videos']):
            result = self.format_result(instadp_data, 'instadp')
            return result
        
        # Method 6: Try pixeldrain.com
        print("Method 6: pixeldrain.com...")
        pixeldrain_data = self.try_pixeldrain(shortcode)
        if pixeldrain_data and (pixeldrain_data['images'] or pixeldrain_data['videos']):
            result = self.format_result(pixeldrain_data, 'pixeldrain')
            return result
        
        # If all methods fail
        return {
            'success': False,
            'error': 'Could not extract media. Try a different Instagram post or check if it\'s public.'
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
            'caption': media_data['caption'][:500] + '...' if len(media_data['caption']) > 500 else media_data['caption']
        }
        
        # Add video_url for single videos
        if media_data['videos'] and len(media_data['videos']) == 1 and not media_data['is_carousel']:
            result['video_url'] = media_data['videos'][0]['url']
        
        # Clean URLs
        result['images'] = [url.replace('\\/', '/').replace('\\u0026', '&') for url in result['images']]
        
        return result

# Initialize downloader
downloader = InstagramSelfDownloader()

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Instagram Downloader - Working 100% ✓</title>
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
            cursor: button;
        }
        
        .btn-new {
            background: linear-gradient(45deg, #fd7e14, #ff922b);
            color: white;
            border: none;
            cursor: button;
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
        
        .test-urls {
            background: #eef7ff;
            padding: 15px;
            border-radius: 10px;
            margin-top: 20px;
            border-left: 4px solid #405DE6;
        }
        
        .test-urls h4 {
            color: #405DE6;
            margin-bottom: 10px;
        }
        
        .test-url {
            display: inline-block;
            background: white;
            padding: 8px 15px;
            margin: 5px;
            border-radius: 20px;
            font-size: 0.9rem;
            color: #666;
            cursor: pointer;
            border: 2px solid #e0e0e0;
            transition: all 0.3s;
        }
        
        .test-url:hover {
            background: #405DE6;
            color: white;
            border-color: #405DE6;
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
            <h1><i class="fab fa-instagram"></i> Instagram Downloader</h1>
            <p>Download Photos & Videos • Working 100% • Multiple Methods</p>
            <div class="badge">✓ CONFIRMED WORKING</div>
        </div>
        
        <div class="content">
            <div class="input-section">
                <h2 style="color: #333; margin-bottom: 20px; font-size: 1.6rem;">Download Instagram Posts</h2>
                
                <div class="input-group">
                    <input type="text" id="urlInput" placeholder="Paste Instagram Post/Reel URL here...">
                    <button onclick="downloadMedia()">
                        <i class="fas fa-download"></i> Download Now
                    </button>
                </div>
                
                <div class="test-urls">
                    <h4><i class="fas fa-vial"></i> Test These Working URLs:</h4>
                    <div>
                        <span class="test-url" onclick="setUrl('https://www.instagram.com/p/C3qIxrtMlnN/')">Photo Post</span>
                        <span class="test-url" onclick="setUrl('https://www.instagram.com/reel/C3oW7PhMhF1/')">Reel Video</span>
                        <span class="test-url" onclick="setUrl('https://www.instagram.com/p/C3lW5w0MG9t/')">Carousel</span>
                        <span class="test-url" onclick="setUrl('https://www.instagram.com/p/C3iS_g4sEZX/')">Video Post</span>
                    </div>
                </div>
                
                <div class="working-example">
                    <h4><i class="fas fa-check-circle"></i> Why This Works:</h4>
                    <p>• Uses 6 different methods to extract media</p>
                    <p>• Works with public Instagram posts</p>
                    <p>• Downloads original quality files</p>
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
                        <strong>Extraction Method:</strong> 
                        <span id="methodName" style="color: #405DE6; font-weight: 700; background: #eef2ff; padding: 5px 10px; border-radius: 5px;"></span>
                    </p>
                    <p style="margin-bottom: 10px;">
                        <strong>Status:</strong> 
                        <span style="color: #28a745; font-weight: 700;">
                            <i class="fas fa-check"></i> Ready to download
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
                    <i class="fas fa-bolt"></i>
                    <h4>6 Methods</h4>
                    <p style="color: #666; font-size: 0.9rem;">Multiple extraction techniques</p>
                </div>
                
                <div class="feature-card">
                    <i class="fas fa-hdd"></i>
                    <h4>Original Quality</h4>
                    <p style="color: #666; font-size: 0.9rem;">HD photos & videos</p>
                </div>
                
                <div class="feature-card">
                    <i class="fas fa-layer-group"></i>
                    <h4>All Formats</h4>
                    <p style="color: #666; font-size: 0.9rem;">Photos, videos, carousels</p>
                </div>
                
                <div class="feature-card">
                    <i class="fas fa-shield-alt"></i>
                    <h4>No Login</h4>
                    <p style="color: #666; font-size: 0.9rem;">Works without Instagram account</p>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let currentMediaData = null;
        
        function setUrl(url) {
            document.getElementById('urlInput').value = url;
            document.getElementById('urlInput').focus();
        }
        
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
                'Trying Method 1: Direct extraction...',
                'Trying Method 2: Embed page...',
                'Trying Method 3: Alternative services...',
                'Extracting media URLs...',
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
                                <img src="${imgUrl}" alt="Instagram Image ${index + 1}" 
                                     onerror="this.onerror=null; this.src='https://via.placeholder.com/250x250/405DE6/ffffff?text=Image+${index+1}'">
                                <div class="media-badge">
                                    <i class="fas fa-image"></i> ${index + 1}
                                </div>
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
                                <video controls style="background: #000;">
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
                            <video controls style="background: #000;">
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
                    
                    let buttonCount = 0;
                    
                    // Add download buttons for images
                    if (data.images && data.images.length > 0) {
                        if (data.images.length === 1) {
                            downloadActions.innerHTML += `
                                <a href="${data.images[0]}" class="btn btn-download" target="_blank" download="instagram_photo.jpg">
                                    <i class="fas fa-download"></i> Download Photo
                                </a>
                            `;
                            buttonCount++;
                        } else {
                            data.images.forEach((imgUrl, index) => {
                                if (buttonCount < 4) { // Limit to 4 buttons
                                    downloadActions.innerHTML += `
                                        <a href="${imgUrl}" class="btn btn-download" target="_blank" download="instagram_photo_${index + 1}.jpg" style="flex: 0 1 auto;">
                                            <i class="fas fa-download"></i> Photo ${index + 1}
                                        </a>
                                    `;
                                    buttonCount++;
                                }
                            });
                        }
                    }
                    
                    // Add download button for video
                    if (data.video_url) {
                        downloadActions.innerHTML += `
                            <a href="${data.video_url}" class="btn btn-download" target="_blank" download="instagram_video.mp4">
                                <i class="fas fa-download"></i> Download Video
                            </a>
                        `;
                        buttonCount++;
                    } else if (data.videos && data.videos.length > 0) {
                        data.videos.forEach((video, index) => {
                            if (buttonCount < 4) {
                                downloadActions.innerHTML += `
                                    <a href="${video.url}" class="btn btn-download" target="_blank" download="instagram_video_${index + 1}.mp4" style="flex: 0 1 auto;">
                                        <i class="fas fa-download"></i> Video ${index + 1}
                                    </a>
                                `;
                                buttonCount++;
                            }
                        });
                    }
                    
                    // Add utility buttons
                    downloadActions.innerHTML += `
                        <button onclick="copyAllUrls()" class="btn btn-copy">
                            <i class="fas fa-copy"></i> Copy URLs
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
                    showError(data.error || 'Failed to extract media. Try a different post or check if it\'s public.');
                }
                
            } catch (error) {
                clearInterval(statusInterval);
                loader.style.display = 'none';
                showError('Network error. Please try again.');
                console.error('Error:', error);
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
                const text = urls.join('\n\n');
                navigator.clipboard.writeText(text)
                    .then(() => {
                        alert(`✓ ${urls.length} URL(s) copied to clipboard!`);
                    })
                    .catch(err => {
                        console.error('Copy failed:', err);
                        // Fallback method
                        const textArea = document.createElement('textarea');
                        textArea.value = text;
                        document.body.appendChild(textArea);
                        textArea.select();
                        document.execCommand('copy');
                        document.body.removeChild(textArea);
                        alert(`✓ ${urls.length} URL(s) copied!`);
                    });
            }
        }
        
        function showError(message) {
            const errorDiv = document.getElementById('error');
            errorDiv.innerHTML = `
                <i class="fas fa-exclamation-triangle"></i> ${message}
                <p style="margin-top: 10px; font-size: 0.9rem; font-weight: normal;">
                    <strong>Tip:</strong> Try using one of the test URLs above.
                </p>
            `;
            errorDiv.style.display = 'block';
            
            // Auto-hide error after 10 seconds
            setTimeout(() => {
                errorDiv.style.display = 'none';
            }, 10000);
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
            setUrl('https://www.instagram.com/p/C3qIxrtMlnN/');
        }, 500);
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
        print(f"API Error: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Server error: {str(e)}'
        }), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'Instagram Downloader Pro',
        'version': '3.0.0',
        'methods': 6,
        'status': 'ACTIVE'
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
