import os
import asyncio
from PIL import Image, ImageDraw, ImageFont


def _font(size: int = 36):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Bold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


async def convert_image(src: str, out_fmt: str, dest: str) -> str:
    def sync_op():
        img = Image.open(src)
        if img.mode in ("RGBA", "P", "LA") and out_fmt.upper() in ("JPG", "JPEG"):
            img = img.convert("RGB")
        save_fmt = "JPEG" if out_fmt.upper() in ("JPG", "JPEG") else out_fmt.upper()
        img.save(dest, save_fmt)
        return dest
    return await asyncio.to_thread(sync_op)


async def to_sticker(src: str, dest: str) -> str:
    def sync_op():
        img = Image.open(src).convert("RGBA")
        img.thumbnail((512, 512), Image.LANCZOS)
        canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        offset = ((512 - img.width) // 2, (512 - img.height) // 2)
        canvas.paste(img, offset)
        canvas.save(dest, "WEBP")
        return dest
    return await asyncio.to_thread(sync_op)


async def resize_image(src: str, width: int, height: int, dest: str) -> str:
    def sync_op():
        img = Image.open(src)
        if img.mode in ("RGBA", "P") and dest.lower().endswith((".jpg", ".jpeg")):
            img = img.convert("RGB")
        img = img.resize((width, height), Image.LANCZOS)
        img.save(dest)
        return dest
    return await asyncio.to_thread(sync_op)


async def compress_image(src: str, dest: str, quality: int = 60) -> str:
    def sync_op():
        img = Image.open(src)
        fmt = os.path.splitext(src)[1].lstrip(".").upper()
        if fmt in ("JPG", "JPEG"):
            img = img.convert("RGB")
            img.save(dest, "JPEG", quality=quality, optimize=True)
        elif fmt == "PNG":
            img.save(dest, "PNG", optimize=True)
        elif fmt == "WEBP":
            img.save(dest, "WEBP", quality=quality)
        else:
            img.save(dest, fmt)
        return dest
    return await asyncio.to_thread(sync_op)


async def add_watermark_image(src: str, text: str, position: str, dest: str) -> str:
    def sync_op():
        img = Image.open(src).convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        font = _font(max(24, img.width // 20))

        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        pad = 8

        pos_map = {
            "topleft":     (10, 10),
            "topright":    (img.width - tw - 10, 10),
            "bottomleft":  (10, img.height - th - 10),
            "bottomright": (img.width - tw - 10, img.height - th - 10),
            "center":      ((img.width - tw) // 2, (img.height - th) // 2),
        }
        x, y = pos_map.get(position, (10, 10))
        draw.rectangle([x - pad, y - pad, x + tw + pad, y + th + pad], fill=(0, 0, 0, 160))
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 230))

        out = Image.alpha_composite(img, overlay)
        if dest.lower().endswith((".jpg", ".jpeg")):
            out = out.convert("RGB")
        out.save(dest)
        return dest
    return await asyncio.to_thread(sync_op)


async def ocr_image(src: str) -> str:
    def sync_op():
        try:
            import pytesseract
            img = Image.open(src)
            return pytesseract.image_to_string(img).strip()
        except ImportError:
            raise RuntimeError("pytesseract not installed")
    return await asyncio.to_thread(sync_op)


async def images_to_pdf(src_list: list[str], dest: str) -> str:
    import img2pdf
    def sync_op():
        with open(dest, "wb") as f:
            f.write(img2pdf.convert(src_list))
        return dest
    return await asyncio.to_thread(sync_op)


async def pdf_to_images(src: str, dest_dir: str) -> list[str]:
    def sync_op():
        from pdf2image import convert_from_path
        pages = convert_from_path(src, dpi=150)
        paths = []
        for i, page in enumerate(pages):
            p = os.path.join(dest_dir, f"page_{i+1:03d}.jpg")
            page.save(p, "JPEG")
            paths.append(p)
        return paths
    return await asyncio.to_thread(sync_op)
