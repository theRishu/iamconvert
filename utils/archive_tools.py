import os
import asyncio
import zipfile
import tarfile

try:
    import rarfile
    _HAS_RAR = True
except ImportError:
    _HAS_RAR = False


async def create_zip(file_list: list[str], dest: str) -> str:
    def sync_op():
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in file_list:
                zf.write(f, os.path.basename(f))
        return dest
    return await asyncio.to_thread(sync_op)


async def list_archive(src: str) -> list[str]:
    def sync_op():
        ext = os.path.splitext(src)[1].lower()
        if ext == ".zip":
            with zipfile.ZipFile(src) as zf:
                return zf.namelist()
        if ext in (".tar", ".gz", ".bz2", ".xz") or src.endswith((".tar.gz", ".tar.bz2")):
            with tarfile.open(src, "r:*") as tf:
                return tf.getnames()
        if ext == ".rar" and _HAS_RAR:
            with rarfile.RarFile(src) as rf:
                return rf.namelist()
        raise ValueError(f"Unsupported archive: {ext}")
    return await asyncio.to_thread(sync_op)


async def extract_archive(src: str, dest_dir: str) -> list[str]:
    def sync_op():
        os.makedirs(dest_dir, exist_ok=True)
        ext = os.path.splitext(src)[1].lower()
        if ext == ".zip":
            with zipfile.ZipFile(src) as zf:
                zf.extractall(dest_dir)
                return zf.namelist()
        if ext in (".tar", ".gz", ".bz2", ".xz") or src.endswith((".tar.gz", ".tar.bz2")):
            with tarfile.open(src, "r:*") as tf:
                tf.extractall(dest_dir)
                return tf.getnames()
        if ext == ".rar" and _HAS_RAR:
            with rarfile.RarFile(src) as rf:
                rf.extractall(dest_dir)
                return rf.namelist()
        raise ValueError(f"Unsupported archive: {ext}")
    return await asyncio.to_thread(sync_op)
