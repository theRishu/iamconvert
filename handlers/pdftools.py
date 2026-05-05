import os
import uuid
import zipfile
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from utils.helpers import workdir, dl, cleanup, ext
from utils.pdf_tools import merge_pdfs, extract_pdf_text, split_pdf, compress_pdf, rotate_pdf

router = Router()

_MODE_KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📎 Merge PDFs",        callback_data="pdf:merge"),
     InlineKeyboardButton(text="📄 Extract Text",      callback_data="pdf:text")],
    [InlineKeyboardButton(text="✂️ Split PDF",          callback_data="pdf:split"),
     InlineKeyboardButton(text="🗜 Compress PDF",       callback_data="pdf:compress")],
    [InlineKeyboardButton(text="🔄 Rotate Pages",      callback_data="pdf:rotate")],
])

_DONE_KB = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text="✅ Merge Now", callback_data="pdf:merge_do"),
    InlineKeyboardButton(text="❌ Cancel",    callback_data="pdf:cancel"),
]])

_ROT_KB = lambda sk: InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text="90° CW",  callback_data=f"pdfrot:{sk}:90"),
    InlineKeyboardButton(text="180°",    callback_data=f"pdfrot:{sk}:180"),
    InlineKeyboardButton(text="90° CCW", callback_data=f"pdfrot:{sk}:270"),
]])


class PdfState(StatesGroup):
    choosing_mode = State()
    merge_collecting = State()
    text_waiting = State()
    split_waiting = State()
    compress_waiting = State()
    rotate_waiting = State()
    rotate_choosing = State()


@router.message(Command("pdf"), StateFilter("*"))
async def cmd_pdf(msg: Message, state: FSMContext):
    await state.set_state(PdfState.choosing_mode)
    await msg.answer("📄 <b>PDF Tools</b>\n\nWhat do you want to do?",
                     reply_markup=_MODE_KB, parse_mode="HTML")


# ── Mode selection ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "pdf:merge")
async def pdf_merge_start(cb: CallbackQuery, state: FSMContext):
    session = str(uuid.uuid4())[:8]
    await state.set_state(PdfState.merge_collecting)
    await state.update_data(pdfs=[], session=session)
    await cb.message.edit_reply_markup()
    await cb.answer()
    await cb.message.reply("📎 <b>Merge PDFs</b>\n\nSend PDF files one by one, then tap <b>Merge Now</b>.",
                            reply_markup=_DONE_KB, parse_mode="HTML")


@router.callback_query(F.data == "pdf:text")
async def pdf_text_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(PdfState.text_waiting)
    await cb.message.edit_reply_markup()
    await cb.answer()
    await cb.message.reply("📄 <b>Extract Text</b>\n\nSend the PDF file.", parse_mode="HTML")


@router.callback_query(F.data == "pdf:split")
async def pdf_split_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(PdfState.split_waiting)
    await cb.message.edit_reply_markup()
    await cb.answer()
    await cb.message.reply("✂️ <b>Split PDF</b>\n\nSend the PDF — I'll split each page into its own file.", parse_mode="HTML")


@router.callback_query(F.data == "pdf:compress")
async def pdf_compress_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(PdfState.compress_waiting)
    await cb.message.edit_reply_markup()
    await cb.answer()
    await cb.message.reply("🗜 <b>Compress PDF</b>\n\nSend the PDF to compress.", parse_mode="HTML")


@router.callback_query(F.data == "pdf:rotate")
async def pdf_rotate_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(PdfState.rotate_waiting)
    await cb.message.edit_reply_markup()
    await cb.answer()
    await cb.message.reply("🔄 <b>Rotate PDF</b>\n\nSend the PDF.", parse_mode="HTML")


@router.callback_query(F.data == "pdf:cancel")
async def pdf_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ Cancelled.")
    await cb.answer()


# ── Merge ────────────────────────────────────────────────────────────────────

@router.message(PdfState.merge_collecting, F.document)
async def pdf_merge_collect(msg: Message, state: FSMContext):
    if not msg.document.file_name.lower().endswith(".pdf"):
        await msg.reply("Please send a PDF file.")
        return
    data = await state.get_data()
    pdfs = data.get("pdfs", [])
    pdfs.append({"file_id": msg.document.file_id, "filename": msg.document.file_name})
    await state.update_data(pdfs=pdfs)
    await msg.reply(f"📄 PDF {len(pdfs)} added. Send more or tap Merge.", reply_markup=_DONE_KB)


