import os
import uuid
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from utils.helpers import workdir, dl, cleanup, ext
from utils.image_tools import resize_image
from utils.video_tools import resize_video

router = Router()

VIDEO_EXTS = {"mp4", "avi", "mkv", "mov", "webm"}
IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "bmp", "tiff"}

PRESETS = [
    ("HD 1280×720",    "1280x720"),
    ("FHD 1920×1080",  "1920x1080"),
    ("4K 3840×2160",   "3840x2160"),
    ("Square 1080×1080", "1080x1080"),
    ("Instagram 1080×1350", "1080x1350"),
    ("Twitter 1200×675", "1200x675"),
    ("Custom…",        "custom"),
]


class ResizeState(StatesGroup):
    waiting_file = State()
    waiting_size = State()
    waiting_custom = State()


def _size_kb(src_key: str) -> InlineKeyboardMarkup:
    rows = []
    for label, val in PRESETS:
        rows.append([InlineKeyboardButton(text=label, callback_data=f"rsz:{src_key}:{val}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("resize"), StateFilter("*"))
async def cmd_resize(msg: Message, state: FSMContext):
    await state.set_state(ResizeState.waiting_file)
    await msg.answer("📏 <b>Resize</b>\n\nSend an image or video.", parse_mode="HTML")


@router.callback_query(F.data.regexp(r"^tool:[^:]+:resize$"))
async def cb_resize(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    _, src_key, _ = cb.data.split(":", 2)
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await state.set_state(ResizeState.waiting_size)
    await cb.answer()
    await cb.message.reply("📏 <b>Resize</b>\n\nChoose size:",
                           reply_markup=_size_kb(src_key), parse_mode="HTML")


@router.message(ResizeState.waiting_file, F.video | F.document | F.photo)
async def resize_got_file(msg: Message, state: FSMContext):
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
        await msg.reply("Please send an image or video.")
        return

    src_key = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"rsz_in_{src_key}.{ext(fname)}")
    await dl(msg.bot, fid, src)
    await state.update_data(src_path=src, src_key=src_key, kind=kind, filename=fname, file_id=fid)
    await state.set_state(ResizeState.waiting_size)
    await msg.reply("Choose size:", reply_markup=_size_kb(src_key))


@router.callback_query(F.data.startswith("rsz:"), ResizeState.waiting_size)
async def resize_size_chosen(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":", 2)
    src_key, size_val = parts[1], parts[2]
    data = await state.get_data()
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return

    await cb.message.edit_reply_markup()
    await cb.answer()

    if size_val == "custom":
        await state.set_state(ResizeState.waiting_custom)
        await cb.message.reply("Enter custom dimensions as <code>WIDTHxHEIGHT</code> (e.g. <code>800x600</code>):",
                               parse_mode="HTML")
        return

    w, h = map(int, size_val.split("x"))
    await _do_resize(cb.message, cb.bot, state, data, src_key, w, h)


@router.message(ResizeState.waiting_custom)
async def resize_custom(msg: Message, state: FSMContext):
    try:
        w_str, h_str = (msg.text or "").lower().replace(" ", "").split("x")
        w, h = int(w_str), int(h_str)
        assert w > 0 and h > 0
    except Exception:
        await msg.reply("Invalid format. Try <code>800x600</code>:", parse_mode="HTML")
        return
    data = await state.get_data()
    src_key = data.get("src_key", "")
    await _do_resize(msg, msg.bot, state, data, src_key, w, h)


async def _do_resize(msg, bot, state, data, src_key, w, h):
    src = data.get("src_path")
    if not src:
        wd = workdir(msg.from_user.id)
        fname = data.get("filename", "file")
        src = os.path.join(wd, f"rsz_in_{src_key}.{ext(fname)}")
        await dl(bot, data["file_id"], src)

    kind = data.get("kind", "image")
    wd = workdir(msg.from_user.id)
    out_ext = ext(data.get("filename", "out.jpg")) or ("mp4" if kind == "video" else "jpg")
    dest = os.path.join(wd, f"resized_{src_key}.{out_ext}")

    status = await msg.reply(f"📏 Resizing to {w}×{h}…")
    try:
        if kind == "video":
            await resize_video(src, w, h, dest)
        else:
            await resize_image(src, w, h, dest)
        await status.edit_text("✅ Done! Sending…")
        with open(dest, "rb") as f:
            await msg.reply_document(f, filename=f"resized_{w}x{h}.{out_ext}")
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(src, dest)
        await state.clear()
