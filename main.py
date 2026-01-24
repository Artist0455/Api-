from flask import Flask, request, jsonify
import requests
import re
import json
import os

app = Flask(__name__)

def extract_instagram_data(url):
    """Extract media data from Instagram URL"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        # Try to find JSON data in the HTML
        html = response.text
        
        # Look for embedded JSON data
        patterns = [
            r'window\._sharedData\s*=\s*({.*?});</script>',
            r'"video_url":"(https?://[^"]+)"',
            r'"display_url":"(https?://[^"]+)"',
            r'"display_resources":\[(.*?)\]'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                if pattern == patterns[0]:  # _sharedData
                    try:
                        data = json.loads(match.group(1))
                        # Extract media data from the JSON structure
                        media_data = extract_from_json(data)
                        return media_data
                    except:
                        continue
        
        # Fallback: Extract direct video/image URLs
        video_url = re.search(r'"contentUrl":"(https?://[^"]+\.mp4[^"]*)"', html)
        if video_url:
            return {
                'type': 'video',
                'urls': [video_url.group(1)],
                'success': True
            }
        
        image_url = re.search(r'"og:image"\s+content="(https?://[^"]+)"', html)
        if image_url:
            return {
                'type': 'image',
                'urls': [image_url.group(1)],
                'success': True
            }
        
        return {'success': False, 'error': 'Media not found'}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

def extract_from_json(data):
    """Extract media URLs from Instagram JSON data"""
    try:
        # Navigate through Instagram's JSON structure
        posts = []
        
        # Try different JSON structures
        if 'entry_data' in data:
            posts = data['entry_data'].get('PostPage', [{}])[0].get('graphql', {}).get('shortcode_media', {})
        elif 'graphql' in data:
            posts = data['graphql'].get('shortcode_media', {})
        
        if not posts:
            return {'success': False, 'error': 'No media data found'}
        
        # Extract media information
        media_type = posts.get('__typename', '')
        is_video = media_type in ['GraphVideo', 'GraphSidecar']
        
        urls = []
        
        if is_video:
            # Get video URL
            video_url = posts.get('video_url')
            if video_url:
                urls.append(video_url)
        else:
            # Get image URLs
            if 'display_resources' in posts:
                # Get highest quality
                resources = posts['display_resources']
                if resources:
                    urls.append(resources[-1]['src'])
            elif 'display_url' in posts:
                urls.append(posts['display_url'])
        
        # For carousel posts (multiple media)
        if 'edge_sidecar_to_children' in posts:
            edges = posts['edge_sidecar_to_children']['edges']
            for edge in edges:
                node = edge['node']
                if node.get('is_video'):
                    if 'video_url' in node:
                        urls.append(node['video_url'])
                else:
                    if 'display_resources' in node:
                        resources = node['display_resources']
                        if resources:
                            urls.append(resources[-1]['src'])
                    elif 'display_url' in node:
                        urls.append(node['display_url'])
        
        if urls:
            return {
                'success': True,
                'type': 'video' if is_video else 'image',
                'urls': urls,
                'caption': posts.get('edge_media_to_caption', {}).get('edges', [{}])[0].get('node', {}).get('text', ''),
                'username': posts.get('owner', {}).get('username', '')
            }
        else:
            return {'success': False, 'error': 'No media URLs found'}
            
    except Exception as e:
        return {'success': False, 'error': f'JSON parsing error: {str(e)}'}

@app.route('/')
def home():
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Instagram Downloader</title>
        <style>
            body { font-family: Arial; max-width: 800px; margin: 0 auto; padding: 20px; }
            .container { background: #f5f5f5; padding: 30px; border-radius: 10px; }
            input { width: 100%; padding: 12px; margin: 10px 0; border: 1px solid #ddd; }
            button { background: #405de6; color: white; border: none; padding: 12px 24px; cursor: pointer; }
            .result { margin-top: 20px; }
            .media { margin: 10px 0; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Instagram Downloader</h1>
            <input type="text" id="url" placeholder="Paste Instagram URL here">
            <button onclick="downloadMedia()">Download</button>
            <div id="result" class="result"></div>
        </div>
        <script>
            async function downloadMedia() {
                const url = document.getElementById('url').value;
                const resultDiv = document.getElementById('result');
                resultDiv.innerHTML = 'Loading...';
                
                try {
                    const response = await fetch('/download', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({url: url})
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        let html = `<h3>Found ${data.urls.length} media files:</h3>`;
                        data.urls.forEach((mediaUrl, index) => {
                            if (data.type === 'video') {
                                html += `
                                    <div class="media">
                                        <video width="320" controls>
                                            <source src="${mediaUrl}" type="video/mp4">
                                        </video>
                                        <br>
                                        <a href="${mediaUrl}" download>Download Video ${index + 1}</a>
                                    </div>`;
                            } else {
                                html += `
                                    <div class="media">
                                        <img src="${mediaUrl}" width="320">
                                        <br>
                                        <a href="${mediaUrl}" download>Download Image ${index + 1}</a>
                                    </div>`;
                            }
                        });
                        resultDiv.innerHTML = html;
                    } else {
                        resultDiv.innerHTML = `Error: ${data.error}`;
                    }
                } catch (error) {
                    resultDiv.innerHTML = `Error: ${error}`;
                }
            }
        </script>
    </body>
    </html>
    '''

@app.route('/download', methods=['POST'])
def download():
    data = request.json
    url = data.get('url', '')
    
    if not url:
        return jsonify({'success': False, 'error': 'No URL provided'})
    
    if 'instagram.com' not in url:
        return jsonify({'success': False, 'error': 'Invalid Instagram URL'})
    
    result = extract_instagram_data(url)
    return jsonify(result)

@app.route('/api/download', methods=['GET'])
def api_download():
    url = request.args.get('url', '')
    
    if not url:
        return jsonify({'success': False, 'error': 'No URL provided'})
    
    if 'instagram.com' not in url:
        return jsonify({'success': False, 'error': 'Invalid Instagram URL'})
    
    result = extract_instagram_data(url)
    return jsonify(result)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
