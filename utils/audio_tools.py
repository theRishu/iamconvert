import os
import asyncio


async def _run(cmd: list, timeout: int = 300):
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        if proc.returncode != 0:
            raise RuntimeError(stderr.decode(errors="replace")[-800:])
        return stdout.decode()
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        raise RuntimeError("Process timed out")


async def mute_video(src: str, dest: str) -> str:
    await _run(["ffmpeg", "-y", "-i", src, "-c:v", "copy", "-an", dest])
    return dest


async def add_audio_to_video(video: str, audio: str, dest: str, replace: bool = True) -> str:
    if replace:
        await _run(["ffmpeg", "-y", "-i", video, "-i", audio,
                    "-c:v", "copy", "-c:a", "aac",
                    "-map", "0:v:0", "-map", "1:a:0", "-shortest", dest])
    else:
        await _run(["ffmpeg", "-y", "-i", video, "-i", audio,
                    "-filter_complex", "[0:a][1:a]amerge=inputs=2[a]",
                    "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-ac", "2", "-shortest", dest])
    return dest


async def change_volume(src: str, dest: str, db: float = 0.0) -> str:
    factor = 10 ** (db / 20)
    await _run(["ffmpeg", "-y", "-i", src, "-af", f"volume={factor:.4f}", dest])
    return dest


async def normalize_audio(src: str, dest: str) -> str:
    await _run(["ffmpeg", "-y", "-i", src,
                "-af", "loudnorm=I=-16:LRA=11:TP=-1.5", dest])
    return dest


async def trim_audio(src: str, start: float, end: float, dest: str) -> str:
    await _run(["ffmpeg", "-y", "-ss", str(start), "-to", str(end), "-i", src, "-c", "copy", dest])
    return dest


async def merge_audio(src_list: list[str], dest: str) -> str:
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


async def change_pitch(src: str, semitones: float, dest: str) -> str:
    factor = 2 ** (semitones / 12)
    await _run(["ffmpeg", "-y", "-i", src,
                "-af", f"asetrate=44100*{factor:.4f},aresample=44100", dest])
    return dest


async def fade_audio(src: str, dest: str, fade_in: float = 0,
                     fade_out: float = 0, duration: float = 0) -> str:
    af_parts = []
    if fade_in > 0:
        af_parts.append(f"afade=t=in:st=0:d={fade_in}")
    if fade_out > 0 and duration:
        start = max(0, duration - fade_out)
        af_parts.append(f"afade=t=out:st={start:.2f}:d={fade_out}")
    af = ",".join(af_parts) if af_parts else "anull"
    await _run(["ffmpeg", "-y", "-i", src, "-af", af, dest])
    return dest


async def reverse_video(src: str, dest: str) -> str:
    await _run(["ffmpeg", "-y", "-i", src, "-vf", "reverse", "-af", "areverse", dest])
    return dest


async def loop_video(src: str, dest: str, times: int) -> str:
    await _run(["ffmpeg", "-y", "-stream_loop", str(times - 1),
                "-i", src, "-c", "copy", dest])
    return dest


async def split_video(src: str, dest_dir: str, parts: int, duration: float) -> list[str]:
    os.makedirs(dest_dir, exist_ok=True)
    segment_duration = duration / parts
    paths = []
    for i in range(parts):
        start = i * segment_duration
        p = os.path.join(dest_dir, f"part_{i+1:02d}.mp4")
        await _run(["ffmpeg", "-y", "-ss", str(start),
                    "-t", str(segment_duration), "-i", src, "-c", "copy", p])
        paths.append(p)
    return paths


async def video_to_videonote(src: str, dest: str) -> str:
    """Convert video to circular Telegram video note (max 640×640)."""
    await _run(["ffmpeg", "-y", "-i", src,
                "-vf", "crop=min(iw\\,ih):min(iw\\,ih),scale=640:640",
                "-c:v", "libx264", "-c:a", "aac", "-t", "60", dest])
    return dest
