from aiogram import Router
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

router = Router()

SECTIONS = {
    "video":   "🎬 Video Tools",
    "image":   "🖼 Image Tools",
    "audio":   "🎵 Audio Tools",
    "file":    "📁 File Tools",
    "misc":    "🔧 Misc / Utility",
}

HELP_SECTIONS = {
    "video": """🎬 <b>VIDEO TOOLS</b>

/trim — Cut video between two timestamps
  → Send video → enter start time → enter end time
  Example: <code>00:01:30</code> or <code>90</code>

/compress — Shrink video file size
  → 4 quality presets: Low / Medium / High / Near-lossless
  → Uses H.264 (libx264) with CRF encoding

/merge — Join multiple videos into one
  → Send videos one by one → tap Done

/screenshot — Capture frames from video
  → 5 auto-distributed frames
  → 10 auto-distributed frames
  → Single frame at custom timestamp

/watermark — Add text overlay to video
  → 5 position options: Top-Left, Top-Right, Bottom-Left, Bottom-Right, Center

/speed — Change video playback speed
  → Options: 0.25× 0.5× 0.75× 1.25× 1.5× 2× 4×

/subtitle — Extract or embed subtitles
  → Extract: pulls .srt/.ass from MKV/MP4
  → Embed: add .srt/.ass file into video

/rotate — Rotate or flip video
  → 90° Left / 90° Right / 180° / Flip Horizontal / Flip Vertical

/reverse — Play video backwards
  ⚠️ Warning: slow for large files (loads entire video into memory)

/loop — Repeat video N times
  → Options: 2× 3× 5× 10×

/split — Split video into equal parts
  → Options: 2 / 3 / 4 / 6 parts → sent as ZIP

/mute — Remove audio track from video

/addaudio — Add or replace audio in video
  → Send video first → then send audio file

/volume — Change video/audio volume
  → Options: −12dB −6dB −3dB +3dB +6dB +12dB

/videonote — Convert video to circular Telegram video note
  → Auto-crops to square, max 60 seconds

<b>Format conversion</b> (just send a file):
  MP4 ↔ AVI MKV MOV WEBM
  Any video → GIF
  Any video → MP3 WAV OGG FLAC AAC M4A""",

    "image": """🖼 <b>IMAGE TOOLS</b>

/filter — Apply artistic filters to image
  → Grayscale • Sepia • Invert • Blur • Sharpen
  → Emboss • Vintage • Sketch • Cartoon
  → Oil Paint • Pixelate • Edge Detect

/enhance — Adjust image properties
  → Brightness: Very Low / Low / Normal / High / Very High
  → Contrast, Saturation, Sharpness (same levels)

/rotate — Rotate or flip image
  → 90° Left / 90° Right / 180°
  → Flip Horizontal / Flip Vertical

/crop — Crop image to aspect ratio or custom coords
  → Presets: 1:1 • 4:3 • 3:4 • 16:9 • 9:16 • 3:2 • 2:3
  → Custom: enter <code>left,top,right,bottom</code> in pixels

/resize — Resize image to preset or custom size
  → HD 1280×720 • FHD 1920×1080 • 4K 3840×2160
  → Square 1080×1080 • Instagram 1080×1350 • Twitter 1200×675
  → Custom: enter <code>WIDTHxHEIGHT</code>

/watermark — Add text overlay to image
  → 5 positions: Top-Left, Top-Right, Bottom-Left, Bottom-Right, Center

/compress — Reduce image file size
  → Low / Medium / High / Near-lossless quality

/removebg — Remove image background (AI-powered)
  → Output: PNG with transparent background
  → First run downloads AI model (~170 MB)

/meme — Add top/bottom text to image (meme style)
  → Classic white text with black outline

/ocr — Extract text from image (Tesseract OCR)
  → Returns text as message or .txt file if large

/makegif — Create animated GIF from multiple images
  → Send 2+ images → choose speed: 2 / 5 / 10 FPS

<b>Format conversion</b> (just send a file):
  JPG PNG WEBP BMP TIFF ↔ any of the above
  Image → ICO • PDF • Telegram Sticker (512×512 WEBP)""",

    "audio": """🎵 <b>AUDIO TOOLS</b>

/volume — Change audio/video volume
  → Options: −12dB −6dB −3dB +3dB +6dB +12dB

/normalize — Normalize audio to standard loudness
  → Uses EBU R128 / loudnorm filter (−16 LUFS)

/pitch — Change audio pitch without changing speed
  → Options: −4 −2 −1 +1 +2 +4 semitones

/addaudio — Add or replace audio track in video
  → Send video → send audio file → combined output

/mute — Remove audio from video (silent video)

<b>Format conversion</b> (just send an audio file):
  MP3 ↔ WAV OGG FLAC AAC M4A
  Voice message → MP3 / WAV

<b>Trimming audio</b>: use /trim — works on audio files too""",

    "file": """📁 <b>FILE TOOLS</b>

/archive — Create or extract archives
  → Create ZIP: send multiple files → tap Done
  → Extract: send .zip / .rar / .tar.gz / .tar.bz2
  → Extracted files sent back as ZIP if multiple

/download — Download file from URL
  → YouTube, Instagram, TikTok, Twitter/X, Facebook
  → Any direct HTTP/HTTPS link
  Limit: 50 MB output

/pdf — PDF toolkit (5 tools in one)
  → 📎 Merge PDFs: collect multiple PDFs → merge into one
  → 📄 Extract Text: extract all text to .txt file
  → ✂️ Split PDF: each page becomes its own PDF → ZIP
  → 🗜 Compress PDF: reduce file size using stream compression
  → 🔄 Rotate Pages: rotate all pages 90° / 180° / 270°""",

    "misc": """🔧 <b>MISC / UTILITY</b>

/qr — Generate QR code from text or URL
  → Returns QR code as image
  → Works with: URLs, text, phone numbers, WiFi codes, etc.

/readqr — Decode QR code from image
  → Send any image containing a QR code
  → Returns the decoded text

/mediainfo — Show detailed media metadata
  → Video: codec, resolution, FPS, bitrate, duration
  → Audio: codec, sample rate, channels
  → Image: dimensions, mode, format, EXIF data (camera, GPS, etc.)

<b>Special inputs</b>:
  Sticker → treated as image (convert to PNG, JPG, WEBP, etc.)
  Voice message → convert to MP3, WAV, OGG
  URL in chat → auto-download (same as /download)""",
}

