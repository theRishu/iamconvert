import os
import uuid
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from utils.helpers import workdir, dl, cleanup, ext
from utils.image_tools import ocr_image

router = Router()


class OcrState(StatesGroup):
    waiting_image = State()


@router.message(Command("ocr"), StateFilter("*"))
async def cmd_ocr(msg: Message, state: FSMContext):
    await state.set_state(OcrState.waiting_image)
    await msg.answer("🔍 <b>OCR — Extract Text</b>\n\nSend an image.", parse_mode="HTML")


@router.callback_query(F.data.regexp(r"^tool:[^:]+:ocr$"))
async def cb_ocr(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    _, src_key, _ = cb.data.split(":", 2)
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    if data.get("kind") != "image":
        await cb.answer("OCR only works with images.", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await cb.answer()
    status = await cb.message.reply("🔍 Extracting text…")
    await _run_ocr(cb.message, cb.bot, status, data, src_key)


@router.message(OcrState.waiting_image, F.photo | F.document)
async def ocr_got_image(msg: Message, state: FSMContext):
    if msg.photo:
        fid, fname = msg.photo[-1].file_id, "photo.jpg"
    else:
        fid, fname = msg.document.file_id, msg.document.file_name

    src_key = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"ocr_{src_key}.{ext(fname)}")
    status = await msg.reply("🔍 Extracting text…")
    try:
        await dl(msg.bot, fid, src)
        text = await ocr_image(src)
        if not text:
            await status.edit_text("No readable text found in the image.")
        elif len(text) <= 4000:
            await status.edit_text(f"📄 <b>Extracted Text:</b>\n\n<code>{text}</code>",
                                    parse_mode="HTML")
        else:
            await status.edit_text(f"📄 Text extracted ({len(text)} chars). Sending as file…")
            txt_path = os.path.join(wd, f"ocr_{src_key}.txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text)
            with open(txt_path, "rb") as f:
                await msg.reply_document(f, filename="extracted_text.txt")
            cleanup(txt_path)
    except Exception as e:
        await status.edit_text(f"❌ OCR failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(src)
        await state.clear()


async def _run_ocr(msg, bot, status, data, src_key):
    wd = workdir(msg.from_user.id)
    fname = data.get("filename", "photo.jpg")
    src = os.path.join(wd, f"ocr_{src_key}.{ext(fname)}")
    try:
        await dl(bot, data["file_id"], src)
        text = await ocr_image(src)
        if not text:
            await status.edit_text("No readable text found.")
        elif len(text) <= 4000:
            await status.edit_text(f"📄 <b>Extracted Text:</b>\n\n<code>{text}</code>",
                                    parse_mode="HTML")
        else:
            txt_path = os.path.join(wd, f"ocr_{src_key}.txt")
            with open(txt_path, "w") as f:
                f.write(text)
            await status.edit_text("Sending as file…")
            with open(txt_path, "rb") as f:
                await msg.reply_document(f, filename="extracted_text.txt")
            cleanup(txt_path)
    except Exception as e:
        await status.edit_text(f"❌ OCR failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(src)
