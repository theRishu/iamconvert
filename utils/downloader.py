import os
import re
import asyncio
import requests


async def download_url(url: str, dest_dir: str, progress_cb=None) -> str:
    """Try yt-dlp first (YouTube/social), fall back to direct HTTP download."""
    try:
        # Check size early via HEAD request
        resp = await asyncio.to_thread(requests.head, url, allow_redirects=True, timeout=10)
        size = int(resp.headers.get("Content-Length", 0))
        if size > 50 * 1024 * 1024:
            raise ValueError(f"File too large ({size / 1024 / 1024:.1f} MB)")
    except Exception as e:
        if "too large" in str(e).lower():
            raise e
        pass # Ignore errors on HEAD, try downloading anyway

    try:
        return await asyncio.to_thread(_yt_dlp, url, dest_dir, progress_cb)
    except Exception:
        return await asyncio.to_thread(_direct, url, dest_dir, progress_cb)


def _yt_dlp(url: str, dest_dir: str, progress_cb=None) -> str:
    import yt_dlp
    result = {}

    def hook(d):
        if d["status"] == "finished":
            result["path"] = d["filename"]
        if progress_cb and d["status"] == "downloading":
            pct = d.get("_percent_str", "?")
            progress_cb(pct)

    ydl_opts = {
        "outtmpl": os.path.join(dest_dir, "%(title).60s.%(ext)s"),
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
        "merge_output_format": "mp4",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return result.get("path") or ydl.prepare_filename(info)


def _direct(url: str, dest_dir: str, progress_cb=None) -> str:
    resp = requests.get(url, stream=True, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()

    cd = resp.headers.get("Content-Disposition", "")
    if "filename=" in cd:
        filename = re.findall(r'filename="?([^";\s]+)"?', cd)[0]
    else:
        filename = url.split("?")[0].split("/")[-1] or "download"

    # Sanitize filename
    filename = re.sub(r'[^\w\.-]', '_', filename)
    dest = os.path.join(dest_dir, filename)
    
    total = int(resp.headers.get("Content-Length", 0))
    if total > 50 * 1024 * 1024:
        raise ValueError("File exceeds 50 MB limit")

    downloaded = 0
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
            downloaded += len(chunk)
            if downloaded > 50 * 1024 * 1024:
                raise ValueError("File exceeded 50 MB during download")
            if progress_cb and total:
                progress_cb(f"{downloaded/total*100:.0f}%")
    return dest
