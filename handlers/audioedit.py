import os
import uuid
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from utils.helpers import workdir, dl, cleanup, ext
from utils.audio_tools import (mute_video, add_audio_to_video, change_volume,
                                normalize_audio, change_pitch, fade_audio)
from utils.video_tools import get_duration

router = Router()

VIDEO_EXTS = {"mp4", "avi", "mkv", "mov", "webm"}
AUDIO_EXTS = {"mp3", "wav", "ogg", "flac", "aac", "m4a", "oga"}

DB_OPTIONS = [("-12 dB", -12), ("-6 dB", -6), ("-3 dB", -3),
              ("+3 dB", 3), ("+6 dB", 6), ("+12 dB", 12)]
PITCH_OPTIONS = [("-4 st", -4), ("-2 st", -2), ("-1 st", -1),
                 ("+1 st", 1), ("+2 st", 2), ("+4 st", 4)]


class AudioEditState(StatesGroup):
    # Volume
    vol_waiting_file = State()
    vol_waiting_amount = State()
    # Mute
    mute_waiting_file = State()
    # Add audio
    add_waiting_video = State()
    add_waiting_audio = State()
    # Normalize
    norm_waiting_file = State()
    # Pitch
    pitch_waiting_file = State()
    pitch_waiting_amount = State()


def _vol_kb(src_key: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=f"vol:{src_key}:{db}")
             for label, db in DB_OPTIONS[:3]],
            [InlineKeyboardButton(text=label, callback_data=f"vol:{src_key}:{db}")
             for label, db in DB_OPTIONS[3:]]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _pitch_kb(src_key: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=f"pit:{src_key}:{st}")
             for label, st in PITCH_OPTIONS[:3]],
            [InlineKeyboardButton(text=label, callback_data=f"pit:{src_key}:{st}")
             for label, st in PITCH_OPTIONS[3:]]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── /mute ─────────────────────────────────────────────────────────────────────

@router.message(Command("mute"), StateFilter("*"))
async def cmd_mute(msg: Message, state: FSMContext):
    await state.set_state(AudioEditState.mute_waiting_file)
    await msg.answer("🔇 <b>Mute Video</b>\n\nSend the video to remove audio from.", parse_mode="HTML")


