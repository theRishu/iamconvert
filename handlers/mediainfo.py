import os
import json
import uuid
import asyncio
import subprocess
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from utils.helpers import workdir, dl, cleanup, ext

router = Router()

VIDEO_EXTS = {"mp4", "avi", "mkv", "mov", "webm", "m4v", "flv"}
AUDIO_EXTS = {"mp3", "wav", "ogg", "flac", "aac", "m4a", "oga", "opus"}
IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "bmp", "tiff", "tif", "gif"}


class InfoState(StatesGroup):
    waiting_file = State()


@router.message(Command("mediainfo"), StateFilter("*"))
async def cmd_mediainfo(msg: Message, state: FSMContext):
    await state.set_state(InfoState.waiting_file)
    await msg.answer("📊 <b>Media Info</b>\n\nSend any media file to see detailed info.", parse_mode="HTML")


@router.callback_query(F.data.regexp(r"^tool:[^:]+:mediainfo$"))
async def cb_mediainfo(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    _, src_key, _ = cb.data.split(":", 2)
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await cb.answer()
    status = await cb.message.reply("📊 Fetching info…")
    await _do_info(cb.message, cb.bot, status, data, src_key)


@router.message(InfoState.waiting_file, F.video | F.document | F.audio | F.photo)
async def info_got_file(msg: Message, state: FSMContext):
    if msg.photo:
        fid, fname = msg.photo[-1].file_id, "photo.jpg"
    elif msg.video:
        fid, fname = msg.video.file_id, "video.mp4"
    elif msg.audio:
        fid, fname = msg.audio.file_id, msg.audio.file_name or "audio.mp3"
    else:
        fid, fname = msg.document.file_id, msg.document.file_name
    session = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"info_{session}.{ext(fname)}")
    status = await msg.reply("📊 Fetching info…")
    await dl(msg.bot, fid, src)
    data = {"src_path": src, "filename": fname, "src_key": session, "file_id": fid}
    await _do_info(msg, msg.bot, status, data, session)
    await state.clear()


async def _do_info(msg, bot, status, data, src_key):
    fname = data.get("filename", "file")
    src = data.get("src_path")
    wd = workdir(msg.from_user.id)
    if not src:
        src = os.path.join(wd, f"info_{src_key}.{ext(fname)}")
        await dl(bot, data["file_id"], src)
    e = ext(fname)
    try:
        if e in IMAGE_EXTS:
            text = await asyncio.to_thread(_image_info, src, fname)
        else:
            text = await asyncio.to_thread(_ffprobe_info, src, fname)
        await status.edit_text(text, parse_mode="HTML")
    except Exception as err:
        await status.edit_text(f"❌ Failed:\n<code>{err}</code>", parse_mode="HTML")
    finally:
        cleanup(src)


def _ffprobe_info(src: str, fname: str) -> str:
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json",
           "-show_format", "-show_streams", src]
    r = subprocess.run(cmd, capture_output=True, timeout=30)
    info = json.loads(r.stdout.decode())
    fmt = info.get("format", {})
    streams = info.get("streams", [])

    size_mb = os.path.getsize(src) / 1024 / 1024
    duration = float(fmt.get("duration", 0))
    h = int(duration // 3600)
    m = int((duration % 3600) // 60)
    s = int(duration % 60)
    dur_str = f"{h:02d}:{m:02d}:{s:02d}"
    bitrate = int(fmt.get("bit_rate", 0)) // 1000

    lines = [f"📊 <b>Media Info — {fname}</b>", ""]
    lines.append(f"📦 Size: <b>{size_mb:.2f} MB</b>")
    lines.append(f"⏱ Duration: <b>{dur_str}</b>")
    lines.append(f"📡 Bitrate: <b>{bitrate} kbps</b>")
    lines.append(f"📁 Format: <b>{fmt.get('format_long_name', '?')}</b>")
    lines.append("")

    for s in streams:
        stype = s.get("codec_type", "?")
        codec = s.get("codec_name", "?")
        if stype == "video":
            w, h_ = s.get("width", "?"), s.get("height", "?")
            fps_raw = s.get("r_frame_rate", "0/1")
            try:
                n, d_ = fps_raw.split("/")
                fps = f"{int(n)//int(d_)} fps"
            except Exception:
                fps = fps_raw
            lines.append(f"🎬 Video: <b>{codec}</b> {w}×{h_} {fps}")
            pix = s.get("pix_fmt", "")
            if pix:
                lines.append(f"   Pixel format: {pix}")
        elif stype == "audio":
            sr = s.get("sample_rate", "?")
            ch = s.get("channels", "?")
            lines.append(f"🔊 Audio: <b>{codec}</b> {sr}Hz {ch}ch")

    return "\n".join(lines)


def _image_info(src: str, fname: str) -> str:
    from PIL import Image
    img = Image.open(src)
    size_kb = os.path.getsize(src) / 1024
    exif_data = {}
    try:
        raw = img._getexif()
        if raw:
            from PIL.ExifTags import TAGS
            exif_data = {TAGS.get(k, k): v for k, v in raw.items()
                         if isinstance(v, (str, int, float))}
    except Exception:
        pass

    lines = [f"📊 <b>Image Info — {fname}</b>", ""]
    lines.append(f"📐 Size: <b>{img.width}×{img.height}</b>")
    lines.append(f"📦 File size: <b>{size_kb:.1f} KB</b>")
    lines.append(f"🎨 Mode: <b>{img.mode}</b>")
    lines.append(f"📁 Format: <b>{img.format or ext(fname).upper()}</b>")

    if exif_data:
        lines.append("")
        lines.append("📷 <b>EXIF Data:</b>")
        for key in ["Make", "Model", "DateTime", "ExposureTime", "FNumber",
                    "ISOSpeedRatings", "FocalLength", "Software"]:
            if key in exif_data:
                lines.append(f"  {key}: {exif_data[key]}")

    return "\n".join(lines)
