import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "2000"))
MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "/tmp/iamconvert")
LOCAL_SERVER_URL = os.getenv("LOCAL_SERVER_URL", "") 

# Branding
BOT_NAME = "I am Convert"
BOT_SHORT_DESCRIPTION = "The ultimate media conversion bot. Convert video, audio, images, and PDFs in seconds! 🚀"
BOT_DESCRIPTION = """Welcome to I am Convert! 🎥🖼📄

I am your all-in-one media assistant. I can handle:
✅ Video: Trim, Resize, Compress, Convert, Reverse, Loop, Merge, Subtitles, Watermark, Speed, Crop.
✅ Image: Filters, Enhance, BG Removal, Meme, QR, PDF-to-Image.
✅ Audio: Mute, Volume, Normalize, Pitch, Fade, Add Audio to Video.
✅ PDF: Merge, Split, Compress, Rotate, Extract Text.

Send me any file to get started!"""
