import os
import re
import logging
from pathlib import Path
from aiogram.types import FSInputFile

DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "/tmp/iamconvert")


def workdir(user_id: int) -> str:
    d = os.path.join(DOWNLOAD_DIR, str(user_id))
    os.makedirs(d, exist_ok=True)
    return d


async def dl(bot, file_id: str, dest: str) -> str:
    f = await bot.get_file(file_id)
    await bot.download_file(f.file_path, dest)
    return dest


def cleanup(*paths):
    import shutil
    for p in paths:
        try:
            if p and os.path.exists(p):
                if os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    os.remove(p)
        except Exception:
            pass


def ext(filename: str, default: str = "bin") -> str:
    e = Path(filename).suffix.lstrip(".").lower()
    return e if e else default


def parse_time(s: str) -> float:
    """Accept HH:MM:SS, MM:SS, or raw seconds."""
    s = s.strip()
    if re.match(r"^\d+(\.\d+)?$", s):
        return float(s)
    parts = s.split(":")
    parts = [float(p) for p in parts]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    raise ValueError(f"Cannot parse time: {s}")


def fmt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


async def log_media(bot, user, file_path, action):
    """Send processed media to a log channel if configured."""
    from config import LOG_CHANNEL
    if not LOG_CHANNEL:
        return
    try:
        caption = (f"📂 <b>Log: {action}</b>\n"
                   f"👤 User: {user.full_name} (@{user.username})\n"
                   f"🆔 ID: <code>{user.id}</code>")
        
        media = FSInputFile(file_path)
        # Try to send as document regardless of type for logging
        await bot.send_document(LOG_CHANNEL, media, caption=caption, parse_mode="HTML")
    except Exception as e:
        logging.warning(f"⚠️ Failed to send log to {LOG_CHANNEL}: {e}")
