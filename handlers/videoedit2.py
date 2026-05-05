import os
import uuid
import zipfile
import shutil
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from utils.helpers import workdir, dl, cleanup, ext
from utils.audio_tools import reverse_video, loop_video, split_video, video_to_videonote
from utils.video_tools import get_duration

router = Router()

LOOP_OPTIONS = [("2×", 2), ("3×", 3), ("5×", 5), ("10×", 10)]
SPLIT_OPTIONS = [("2 parts", 2), ("3 parts", 3), ("4 parts", 4), ("6 parts", 6)]


class Vid2State(StatesGroup):
    reverse_waiting = State()
    loop_waiting_file = State()
    loop_waiting_count = State()
    split_waiting_file = State()
    split_waiting_count = State()
    note_waiting = State()


# ── /reverse ─────────────────────────────────────────────────────────────────

@router.message(Command("reverse"), StateFilter("*"))
async def cmd_reverse(msg: Message, state: FSMContext):
    await state.set_state(Vid2State.reverse_waiting)
    await msg.answer("⏪ <b>Reverse Video</b>\n\nSend the video. (Warning: slow for large files)", parse_mode="HTML")


@router.callback_query(F.data.regexp(r"^tool:[^:]+:reverse$"))
async def cb_reverse(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    _, src_key, _ = cb.data.split(":", 2)
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    if data.get("kind") != "video":
        await cb.answer("Reverse only works with videos.", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await cb.answer()
    status = await cb.message.reply("⏪ Reversing… (this may take a while)")
    await _do_reverse(cb.message, cb.bot, status, data, src_key)


@router.message(Vid2State.reverse_waiting, F.video | F.document)
async def reverse_got_file(msg: Message, state: FSMContext):
    if msg.video:
        fid, fname = msg.video.file_id, "video.mp4"
    else:
        fid, fname = msg.document.file_id, msg.document.file_name
    src_key = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"rev_in_{src_key}.{ext(fname)}")
    status = await msg.reply("⏪ Downloading & reversing…")
    await dl(msg.bot, fid, src)
    data = {"src_path": src, "src_key": src_key, "filename": fname, "file_id": fid}
    await state.update_data(**data)
    await _do_reverse(msg, msg.bot, status, data, src_key)
    await state.clear()


async def _do_reverse(msg, bot, status, data, src_key):
    wd = workdir(msg.from_user.id)
    src = data.get("src_path")
    if not src:
        src = os.path.join(wd, f"rev_in_{src_key}.{ext(data.get('filename','video.mp4'))}")
        await dl(bot, data["file_id"], src)
    dest = os.path.join(wd, f"reversed_{src_key}.mp4")
    try:
        await reverse_video(src, dest)
        await status.edit_text("✅ Done!")
        with open(dest, "rb") as f:
            await msg.reply_document(f, filename="reversed.mp4")
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(src, dest)


# ── /loop ─────────────────────────────────────────────────────────────────────

@router.message(Command("loop"), StateFilter("*"))
async def cmd_loop(msg: Message, state: FSMContext):
    await state.set_state(Vid2State.loop_waiting_file)
    await msg.answer("🔁 <b>Loop Video</b>\n\nSend the video.", parse_mode="HTML")


@router.callback_query(F.data.regexp(r"^tool:[^:]+:loop$"))
async def cb_loop(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    _, src_key, _ = cb.data.split(":", 2)
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    if data.get("kind") != "video":
        await cb.answer("Loop only works with videos.", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await state.set_state(Vid2State.loop_waiting_count)
    await cb.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"{n}×", callback_data=f"lp:{src_key}:{n}")
        for _, n in LOOP_OPTIONS
    ]])
    await cb.message.reply("🔁 How many times?", reply_markup=kb)


@router.message(Vid2State.loop_waiting_file, F.video | F.document)
async def loop_got_file(msg: Message, state: FSMContext):
    if msg.video:
        fid, fname = msg.video.file_id, "video.mp4"
    else:
        fid, fname = msg.document.file_id, msg.document.file_name
    src_key = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"loop_in_{src_key}.{ext(fname)}")
    await dl(msg.bot, fid, src)
    await state.update_data(src_path=src, src_key=src_key, filename=fname, file_id=fid)
    await state.set_state(Vid2State.loop_waiting_count)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"{n}×", callback_data=f"lp:{src_key}:{n}")
        for _, n in LOOP_OPTIONS
    ]])
    await msg.reply("🔁 How many times?", reply_markup=kb)


@router.callback_query(F.data.startswith("lp:"), Vid2State.loop_waiting_count)
async def loop_do(cb: CallbackQuery, state: FSMContext):
    _, src_key, n_str = cb.data.split(":", 2)
    times = int(n_str)
    data = await state.get_data()
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await cb.answer()
    status = await cb.message.reply(f"🔁 Looping {times}×…")
    src = data.get("src_path")
    wd = workdir(cb.from_user.id)
    if not src:
        src = os.path.join(wd, f"loop_in_{src_key}.mp4")
        await dl(cb.bot, data["file_id"], src)
    dest = os.path.join(wd, f"looped_{src_key}.mp4")
    try:
        await loop_video(src, dest, times)
        await status.edit_text("✅ Done!")
        with open(dest, "rb") as f:
            await cb.message.reply_document(f, filename=f"looped_{times}x.mp4")
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(src, dest)
        await state.clear()


