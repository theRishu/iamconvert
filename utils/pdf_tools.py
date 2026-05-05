import os
import asyncio


async def merge_pdfs(src_list: list[str], dest: str) -> str:
    def sync_op():
        from pypdf import PdfWriter
        writer = PdfWriter()
        for path in src_list:
            writer.append(path)
        with open(dest, "wb") as f:
            writer.write(f)
        return dest
    return await asyncio.to_thread(sync_op)


async def extract_pdf_text(src: str) -> str:
    def sync_op():
        from pypdf import PdfReader
        reader = PdfReader(src)
        parts = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if text.strip():
                parts.append(f"--- Page {i+1} ---\n{text.strip()}")
        return "\n\n".join(parts)
    return await asyncio.to_thread(sync_op)


async def split_pdf(src: str, dest_dir: str) -> list[str]:
    def sync_op():
        from pypdf import PdfReader, PdfWriter
        os.makedirs(dest_dir, exist_ok=True)
        reader = PdfReader(src)
        paths = []
        for i, page in enumerate(reader.pages):
            writer = PdfWriter()
            writer.add_page(page)
            p = os.path.join(dest_dir, f"page_{i+1:03d}.pdf")
            with open(p, "wb") as f:
                writer.write(f)
            paths.append(p)
        return paths
    return await asyncio.to_thread(sync_op)


async def compress_pdf(src: str, dest: str) -> str:
    def sync_op():
        from pypdf import PdfReader, PdfWriter
        reader = PdfReader(src)
        writer = PdfWriter()
        for page in reader.pages:
            page.compress_content_streams()
            writer.add_page(page)
        with open(dest, "wb") as f:
            writer.write(f)
        return dest
    return await asyncio.to_thread(sync_op)


async def rotate_pdf(src: str, dest: str, degrees: int = 90) -> str:
    def sync_op():
        from pypdf import PdfReader, PdfWriter
        reader = PdfReader(src)
        writer = PdfWriter()
        for page in reader.pages:
            page.rotate(degrees)
            writer.add_page(page)
        with open(dest, "wb") as f:
            writer.write(f)
        return dest
    return await asyncio.to_thread(sync_op)
