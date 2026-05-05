import os
import uuid
import asyncio
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from utils.helpers import workdir, dl, cleanup, ext
from utils.image_effects import images_to_gif

router = Router()

_DONE_KB = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text="✅ Create GIF",  callback_data="gif:done"),
    InlineKeyboardButton(text="❌ Cancel",       callback_data="gif:cancel"),
]])
_FPS_KB = lambda session: InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text="2 FPS (slow)", callback_data=f"gif:fps:{session}:2"),
    InlineKeyboardButton(text="5 FPS",        callback_data=f"gif:fps:{session}:5"),
    InlineKeyboardButton(text="10 FPS (fast)",callback_data=f"gif:fps:{session}:10"),
]])


class GifState(StatesGroup):
    collecting = State()
    choosing_fps = State()


@router.message(Command("makegif"), StateFilter("*"))
async def cmd_makegif(msg: Message, state: FSMContext):
    session = str(uuid.uuid4())[:8]
    await state.set_state(GifState.collecting)
    await state.update_data(images=[], session=session)
    await msg.answer(
        "🎞 <b>GIF Maker</b>\n\n"
        "Send images one by one (min 2), then tap <b>Create GIF</b>.",
        reply_markup=_DONE_KB, parse_mode="HTML",
    )


@router.message(GifState.collecting, F.photo | F.document)
async def gif_collect(msg: Message, state: FSMContext):
    if msg.photo:
        fid, fname = msg.photo[-1].file_id, "photo.jpg"
    else:
        fid, fname = msg.document.file_id, msg.document.file_name
    data = await state.get_data()
    images = data.get("images", [])
    images.append({"file_id": fid, "filename": fname})
    await state.update_data(images=images)
    await msg.reply(f"🖼 Image {len(images)} added. Send more or tap Create GIF.", reply_markup=_DONE_KB)


@router.callback_query(F.data == "gif:cancel")
async def gif_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ Cancelled.")
    await cb.answer()


@router.callback_query(F.data == "gif:done", GifState.collecting)
async def gif_done(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if len(data.get("images", [])) < 2:
        await cb.answer("Need at least 2 images!", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await cb.answer()
    session = data.get("session", "")
    await cb.message.reply("Choose GIF speed:", reply_markup=_FPS_KB(session))
    await state.set_state(GifState.choosing_fps)


@router.callback_query(F.data.startswith("gif:fps:"), GifState.choosing_fps)
async def gif_fps(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")
    session, fps = parts[2], int(parts[3])
    data = await state.get_data()
    images = data.get("images", [])
    await cb.message.edit_reply_markup()
    await cb.answer()
    status = await cb.message.reply(f"🎞 Downloading {len(images)} images…")
    wd = workdir(cb.from_user.id)
    paths = []
    try:
        for i, img in enumerate(images):
            p = os.path.join(wd, f"gif_{session}_{i}.{ext(img['filename'])}")
            await dl(cb.bot, img["file_id"], p)
            paths.append(p)
        await status.edit_text(f"🎞 Creating GIF at {fps} FPS…")
        dest = os.path.join(wd, f"animated_{session}.gif")
        await asyncio.to_thread(images_to_gif, paths, dest, fps)
        size_mb = os.path.getsize(dest) / 1024 / 1024
        await status.edit_text(f"✅ GIF ready ({size_mb:.1f} MB)! Sending…")
        with open(dest, "rb") as f:
            await cb.message.reply_document(f, filename="animated.gif")
        cleanup(dest)
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        for p in paths:
            cleanup(p)
        await state.clear()