@router.callback_query(F.data.regexp(r"^tool:[^:]+:mute$"))
async def cb_mute(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    _, src_key, _ = cb.data.split(":", 2)
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    if data.get("kind") != "video":
        await cb.answer("Mute only works with videos.", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await cb.answer()
    await _do_mute(cb.message, cb.bot, data, src_key)


@router.message(AudioEditState.mute_waiting_file, F.video | F.document)
async def mute_got_file(msg: Message, state: FSMContext):
    if msg.video:
        fid, fname = msg.video.file_id, "video.mp4"
    else:
        fid, fname = msg.document.file_id, msg.document.file_name
    src_key = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"mute_in_{src_key}.{ext(fname)}")
    await dl(msg.bot, fid, src)
    data = {"src_path": src, "src_key": src_key, "filename": fname, "file_id": fid}
    await state.update_data(**data)
    await _do_mute(msg, msg.bot, data, src_key)
    await state.clear()


async def _do_mute(msg, bot, data, src_key):
    src = data.get("src_path")
    wd = workdir(msg.from_user.id)
    if not src:
        src = os.path.join(wd, f"mute_in_{src_key}.{ext(data.get('filename','video.mp4'))}")
        await dl(bot, data["file_id"], src)
    dest = os.path.join(wd, f"muted_{src_key}.mp4")
    status = await msg.reply("🔇 Removing audio…")
    try:
        await mute_video(src, dest)
        await status.edit_text("✅ Done!")
        with open(dest, "rb") as f:
            await msg.reply_document(f, filename="muted.mp4")
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(src, dest)


# ── /addaudio ────────────────────────────────────────────────────────────────

@router.message(Command("addaudio"), StateFilter("*"))
async def cmd_addaudio(msg: Message, state: FSMContext):
    await state.set_state(AudioEditState.add_waiting_video)
    await msg.answer("🎵 <b>Add Audio to Video</b>\n\nSend the video first.", parse_mode="HTML")


@router.message(AudioEditState.add_waiting_video, F.video | F.document)
async def addaudio_got_video(msg: Message, state: FSMContext):
    if msg.video:
        fid, fname = msg.video.file_id, "video.mp4"
    else:
        fid, fname = msg.document.file_id, msg.document.file_name
    src_key = str(uuid.uuid4())[:8]
    await state.update_data(video_fid=fid, video_fname=fname, src_key=src_key)
    await state.set_state(AudioEditState.add_waiting_audio)
    await msg.reply("Video saved. Now send the audio file (MP3, WAV, OGG…):")


@router.message(AudioEditState.add_waiting_audio, F.audio | F.document | F.voice)
async def addaudio_got_audio(msg: Message, state: FSMContext):
    if msg.audio:
        afid, afname = msg.audio.file_id, msg.audio.file_name or "audio.mp3"
    elif msg.voice:
        afid, afname = msg.voice.file_id, "voice.ogg"
    else:
        afid, afname = msg.document.file_id, msg.document.file_name
    data = await state.get_data()
    src_key = data.get("src_key", str(uuid.uuid4())[:8])
    wd = workdir(msg.from_user.id)
    video_src = os.path.join(wd, f"addaud_v_{src_key}.{ext(data['video_fname'])}")
    audio_src = os.path.join(wd, f"addaud_a_{src_key}.{ext(afname)}")
    dest = os.path.join(wd, f"with_audio_{src_key}.mp4")
    status = await msg.reply("🎵 Adding audio…")
    try:
        await dl(msg.bot, data["video_fid"], video_src)
        await dl(msg.bot, afid, audio_src)
        await add_audio_to_video(video_src, audio_src, dest)
        await status.edit_text("✅ Done!")
        with open(dest, "rb") as f:
            await msg.reply_document(f, filename="with_audio.mp4")
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(video_src, audio_src, dest)
        await state.clear()


# ── /volume ──────────────────────────────────────────────────────────────────

@router.message(Command("volume"), StateFilter("*"))
async def cmd_volume(msg: Message, state: FSMContext):
    await state.set_state(AudioEditState.vol_waiting_file)
    await msg.answer("🔊 <b>Change Volume</b>\n\nSend a video or audio file.", parse_mode="HTML")


@router.callback_query(F.data.regexp(r"^tool:[^:]+:volume$"))
async def cb_volume(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    _, src_key, _ = cb.data.split(":", 2)
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await state.set_state(AudioEditState.vol_waiting_amount)
    await cb.answer()
    await cb.message.reply("🔊 Choose volume change:", reply_markup=_vol_kb(src_key))


@router.message(AudioEditState.vol_waiting_file, F.video | F.document | F.audio)
async def vol_got_file(msg: Message, state: FSMContext):
    if msg.audio:
        fid, fname = msg.audio.file_id, msg.audio.file_name or "audio.mp3"
    elif msg.video:
        fid, fname = msg.video.file_id, "video.mp4"
    else:
        fid, fname = msg.document.file_id, msg.document.file_name
    src_key = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"vol_in_{src_key}.{ext(fname)}")
    await dl(msg.bot, fid, src)
    await state.update_data(src_path=src, src_key=src_key, filename=fname, file_id=fid)
    await state.set_state(AudioEditState.vol_waiting_amount)
    await msg.reply("🔊 Choose volume change:", reply_markup=_vol_kb(src_key))


@router.callback_query(F.data.startswith("vol:"), AudioEditState.vol_waiting_amount)
async def vol_do(cb: CallbackQuery, state: FSMContext):
    _, src_key, db_str = cb.data.split(":", 2)
    db = float(db_str)
    data = await state.get_data()
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await cb.answer()
    status = await cb.message.reply(f"🔊 Adjusting volume {db:+.0f} dB…")
    src = data.get("src_path")
    wd = workdir(cb.from_user.id)
    if not src:
        src = os.path.join(wd, f"vol_in_{src_key}.{ext(data.get('filename','file'))}")
        await dl(cb.bot, data["file_id"], src)
    out_e = ext(data.get("filename", "out.mp4")) or "mp4"
    dest = os.path.join(wd, f"vol_out_{src_key}.{out_e}")
    try:
        await change_volume(src, dest, db)
        await status.edit_text("✅ Done!")
        with open(dest, "rb") as f:
            await cb.message.reply_document(f, filename=f"volume_{db:+.0f}dB.{out_e}")
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(src, dest)
        await state.clear()


# ── /normalize ────────────────────────────────────────────────────────────────

@router.message(Command("normalize"), StateFilter("*"))
async def cmd_normalize(msg: Message, state: FSMContext):
    await state.set_state(AudioEditState.norm_waiting_file)
    await msg.answer("📊 <b>Normalize Audio</b>\n\nSend a video or audio file.", parse_mode="HTML")


@router.message(AudioEditState.norm_waiting_file, F.video | F.document | F.audio)
async def norm_got_file(msg: Message, state: FSMContext):
    if msg.audio:
        fid, fname = msg.audio.file_id, msg.audio.file_name or "audio.mp3"
    elif msg.video:
        fid, fname = msg.video.file_id, "video.mp4"
    else:
        fid, fname = msg.document.file_id, msg.document.file_name
    src_key = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"norm_in_{src_key}.{ext(fname)}")
    dest = os.path.join(wd, f"norm_out_{src_key}.{ext(fname)}")
    status = await msg.reply("📊 Normalizing audio…")
    try:
        await dl(msg.bot, fid, src)
        await normalize_audio(src, dest)
        await status.edit_text("✅ Done!")
        with open(dest, "rb") as f:
            await msg.reply_document(f, filename=f"normalized.{ext(fname)}")
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(src, dest)
        await state.clear()


