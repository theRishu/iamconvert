import os
import uuid
import asyncio
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from utils.helpers import workdir, dl, cleanup, ext
from utils.image_effects import apply_filter, FILTERS

router = Router()

IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "bmp", "tiff"}

FILTER_LABELS = {
    "grayscale": "⬛ Grayscale",
    "sepia":     "🟤 Sepia",
    "invert":    "🔲 Invert",
    "blur":      "🌫 Blur",
    "sharpen":   "🔪 Sharpen",
    "emboss":    "🗿 Emboss",
    "vintage":   "🎞 Vintage",
    "sketch":    "✏️ Sketch",
    "cartoon":   "🎨 Cartoon",
    "oilpaint":  "🖌 Oil Paint",
    "pixelate":  "🟦 Pixelate",
    "edge":      "🔍 Edge Detect",
}


class FilterState(StatesGroup):
    waiting_file = State()
    waiting_filter = State()


def _kb(src_key: str) -> InlineKeyboardMarkup:
    items = list(FILTER_LABELS.items())
    rows = []
    for i in range(0, len(items), 2):
        row = [InlineKeyboardButton(text=items[i][1],
                                    callback_data=f"flt:{src_key}:{items[i][0]}")]
        if i + 1 < len(items):
            row.append(InlineKeyboardButton(text=items[i+1][1],
                                            callback_data=f"flt:{src_key}:{items[i+1][0]}"))
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("filter"), StateFilter("*"))
async def cmd_filter(msg: Message, state: FSMContext):
    await state.set_state(FilterState.waiting_file)
    await msg.answer("🎨 <b>Image Filters</b>\n\nSend an image.", parse_mode="HTML")


@router.callback_query(F.data.regexp(r"^tool:[^:]+:filter$"))
async def cb_filter(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    _, src_key, _ = cb.data.split(":", 2)
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    if data.get("kind") != "image":
        await cb.answer("Filters only work with images.", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await state.set_state(FilterState.waiting_filter)
    await cb.answer()
    await cb.message.reply("🎨 Choose filter:", reply_markup=_kb(src_key))


@router.message(FilterState.waiting_file, F.photo | F.document)
async def filter_got_file(msg: Message, state: FSMContext):
    if msg.photo:
        fid, fname = msg.photo[-1].file_id, "photo.jpg"
    else:
        fid, fname = msg.document.file_id, msg.document.file_name
    src_key = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"flt_in_{src_key}.{ext(fname)}")
    await dl(msg.bot, fid, src)
    await state.update_data(src_path=src, src_key=src_key, filename=fname)
    await state.set_state(FilterState.waiting_filter)
    await msg.reply("🎨 Choose filter:", reply_markup=_kb(src_key))


@router.callback_query(F.data.startswith("flt:"), FilterState.waiting_filter)
async def filter_do(cb: CallbackQuery, state: FSMContext):
    _, src_key, filter_name = cb.data.split(":", 2)
    data = await state.get_data()
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await cb.answer()
    status = await cb.message.reply(f"🎨 Applying {FILTER_LABELS.get(filter_name, filter_name)}…")
    src = data.get("src_path")
    if not src:
        wd = workdir(cb.from_user.id)
        src = os.path.join(wd, f"flt_in_{src_key}.{ext(data.get('filename','file'))}")
        await dl(cb.bot, data["file_id"], src)
    wd = workdir(cb.from_user.id)
    out_e = ext(data.get("filename", "out.jpg")) or "jpg"
    dest = os.path.join(wd, f"flt_out_{src_key}.{out_e}")
    try:
        await asyncio.to_thread(apply_filter, src, filter_name, dest)
        await status.edit_text("✅ Done! Sending…")
        with open(dest, "rb") as f:
            await cb.message.reply_document(f, filename=f"{filter_name}.{out_e}")
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(src, dest)
        await state.clear()
