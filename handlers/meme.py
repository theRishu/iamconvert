import os
import uuid
import asyncio
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from utils.helpers import workdir, dl, cleanup, ext
from utils.image_effects import make_meme

router = Router()


class MemeState(StatesGroup):
    waiting_file = State()
    waiting_top = State()
    waiting_bottom = State()


@router.message(Command("meme"), StateFilter("*"))
async def cmd_meme(msg: Message, state: FSMContext):
    await state.set_state(MemeState.waiting_file)
    await msg.answer("🤣 <b>Meme Generator</b>\n\nSend an image.", parse_mode="HTML")


@router.callback_query(F.data.regexp(r"^tool:[^:]+:meme$"))
async def cb_meme(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    _, src_key, _ = cb.data.split(":", 2)
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    if data.get("kind") != "image":
        await cb.answer("Meme tool only works with images.", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await state.set_state(MemeState.waiting_top)
    await cb.answer()
    await cb.message.reply(
        "🤣 <b>Meme</b>\n\nEnter the <b>TOP</b> text (or send <code>skip</code>):",
        parse_mode="HTML",
    )


@router.message(MemeState.waiting_file, F.photo | F.document)
async def meme_got_file(msg: Message, state: FSMContext):
    if msg.photo:
        fid, fname = msg.photo[-1].file_id, "photo.jpg"
    else:
        fid, fname = msg.document.file_id, msg.document.file_name
    src_key = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"meme_in_{src_key}.{ext(fname)}")
    await dl(msg.bot, fid, src)
    await state.update_data(src_path=src, src_key=src_key, filename=fname)
    await state.set_state(MemeState.waiting_top)
    await msg.reply("Enter <b>TOP</b> text (or <code>skip</code>):", parse_mode="HTML")


@router.message(MemeState.waiting_top)
async def meme_got_top(msg: Message, state: FSMContext):
    top = "" if (msg.text or "").strip().lower() == "skip" else (msg.text or "").strip()
    await state.update_data(top_text=top)
    await state.set_state(MemeState.waiting_bottom)
    await msg.reply("Enter <b>BOTTOM</b> text (or <code>skip</code>):", parse_mode="HTML")


@router.message(MemeState.waiting_bottom)
async def meme_got_bottom(msg: Message, state: FSMContext):
    bottom = "" if (msg.text or "").strip().lower() == "skip" else (msg.text or "").strip()
    data = await state.get_data()
    top = data.get("top_text", "")
    src_key = data.get("src_key", "")

    if not top and not bottom:
        await msg.reply("You need at least one text. Try again:")
        return

    src = data.get("src_path")
    if not src:
        wd = workdir(msg.from_user.id)
        src = os.path.join(wd, f"meme_in_{src_key}.{ext(data.get('filename','photo.jpg'))}")
        await dl(msg.bot, data["file_id"], src)

    wd = workdir(msg.from_user.id)
    dest = os.path.join(wd, f"meme_out_{src_key}.jpg")
    status = await msg.reply("🤣 Creating meme…")
    try:
        await asyncio.to_thread(make_meme, src, top, bottom, dest)
        await status.edit_text("✅ Done!")
        with open(dest, "rb") as f:
            await msg.reply_photo(f)
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(src, dest)
        await state.clear()
