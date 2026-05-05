import os
import asyncio
import subprocess


async def _run(cmd: list, timeout: int = 300):
    # Use asyncio for non-blocking execution
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        if proc.returncode != 0:
            err = stderr.decode(errors="replace")[-800:]
            raise RuntimeError(f"FFmpeg failed (code {proc.returncode}): {err}")
        return stdout.decode()
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        raise RuntimeError("Process timed out")


async def get_duration(src: str) -> float:
    try:
        out = await _run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", src],
            timeout=30
        )
        return float(out.strip())
    except Exception:
        return 0.0


async def convert_video(src: str, dest: str):
    await _run(["ffmpeg", "-y", "-i", src, dest])
    return dest


async def video_to_gif(src: str, dest: str):
    palette = dest + ".palette.png"
    await _run(["ffmpeg", "-y", "-i", src,
                "-vf", "fps=10,scale=480:-1:flags=lanczos,palettegen", palette])
    await _run(["ffmpeg", "-y", "-i", src, "-i", palette,
                "-filter_complex", "fps=10,scale=480:-1:flags=lanczos[x];[x][1:v]paletteuse", dest])
    try:
        os.remove(palette)
    except Exception:
        pass
    return dest


async def extract_audio(src: str, dest: str):
    await _run(["ffmpeg", "-y", "-i", src, "-vn", dest])
    return dest


async def trim_video(src: str, start: float, end: float, dest: str):
    # -ss before -i for fast seeking
    await _run(["ffmpeg", "-y", "-ss", str(start), "-to", str(end), "-i", src,
                "-c", "copy", dest])
    return dest


async def compress_video(src: str, dest: str, crf: int = 28, preset: str = "medium"):
    await _run(["ffmpeg", "-y", "-i", src,
                "-c:v", "libx264", "-crf", str(crf), "-preset", preset,
                "-c:a", "aac", "-b:a", "128k", dest])
    return dest


async def merge_videos(src_list: list[str], dest: str):
    list_file = dest + ".list.txt"
    with open(list_file, "w") as f:
        for s in src_list:
            f.write(f"file '{s}'\n")
    await _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", dest])
    try:
        os.remove(list_file)
    except Exception:
        pass
    return dest


async def screenshot_video(src: str, timestamp: float, dest: str):
    await _run(["ffmpeg", "-y", "-ss", str(timestamp), "-i", src,
                "-frames:v", "1", "-q:v", "2", dest])
    return dest


async def add_watermark_video(src: str, text: str, position: str, dest: str):
    pos_map = {
        "topleft":     "x=10:y=10",
        "topright":    "x=w-tw-10:y=10",
        "bottomleft":  "x=10:y=h-th-10",
        "bottomright": "x=w-tw-10:y=h-th-10",
        "center":      "x=(w-tw)/2:y=(h-th)/2",
    }
    pos = pos_map.get(position, "x=10:y=10")
    safe_text = text.replace("'", "\\'").replace(":", "\\:")
    vf = (f"drawtext=text='{safe_text}':fontcolor=white:fontsize=36"
          f":box=1:boxcolor=black@0.5:boxborderw=5:{pos}")
    await _run(["ffmpeg", "-y", "-i", src, "-vf", vf, "-codec:a", "copy", dest])
    return dest


async def extract_subtitles(src: str, dest: str):
    await _run(["ffmpeg", "-y", "-i", src, dest])
    return dest


async def embed_subtitles(src: str, sub_file: str, dest: str):
    await _run(["ffmpeg", "-y", "-i", src, "-i", sub_file,
                "-c", "copy", "-c:s", "mov_text", dest])
    return dest


async def change_speed(src: str, speed: float, dest: str):
    vf = f"setpts={1/speed:.6f}*PTS"
    af_parts = []
    rem = speed
    while rem > 2.0:
        af_parts.append("atempo=2.0")
        rem /= 2.0
    while rem < 0.5:
        af_parts.append("atempo=0.5")
        rem *= 2.0
    af_parts.append(f"atempo={rem:.6f}")
    af = ",".join(af_parts)
    await _run(["ffmpeg", "-y", "-i", src,
                "-filter_complex", f"[0:v]{vf}[v];[0:a]{af}[a]",
                "-map", "[v]", "-map", "[a]", dest])
    return dest


async def resize_video(src: str, width: int, height: int, dest: str):
    w = width if width % 2 == 0 else width + 1
    h = height if height % 2 == 0 else height + 1
    await _run(["ffmpeg", "-y", "-i", src,
                "-vf", f"scale={w}:{h}", "-c:a", "copy", dest])
    return dest


async def multi_screenshots(src: str, count: int, dest_dir: str) -> list[str]:
    duration = await get_duration(src)
    step = duration / (count + 1)
    paths = []
    for i in range(1, count + 1):
        ts = step * i
        p = os.path.join(dest_dir, f"shot_{i:02d}.jpg")
        await screenshot_video(src, ts, p)
        paths.append(p)
    return paths
