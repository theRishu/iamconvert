import os
import uuid
import asyncio
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from utils.helpers import workdir, dl, cleanup, ext
from utils.image_effects import rotate_image
from utils.video_tools import _run as vrun

router = Router()

VIDEO_EXTS = {"mp4", "avi", "mkv", "mov", "webm"}
IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "bmp", "tiff"}

ACTIONS = [
    ("↩ 90° Left",  "90ccw"),
    ("↪ 90° Right", "90cw"),
    ("🔃 180°",      "180"),
    ("↔ Flip H",    "hflip"),
    ("↕ Flip V",    "vflip"),
]
_VF = {"90cw": "transpose=1", "90ccw": "transpose=2",
       "180": "vflip,hflip", "hflip": "hflip", "vflip": "vflip"}


class RotateState(StatesGroup):
    waiting_file = State()
    waiting_action = State()


def _kb(src_key: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=f"rot:{src_key}:{val}")]
            for label, val in ACTIONS]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("rotate"), StateFilter("*"))
async def cmd_rotate(msg: Message, state: FSMContext):
    await state.set_state(RotateState.waiting_file)
    await msg.answer("🔄 <b>Rotate / Flip</b>\n\nSend an image or video.", parse_mode="HTML")


@router.callback_query(F.data.regexp(r"^tool:[^:]+:rotate$"))
async def cb_rotate(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    _, src_key, _ = cb.data.split(":", 2)
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await state.set_state(RotateState.waiting_action)
    await cb.answer()
    await cb.message.reply("🔄 Choose rotation:", reply_markup=_kb(src_key))


@router.message(RotateState.waiting_file, F.video | F.document | F.photo)
async def rotate_got_file(msg: Message, state: FSMContext):
    if msg.photo:
        fid, fname, kind = msg.photo[-1].file_id, "photo.jpg", "image"
    elif msg.video:
        fid, fname, kind = msg.video.file_id, "video.mp4", "video"
    else:
        fid, fname = msg.document.file_id, msg.document.file_name
        kind = "video" if ext(fname) in VIDEO_EXTS else "image"
    src_key = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"rot_in_{src_key}.{ext(fname)}")
    await dl(msg.bot, fid, src)
    await state.update_data(src_path=src, src_key=src_key, kind=kind, filename=fname)
    await state.set_state(RotateState.waiting_action)
    await msg.reply("🔄 Choose rotation:", reply_markup=_kb(src_key))


@router.callback_query(F.data.startswith("rot:"), RotateState.waiting_action)
async def rotate_do(cb: CallbackQuery, state: FSMContext):
    _, src_key, action = cb.data.split(":", 2)
    data = await state.get_data()
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await cb.answer()
    status = await cb.message.reply("🔄 Rotating…")
    src = data.get("src_path")
    if not src:
        wd = workdir(cb.from_user.id)
        src = os.path.join(wd, f"rot_in_{src_key}.{ext(data.get('filename','file'))}")
        await dl(cb.bot, data["file_id"], src)
    wd = workdir(cb.from_user.id)
    kind = data.get("kind", "image")
    dest = None
    try:
        if kind == "video":
            dest = os.path.join(wd, f"rot_out_{src_key}.mp4")
            await vrun(["ffmpeg", "-y", "-i", src, "-vf", _VF[action], "-codec:a", "copy", dest])
        else:
            out_e = ext(data.get("filename", "out.jpg")) or "jpg"
            dest = os.path.join(wd, f"rot_out_{src_key}.{out_e}")
            await asyncio.to_thread(rotate_image, src, action, dest)
        await status.edit_text("✅ Done! Sending…")
        with open(dest, "rb") as f:
            await cb.message.reply_document(f, filename=os.path.basename(dest))
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(src, dest)
        await state.clear()
