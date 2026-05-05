import os
import uuid
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from utils.helpers import workdir, dl, cleanup, ext
from utils.video_tools import add_watermark_video
from utils.image_tools import add_watermark_image

router = Router()

VIDEO_EXTS = {"mp4", "avi", "mkv", "mov", "webm"}
IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "bmp", "tiff"}

POSITIONS = ["topleft", "topright", "bottomleft", "bottomright", "center"]
POS_LABELS = {
    "topleft":     "↖ Top Left",
    "topright":    "↗ Top Right",
    "bottomleft":  "↙ Bottom Left",
    "bottomright": "↘ Bottom Right",
    "center":      "⊙ Center",
}


class WmkState(StatesGroup):
    waiting_file = State()
    waiting_text = State()
    waiting_position = State()


def _pos_kb(src_key: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=POS_LABELS[p], callback_data=f"wmk:{src_key}:{p}")]
            for p in POSITIONS]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("watermark"), StateFilter("*"))
async def cmd_watermark(msg: Message, state: FSMContext):
    await state.set_state(WmkState.waiting_file)
    await msg.answer("💧 <b>Watermark</b>\n\nSend a video or image.", parse_mode="HTML")


@router.callback_query(F.data.regexp(r"^tool:[^:]+:watermark$"))
async def cb_watermark(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    _, src_key, _ = cb.data.split(":", 2)
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await state.set_state(WmkState.waiting_text)
    await cb.answer()
    await cb.message.reply("💧 <b>Watermark</b>\n\nEnter the watermark text:", parse_mode="HTML")


@router.message(WmkState.waiting_file, F.video | F.document | F.photo)
async def wmk_got_file(msg: Message, state: FSMContext):
    if msg.photo:
        fid, fname = msg.photo[-1].file_id, "photo.jpg"
        kind = "image"
    elif msg.video:
        fid, fname = msg.video.file_id, "video.mp4"
        kind = "video"
    else:
        fid, fname = msg.document.file_id, msg.document.file_name
        e = ext(fname)
        kind = "video" if e in VIDEO_EXTS else "image" if e in IMAGE_EXTS else None

    if not kind:
        await msg.reply("Please send a video or image.")
        return

    src_key = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"wmk_in_{src_key}.{ext(fname)}")
    await dl(msg.bot, fid, src)
    await state.update_data(src_path=src, src_key=src_key, kind=kind, filename=fname, file_id=fid)
    await state.set_state(WmkState.waiting_text)
    await msg.reply("Enter the watermark text:")


@router.message(WmkState.waiting_text)
async def wmk_got_text(msg: Message, state: FSMContext):
    text = (msg.text or "").strip()
    if not text:
        await msg.reply("Please send watermark text.")
        return
    await state.update_data(wm_text=text)
    data = await state.get_data()
    await state.set_state(WmkState.waiting_position)
    await msg.reply(
        f"Text: <b>{text}</b>\n\nChoose position:",
        reply_markup=_pos_kb(data["src_key"]), parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("wmk:"), WmkState.waiting_position)
async def wmk_do(cb: CallbackQuery, state: FSMContext):
    _, src_key, position = cb.data.split(":", 2)
    data = await state.get_data()
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return

    await cb.message.edit_reply_markup()
    await cb.answer()
    status = await cb.message.reply("💧 Adding watermark…")

    src = data.get("src_path")
    if not src:
        wd = workdir(cb.from_user.id)
        fname = data.get("filename", "file")
        src = os.path.join(wd, f"wmk_in_{src_key}.{ext(fname)}")
        await dl(cb.bot, data["file_id"], src)

    wd = workdir(cb.from_user.id)
    kind = data["kind"]
    text = data["wm_text"]
    out_ext = "mp4" if kind == "video" else ext(data.get("filename", "out.jpg")) or "jpg"
    dest = os.path.join(wd, f"wmk_out_{src_key}.{out_ext}")

    try:
        if kind == "video":
            await add_watermark_video(src, text, position, dest)
        else:
            await add_watermark_image(src, text, position, dest)
        await status.edit_text("✅ Done! Sending…")
        with open(dest, "rb") as f:
            await cb.message.reply_document(f, filename=f"watermarked.{out_ext}")
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(src, dest)
        await state.clear()
