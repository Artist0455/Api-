import os
import re
import logging
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
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
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', 'YOUR_TELEGRAM_BOT_TOKEN')
RAPIDAPI_HOST = "instagram-scraper-api-stories-reels-va-post.p.rapidapi.com"

def extract_instagram_url(text):
    """Extract Instagram URL from text"""
    patterns = [
        r'https?://(?:www\.)?instagram\.com/(?:p|reel|stories)/([\w\-]+)/?',
        r'https?://(?:www\.)?instagram\.com/([\w\.]+)/?'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return None

def download_instagram_content(url):
    """Download Instagram content using RapidAPI"""
    api_url = "https://instagram-scraper-api-stories-reels-va-post.p.rapidapi.com/"
    
    params = {
        'UserInfo': url
    }
    
    headers = {
        'x-rapidapi-host': RAPIDAPI_HOST,
        'x-rapidapi-key': RAPIDAPI_KEY
    }
    
    try:
        response = requests.get(api_url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API Error: {e}")
        return None

async def start(update: Update, context: CallbackContext):
    """Send welcome message when /start is issued"""
    user = update.effective_user
    welcome_text = f"""
👋 Hello {user.first_name}!

🤖 I'm Instagram Downloader Bot

📥 Send me any Instagram:
• Post URL
• Reel URL  
• Story URL
• Profile URL

📌 Examples:
https://www.instagram.com/p/Cxample123/
https://www.instagram.com/reel/Cxample456/
https://www.instagram.com/stories/username/

🎯 I'll download and send you the media!
"""
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: CallbackContext):
    """Send help message when /help is issued"""
    help_text = """
📖 **How to use:**
1. Copy any Instagram link
2. Paste it here
3. I'll download and send it to you

🔗 **Supported links:**
• Posts (instagram.com/p/...)
• Reels (instagram.com/reel/...)
• Stories (instagram.com/stories/...)
• Profiles (instagram.com/username/)

⚠️ **Note:**
• Stories must be public
• Private accounts not supported
• Max 10 downloads per hour
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def handle_message(update: Update, context: CallbackContext):
    """Handle incoming messages"""
    user_message = update.message.text
    
    # Check if message contains Instagram URL
    instagram_url = extract_instagram_url(user_message)
    
    if not instagram_url:
        await update.message.reply_text("❌ Please send a valid Instagram URL.")
        return
    
    # Send processing message
    processing_msg = await update.message.reply_text("⏳ Processing your request...")
    
    # Download content from Instagram
    result = download_instagram_content(instagram_url)
    
    if not result:
        await processing_msg.edit_text("❌ Failed to download content. Please try again.")
        return
    
    # Check if API returned valid data
    if 'error' in result:
        await processing_msg.edit_text(f"❌ Error: {result.get('error', 'Unknown error')}")
        return
    
    # Extract media URLs from response
    media_urls = []
    
    # Try different response formats
    if 'data' in result:
        data = result['data']
        if 'media' in data:
            media_urls = data['media']
        elif 'url' in data:
            media_urls = [data['url']]
        elif isinstance(data, list):
            media_urls = data
    
    if not media_urls:
        await processing_msg.edit_text("❌ No media found in the response.")
        return
    
    # Send media to user
    try:
        for i, media_url in enumerate(media_urls[:10]):  # Limit to 10 media items
            if i == 0:
                await processing_msg.edit_text(f"✅ Download successful! Sending media...")
            
            # Send media based on type
            if media_url.endswith(('.jpg', '.jpeg', '.png')):
                await update.message.reply_photo(media_url)
            elif media_url.endswith(('.mp4', '.mov', '.avi')):
                await update.message.reply_video(media_url)
            else:
                await update.message.reply_text(f"📎 Media {i+1}: {media_url}")
        
        await update.message.reply_text("✅ All media sent successfully!")
        
    except Exception as e:
        logger.error(f"Error sending media: {e}")
        await update.message.reply_text("❌ Error sending media. Sending URLs instead:")
        for url in media_urls:
            await update.message.reply_text(url)

async def error_handler(update: Update, context: CallbackContext):
    """Log errors"""
    logger.error(f"Update {update} caused error {context.error}")

def main():
    """Start the bot"""
    # Check for required tokens
    if TELEGRAM_TOKEN == 'YOUR_TELEGRAM_BOT_TOKEN':
        logger.error("Please set TELEGRAM_TOKEN in environment variables!")
        return
    
    # Create application
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    
    # Start bot
    logger.info("Bot started!")
    app.run_polling()

if __name__ == '__main__':
    main()
