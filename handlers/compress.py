import os
import uuid
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from utils.helpers import workdir, dl, cleanup, ext
from utils.video_tools import compress_video
from utils.image_tools import compress_image

router = Router()

VIDEO_EXTS = {"mp4", "avi", "mkv", "mov", "webm"}
IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "bmp"}

PRESETS = {
    "low":    ("Low quality (smallest size)",    36, "ultrafast"),
    "medium": ("Medium quality (balanced)",      28, "medium"),
    "high":   ("High quality (larger file)",     22, "slow"),
    "lossless":("Near-lossless",                 18, "slow"),
}


class CompressState(StatesGroup):
    waiting_file = State()
    waiting_preset = State()


def _preset_kb(src_key: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"{k.upper()} — {v[0]}", callback_data=f"cmp:{src_key}:{k}")]
            for k, v in PRESETS.items()]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("compress"), StateFilter("*"))
async def cmd_compress(msg: Message, state: FSMContext):
    await state.set_state(CompressState.waiting_file)
    await msg.answer("🗜 <b>Compress</b>\n\nSend a video or image to compress.", parse_mode="HTML")


@router.callback_query(F.data.regexp(r"^tool:[^:]+:compress$"))
async def cb_compress(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    _, src_key, _ = cb.data.split(":", 2)
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await state.set_state(CompressState.waiting_preset)
    await cb.answer()
    await cb.message.reply("🗜 <b>Compress</b>\n\nChoose quality preset:",
                           reply_markup=_preset_kb(src_key), parse_mode="HTML")


@router.message(CompressState.waiting_file, F.video | F.document | F.photo)
async def compress_got_file(msg: Message, state: FSMContext):
    if msg.photo:
        fid, fname, fsize = msg.photo[-1].file_id, "photo.jpg", msg.photo[-1].file_size
        kind = "image"
    elif msg.video:
        fid, fname, fsize = msg.video.file_id, "video.mp4", msg.video.file_size
        kind = "video"
    else:
        fid, fname, fsize = msg.document.file_id, msg.document.file_name, msg.document.file_size
        e = ext(fname)
        kind = "video" if e in VIDEO_EXTS else "image" if e in IMAGE_EXTS else None

    if not kind:
        await msg.reply("Unsupported file type for compression.")
        return

    src_key = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"cmp_in_{src_key}.{ext(fname)}")
    await dl(msg.bot, fid, src)
    dur = await get_duration(src)
    await state.update_data(src_path=src, src_key=src_key, kind=kind, filename=fname, duration=dur, file_id=fid)
    await state.set_state(CompressState.waiting_preset)
    await msg.reply("🗜 Choose quality preset:", reply_markup=_preset_kb(src_key))


@router.callback_query(F.data.startswith("cmp:"), CompressState.waiting_preset)
async def compress_do(cb: CallbackQuery, state: FSMContext):
    _, src_key, preset_key = cb.data.split(":", 2)
    data = await state.get_data()
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return

    await cb.message.edit_reply_markup()
    await cb.answer()
    status = await cb.message.reply("🗜 Compressing…")

    src = data.get("src_path")
    if not src:
        wd = workdir(cb.from_user.id)
        fname = data.get("filename", "file")
        src = os.path.join(wd, f"cmp_in_{src_key}.{ext(fname)}")
        await dl(cb.bot, data["file_id"], src)

    wd = workdir(cb.from_user.id)
    kind = data.get("kind", "video")
    _, crf, preset = PRESETS[preset_key]

    if kind == "video":
        dest = os.path.join(wd, f"compressed_{src_key}.mp4")
        await compress_video(src, dest, crf=crf, preset=preset)
    else:
        quality = max(10, 100 - crf * 2)
        dest_ext = ext(data.get("filename", "img.jpg")) or "jpg"
        dest = os.path.join(wd, f"compressed_{src_key}.{dest_ext}")
        await compress_image(src, dest, quality=quality)

    try:
        orig_size = os.path.getsize(src) / 1024 / 1024
        new_size = os.path.getsize(dest) / 1024 / 1024
        saved = (1 - new_size / orig_size) * 100
        await status.edit_text(
            f"✅ Compressed! {orig_size:.1f} MB → {new_size:.1f} MB ({saved:.0f}% saved)\nSending…"
        )
        with open(dest, "rb") as f:
            await cb.message.reply_document(f, filename=f"compressed.{ext(dest)}")
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(src, dest)
        await state.clear()
