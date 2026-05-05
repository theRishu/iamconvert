import os
import uuid
import asyncio
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from utils.helpers import workdir, dl, cleanup, ext
from utils.image_effects import enhance_image, ENHANCE_MAP, ENHANCE_LEVELS

router = Router()

PROPS = {
    "brightness": "☀️ Brightness",
    "contrast":   "🎛 Contrast",
    "saturation": "🌈 Saturation",
    "sharpness":  "🔆 Sharpness",
}
LEVELS = {
    "very_low":  "🔅 Very Low",
    "low":       "🔽 Low",
    "normal":    "⬜ Normal",
    "high":      "🔼 High",
    "very_high": "🔆 Very High",
}


class EnhanceState(StatesGroup):
    waiting_file = State()
    waiting_prop = State()
    waiting_level = State()


def _prop_kb(src_key: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=f"enh:{src_key}:prop:{key}")]
            for key, label in PROPS.items()]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _level_kb(src_key: str, prop: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=f"enh:{src_key}:lvl:{prop}:{key}")]
            for key, label in LEVELS.items()]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("enhance"), StateFilter("*"))
async def cmd_enhance(msg: Message, state: FSMContext):
    await state.set_state(EnhanceState.waiting_file)
    await msg.answer("✨ <b>Enhance Image</b>\n\nSend an image.", parse_mode="HTML")


@router.callback_query(F.data.regexp(r"^tool:[^:]+:enhance$"))
async def cb_enhance(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    _, src_key, _ = cb.data.split(":", 2)
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    if data.get("kind") != "image":
        await cb.answer("Enhance only works with images.", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await state.set_state(EnhanceState.waiting_prop)
    await cb.answer()
    await cb.message.reply("✨ What do you want to adjust?", reply_markup=_prop_kb(src_key))


@router.message(EnhanceState.waiting_file, F.photo | F.document)
async def enhance_got_file(msg: Message, state: FSMContext):
    if msg.photo:
        fid, fname = msg.photo[-1].file_id, "photo.jpg"
    else:
        fid, fname = msg.document.file_id, msg.document.file_name
    src_key = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"enh_in_{src_key}.{ext(fname)}")
    await dl(msg.bot, fid, src)
    await state.update_data(src_path=src, src_key=src_key, filename=fname)
    await state.set_state(EnhanceState.waiting_prop)
    await msg.reply("✨ What do you want to adjust?", reply_markup=_prop_kb(src_key))


@router.callback_query(F.data.regexp(r"^enh:[^:]+:prop:.+$"), EnhanceState.waiting_prop)
async def enhance_prop(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")
    src_key, prop = parts[1], parts[3]
    data = await state.get_data()
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    await state.update_data(prop=prop)
    await state.set_state(EnhanceState.waiting_level)
    await cb.message.edit_reply_markup()
    await cb.answer()
    await cb.message.reply(
        f"Choose level for <b>{PROPS[prop]}</b>:",
        reply_markup=_level_kb(src_key, prop), parse_mode="HTML",
    )


@router.callback_query(F.data.regexp(r"^enh:[^:]+:lvl:.+:.+$"), EnhanceState.waiting_level)
async def enhance_do(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")
    src_key, prop, level = parts[1], parts[3], parts[4]
    data = await state.get_data()
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await cb.answer()
    status = await cb.message.reply(f"✨ Enhancing {PROPS[prop]}…")
    src = data.get("src_path")
    if not src:
        wd = workdir(cb.from_user.id)
        src = os.path.join(wd, f"enh_in_{src_key}.{ext(data.get('filename','file'))}")
        await dl(cb.bot, data["file_id"], src)
    wd = workdir(cb.from_user.id)
    out_e = ext(data.get("filename", "out.jpg")) or "jpg"
    dest = os.path.join(wd, f"enh_out_{src_key}.{out_e}")
    try:
        await asyncio.to_thread(enhance_image, src, prop, level, dest)
        await status.edit_text("✅ Done! Sending…")
        with open(dest, "rb") as f:
            await cb.message.reply_document(f, filename=f"enhanced.{out_e}")
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(src, dest)
        await state.clear()
