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


class QrState(StatesGroup):
    waiting_text = State()
    waiting_image = State()


@router.message(Command("qr"), StateFilter("*"))
async def cmd_qr(msg: Message, state: FSMContext):
    await state.set_state(QrState.waiting_text)
    await msg.answer(
        "📱 <b>QR Code Generator</b>\n\nSend the text or URL to encode as a QR code:",
        parse_mode="HTML",
    )


@router.message(QrState.waiting_text, F.text)
async def qr_got_text(msg: Message, state: FSMContext):
    text = (msg.text or "").strip()
    if not text:
        await msg.reply("Please send some text or a URL.")
        return
    session = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    dest = os.path.join(wd, f"qr_{session}.png")
    status = await msg.reply("📱 Generating QR code…")
    try:
        await asyncio.to_thread(_make_qr_segno, text, dest)
        await status.delete()
        with open(dest, "rb") as f:
            await msg.reply_photo(f, caption=f"📱 QR: <code>{text[:100]}</code>", parse_mode="HTML")
        cleanup(dest)
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        await state.clear()


def _make_qr_segno(text: str, dest: str):
    try:
        import segno
        qr = segno.make(text, error="h")
        qr.save(dest, scale=10, border=4, dark="black", light="white")
    except ImportError:
        raise RuntimeError("segno not installed. Run: pip install segno")


# ── Read QR ──────────────────────────────────────────────────────────────────

@router.message(Command("readqr"), StateFilter("*"))
async def cmd_readqr(msg: Message, state: FSMContext):
    await state.set_state(QrState.waiting_image)
    await msg.answer(
        "🔍 <b>QR Code Reader</b>\n\nSend an image containing a QR code.",
        parse_mode="HTML",
    )


@router.message(QrState.waiting_image, F.photo | F.document)
async def readqr_got_image(msg: Message, state: FSMContext):
    if msg.photo:
        fid, fname = msg.photo[-1].file_id, "photo.jpg"
    else:
        fid, fname = msg.document.file_id, msg.document.file_name
    session = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"qr_read_{session}.{ext(fname)}")
    status = await msg.reply("🔍 Scanning QR code…")
    try:
        await dl(msg.bot, fid, src)
        result = await asyncio.to_thread(_read_qr, src)
        if result:
            await status.edit_text(
                f"✅ QR decoded:\n\n<code>{result}</code>",
                parse_mode="HTML",
            )
        else:
            await status.edit_text("❌ No QR code found in the image.")
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(src)
        await state.clear()


def _read_qr(src: str) -> str:
    # Try pyzbar
    try:
        from pyzbar.pyzbar import decode
        from PIL import Image
        results = decode(Image.open(src))
        if results:
            return results[0].data.decode("utf-8", errors="replace")
    except ImportError:
        pass

    # Try opencv
    try:
        import cv2
        img = cv2.imread(src)
        data, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
        if data:
            return data
    except ImportError:
        pass

    # Try segno reader (zxing-cpp if available)
    try:
        import zxingcpp
        from PIL import Image
        img = Image.open(src)
        results = zxingcpp.read_barcodes(img)
        if results:
            return results[0].text
    except ImportError:
        pass

    raise RuntimeError(
        "No QR reading library found.\n"
        "Install one: <code>pip install pyzbar</code> (+ brew install zbar)"
    )
