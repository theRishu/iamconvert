import os
import uuid
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from utils.helpers import workdir, dl, cleanup, ext, parse_time, fmt_time
from utils.video_tools import trim_video, get_duration

router = Router()


class TrimState(StatesGroup):
    waiting_file = State()
    waiting_start = State()
    waiting_end = State()


# ── /trim command ─────────────────────────────────────────────────────────────

@router.message(Command("trim"), StateFilter("*"))
async def cmd_trim(msg: Message, state: FSMContext):
    await state.set_state(TrimState.waiting_file)
    await msg.answer("✂️ <b>Trim Video</b>\n\nSend me the video you want to trim.", parse_mode="HTML")


# ── Entry from convert.py file menu ──────────────────────────────────────────

@router.callback_query(F.data.regexp(r"^tool:[^:]+:trim$"))
async def cb_trim(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    _, src_key, _ = cb.data.split(":", 2)
    if data.get("src_key") != src_key:
        await cb.answer("Session expired. Resend the file.", show_alert=True)
        return
    if data.get("kind") != "video":
        await cb.answer("Trim only works with videos.", show_alert=True)
        return
    dur = data.get("duration", 0)
    dur_str = f"  Duration: <code>{fmt_time(dur)}</code>" if dur else ""
    await cb.message.edit_reply_markup()
    await state.set_state(TrimState.waiting_start)
    await cb.answer()
    await cb.message.reply(
        f"✂️ <b>Trim Video</b>\n{dur_str}\n\n"
        "Send <b>start time</b> (e.g. <code>00:01:30</code> or <code>90</code>):",
        parse_mode="HTML",
    )


# ── File received from /trim command ─────────────────────────────────────────

@router.message(TrimState.waiting_file, F.video | F.document)
async def trim_got_file(msg: Message, state: FSMContext):
    if msg.video:
        fid, fname, fsize = msg.video.file_id, "video.mp4", msg.video.file_size
    else:
        fid, fname, fsize = msg.document.file_id, msg.document.file_name, msg.document.file_size

    src_key = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"trim_in_{src_key}.{ext(fname)}")
    await dl(msg.bot, fid, src)
    dur = await get_duration(src)
    await state.update_data(src_path=src, src_key=src_key, duration=dur, file_id=fid)
    await state.set_state(TrimState.waiting_start)
    await msg.reply(
        f"Video received! Duration: <code>{fmt_time(dur)}</code>\n\n"
        "Send <b>start time</b> (e.g. <code>00:01:30</code> or <code>90</code>):",
        parse_mode="HTML",
    )


# ── Start time ────────────────────────────────────────────────────────────────

@router.message(TrimState.waiting_start)
async def trim_got_start(msg: Message, state: FSMContext):
    try:
        start = parse_time(msg.text or "")
    except Exception:
        await msg.reply("Invalid format. Try <code>00:01:30</code> or <code>90</code>:", parse_mode="HTML")
        return
    await state.update_data(start=start)
    await state.set_state(TrimState.waiting_end)
    await msg.reply(
        f"Start: <code>{fmt_time(start)}</code>\n\nNow send the <b>end time</b>:",
        parse_mode="HTML",
    )


# ── End time + process ────────────────────────────────────────────────────────

@router.message(TrimState.waiting_end)
async def trim_got_end(msg: Message, state: FSMContext):
    data = await state.get_data()
    try:
        end = parse_time(msg.text or "")
    except Exception:
        await msg.reply("Invalid format. Try <code>00:02:00</code>:", parse_mode="HTML")
        return

    start = data["start"]
    if end <= start:
        await msg.reply("End time must be after start time.")
        return

    # If file came from /trim command it's already downloaded; from convert.py we need to download
    src = data.get("src_path")
    if not src:
        src_key = data["src_key"]
        wd = workdir(msg.from_user.id)
        fname = data.get("filename", "video.mp4")
        src = os.path.join(wd, f"trim_in_{src_key}.{ext(fname)}")
        await dl(msg.bot, data["file_id"], src)

    wd = workdir(msg.from_user.id)
    dest = os.path.join(wd, f"trimmed_{data['src_key']}.mp4")
    status = await msg.reply("✂️ Trimming…")
    try:
        await trim_video(src, start, end, dest)
        await status.edit_text("✅ Done! Sending…")
        with open(dest, "rb") as f:
            await msg.reply_document(f, filename="trimmed.mp4",
                                     caption=f"Trimmed {fmt_time(start)} → {fmt_time(end)}")
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(dest)
        if data.get("src_path"):
            cleanup(data["src_path"])
        await state.clear()
