import os
import uuid
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from utils.helpers import workdir, dl, cleanup, ext
from utils.video_tools import merge_videos

router = Router()

VIDEO_EXTS = {"mp4", "avi", "mkv", "mov", "webm", "m4v"}

_DONE_KB = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text="✅ Done — Merge Now", callback_data="merge:done"),
    InlineKeyboardButton(text="❌ Cancel", callback_data="merge:cancel"),
]])


class MergeState(StatesGroup):
    collecting = State()


@router.message(Command("merge"), StateFilter("*"))
async def cmd_merge(msg: Message, state: FSMContext):
    session = str(uuid.uuid4())[:8]
    await state.set_state(MergeState.collecting)
    await state.update_data(videos=[], session=session)
    await msg.answer(
        "🔀 <b>Merge Videos</b>\n\n"
        "Send videos one by one.\n"
        "Tap <b>Done</b> when ready to merge (min 2 videos).",
        reply_markup=_DONE_KB, parse_mode="HTML",
    )


@router.callback_query(F.data.regexp(r"^tool:[^:]+:merge$"))
async def cb_merge(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    _, src_key, _ = cb.data.split(":", 2)
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    if data.get("kind") != "video":
        await cb.answer("Merge only works with videos.", show_alert=True)
        return

    # Seed first video from convert.py selection
    first = {"file_id": data["file_id"], "filename": data.get("filename", "video.mp4")}
    await cb.message.edit_reply_markup()
    await state.set_state(MergeState.collecting)
    await state.update_data(videos=[first], session=src_key)
    await cb.answer()
    await cb.message.reply(
        "🔀 <b>Merge Videos</b>\n\n"
        "First video added. Send more, then tap <b>Done</b>.",
        reply_markup=_DONE_KB, parse_mode="HTML",
    )


@router.message(MergeState.collecting, F.video | F.document)
async def merge_collect(msg: Message, state: FSMContext):
    if msg.video:
        fid, fname = msg.video.file_id, "video.mp4"
    else:
        fid, fname = msg.document.file_id, msg.document.file_name
        if ext(fname) not in VIDEO_EXTS:
            await msg.reply("Please send a video file.")
            return

    data = await state.get_data()
    videos = data.get("videos", [])
    videos.append({"file_id": fid, "filename": fname})
    await state.update_data(videos=videos)
    await msg.reply(f"✅ Video {len(videos)} added. Send more or tap Done.", reply_markup=_DONE_KB)


@router.callback_query(F.data == "merge:cancel")
async def merge_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ Merge cancelled.")
    await cb.answer()


@router.callback_query(F.data == "merge:done", MergeState.collecting)
async def merge_do(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    videos = data.get("videos", [])
    if len(videos) < 2:
        await cb.answer("Need at least 2 videos!", show_alert=True)
        return

    await cb.message.edit_reply_markup()
    await cb.answer()
    status = await cb.message.reply(f"🔀 Downloading {len(videos)} videos…")

    wd = workdir(cb.from_user.id)
    session = data.get("session", str(uuid.uuid4())[:8])
    src_paths = []

    try:
        for i, v in enumerate(videos):
            p = os.path.join(wd, f"merge_{session}_{i}.mp4")
            await dl(cb.bot, v["file_id"], p)
            src_paths.append(p)

        await status.edit_text(f"🔀 Merging {len(src_paths)} videos…")
        dest = os.path.join(wd, f"merged_{session}.mp4")
        await merge_videos(src_paths, dest)

        size_mb = os.path.getsize(dest) / 1024 / 1024
        await status.edit_text(f"✅ Merged! {size_mb:.1f} MB. Sending…")
        with open(dest, "rb") as f:
            await cb.message.reply_document(f, filename="merged.mp4",
                                             caption=f"{len(src_paths)} videos merged")
        cleanup(dest)
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        for p in src_paths:
            cleanup(p)
        await state.clear()