# ── /split ────────────────────────────────────────────────────────────────────

@router.message(Command("split"), StateFilter("*"))
async def cmd_split(msg: Message, state: FSMContext):
    await state.set_state(Vid2State.split_waiting_file)
    await msg.answer("✂️ <b>Split Video</b>\n\nSend the video to split.", parse_mode="HTML")


@router.callback_query(F.data.regexp(r"^tool:[^:]+:split$"))
async def cb_split(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    _, src_key, _ = cb.data.split(":", 2)
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    if data.get("kind") != "video":
        await cb.answer("Split only works with videos.", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await state.set_state(Vid2State.split_waiting_count)
    await cb.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=label, callback_data=f"spl:{src_key}:{n}")
        for label, n in SPLIT_OPTIONS[:2]
    ], [
        InlineKeyboardButton(text=label, callback_data=f"spl:{src_key}:{n}")
        for label, n in SPLIT_OPTIONS[2:]
    ]])
    await cb.message.reply("✂️ Split into how many parts?", reply_markup=kb)


@router.message(Vid2State.split_waiting_file, F.video | F.document)
async def split_got_file(msg: Message, state: FSMContext):
    if msg.video:
        fid, fname = msg.video.file_id, "video.mp4"
    else:
        fid, fname = msg.document.file_id, msg.document.file_name
    src_key = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"spl_in_{src_key}.{ext(fname)}")
    await dl(msg.bot, fid, src)
    dur = await get_duration(src)
    await state.update_data(src_path=src, src_key=src_key, filename=fname, duration=dur, file_id=fid)
    await state.set_state(Vid2State.split_waiting_count)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=label, callback_data=f"spl:{src_key}:{n}")
        for label, n in SPLIT_OPTIONS[:2]
    ], [
        InlineKeyboardButton(text=label, callback_data=f"spl:{src_key}:{n}")
        for label, n in SPLIT_OPTIONS[2:]
    ]])
    await msg.reply(f"Duration: {dur:.0f}s. Split into how many parts?", reply_markup=kb)


@router.callback_query(F.data.startswith("spl:"), Vid2State.split_waiting_count)
async def split_do(cb: CallbackQuery, state: FSMContext):
    _, src_key, n_str = cb.data.split(":", 2)
    parts = int(n_str)
    data = await state.get_data()
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await cb.answer()
    status = await cb.message.reply(f"✂️ Splitting into {parts} parts…")
    src = data.get("src_path")
    wd = workdir(cb.from_user.id)
    dur = data.get("duration", 0)
    if not src or not dur:
        src = os.path.join(wd, f"spl_in_{src_key}.mp4")
        await dl(cb.bot, data["file_id"], src)
        dur = await get_duration(src)
    split_dir = os.path.join(wd, f"split_{src_key}")
    zip_path = os.path.join(wd, f"split_{src_key}.zip")
    try:
        part_paths = await split_video(src, split_dir, parts, dur)
        await status.edit_text(f"✅ {len(part_paths)} parts created. Sending as ZIP…")
        with zipfile.ZipFile(zip_path, "w") as zf:
            for p in part_paths:
                zf.write(p, os.path.basename(p))
        with open(zip_path, "rb") as f:
            await cb.message.reply_document(f, filename=f"split_{parts}parts.zip")
        cleanup(zip_path)
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(src)
        shutil.rmtree(split_dir, ignore_errors=True)
        await state.clear()


# ── /videonote ────────────────────────────────────────────────────────────────

@router.message(Command("videonote"), StateFilter("*"))
async def cmd_videonote(msg: Message, state: FSMContext):
    await state.set_state(Vid2State.note_waiting)
    await msg.answer("⭕ <b>Video Note</b>\n\nSend a video to convert to circular video note (max 60s).", parse_mode="HTML")


@router.message(Vid2State.note_waiting, F.video | F.document)
async def videonote_got_file(msg: Message, state: FSMContext):
    if msg.video:
        fid, fname = msg.video.file_id, "video.mp4"
    else:
        fid, fname = msg.document.file_id, msg.document.file_name
    src_key = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"note_in_{src_key}.{ext(fname)}")
    dest = os.path.join(wd, f"note_out_{src_key}.mp4")
    status = await msg.reply("⭕ Converting to video note…")
    try:
        await dl(msg.bot, fid, src)
        await video_to_videonote(src, dest)
        await status.edit_text("✅ Done!")
        with open(dest, "rb") as f:
            await msg.reply_video_note(f)
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(src, dest)
        await state.clear()
