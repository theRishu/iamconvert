import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "2000"))
MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "/tmp/iamconvert")
LOCAL_SERVER_URL = os.getenv("LOCAL_SERVER_URL", "") # e.g. http://localhost:8081
