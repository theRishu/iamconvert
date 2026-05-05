import os
import uuid
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (Message, CallbackQuery,
                            InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile)

from utils.helpers import workdir, dl, cleanup, ext, parse_time, fmt_time
from utils.video_tools import screenshot_video, multi_screenshots, get_duration

router = Router()


class ShotState(StatesGroup):
    waiting_file = State()
    waiting_time = State()


def _shot_kb(src_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 5 Auto Screenshots", callback_data=f"shot:{src_key}:auto5"),
         InlineKeyboardButton(text="📸 10 Auto Screenshots", callback_data=f"shot:{src_key}:auto10")],
        [InlineKeyboardButton(text="⌨️ Enter Timestamp", callback_data=f"shot:{src_key}:manual")],
    ])


@router.message(Command("screenshot"), StateFilter("*"))
async def cmd_screenshot(msg: Message, state: FSMContext):
    await state.set_state(ShotState.waiting_file)
    await msg.answer("📸 <b>Screenshot</b>\n\nSend the video.", parse_mode="HTML")


@router.callback_query(F.data.regexp(r"^tool:[^:]+:screenshot$"))
async def cb_screenshot(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    _, src_key, _ = cb.data.split(":", 2)
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    if data.get("kind") != "video":
        await cb.answer("Screenshot only works with videos.", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await state.set_state(ShotState.waiting_time)
    await cb.answer()
    dur = data.get("duration", 0)
    dur_str = f"  Duration: <code>{fmt_time(dur)}</code>" if dur else ""
    await cb.message.reply(
        f"📸 <b>Screenshot</b>\n{dur_str}\n\nHow do you want to capture?",
        reply_markup=_shot_kb(src_key), parse_mode="HTML",
    )


@router.message(ShotState.waiting_file, F.video | F.document)
async def shot_got_file(msg: Message, state: FSMContext):
    if msg.video:
        fid, fname = msg.video.file_id, "video.mp4"
    else:
        fid, fname = msg.document.file_id, msg.document.file_name

    src_key = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"shot_in_{src_key}.{ext(fname)}")
    await dl(msg.bot, fid, src)
    dur = await get_duration(src)
    await state.update_data(src_path=src, src_key=src_key, duration=dur, file_id=fid)
    await state.set_state(ShotState.waiting_time)
    await msg.reply(
        f"Video received! Duration: <code>{fmt_time(dur)}</code>\n\n"
        "How do you want to capture?",
        reply_markup=_shot_kb(src_key), parse_mode="HTML",
    )


@router.callback_query(F.data.regexp(r"^shot:[^:]+:auto\d+$"), ShotState.waiting_time)
async def shot_auto(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")
    src_key, mode = parts[1], parts[2]
    count = int(mode.replace("auto", ""))
    data = await state.get_data()
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await cb.answer()
    await _capture(cb.message, cb.bot, state, data, src_key, auto_count=count)


@router.callback_query(F.data.regexp(r"^shot:[^:]+:manual$"), ShotState.waiting_time)
async def shot_manual_prompt(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_reply_markup()
    await cb.answer()
    await cb.message.reply(
        "Send timestamp (e.g. <code>00:01:30</code> or <code>90</code>):",
        parse_mode="HTML",
    )


@router.message(ShotState.waiting_time)
async def shot_manual(msg: Message, state: FSMContext):
    try:
        ts = parse_time(msg.text or "")
    except Exception:
        await msg.reply("Invalid time. Try <code>00:01:30</code>:", parse_mode="HTML")
        return
    data = await state.get_data()
    src_key = data.get("src_key", "")
    await _capture(msg, msg.bot, state, data, src_key, timestamp=ts)


async def _capture(msg, bot, state, data, src_key, *, auto_count=None, timestamp=None):
    src = data.get("src_path")
    if not src:
        wd = workdir(msg.from_user.id)
        fname = data.get("filename", "video.mp4")
        src = os.path.join(wd, f"shot_in_{src_key}.{ext(fname)}")
        await dl(bot, data["file_id"], src)

    wd = workdir(msg.from_user.id)
    status = await msg.reply("📸 Capturing…")
    paths = []
    try:
        if auto_count:
            paths = await multi_screenshots(src, auto_count, wd)
        else:
            p = os.path.join(wd, f"shot_{src_key}.jpg")
            await screenshot_video(src, timestamp, p)
            paths = [p]

        await status.edit_text(f"✅ {len(paths)} screenshot(s). Sending…")
        for p in paths:
            photo = FSInputFile(p)
            await msg.reply_photo(photo, caption=f"Frame @ {fmt_time(timestamp or 0)}" if timestamp else "Auto frame")
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        for p in paths:
            cleanup(p)
        if data.get("src_path"):
            cleanup(data["src_path"])
        await state.clear()
