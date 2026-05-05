import os
import uuid
from pathlib import Path

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import MAX_FILE_BYTES, DOWNLOAD_DIR
from utils.helpers import workdir, dl, cleanup, ext
from utils.video_tools import (convert_video, video_to_gif, extract_audio, get_duration)
from utils.image_tools import (convert_image, to_sticker, compress_image, images_to_pdf, pdf_to_images)

router = Router()

VIDEO_EXTS = {"mp4", "avi", "mkv", "mov", "webm", "m4v"}
AUDIO_EXTS = {"mp3", "wav", "ogg", "flac", "aac", "m4a", "oga", "opus"}
IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "bmp", "tiff", "tif"}

VIDEO_FMT   = ["mp4", "avi", "mkv", "mov", "webm", "gif"]
AUDIO_FMT   = ["mp3", "wav", "ogg", "flac", "aac", "m4a"]
IMAGE_FMT   = ["jpg", "png", "webp", "bmp", "tiff", "ico", "pdf", "sticker"]

VIDEO_TOOLS = [
    ("✂️ Trim",        "trim"),
    ("🗜 Compress",    "compress"),
    ("📸 Screenshot",  "screenshot"),
    ("💧 Watermark",   "watermark"),
    ("⚡ Speed",       "speed"),
    ("📝 Subtitles",   "subtitle"),
    ("🔀 Merge",       "merge"),
    ("🔄 Rotate",      "rotate"),
    ("⏪ Reverse",     "reverse"),
    ("🔁 Loop",        "loop"),
    ("✂️ Split",       "split"),
    ("🔇 Mute",        "mute"),
    ("🎵 Add Audio",   "addaudio"),
    ("🔊 Volume",      "volume"),
    ("📊 Media Info",  "mediainfo"),
    ("⭕ Video Note",  "videonote"),
]
IMAGE_TOOLS = [
    ("📏 Resize",      "resize"),
    ("🗜 Compress",    "compress"),
    ("💧 Watermark",   "watermark"),
    ("🔍 OCR (Text)",  "ocr"),
    ("🔄 Rotate",      "rotate"),
    ("✂️ Crop",        "crop"),
    ("🎨 Filter",      "filter"),
    ("✨ Enhance",     "enhance"),
    ("🎭 Remove BG",   "removebg"),
    ("🤣 Meme",        "meme"),
    ("📊 Media Info",  "mediainfo"),
]
AUDIO_TOOLS = [
    ("🔊 Volume",      "volume"),
    ("📊 Normalize",   "normalize"),
    ("🎼 Pitch",       "pitch"),
    ("📊 Media Info",  "mediainfo"),
]


class CvtState(StatesGroup):
    waiting_fmt = State()