# ── /pitch ────────────────────────────────────────────────────────────────────

@router.message(Command("pitch"), StateFilter("*"))
async def cmd_pitch(msg: Message, state: FSMContext):
    await state.set_state(AudioEditState.pitch_waiting_file)
    await msg.answer("🎼 <b>Change Pitch</b>\n\nSend an audio or video file.", parse_mode="HTML")


@router.message(AudioEditState.pitch_waiting_file, F.video | F.document | F.audio)
async def pitch_got_file(msg: Message, state: FSMContext):
    if msg.audio:
        fid, fname = msg.audio.file_id, msg.audio.file_name or "audio.mp3"
    elif msg.video:
        fid, fname = msg.video.file_id, "video.mp4"
    else:
        fid, fname = msg.document.file_id, msg.document.file_name
    src_key = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"pit_in_{src_key}.{ext(fname)}")
    await dl(msg.bot, fid, src)
    await state.update_data(src_path=src, src_key=src_key, filename=fname, file_id=fid)
    await state.set_state(AudioEditState.pitch_waiting_amount)
    await msg.reply("🎼 Choose pitch shift (semitones):", reply_markup=_pitch_kb(src_key))


@router.callback_query(F.data.startswith("pit:"), AudioEditState.pitch_waiting_amount)
async def pitch_do(cb: CallbackQuery, state: FSMContext):
    _, src_key, st_str = cb.data.split(":", 2)
    semitones = float(st_str)
    data = await state.get_data()
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await cb.answer()
    status = await cb.message.reply(f"🎼 Shifting pitch {semitones:+.0f} semitones…")
    src = data.get("src_path")
    wd = workdir(cb.from_user.id)
    if not src:
        src = os.path.join(wd, f"pit_in_{src_key}.{ext(data.get('filename','file'))}")
        await dl(cb.bot, data["file_id"], src)
    out_e = ext(data.get("filename", "audio.mp3")) or "mp3"
    dest = os.path.join(wd, f"pitch_{src_key}.{out_e}")
    try:
        await change_pitch(src, semitones, dest)
        await status.edit_text("✅ Done!")
        with open(dest, "rb") as f:
            await cb.message.reply_document(f, filename=f"pitch_{semitones:+.0f}st.{out_e}")
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(src, dest)
        await state.clear()
