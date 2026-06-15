"""
Integration tests for IamConvert bot.
Tests core processing functions and the FSInputFile/dl() fixes.
Run with: venv/bin/python3.14 test_bot.py
"""
import asyncio
import os
import shutil
import tempfile
import struct
import sys

# Add project root to path
sys.path.insert(0, "/root/iamconvert")
os.chdir("/root/iamconvert")

from dotenv import load_dotenv
load_dotenv()

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
results = []

def check(name, ok, detail=""):
    status = PASS if ok else FAIL
    print(f"  [{status}] {name}" + (f": {detail}" if detail else ""))
    results.append((name, ok))

# ── Helpers ────────────────────────────────────────────────────────────────────

def make_test_video(path, duration=2):
    """Create a minimal valid MP4 using ffmpeg."""
    ret = os.system(
        f"ffmpeg -y -f lavfi -i testsrc=duration={duration}:size=320x240:rate=10 "
        f"-f lavfi -i sine=frequency=440:duration={duration} "
        f"-c:v libx264 -c:a aac -shortest '{path}' -loglevel error"
    )
    return ret == 0 and os.path.exists(path) and os.path.getsize(path) > 0

def make_test_image(path):
    """Create a minimal PNG via PIL."""
    from PIL import Image
    img = Image.new("RGB", (200, 200), color=(100, 149, 237))
    img.save(path)
    return os.path.exists(path)

def make_test_audio(path, duration=2):
    """Create a minimal MP3 using ffmpeg."""
    ret = os.system(
        f"ffmpeg -y -f lavfi -i sine=frequency=440:duration={duration} "
        f"'{path}' -loglevel error"
    )
    return ret == 0 and os.path.exists(path)

def make_test_pdf(path):
    """Create a minimal PDF."""
    from pypdf import PdfWriter
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    with open(path, "wb") as f:
        w.write(f)
    return os.path.exists(path)

# ── Test: helpers ──────────────────────────────────────────────────────────────

print("\n=== helpers.py ===")

from utils.helpers import workdir, cleanup, ext, parse_time, fmt_time, LOCAL_SERVER_URL

check("LOCAL_SERVER_URL loaded", LOCAL_SERVER_URL == "http://localhost:8088", LOCAL_SERVER_URL)

wd = workdir(99999)
check("workdir creates dir", os.path.isdir(wd))

check("ext() mp4", ext("video.mp4") == "mp4")
check("ext() no extension uses default", ext("file", "bin") == "bin")
check("parse_time seconds", parse_time("5") == 5.0)
check("parse_time MM:SS", parse_time("1:30") == 90.0)
check("parse_time HH:MM:SS", parse_time("1:01:01") == 3661.0)
check("fmt_time", fmt_time(3661) == "01:01:01")

tmp = os.path.join(wd, "dummy.txt")
open(tmp, "w").write("x")
cleanup(tmp)
check("cleanup removes file", not os.path.exists(tmp))

cleanup(wd)

# ── Test: dl() uses shutil.copy2 on local server ──────────────────────────────

print("\n=== dl() local server path fix ===")

import types
from utils.helpers import dl

async def test_dl_local():
    src = tempfile.mktemp(suffix=".mp4")
    dst = tempfile.mktemp(suffix=".mp4")
    open(src, "wb").write(b"fake video data 12345")
    try:
        fake_file = types.SimpleNamespace(file_path=src)
        bot = types.SimpleNamespace(
            get_file=lambda fid: asyncio.coroutine(lambda: fake_file)(),
            download_file=lambda fp, d: (_ for _ in ()).throw(AssertionError("should not call download_file on local server"))
        )
        # Patch coroutine
        async def get_file(fid): return fake_file
        bot.get_file = get_file

        await dl(bot, "fake_id", dst)
        ok = os.path.exists(dst) and open(dst, "rb").read() == b"fake video data 12345"
        check("dl() copies file directly from local path", ok)
    finally:
        for p in (src, dst):
            if os.path.exists(p): os.remove(p)

asyncio.run(test_dl_local())

# ── Test: video tools ──────────────────────────────────────────────────────────

print("\n=== video_tools ===")

from utils.video_tools import _run as vrun

