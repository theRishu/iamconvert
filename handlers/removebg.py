import os
import uuid
import asyncio
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from utils.helpers import workdir, dl, cleanup, ext

router = Router()


class RmbgState(StatesGroup):
    waiting_file = State()


@router.message(Command("removebg"), StateFilter("*"))
async def cmd_removebg(msg: Message, state: FSMContext):
    await state.set_state(RmbgState.waiting_file)
    await msg.answer(
        "🎭 <b>Remove Background</b>\n\n"
        "Send an image and I'll remove its background.\n"
        "<i>First run downloads the AI model (~170 MB). Subsequent runs are fast.</i>",
        parse_mode="HTML",
    )


@router.callback_query(F.data.regexp(r"^tool:[^:]+:removebg$"))
async def cb_removebg(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    _, src_key, _ = cb.data.split(":", 2)
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    if data.get("kind") != "image":
        await cb.answer("Remove BG only works with images.", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await cb.answer()
    status = await cb.message.reply("🎭 Removing background… (may take a moment)")
    await _do_removebg(cb.message, cb.bot, status, data, data["src_key"])


@router.message(RmbgState.waiting_file, F.photo | F.document)
async def removebg_got_file(msg: Message, state: FSMContext):
    if msg.photo:
        fid, fname = msg.photo[-1].file_id, "photo.jpg"
    else:
        fid, fname = msg.document.file_id, msg.document.file_name
    src_key = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"rmbg_in_{src_key}.{ext(fname)}")
    status = await msg.reply("🎭 Removing background… (may take a moment)")
    await state.update_data(src_path=src, src_key=src_key, filename=fname, file_id=fid)
    try:
        await dl(msg.bot, fid, src)
        dest = os.path.join(wd, f"rmbg_out_{src_key}.png")
        await asyncio.to_thread(_remove_bg, src, dest)
        await status.edit_text("✅ Done! Sending PNG with transparent background…")
        with open(dest, "rb") as f:
            await msg.reply_document(f, filename="no_background.png")
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(src)
        await state.clear()


async def _do_removebg(msg, bot, status, data, src_key):
    wd = workdir(msg.from_user.id)
    fname = data.get("filename", "photo.jpg")
    src = data.get("src_path") or os.path.join(wd, f"rmbg_in_{src_key}.{ext(fname)}")
    if not data.get("src_path"):
        await dl(bot, data["file_id"], src)
    dest = os.path.join(wd, f"rmbg_out_{src_key}.png")
    try:
        await asyncio.to_thread(_remove_bg, src, dest)
        await status.edit_text("✅ Done! Sending PNG with transparent background…")
        with open(dest, "rb") as f:
            await msg.reply_document(f, filename="no_background.png")
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(src, dest)


def _remove_bg(src: str, dest: str):
    try:
        from rembg import remove
        with open(src, "rb") as f:
            data = f.read()
        result = remove(data)
        with open(dest, "wb") as f:
            f.write(result)
    except ImportError:
        raise RuntimeError("rembg not installed. Run: pip install rembg")
