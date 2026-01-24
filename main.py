#!/usr/bin/env python3
"""
Instagram Public Post Downloader - Educational Purpose Only
Use responsibly and respect copyright laws
"""

import requests
import re
import json
import os
import sys
from urllib.parse import urlparse, unquote
from datetime import datetime

class InstagramPublicDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.setup_headers()
        
    def setup_headers(self):
        """Setup browser-like headers"""
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0'
        }
        
    def extract_shortcode(self, url):
        """Extract shortcode from Instagram URL"""
        patterns = [
            r'instagram\.com/p/([^/?]+)',
            r'instagram\.com/reel/([^/?]+)',
            r'instagram\.com/tv/([^/?]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    def get_post_data(self, shortcode):
        """Fetch post data using public endpoints"""
        endpoints = [
            f"https://www.instagram.com/p/{shortcode}/?__a=1&__d=dis",
            f"https://www.instagram.com/p/{shortcode}/?__a=1",
            f"https://i.instagram.com/api/v1/media/{shortcode}/info/"
        ]
        
        for endpoint in endpoints:
            try:
                print(f"Trying endpoint: {endpoint}")
                response = self.session.get(endpoint, headers=self.headers, timeout=10)
                
                if response.status_code == 200:
                    try:
                        return response.json()
                    except json.JSONDecodeError:
                        # Try extracting from HTML
                        return self.extract_from_html(response.text)
                        
            except Exception as e:
                print(f"Error with endpoint {endpoint}: {e}")
                continue
        
        return None
    
    def extract_from_html(self, html):
        """Extract data from HTML page"""
        data = {}
        
        # Try to find JSON-LD data
        json_ld_pattern = r'<script type="application/ld\+json">(.*?)</script>'
        json_ld_match = re.search(json_ld_pattern, html, re.DOTALL)
        
        if json_ld_match:
            try:
                data['json_ld'] = json.loads(json_ld_match.group(1))
            except:
                pass
        
        # Try to find GraphQL data
        graphql_pattern = r'window\.__additionalDataLoaded.*?({.*?});</script>'
        graphql_match = re.search(graphql_pattern, html, re.DOTALL)
        
        if graphql_match:
            try:
                graphql_data = json.loads(graphql_match.group(1))
                if 'graphql' in graphql_data:
                    return {'graphql': graphql_data['graphql']}
            except:
                pass
        
        # Extract image URLs from meta tags
        og_image_pattern = r'<meta property="og:image" content="([^"]+)"'
        og_image_matches = re.findall(og_image_pattern, html)
        
        if og_image_matches:
            data['images'] = og_image_matches
        
        # Extract video URLs
        video_pattern = r'"video_url":"([^"]+)"'
        video_matches = re.findall(video_pattern, html)
        
        if video_matches:
            data['videos'] = [url.replace('\\/', '/') for url in video_matches]
        
        return data if data else None
    
    def parse_media_urls(self, data):
        """Parse media URLs from the fetched data"""
        media_urls = []
        
        if not data:
            return media_urls
        
        # Method 1: GraphQL structure
        if 'graphql' in data:
            shortcode_media = data['graphql'].get('shortcode_media', {})
            
            # Single image
            if shortcode_media.get('__typename') == 'GraphImage':
                display_url = shortcode_media.get('display_url')
                if display_url:
                    media_urls.append({
                        'type': 'image',
                        'url': display_url,
                        'width': shortcode_media.get('dimensions', {}).get('width'),
                        'height': shortcode_media.get('dimensions', {}).get('height')
                    })
            
            # Video/Reel
            elif shortcode_media.get('__typename') == 'GraphVideo':
                video_url = shortcode_media.get('video_url')
                if video_url:
                    media_urls.append({
                        'type': 'video',
                        'url': video_url,
                        'duration': shortcode_media.get('video_duration'),
                        'width': shortcode_media.get('dimensions', {}).get('width'),
                        'height': shortcode_media.get('dimensions', {}).get('height')
                    })
            
            # Carousel
            elif shortcode_media.get('__typename') == 'GraphSidecar':
                edges = shortcode_media.get('edge_sidecar_to_children', {}).get('edges', [])
                for edge in edges:
                    node = edge.get('node', {})
                    if node.get('is_video'):
                        video_url = node.get('video_url')
                        if video_url:
                            media_urls.append({
                                'type': 'video',
                                'url': video_url
                            })
                    else:
                        display_url = node.get('display_url')
                        if display_url:
                            media_urls.append({
                                'type': 'image',
                                'url': display_url
                            })
        
        # Method 2: Direct URLs from HTML
        if 'images' in data:
            for img_url in data['images']:
                media_urls.append({
                    'type': 'image',
                    'url': img_url
                })
        
        if 'videos' in data:
            for vid_url in data['videos']:
                media_urls.append({
                    'type': 'video',
                    'url': vid_url
                })
        
        # Method 3: JSON-LD data
        if 'json_ld' in data:
            json_ld = data['json_ld']
            if isinstance(json_ld, list):
                json_ld = json_ld[0]
            
            # Check for image in JSON-LD
            if 'image' in json_ld:
                if isinstance(json_ld['image'], list):
                    media_urls.extend([{'type': 'image', 'url': url} for url in json_ld['image']])
                else:
                    media_urls.append({'type': 'image', 'url': json_ld['image']})
        
        return media_urls
    
    def download_media(self, media_info, output_dir="downloads"):
        """Download media file"""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        url = media_info['url']
        media_type = media_info['type']
        
        # Generate filename
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        
        # Clean filename
        filename = unquote(filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"{timestamp}_{filename}"
        
        filepath = os.path.join(output_dir, safe_filename)
        
        try:
            print(f"Downloading {media_type}: {filename}")
            
            # Set referer header for CDN
            download_headers = self.headers.copy()
            download_headers['Referer'] = 'https://www.instagram.com/'
            download_headers['Accept'] = '*/*'
            
            response = self.session.get(url, headers=download_headers, stream=True, timeout=30)
            
            if response.status_code == 200:
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                print(f"✓ Downloaded: {filepath}")
                return filepath
            else:
                print(f"✗ Failed to download: HTTP {response.status_code}")
                return None
                
        except Exception as e:
            print(f"✗ Error downloading: {e}")
            return None
    
    def process_url(self, url, download=True):
        """Main function to process Instagram URL"""
        print(f"\nProcessing URL: {url}")
        
        # Extract shortcode
        shortcode = self.extract_shortcode(url)
        if not shortcode:
            print("✗ Invalid Instagram URL")
            return None
        
        print(f"✓ Shortcode found: {shortcode}")
        
        # Get post data
        print("Fetching post data...")
        data = self.get_post_data(shortcode)
        
        if not data:
            print("✗ Could not fetch post data")
            return None
        
        print("✓ Post data fetched successfully")
        
        # Parse media URLs
        media_urls = self.parse_media_urls(data)
        
        if not media_urls:
            print("✗ No media URLs found")
            return None
        
        print(f"✓ Found {len(media_urls)} media file(s)")
        
        # Display media info
        for i, media in enumerate(media_urls, 1):
            print(f"{i}. Type: {media['type']}")
            print(f"   URL: {media['url'][:80]}...")
            if 'width' in media and 'height' in media:
                print(f"   Resolution: {media['width']}x{media['height']}")
        
        # Download if requested
        downloaded_files = []
        if download and media_urls:
            print("\nStarting downloads...")
            for i, media in enumerate(media_urls, 1):
                print(f"\nDownloading file {i}/{len(media_urls)}")
                filepath = self.download_media(media)
                if filepath:
                    downloaded_files.append(filepath)
        
        return {
            'shortcode': shortcode,
            'media_count': len(media_urls),
            'media_info': media_urls,
            'downloaded_files': downloaded_files
        }

def main():
    """Main function"""
    print("=" * 60)
    print("INSTAGRAM PUBLIC POST DOWNLOADER")
    print("Educational Purpose Only - Use Responsibly")
    print("=" * 60)
    
    downloader = InstagramPublicDownloader()
    
    # Get URL from user
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = input("\nEnter Instagram Post URL: ").strip()
    
    if not url:
        print("No URL provided. Exiting.")
        return
    
    # Process the URL
    try:
        result = downloader.process_url(url, download=True)
        
        if result:
            print("\n" + "=" * 60)
            print("DOWNLOAD SUMMARY")
            print("=" * 60)
            print(f"Shortcode: {result['shortcode']}")
            print(f"Media Files Found: {result['media_count']}")
            print(f"Successfully Downloaded: {len(result['downloaded_files'])}")
            
            if result['downloaded_files']:
                print("\nDownloaded Files:")
                for file in result['downloaded_files']:
                    print(f"  • {file}")
        
        print("\nNote: Always respect content creators' rights.")
        print("Only download content you have permission to use.")
        
    except KeyboardInterrupt:
        print("\n\nProcess interrupted by user.")
    except Exception as e:
        print(f"\nError: {e}")
        print("Please check the URL and try again.")

if __name__ == "__main__":
    main()
