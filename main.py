import os
import logging
import re
import requests
import time
from threading import Thread

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
RAPIDAPI_KEY = os.getenv('RAPIDAPI_KEY', 'c39530dad2msh8aa5bb904864303p188dbbjsn30e79193a8fc')

# YouTube API
YT_API_URL = "https://youtube-media-downloader.p.rapidapi.com/v2/video/details"

class YouTubeDownloaderBot:
    def __init__(self):
        self.last_update_id = 0
        self.running = True
        
    def send_message(self, chat_id, text, parse_mode=None, reply_markup=None):
        """Send message to Telegram"""
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            
            payload = {
                'chat_id': chat_id,
                'text': text
            }
            
            if parse_mode:
                payload['parse_mode'] = parse_mode
            
            if reply_markup:
                payload['reply_markup'] = reply_markup
            
            response = requests.post(url, json=payload, timeout=10)
            return response.json()
            
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return None
    
    def extract_video_id(self, url):
        """Extract video ID from YouTube URL"""
        try:
            url = url.strip()
            
            patterns = [
                r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})',
                r'youtube\.com/embed/([a-zA-Z0-9_-]{11})'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, url, re.IGNORECASE)
                if match:
                    return match.group(1)
            
            return None
        except Exception as e:
            logger.error(f"Error extracting video ID: {e}")
            return None
    
    def get_youtube_info(self, video_id):
        """Get YouTube video information"""
        try:
            url = f"{YT_API_URL}?videoId={video_id}"
            headers = {
                'x-rapidapi-host': 'youtube-media-downloader.p.rapidapi.com',
                'x-rapidapi-key': RAPIDAPI_KEY
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"API Error: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching YouTube info: {e}")
            return None
    
    def create_inline_keyboard(self, options):
        """Create inline keyboard markup"""
        keyboard = []
        
        for option in options:
            if option.get('url'):
                keyboard.append([{
                    'text': option['text'],
                    'url': option['url']
                }])
            elif option.get('callback_data'):
                keyboard.append([{
                    'text': option['text'],
                    'callback_data': option['callback_data']
                }])
        
        return {'inline_keyboard': keyboard}
    
    def handle_start(self, chat_id):
        """Handle /start command"""
        welcome_text = (
            "🎬 *YouTube Video Downloader Bot* 🎬\n\n"
            "📥 *I can download:*\n"
            "• YouTube Videos\n"
            "• YouTube Shorts\n"
            "• Multiple qualities\n\n"
            "*How to use:*\n"
            "1. Send YouTube video URL\n"
            "2. I'll fetch download links\n"
            "3. Click to download\n\n"
            "📱 *Example URLs:*\n"
            "`https://youtube.com/watch?v=dQw4w9WgXcQ`\n"
            "`https://youtu.be/dQw4w9WgXcQ`\n"
            "`https://youtube.com/shorts/ABC123`\n\n"
            "⚠️ *Note:* Download only content you have permission for."
        )
        
        self.send_message(
            chat_id=chat_id,
            text=welcome_text,
            parse_mode='Markdown'
        )
    
    def handle_help(self, chat_id):
        """Handle /help command"""
        help_text = (
            "📋 *Help Guide*\n\n"
            "1. Copy YouTube video URL\n"
            "2. Send it to me\n"
            "3. I'll provide download links\n"
            "4. Click to download\n\n"
            "*Supported Formats:* MP4, WebM\n"
            "*Quality:* Up to 1080p\n\n"
            "*Tips:*\n"
            "• Video must be public\n"
            "• Max size: 50MB for Telegram\n"
            "• Shorter videos work better"
        )
        
        self.send_message(
            chat_id=chat_id,
            text=help_text,
            parse_mode='Markdown'
        )
    
    def handle_youtube_url(self, chat_id, text):
        """Handle YouTube URL"""
        # Send processing message
        self.send_message(
            chat_id=chat_id,
            text="🔍 *Processing your YouTube link...*",
            parse_mode='Markdown'
        )
        
        # Extract video ID
        video_id = self.extract_video_id(text)
        
        if not video_id:
            self.send_message(
                chat_id=chat_id,
                text="❌ *Invalid YouTube URL*\n\nPlease send a valid YouTube video URL.",
                parse_mode='Markdown'
            )
            return
        
        # Get video information
        video_data = self.get_youtube_info(video_id)
        
        if not video_data:
            self.send_message(
                chat_id=chat_id,
                text="❌ *Could not fetch video information*\n\nPlease try:\n• Different video\n• Check URL\n• Try again later",
                parse_mode='Markdown'
            )
            return
        
        # Extract video details
        title = video_data.get('title', 'YouTube Video')[:100]
        channel = video_data.get('channel', {})
        if isinstance(channel, dict):
            channel_name = channel.get('name', 'Unknown Channel')
        else:
            channel_name = str(channel)
        
        duration = video_data.get('duration', '00:00')
        
        # Prepare download options
        download_options = []
        
        if video_data.get('videos') and video_data['videos'].get('items'):
            for i, video in enumerate(video_data['videos']['items'][:3]):
                if video.get('url'):
                    quality = video.get('quality', 'HD')
                    format_type = video.get('format', 'mp4')
                    size = video.get('size', 'N/A')
                    
                    download_options.append({
                        'text': f"⬇️ {quality} ({format_type.upper()}) - {size}",
                        'url': video['url']
                    })
        
        # If no download options, show direct YouTube link
        if not download_options:
            download_options.append({
                'text': '🎬 Watch on YouTube',
                'url': f'https://www.youtube.com/watch?v={video_id}'
            })
        
        # Create keyboard
        keyboard = self.create_inline_keyboard(download_options)
        
        # Send result
        result_text = (
            f"✅ *YouTube Video Found!*\n\n"
            f"📹 *Title:* {title}\n"
            f"👤 *Channel:* {channel_name}\n"
            f"⏱ *Duration:* {duration}\n\n"
            f"*Select download quality:* 👇"
        )
        
        self.send_message(
            chat_id=chat_id,
            text=result_text,
            parse_mode='Markdown',
            reply_markup=keyboard
        )
    
    def process_message(self, message):
        """Process incoming message"""
        try:
            chat_id = message['chat']['id']
            text = message.get('text', '').strip()
            
            if not text:
                return
            
            # Handle commands
            if text == '/start':
                self.handle_start(chat_id)
            
            elif text == '/help':
                self.handle_help(chat_id)
            
            # Check if it's a YouTube URL
            elif 'youtube.com' in text or 'youtu.be' in text:
                self.handle_youtube_url(chat_id, text)
            
            else:
                self.send_message(
                    chat_id=chat_id,
                    text="❌ *Please send a YouTube URL*\n\nExample:\n`https://youtube.com/watch?v=dQw4w9WgXcQ`",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def get_updates(self):
        """Get new updates from Telegram"""
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
            params = {
                'offset': self.last_update_id + 1,
                'timeout': 30,
                'allowed_updates': ['message']
            }
            
            response = requests.get(url, params=params, timeout=35)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('ok') and data.get('result'):
                    for update in data['result']:
                        self.last_update_id = update['update_id']
                        
                        if 'message' in update:
                            self.process_message(update['message'])
                
                return True
            else:
                logger.error(f"GetUpdates error: {response.status_code}")
                return False
                
        except requests.exceptions.Timeout:
            # Timeout is expected in long polling
            return True
        except Exception as e:
            logger.error(f"Error getting updates: {e}")
            return False
    
    def start_polling(self):
        """Start polling for updates"""
        logger.info("Starting bot polling...")
        
        # Send startup notification
        self.send_message(
            chat_id=os.getenv('ADMIN_CHAT_ID', ''),
            text="🤖 Bot started successfully!"
        )
        
        while self.running:
            try:
                self.get_updates()
                time.sleep(0.1)  # Small delay between requests
                
            except KeyboardInterrupt:
                logger.info("Bot stopped by user")
                self.running = False
                break
            except Exception as e:
                logger.error(f"Polling error: {e}")
                time.sleep(5)  # Wait before retry
    
    def stop(self):
        """Stop the bot"""
        self.running = False

def main():
    """Main function"""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN environment variable is required!")
        return
    
    bot = YouTubeDownloaderBot()
    
    # Start polling in a separate thread
    polling_thread = Thread(target=bot.start_polling)
    polling_thread.daemon = True
    polling_thread.start()
    
    logger.info("Bot is running. Press Ctrl+C to stop.")
    
    try:
        # Keep main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping bot...")
        bot.stop()
        polling_thread.join(timeout=5)
        logger.info("Bot stopped.")

if __name__ == '__main__':
    main()