@router.callback_query(F.data == "pdf:merge_do", PdfState.merge_collecting)
async def pdf_merge_do(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    pdfs = data.get("pdfs", [])
    if len(pdfs) < 2:
        await cb.answer("Need at least 2 PDFs!", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await cb.answer()
    status = await cb.message.reply(f"📎 Merging {len(pdfs)} PDFs…")
    session = data.get("session", str(uuid.uuid4())[:8])
    wd = workdir(cb.from_user.id)
    paths = []
    try:
        for i, p in enumerate(pdfs):
            fp = os.path.join(wd, f"merge_pdf_{session}_{i}.pdf")
            await dl(cb.bot, p["file_id"], fp)
            paths.append(fp)
        dest = os.path.join(wd, f"merged_{session}.pdf")
        merge_pdfs(paths, dest)
        size_mb = os.path.getsize(dest) / 1024 / 1024
        await status.edit_text(f"✅ Merged! {size_mb:.1f} MB. Sending…")
        with open(dest, "rb") as f:
            await cb.message.reply_document(f, filename="merged.pdf")
        cleanup(dest)
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        for p in paths:
            cleanup(p)
        await state.clear()


# ── Text extraction ───────────────────────────────────────────────────────────

@router.message(PdfState.text_waiting, F.document)
async def pdf_text_do(msg: Message, state: FSMContext):
    session = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"pdf_text_{session}.pdf")
    status = await msg.reply("📄 Extracting text…")
    try:
        await dl(msg.bot, msg.document.file_id, src)
        text = extract_pdf_text(src)
        if not text.strip():
            await status.edit_text("❌ No extractable text found. PDF may be scanned.")
        elif len(text) <= 4000:
            await status.edit_text(f"📄 <b>Extracted Text:</b>\n\n<code>{text[:4000]}</code>",
                                    parse_mode="HTML")
        else:
            txt_path = os.path.join(wd, f"extracted_{session}.txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text)
            await status.edit_text(f"✅ {len(text)} chars extracted. Sending as .txt file…")
            with open(txt_path, "rb") as f:
                await msg.reply_document(f, filename="extracted_text.txt")
            cleanup(txt_path)
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(src)
        await state.clear()


# ── Split ────────────────────────────────────────────────────────────────────

@router.message(PdfState.split_waiting, F.document)
async def pdf_split_do(msg: Message, state: FSMContext):
    session = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"pdf_split_{session}.pdf")
    split_dir = os.path.join(wd, f"split_pdf_{session}")
    status = await msg.reply("✂️ Splitting PDF…")
    try:
        await dl(msg.bot, msg.document.file_id, src)
        pages = split_pdf(src, split_dir)
        zip_path = os.path.join(wd, f"split_{session}.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            for p in pages:
                zf.write(p, os.path.basename(p))
        await status.edit_text(f"✅ {len(pages)} pages split. Sending as ZIP…")
        with open(zip_path, "rb") as f:
            await msg.reply_document(f, filename=f"split_{len(pages)}pages.zip")
        cleanup(zip_path)
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(src)
        import shutil
        try:
            shutil.rmtree(split_dir, ignore_errors=True)
        except Exception:
            pass
        await state.clear()


# ── Compress ─────────────────────────────────────────────────────────────────

@router.message(PdfState.compress_waiting, F.document)
async def pdf_compress_do(msg: Message, state: FSMContext):
    session = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"pdf_cmp_{session}.pdf")
    dest = os.path.join(wd, f"compressed_{session}.pdf")
    status = await msg.reply("🗜 Compressing PDF…")
    try:
        await dl(msg.bot, msg.document.file_id, src)
        compress_pdf(src, dest)
        orig = os.path.getsize(src) / 1024
        new = os.path.getsize(dest) / 1024
        saved = (1 - new / orig) * 100
        await status.edit_text(f"✅ {orig:.0f} KB → {new:.0f} KB ({saved:.0f}% saved). Sending…")
        with open(dest, "rb") as f:
            await msg.reply_document(f, filename="compressed.pdf")
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(src, dest)
        await state.clear()


# ── Rotate ───────────────────────────────────────────────────────────────────

@router.message(PdfState.rotate_waiting, F.document)
async def pdf_rotate_got(msg: Message, state: FSMContext):
    session = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"pdf_rot_{session}.pdf")
    await dl(msg.bot, msg.document.file_id, src)
    await state.update_data(src_path=src, session=session)
    await state.set_state(PdfState.rotate_choosing)
    await msg.reply("Choose rotation angle:", reply_markup=_ROT_KB(session))


@router.callback_query(F.data.startswith("pdfrot:"), PdfState.rotate_choosing)
async def pdf_rotate_do(cb: CallbackQuery, state: FSMContext):
    _, session, deg_str = cb.data.split(":", 2)
    deg = int(deg_str)
    data = await state.get_data()
    await cb.message.edit_reply_markup()
    await cb.answer()
    src = data.get("src_path")
    wd = workdir(cb.from_user.id)
    dest = os.path.join(wd, f"rotated_{session}.pdf")
    status = await cb.message.reply(f"🔄 Rotating {deg}°…")
    try:
        rotate_pdf(src, dest, deg)
        await status.edit_text("✅ Done!")
        with open(dest, "rb") as f:
            await cb.message.reply_document(f, filename=f"rotated_{deg}deg.pdf")
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(src, dest)
        await state.clear()