def _kb(fmts: list[str], tools: list[tuple], src_key: str) -> InlineKeyboardMarkup:
    rows = []
    # Format buttons — 3 per row
    fmt_row = []
    for f in fmts:
        fmt_row.append(InlineKeyboardButton(text=f.upper(), callback_data=f"cvt:{src_key}:{f}"))
        if len(fmt_row) == 3:
            rows.append(fmt_row)
            fmt_row = []
    if fmt_row:
        rows.append(fmt_row)
    # Audio extract row for videos
    if "mp3" not in fmts and tools:
        audio_row = [InlineKeyboardButton(text=f, callback_data=f"cvt:{src_key}:{f}")
                     for f in AUDIO_FMT[:3]]
        rows.append(audio_row)
        rows.append([InlineKeyboardButton(text=f, callback_data=f"cvt:{src_key}:{f}")
                     for f in AUDIO_FMT[3:]])
    # Separator label
    if tools:
        rows.append([InlineKeyboardButton(text="── Tools ──", callback_data="noop")])
        tool_row = []
        for label, name in tools:
            tool_row.append(InlineKeyboardButton(text=label, callback_data=f"tool:{src_key}:{name}"))
            if len(tool_row) == 3:
                rows.append(tool_row)
                tool_row = []
        if tool_row:
            rows.append(tool_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _handle_media(msg: Message, state: FSMContext,
                        file_id: str, filename: str, file_size: int):
    if file_size and file_size > MAX_FILE_BYTES:
        await msg.reply("❌ File too large. Max 50 MB.")
        return

    e = ext(filename)
    if e in VIDEO_EXTS or filename == "video.mp4":
        kind, fmts, tools = "video", VIDEO_FMT, VIDEO_TOOLS
    elif e in AUDIO_EXTS or filename == "voice.ogg":
        kind, fmts, tools = "audio", AUDIO_FMT, AUDIO_TOOLS
    elif e in IMAGE_EXTS or filename == "photo.jpg":
        kind, fmts, tools = "image", IMAGE_FMT, IMAGE_TOOLS
    elif e == "pdf":
        kind, fmts, tools = "pdf", ["images_zip"], []
    else:
        await msg.reply("❓ Unsupported file type. Send a video, audio, image, or PDF.")
        return

    src_key = str(uuid.uuid4())[:8]
    dur = 0
    await state.update_data(file_id=file_id, filename=filename, kind=kind,
                            src_key=src_key, duration=dur)
    await state.set_state(CvtState.waiting_fmt)

    type_label = {"video": "🎬 VIDEO", "audio": "🎵 AUDIO",
                  "image": "🖼 IMAGE", "pdf": "📄 PDF"}[kind]
    await msg.reply(
        f"{type_label} — <b>{filename}</b>\n\nChoose an action:",
        reply_markup=_kb(fmts, tools, src_key),
        parse_mode="HTML",
    )


# ── Incoming media (only when no active state) ────────────────────────────────

@router.message(F.document, StateFilter(None))
async def on_document(msg: Message, state: FSMContext):
    doc = msg.document
    await _handle_media(msg, state, doc.file_id, doc.file_name or "file", doc.file_size or 0)


@router.message(F.video, StateFilter(None))
async def on_video(msg: Message, state: FSMContext):
    v = msg.video
    await _handle_media(msg, state, v.file_id, "video.mp4", v.file_size or 0)


@router.message(F.audio, StateFilter(None))
async def on_audio(msg: Message, state: FSMContext):
    a = msg.audio
    await _handle_media(msg, state, a.file_id, a.file_name or "audio.mp3", a.file_size or 0)


@router.message(F.voice, StateFilter(None))
async def on_voice(msg: Message, state: FSMContext):
    v = msg.voice
    await _handle_media(msg, state, v.file_id, "voice.ogg", v.file_size or 0)


@router.message(F.photo, StateFilter(None))
async def on_photo(msg: Message, state: FSMContext):
    photo = msg.photo[-1]
    await _handle_media(msg, state, photo.file_id, "photo.jpg", photo.file_size or 0)


# ── No-op for separator button ────────────────────────────────────────────────

@router.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery):
    await cb.answer()


# ── Format selected ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cvt:"), CvtState.waiting_fmt)
async def on_format(cb: CallbackQuery, state: FSMContext):
    _, src_key, out_fmt = cb.data.split(":", 2)
    data = await state.get_data()

    if data.get("src_key") != src_key:
        await cb.answer("Session mismatch — resend the file.", show_alert=True)
        return

    await cb.message.edit_reply_markup()
    await cb.answer()
    status = await cb.message.reply("⏳ Converting…")

    wd = workdir(cb.from_user.id)
    fname = data["filename"]
    src = os.path.join(wd, f"in_{src_key}.{ext(fname)}")
    await dl(cb.bot, data["file_id"], src)

    out_path = os.path.join(wd, f"out_{src_key}.{out_fmt}")
    kind = data["kind"]

    try:
        if kind == "video":
            if out_fmt == "gif":
                result = await video_to_gif(src, out_path)
            elif out_fmt in AUDIO_EXTS:
                result = await extract_audio(src, out_path)
            else:
                result = await convert_video(src, out_path)

        elif kind == "audio":
            result = await extract_audio(src, out_path)   # ffmpeg handles audio→audio too

        elif kind == "image":
            if out_fmt == "sticker":
                out_path = out_path.replace(".sticker", ".webp")
                result = await to_sticker(src, out_path)
            elif out_fmt == "pdf":
                out_path = out_path.replace(f".{out_fmt}", ".pdf")
                result = await images_to_pdf([src], out_path)
            else:
                out_path = os.path.join(wd, f"out_{src_key}.{out_fmt}")
                result = await convert_image(src, out_fmt, out_path)

        elif kind == "pdf":
            import zipfile as zf
            pages = await pdf_to_images(src, wd)
            zip_path = os.path.join(wd, f"pages_{src_key}.zip")
            with zf.ZipFile(zip_path, "w") as z:
                for p in pages:
                    z.write(p, os.path.basename(p))
                    cleanup(p)
            result = zip_path
            out_path = zip_path
        else:
            raise ValueError("Unknown type")

        await status.edit_text("✅ Sending…")
        with open(result, "rb") as f:
            await cb.message.reply_document(f, filename=os.path.basename(result))

    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(src, out_path)
        await state.clear()
