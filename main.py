import os
import re
import logging
import requests
from telegram import Update, ParseMode
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# API Configuration
RAPIDAPI_KEY = os.getenv('RAPIDAPI_KEY', 'bdc73c303bmsh843b16f8f83b0fep13d6c1jsn98a1abccf938')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
RAPIDAPI_HOST = "instagram-scraper-api-stories-reels-va-post.p.rapidapi.com"

def extract_instagram_url(text):
    """Extract Instagram URL from text"""
    patterns = [
        r'https?://(?:www\.)?instagram\.com/(?:p|reel|stories)/([\w\-]+)/?',
        r'https?://(www\.)?instagram\.com/([\w\.]+)/?',
        r'instagram\.com/(?:p|reel|stories)/([\w\-]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0)
    return None

def download_instagram_content(url):
    """Download Instagram content using RapidAPI"""
    api_url = "https://instagram-scraper-api-stories-reels-va-post.p.rapidapi.com/"
    
    params = {'UserInfo': url}
    
    headers = {
        'x-rapidapi-host': RAPIDAPI_HOST,
        'x-rapidapi-key': RAPIDAPI_KEY
    }
    
    try:
        response = requests.get(api_url, headers=headers, params=params, timeout=30)
        logger.info(f"API Response Status: {response.status_code}")
        
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"API Error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"Request Exception: {e}")
        return None

def start(update: Update, context: CallbackContext):
    """Send welcome message when /start is issued"""
    user = update.effective_user
    welcome_text = f"""
👋 Hello {user.first_name}!

🤖 *Instagram Downloader Bot*

📥 *Send me any Instagram link:*
• Post URL
• Reel URL  
• Story URL
• Profile URL

📌 *Examples:*
`https://www.instagram.com/p/Cxample123/`
`https://www.instagram.com/reel/Cxample456/`
`https://www.instagram.com/stories/username/`

🎯 I'll download and send you the media!

⚠️ *Note:* Stories must be public
"""
    update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)

def help_command(update: Update, context: CallbackContext):
    """Send help message when /help is issued"""
    help_text = """
📖 *How to use:*
1. Copy any Instagram link
2. Paste it here
3. I'll download and send it

🔗 *Supported links:*
• Posts (instagram.com/p/...)
• Reels (instagram.com/reel/...)
• Stories (instagram.com/stories/...)

⚠️ *Limitations:*
• Stories must be public
• Private accounts not supported
• Rate limits apply

🔄 *Commands:*
/start - Start the bot
/help - Show this help
"""
    update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

def handle_message(update: Update, context: CallbackContext):
    """Handle incoming messages"""
    user_message = update.message.text
    
    # Check if message contains Instagram URL
    instagram_url = extract_instagram_url(user_message)
    
    if not instagram_url:
        update.message.reply_text("❌ Please send a valid Instagram URL.\nExample: `https://www.instagram.com/p/Cxample123/`", parse_mode=ParseMode.MARKDOWN)
        return
    
    # Send processing message
    processing_msg = update.message.reply_text("⏳ Processing your request...")
    
    # Download content from Instagram
    result = download_instagram_content(instagram_url)
    
    if not result:
        processing_msg.edit_text("❌ Failed to download content. Please try again later.")
        return
    
    # Check if API returned valid data
    if 'error' in result:
        processing_msg.edit_text(f"❌ API Error: {result.get('error', 'Unknown error')}")
        return
    
    # Extract media URLs from response
    media_urls = []
    
    # Debug: Log the API response
    logger.info(f"API Response: {result}")
    
    # Try different response formats
    if 'data' in result:
        data = result['data']
        if isinstance(data, dict):
            # Check for media array
            if 'media' in data and isinstance(data['media'], list):
                media_urls = data['media']
            # Check for single URL
            elif 'url' in data:
                media_urls = [data['url']]
            # Check for items array
            elif 'items' in data and isinstance(data['items'], list):
                for item in data['items']:
                    if 'url' in item:
                        media_urls.append(item['url'])
        elif isinstance(data, list):
            media_urls = data
    
    # If still no media, check root level
    if not media_urls:
        if 'url' in result:
            media_urls = [result['url']]
        elif 'media' in result:
            media_urls = result['media']
    
    if not media_urls:
        processing_msg.edit_text("❌ No media found in the response.")
        logger.error(f"No media found in response: {result}")
        return
    
    # Send media to user
    try:
        processing_msg.edit_text(f"✅ Found {len(media_urls)} media item(s). Downloading...")
        
        for i, media_url in enumerate(media_urls[:5]):  # Limit to 5 items
            # Clean URL
            if media_url.startswith('"') or media_url.startswith("'"):
                media_url = media_url[1:-1]
            
            logger.info(f"Sending media {i+1}: {media_url}")
            
            # Determine media type
            if any(ext in media_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                update.message.reply_photo(media_url, caption=f"📷 Item {i+1}")
            elif any(ext in media_url.lower() for ext in ['.mp4', '.mov', '.avi', '.webm']):
                update.message.reply_video(media_url, caption=f"🎬 Item {i+1}")
            else:
                update.message.reply_text(f"📎 Item {i+1}: {media_url}")
        
        update.message.reply_text(f"✅ Successfully sent {len(media_urls[:5])} media items!")
        
    except Exception as e:
        logger.error(f"Error sending media: {e}")
        processing_msg.edit_text("❌ Error sending media. Sending direct URLs...")
        for url in media_urls[:3]:
            update.message.reply_text(url)

def error_handler(update: Update, context: CallbackContext):
    """Log errors"""
    logger.error(f"Update {update} caused error {context.error}")

def main():
    """Start the bot"""
    # Check for required tokens
    if not TELEGRAM_TOKEN:
        logger.error("❌ TELEGRAM_TOKEN not found in environment variables!")
        print("Please set TELEGRAM_TOKEN in Render environment variables")
        return
    
    if not RAPIDAPI_KEY:
        logger.warning("⚠️ RAPIDAPI_KEY not found, using default key")
    
    logger.info("🚀 Starting Instagram Downloader Bot...")
    
    try:
        # Create Updater
        updater = Updater(TELEGRAM_TOKEN, use_context=True)
        
        # Get dispatcher
        dp = updater.dispatcher
        
        # Add handlers
        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(CommandHandler("help", help_command))
        dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
        
        # Add error handler
        dp.add_error_handler(error_handler)
        
        # Start bot
        updater.start_polling()
        logger.info("✅ Bot is running and polling...")
        print("🤖 Bot is now running! Press Ctrl+C to stop.")
        
        # Run until interrupted
        updater.idle()
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        print(f"❌ Bot failed to start: {e}")

if __name__ == '__main__':
    main()
