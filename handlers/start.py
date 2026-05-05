from aiogram import Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

router = Router()

WELCOME = (
    "👋 <b>Welcome to iamconvert!</b>\n\n"
    "The most powerful media converter bot.\n\n"
    "<b>Just send any file</b> and I'll show you all available actions.\n\n"
    "🎬 Video → Convert, Trim, Compress, Screenshot, Watermark, Speed, Subtitles, Merge\n"
    "🎵 Audio → Convert between MP3, WAV, OGG, FLAC, AAC, M4A\n"
    "🖼 Image → Convert, Resize, Compress, Watermark, OCR, Sticker\n"
    "📄 PDF  → Images (per page)\n"
    "📦 Archive → Create ZIP, Extract ZIP/RAR/TAR\n"
    "⬇️ Download → YouTube, Instagram, TikTok, direct URLs\n\n"
    "Type /help for the full command list."
)


@router.message(Command("start"), StateFilter("*"))
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer(WELCOME, parse_mode="HTML")


@router.message(Command("cancel"), StateFilter("*"))
async def cmd_cancel(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("❌ Cancelled. Send a file or /start to begin again.")
