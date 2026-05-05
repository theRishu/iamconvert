import os
import uuid
import zipfile
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from utils.helpers import workdir, dl, cleanup, ext
from utils.archive_tools import create_zip, extract_archive, list_archive

router = Router()

ARCHIVE_EXTS = {"zip", "rar", "tar", "gz", "bz2", "xz", "7z"}

_MODE_KB = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text="📦 Create ZIP from files", callback_data="arc:create"),
    InlineKeyboardButton(text="📂 Extract archive",       callback_data="arc:extract"),
]])
_DONE_KB = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text="✅ Done — Create ZIP", callback_data="arc:zip_done"),
    InlineKeyboardButton(text="❌ Cancel",             callback_data="arc:cancel"),
]])


class ArcState(StatesGroup):
    choosing_mode = State()
    collecting_files = State()
    waiting_archive = State()


@router.message(Command("archive"), StateFilter("*"))
async def cmd_archive(msg: Message, state: FSMContext):
    await state.set_state(ArcState.choosing_mode)
    await msg.answer("📦 <b>Archive Tool</b>\n\nWhat do you want to do?",
                     reply_markup=_MODE_KB, parse_mode="HTML")


@router.callback_query(F.data == "arc:create")
async def arc_create_mode(cb: CallbackQuery, state: FSMContext):
    session = str(uuid.uuid4())[:8]
    await state.set_state(ArcState.collecting_files)
    await state.update_data(files=[], session=session)
    await cb.message.edit_reply_markup()
    await cb.answer()
    await cb.message.reply(
        "📦 <b>Create ZIP</b>\n\nSend files one by one, then tap <b>Done</b>.",
        reply_markup=_DONE_KB, parse_mode="HTML",
    )


@router.callback_query(F.data == "arc:extract")
async def arc_extract_mode(cb: CallbackQuery, state: FSMContext):
    await state.set_state(ArcState.waiting_archive)
    await cb.message.edit_reply_markup()
    await cb.answer()
    await cb.message.reply("📂 <b>Extract</b>\n\nSend the archive file (.zip, .rar, .tar.gz).",
                            parse_mode="HTML")


@router.callback_query(F.data == "arc:cancel")
async def arc_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ Cancelled.")
    await cb.answer()


# ── Collecting files for ZIP ──────────────────────────────────────────────────

@router.message(ArcState.collecting_files, F.document | F.photo | F.video | F.audio)
async def arc_collect(msg: Message, state: FSMContext):
    if msg.document:
        fid, fname = msg.document.file_id, msg.document.file_name
    elif msg.photo:
        fid, fname = msg.photo[-1].file_id, "photo.jpg"
    elif msg.video:
        fid, fname = msg.video.file_id, "video.mp4"
    else:
        fid, fname = msg.audio.file_id, msg.audio.file_name or "audio.mp3"

    data = await state.get_data()
    files = data.get("files", [])
    files.append({"file_id": fid, "filename": fname})
    await state.update_data(files=files)
    await msg.reply(f"✅ File {len(files)} added. Send more or tap Done.", reply_markup=_DONE_KB)


@router.callback_query(F.data == "arc:zip_done", ArcState.collecting_files)
async def arc_zip_done(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    files = data.get("files", [])
    if not files:
        await cb.answer("No files yet!", show_alert=True)
        return

    await cb.message.edit_reply_markup()
    await cb.answer()
    status = await cb.message.reply(f"📦 Downloading {len(files)} files…")
    session = data.get("session", str(uuid.uuid4())[:8])
    wd = workdir(cb.from_user.id)
    paths = []

    try:
        for i, f in enumerate(files):
            name = f["filename"] or f"file_{i}"
            p = os.path.join(wd, f"arc_{session}_{i}_{name}")
            await dl(cb.bot, f["file_id"], p)
            paths.append(p)

        await status.edit_text("📦 Creating ZIP…")
        dest = os.path.join(wd, f"archive_{session}.zip")
        await create_zip(paths, dest)
        size_mb = os.path.getsize(dest) / 1024 / 1024
        await status.edit_text(f"✅ ZIP created ({size_mb:.1f} MB). Sending…")
        with open(dest, "rb") as f:
            await cb.message.reply_document(f, filename=f"archive_{session}.zip")
        cleanup(dest)
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        for p in paths:
            cleanup(p)
        await state.clear()


# ── Extracting archive ────────────────────────────────────────────────────────

@router.message(ArcState.waiting_archive, F.document)
async def arc_extract(msg: Message, state: FSMContext):
    fid = msg.document.file_id
    fname = msg.document.file_name or "archive.zip"
    e = ext(fname)

    if e not in ARCHIVE_EXTS and not fname.endswith((".tar.gz", ".tar.bz2")):
        await msg.reply("Unsupported archive format. Send .zip, .rar, or .tar.gz")
        return

    session = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"arc_{session}.{e}")
    extract_dir = os.path.join(wd, f"extracted_{session}")
    status = await msg.reply("📂 Extracting…")

    try:
        await dl(msg.bot, fid, src)
        names = await extract_archive(src, extract_dir)
        await status.edit_text(f"✅ Extracted {len(names)} files. Zipping for transfer…")

        # Re-zip extracted files to send back
        extracted_files = []
        for root, _, files in os.walk(extract_dir):
            for f in files:
                extracted_files.append(os.path.join(root, f))

        if len(extracted_files) == 1:
            with open(extracted_files[0], "rb") as f:
                await msg.reply_document(f, filename=os.path.basename(extracted_files[0]))
        else:
            out_zip = os.path.join(wd, f"extracted_{session}.zip")
            with zipfile.ZipFile(out_zip, "w") as zf:
                for fp in extracted_files:
                    zf.write(fp, os.path.relpath(fp, extract_dir))
            await status.edit_text(f"✅ {len(extracted_files)} files extracted. Sending…")
            with open(out_zip, "rb") as f:
                await msg.reply_document(f, filename=f"extracted_{session}.zip")
            cleanup(out_zip)

    except Exception as e_:
        await status.edit_text(f"❌ Failed:\n<code>{e_}</code>", parse_mode="HTML")
    finally:
        cleanup(src)
        import shutil
        try:
            shutil.rmtree(extract_dir, ignore_errors=True)
        except Exception:
            pass
        await state.clear()