MAIN_HELP = """<b>iamconvert</b> — Most powerful Telegram media converter

<b>Quick start:</b> Just send any file — the bot shows all available options.

Choose a category for detailed help:"""

_SECTION_KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🎬 Video Tools",   callback_data="help:video"),
     InlineKeyboardButton(text="🖼 Image Tools",   callback_data="help:image")],
    [InlineKeyboardButton(text="🎵 Audio Tools",   callback_data="help:audio"),
     InlineKeyboardButton(text="📁 File Tools",    callback_data="help:file")],
    [InlineKeyboardButton(text="🔧 Misc / Utility", callback_data="help:misc")],
    [InlineKeyboardButton(text="📋 All commands list", callback_data="help:all")],
])

ALL_COMMANDS = """📋 <b>Complete Command List</b>

<b>Video</b>
/trim /compress /merge /screenshot /watermark
/speed /subtitle /rotate /reverse /loop
/split /mute /addaudio /volume /videonote

<b>Image</b>
/filter /enhance /rotate /crop /resize
/watermark /compress /removebg /meme /ocr /makegif

<b>Audio</b>
/volume /normalize /pitch /addaudio /mute

<b>Files</b>
/archive /download /pdf

<b>Utility</b>
/qr /readqr /mediainfo

<b>General</b>
/start — Welcome message
/help — This help menu
/cancel — Cancel current operation"""


@router.message(Command("help"), StateFilter("*"))
async def cmd_help(msg: Message):
    await msg.answer(MAIN_HELP, reply_markup=_SECTION_KB, parse_mode="HTML")


from aiogram.types import CallbackQuery

@router.callback_query(lambda c: c.data and c.data.startswith("help:"))
async def help_section(cb: CallbackQuery):
    section = cb.data.split(":", 1)[1]
    await cb.answer()
    if section == "all":
        await cb.message.answer(ALL_COMMANDS, parse_mode="HTML")
    elif section in HELP_SECTIONS:
        back_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="« Back to Help Menu", callback_data="help:back")
        ]])
        await cb.message.answer(HELP_SECTIONS[section], parse_mode="HTML", reply_markup=back_kb)
    elif section == "back":
        await cb.message.answer(MAIN_HELP, reply_markup=_SECTION_KB, parse_mode="HTML")
