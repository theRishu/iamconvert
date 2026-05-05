import asyncio
import logging
import os
import time

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.types import BotCommand

from config import (BOT_TOKEN, DOWNLOAD_DIR, LOCAL_SERVER_URL, 
                    BOT_NAME, BOT_SHORT_DESCRIPTION, BOT_DESCRIPTION)
from handlers import routers_list

logging.basicConfig(level=logging.INFO)

CLEANUP_INTERVAL = 600   # run every 10 minutes
FILE_MAX_AGE = 1800      # delete files older than 30 minutes


async def periodic_cleanup():
    import shutil
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL)
        now = time.time()
        if not os.path.isdir(DOWNLOAD_DIR):
            continue
        try:
            for entry in os.scandir(DOWNLOAD_DIR):
                try:
                    age = now - entry.stat().st_mtime
                    if age > FILE_MAX_AGE:
                        if entry.is_dir(follow_symlinks=False):
                            shutil.rmtree(entry.path, ignore_errors=True)
                        else:
                            os.remove(entry.path)
                        logging.info(f"🗑 Cleaned stale: {entry.path}")
                except Exception:
                    pass
        except Exception:
            pass


async def main():
    # Clear and recreate download directory on startup
    import shutil
    if os.path.exists(DOWNLOAD_DIR):
        logging.info(f"🧹 Clearing download directory: {DOWNLOAD_DIR}")
        shutil.rmtree(DOWNLOAD_DIR, ignore_errors=True)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    # Configure local bot API server if URL is provided
    if LOCAL_SERVER_URL:
        session = AiohttpSession(
            api=TelegramAPIServer.from_base(LOCAL_SERVER_URL)
        )
        bot = Bot(token=BOT_TOKEN, session=session)
    else:
        bot = Bot(token=BOT_TOKEN)

    dp = Dispatcher(storage=MemoryStorage())

    for router in routers_list:
        dp.include_router(router)

    # Set basic commands list
    commands = [
        BotCommand(command="start", description="Welcome & feature overview"),
        BotCommand(command="help", description="Full command reference"),
        BotCommand(command="trim", description="Trim a video"),
        BotCommand(command="compress", description="Compress video or image"),
        BotCommand(command="cancel", description="Abort current operation"),
    ]
    try:
        await bot.set_my_commands(commands)
        # Set Branding
        await bot.set_my_name(BOT_NAME)
        await bot.set_my_description(BOT_DESCRIPTION)
        await bot.set_my_short_description(BOT_SHORT_DESCRIPTION)
        logging.info(f"✅ Bot branding setup complete: {BOT_NAME}")
    except Exception as e:
        logging.warning(f"⚠️ Could not set bot profile info: {e}")

    await bot.delete_webhook(drop_pending_updates=True)

    asyncio.create_task(periodic_cleanup())

    print(f"🚀 Bot started! Local Server: {LOCAL_SERVER_URL or 'Default'}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
