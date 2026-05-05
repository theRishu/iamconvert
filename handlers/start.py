from aiogram import Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

router = Router()

WELCOME = (
    "🚀 <b>Welcome to I am Convert!</b>\n\n"
    "The ultimate all-in-one media conversion bot.\n\n"
    "<b>Just send any file</b> (Video, Audio, Image, or PDF) and I'll show you the magic! ✨\n\n"
    "🎬 <b>Video:</b> Trim, Resize, Compress, Subtitles, Merge, Speed, Reverse, Loop\n"
    "🎵 <b>Audio:</b> Normalize, Pitch, Fade, Mute, Volume, Add to Video\n"
    "🖼 <b>Image:</b> BG Removal, Filters, Enhance, Meme, QR, Sticker, PDF conversion\n"
    "📄 <b>PDF:</b> Merge, Split, Compress, Rotate, Extract Text\n"
    "📦 <b>Archive:</b> Create or Extract ZIP/RAR/TAR\n"
    "⬇️ <b>Download:</b> YouTube, Instagram, TikTok, and more!\n\n"
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
