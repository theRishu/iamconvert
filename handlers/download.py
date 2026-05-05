import os
import re
import uuid
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from utils.helpers import workdir, cleanup
from utils.downloader import download_url

router = Router()

URL_RE = re.compile(r"https?://[^\s]+")


class DlState(StatesGroup):
    waiting_url = State()


@router.message(Command("download"), StateFilter("*"))
async def cmd_download(msg: Message, state: FSMContext):
    await state.set_state(DlState.waiting_url)
    await msg.answer(
        "⬇️ <b>Download</b>\n\n"
        "Send a URL to download from.\n"
        "Supports: YouTube, Instagram, Twitter/X, TikTok, Facebook, direct links.",
        parse_mode="HTML",
    )


@router.message(DlState.waiting_url, F.text)
async def dl_got_url(msg: Message, state: FSMContext):
    url = (msg.text or "").strip()
    if not URL_RE.match(url):
        await msg.reply("That doesn't look like a URL. Send a full URL starting with http:// or https://")
        return
    await _do_download(msg, state, url)


# Also trigger if user sends a URL directly (not in state)
@router.message(F.text.regexp(r"^https?://"), StateFilter(None))
async def dl_url_direct(msg: Message, state: FSMContext):
    await _do_download(msg, state, msg.text.strip())


async def _do_download(msg: Message, state: FSMContext, url: str):
    session = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    status = await msg.reply(f"⬇️ Downloading from:\n<code>{url[:100]}</code>…", parse_mode="HTML")
    path = None
    try:
        path = await download_url(url, wd)
        size_mb = os.path.getsize(path) / 1024 / 1024
        fname = os.path.basename(path)

        if size_mb > 50:
            await status.edit_text(
                f"❌ Downloaded file is {size_mb:.1f} MB — too large for Telegram (max 50 MB)."
            )
            return

        await status.edit_text(f"✅ Downloaded ({size_mb:.1f} MB). Sending…")
        with open(path, "rb") as f:
            await msg.reply_document(f, filename=fname, caption=f"Downloaded from {url[:60]}")
    except Exception as e:
        await status.edit_text(f"❌ Download failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        if path:
            cleanup(path)
        await state.clear()