with tempfile.TemporaryDirectory() as td:
    src = os.path.join(td, "in.mp4")
    out = os.path.join(td, "out.mp4")
    if make_test_video(src):
        check("test video created", True)
        async def test_trim():
            await vrun(["ffmpeg", "-y", "-i", src, "-ss", "0", "-t", "1", "-c", "copy", out])
        try:
            asyncio.run(test_trim())
            check("trim (ffmpeg -t 1s)", os.path.exists(out) and os.path.getsize(out) > 0)
        except Exception as e:
            check("trim", False, str(e))

        out2 = os.path.join(td, "compressed.mp4")
        async def test_compress():
            await vrun(["ffmpeg", "-y", "-i", src, "-vf", "scale=160:120", "-crf", "35", out2])
        try:
            asyncio.run(test_compress())
            check("compress video (scale down)", os.path.exists(out2) and os.path.getsize(out2) > 0)
        except Exception as e:
            check("compress video", False, str(e))
    else:
        check("test video created", False, "ffmpeg not available?")

# ── Test: image tools ──────────────────────────────────────────────────────────

print("\n=== image_tools / image_effects ===")

from utils.image_effects import rotate_image

with tempfile.TemporaryDirectory() as td:
    src = os.path.join(td, "in.jpg")
    out = os.path.join(td, "out.jpg")
    if make_test_image(src):
        check("test image created", True)
        try:
            rotate_image(src, "90cw", out)
            check("rotate image 90cw", os.path.exists(out) and os.path.getsize(out) > 0)
        except Exception as e:
            check("rotate image", False, str(e))
    else:
        check("test image created", False)

# ── Test: FSInputFile usage (no raw BufferedReader) ───────────────────────────

print("\n=== FSInputFile audit ===")

import ast, glob

bad_files = []
for fpath in sorted(glob.glob("handlers/*.py")):
    src_code = open(fpath).read()
    # Check for leftover `with open(..., "rb") as f:` followed by aiogram send calls
    lines = src_code.splitlines()
    for i, line in enumerate(lines):
        if 'with open(' in line and '"rb"' in line and 'as f:' in line:
            # Check next few lines for aiogram send
            context = "\n".join(lines[i:i+3])
            if any(x in context for x in ["reply_", "send_", "answer_"]):
                bad_files.append(f"{fpath}:{i+1}")

check("No raw file handles passed to aiogram", len(bad_files) == 0,
      f"Found in: {bad_files}" if bad_files else "")

# Also check FSInputFile is imported in files that use it
missing_import = []
for fpath in sorted(glob.glob("handlers/*.py")):
    src_code = open(fpath).read()
    uses_it = "FSInputFile(" in src_code
    # FSInputFile might be on a continuation line — just check it appears before first use
    imports_it = "FSInputFile" in src_code[:src_code.index("FSInputFile(")] if uses_it else True
    if uses_it and not imports_it:
        missing_import.append(fpath)

check("FSInputFile imported in all handlers that use it", len(missing_import) == 0,
      str(missing_import) if missing_import else "")

# ── Test: PDF tools ────────────────────────────────────────────────────────────

print("\n=== pdf_tools ===")

with tempfile.TemporaryDirectory() as td:
    p1 = os.path.join(td, "a.pdf")
    p2 = os.path.join(td, "b.pdf")
    out = os.path.join(td, "merged.pdf")
    if make_test_pdf(p1) and make_test_pdf(p2):
        check("test PDFs created", True)
        try:
            from utils.pdf_tools import merge_pdfs
            asyncio.run(merge_pdfs([p1, p2], out))
            check("merge PDFs", os.path.exists(out) and os.path.getsize(out) > 0)
        except Exception as e:
            check("merge PDFs", False, str(e))
    else:
        check("test PDFs created", False)

# ── Summary ────────────────────────────────────────────────────────────────────

print(f"\n{'='*40}")
passed = sum(1 for _, ok in results if ok)
total = len(results)
color = "\033[92m" if passed == total else "\033[91m"
print(f"{color}{passed}/{total} tests passed\033[0m")
if passed < total:
    print("Failed:")
    for name, ok in results:
        if not ok:
            print(f"  - {name}")
sys.exit(0 if passed == total else 1)
