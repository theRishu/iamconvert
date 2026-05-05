import os
import uuid
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from utils.helpers import workdir, dl, cleanup, ext
from utils.video_tools import extract_subtitles, embed_subtitles

router = Router()


class SubState(StatesGroup):
    choosing_mode = State()
    waiting_video_extract = State()
    waiting_video_embed = State()
    waiting_subtitle = State()


_MODE_KB = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text="📤 Extract subtitles from video", callback_data="sub:extract"),
    InlineKeyboardButton(text="📥 Embed subtitle into video",   callback_data="sub:embed"),
]])


@router.message(Command("subtitle"), StateFilter("*"))
async def cmd_subtitle(msg: Message, state: FSMContext):
    await state.set_state(SubState.choosing_mode)
    await msg.answer("📝 <b>Subtitles</b>\n\nWhat do you want to do?",
                     reply_markup=_MODE_KB, parse_mode="HTML")


@router.callback_query(F.data.regexp(r"^tool:[^:]+:subtitle$"))
async def cb_subtitle(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    _, src_key, _ = cb.data.split(":", 2)
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    if data.get("kind") != "video":
        await cb.answer("Subtitle tools only work with videos.", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await state.set_state(SubState.choosing_mode)
    await cb.answer()
    await cb.message.reply("📝 <b>Subtitles</b>\n\nWhat do you want to do?",
                            reply_markup=_MODE_KB, parse_mode="HTML")


@router.callback_query(F.data == "sub:extract", SubState.choosing_mode)
async def sub_choose_extract(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await cb.message.edit_reply_markup()
    await cb.answer()
    if data.get("file_id"):
        # File already known from convert.py
        await state.update_data(mode="extract")
        await _do_extract(cb.message, cb.bot, state, data)
    else:
        await state.update_data(mode="extract")
        await state.set_state(SubState.waiting_video_extract)
        await cb.message.reply("Send the video to extract subtitles from:")


@router.callback_query(F.data == "sub:embed", SubState.choosing_mode)
async def sub_choose_embed(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await cb.message.edit_reply_markup()
    await cb.answer()
    await state.update_data(mode="embed")
    if data.get("file_id"):
        await state.set_state(SubState.waiting_subtitle)
        await cb.message.reply("Video noted. Now send the subtitle file (.srt or .ass):")
    else:
        await state.set_state(SubState.waiting_video_embed)
        await cb.message.reply("Send the video you want to embed subtitles into:")


@router.message(SubState.waiting_video_extract, F.video | F.document)
async def sub_got_video_extract(msg: Message, state: FSMContext):
    if msg.video:
        fid, fname = msg.video.file_id, "video.mp4"
    else:
        fid, fname = msg.document.file_id, msg.document.file_name
    src_key = str(uuid.uuid4())[:8]
    await state.update_data(file_id=fid, filename=fname, src_key=src_key)
    data = await state.get_data()
    await _do_extract(msg, msg.bot, state, data)


@router.message(SubState.waiting_video_embed, F.video | F.document)
async def sub_got_video_embed(msg: Message, state: FSMContext):
    if msg.video:
        fid, fname = msg.video.file_id, "video.mp4"
    else:
        fid, fname = msg.document.file_id, msg.document.file_name
    src_key = str(uuid.uuid4())[:8]
    await state.update_data(file_id=fid, filename=fname, src_key=src_key)
    await state.set_state(SubState.waiting_subtitle)
    await msg.reply("Video received. Now send the subtitle file (.srt or .ass):")


@router.message(SubState.waiting_subtitle, F.document)
async def sub_got_subtitle(msg: Message, state: FSMContext):
    data = await state.get_data()
    sub_id = msg.document.file_id
    sub_name = msg.document.file_name
    src_key = data.get("src_key", str(uuid.uuid4())[:8])

    wd = workdir(msg.from_user.id)
    video_src = os.path.join(wd, f"sub_vid_{src_key}.{ext(data.get('filename', 'video.mp4'))}")
    sub_src = os.path.join(wd, f"sub_sub_{src_key}.{ext(sub_name)}")
    dest = os.path.join(wd, f"subbed_{src_key}.mp4")

    status = await msg.reply("📥 Embedding subtitles…")
    try:
        await dl(msg.bot, data["file_id"], video_src)
        await dl(msg.bot, sub_id, sub_src)
        await embed_subtitles(video_src, sub_src, dest)
        await status.edit_text("✅ Done! Sending…")
        with open(dest, "rb") as f:
            await msg.reply_document(f, filename="with_subtitles.mp4")
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(video_src, sub_src, dest)
        await state.clear()


async def _do_extract(msg, bot, state, data):
    src_key = data.get("src_key", str(uuid.uuid4())[:8])
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"sub_in_{src_key}.{ext(data.get('filename', 'video.mp4'))}")
    dest_srt = os.path.join(wd, f"subs_{src_key}.srt")
    dest_ass = os.path.join(wd, f"subs_{src_key}.ass")

    status = await msg.reply("📤 Extracting subtitles…")
    try:
        await dl(bot, data["file_id"], src)
        try:
            await extract_subtitles(src, dest_srt)
            out = dest_srt
        except Exception:
            await extract_subtitles(src, dest_ass)
            out = dest_ass
        await status.edit_text("✅ Done! Sending…")
        with open(out, "rb") as f:
            await msg.reply_document(f, filename=os.path.basename(out))
    except Exception as e:
        await status.edit_text(f"❌ No subtitles found or extraction failed:\n<code>{e}</code>",
                                parse_mode="HTML")
    finally:
        cleanup(src, dest_srt, dest_ass)
        await state.clear()
