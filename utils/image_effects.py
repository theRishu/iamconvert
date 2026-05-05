import os
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance, ImageOps, ImageDraw, ImageFont
from PIL import ImageFont as _ImageFont
import os as _os


def _get_font_path():
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
               "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
               "/System/Library/Fonts/Helvetica.ttc",
               "/Library/Fonts/Arial Bold.ttf"]:
        if _os.path.exists(p):
            return p
    return None


# ── Filters ───────────────────────────────────────────────────────────────────

def _sepia(img: Image.Image) -> Image.Image:
    img = img.convert("RGB")
    arr = np.array(img, dtype=float)
    r = np.clip(arr[:,:,0]*0.393 + arr[:,:,1]*0.769 + arr[:,:,2]*0.189, 0, 255)
    g = np.clip(arr[:,:,0]*0.349 + arr[:,:,1]*0.686 + arr[:,:,2]*0.168, 0, 255)
    b = np.clip(arr[:,:,0]*0.272 + arr[:,:,1]*0.534 + arr[:,:,2]*0.131, 0, 255)
    return Image.fromarray(np.stack([r, g, b], axis=2).astype(np.uint8))


def _sketch(img: Image.Image) -> Image.Image:
    gray = img.convert("L")
    inv = ImageOps.invert(gray)
    blur = inv.filter(ImageFilter.GaussianBlur(radius=21))
    gray_arr = np.array(gray, dtype=float)
    blur_arr = np.array(blur, dtype=float)
    result = np.clip(gray_arr / (1.0 - blur_arr / 255.0 + 1e-7), 0, 255).astype(np.uint8)
    return Image.fromarray(result).convert("RGB")


def _vintage(img: Image.Image) -> Image.Image:
    img = img.convert("RGB")
    img = ImageEnhance.Color(img).enhance(0.7)
    img = ImageEnhance.Brightness(img).enhance(1.05)
    arr = np.array(img, dtype=float)
    arr[:,:,0] = np.clip(arr[:,:,0] * 1.1, 0, 255)
    arr[:,:,2] = np.clip(arr[:,:,2] * 0.85, 0, 255)
    return Image.fromarray(arr.astype(np.uint8))


def _cartoon(img: Image.Image) -> Image.Image:
    img = img.convert("RGB")
    posterized = ImageOps.posterize(img, 4)
    edges = img.convert("L").filter(ImageFilter.FIND_EDGES)
    edges = ImageOps.invert(edges).convert("RGB")
    return Image.blend(posterized, edges, 0.25)


def _oil_paint(img: Image.Image) -> Image.Image:
    img = img.convert("RGB")
    img = img.filter(ImageFilter.ModeFilter(size=5))
    img = ImageEnhance.Color(img).enhance(1.5)
    return img


def _pixelate(img: Image.Image, block: int = 16) -> Image.Image:
    small = img.resize((img.width // block, img.height // block), Image.BOX)
    return small.resize(img.size, Image.NEAREST)


FILTERS = {
    "grayscale": lambda img: ImageOps.grayscale(img).convert("RGB"),
    "sepia":     _sepia,
    "invert":    lambda img: ImageOps.invert(img.convert("RGB")),
    "blur":      lambda img: img.filter(ImageFilter.GaussianBlur(radius=4)),
    "sharpen":   lambda img: img.filter(ImageFilter.SHARPEN),
    "emboss":    lambda img: img.filter(ImageFilter.EMBOSS).convert("RGB"),
    "vintage":   _vintage,
    "sketch":    _sketch,
    "cartoon":   _cartoon,
    "oilpaint":  _oil_paint,
    "pixelate":  _pixelate,
    "edge":      lambda img: img.filter(ImageFilter.FIND_EDGES).convert("RGB"),
}


def apply_filter(src: str, filter_name: str, dest: str) -> str:
    img = Image.open(src)
    fn = FILTERS.get(filter_name)
    if not fn:
        raise ValueError(f"Unknown filter: {filter_name}")
    result = fn(img)
    result.save(dest)
    return dest


# ── Enhance ───────────────────────────────────────────────────────────────────

ENHANCE_MAP = {
    "brightness": ImageEnhance.Brightness,
    "contrast":   ImageEnhance.Contrast,
    "saturation": ImageEnhance.Color,
    "sharpness":  ImageEnhance.Sharpness,
}

ENHANCE_LEVELS = {
    "very_low":  0.3,
    "low":       0.6,
    "normal":    1.0,
    "high":      1.5,
    "very_high": 2.0,
}


def enhance_image(src: str, property_name: str, level: str, dest: str) -> str:
    img = Image.open(src)
    enhancer_cls = ENHANCE_MAP.get(property_name)
    factor = ENHANCE_LEVELS.get(level, 1.0)
    if not enhancer_cls:
        raise ValueError(f"Unknown property: {property_name}")
    result = enhancer_cls(img).enhance(factor)
    result.save(dest)
    return dest


# ── Rotate / Flip ─────────────────────────────────────────────────────────────

def rotate_image(src: str, action: str, dest: str) -> str:
    img = Image.open(src)
    if action == "90cw":
        img = img.rotate(-90, expand=True)
    elif action == "90ccw":
        img = img.rotate(90, expand=True)
    elif action == "180":
        img = img.rotate(180, expand=True)
    elif action == "hflip":
        img = ImageOps.mirror(img)
    elif action == "vflip":
        img = ImageOps.flip(img)
    else:
        raise ValueError(f"Unknown rotation: {action}")
    img.save(dest)
    return dest


# ── Crop ─────────────────────────────────────────────────────────────────────

CROP_RATIOS = {
    "1:1":  (1, 1),
    "4:3":  (4, 3),
    "3:4":  (3, 4),
    "16:9": (16, 9),
    "9:16": (9, 16),
    "3:2":  (3, 2),
    "2:3":  (2, 3),
}


def crop_image_ratio(src: str, ratio: str, dest: str) -> str:
    img = Image.open(src)
    rw, rh = CROP_RATIOS[ratio]
    w, h = img.size
    target_w = min(w, int(h * rw / rh))
    target_h = min(h, int(w * rh / rw))
    left  = (w - target_w) // 2
    top   = (h - target_h) // 2
    img = img.crop((left, top, left + target_w, top + target_h))
    img.save(dest)
    return dest


def crop_image_coords(src: str, left: int, top: int, right: int, bottom: int, dest: str) -> str:
    img = Image.open(src)
    img = img.crop((left, top, right, bottom))
    img.save(dest)
    return dest


# ── Meme ─────────────────────────────────────────────────────────────────────

def make_meme(src: str, top_text: str, bottom_text: str, dest: str) -> str:
    img = Image.open(src).convert("RGBA")
    draw = ImageDraw.Draw(img)
    font_size = max(24, img.width // 12)

    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/Library/Fonts/Impact.ttf",
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    font = None
    for path in candidates:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, font_size)
                break
            except Exception:
                continue
    if not font:
        font = ImageFont.load_default()

    def draw_text_with_outline(text, y_frac):
        if not text:
            return
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        x = (img.width - tw) // 2
        y = int(img.height * y_frac)
        for dx, dy in [(-2,-2),(-2,2),(2,-2),(2,2),(-2,0),(2,0),(0,-2),(0,2)]:
            draw.text((x+dx, y+dy), text, font=font, fill=(0, 0, 0, 255))
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))

    draw_text_with_outline(top_text.upper(), 0.02)
    draw_text_with_outline(bottom_text.upper(), 0.88)

    out = img.convert("RGB") if dest.lower().endswith((".jpg", ".jpeg")) else img
    out.save(dest)
    return dest


# ── GIF from images ───────────────────────────────────────────────────────────

def images_to_gif(src_list: list[str], dest: str, fps: int = 5, loop: int = 0) -> str:
    frames = [Image.open(p).convert("RGBA") for p in src_list]
    duration_ms = int(1000 / fps)
    frames[0].save(
        dest,
        save_all=True,
        append_images=frames[1:],
        duration=duration_ms,
        loop=loop,
        optimize=True,
    )
    return dest


# ── Remove background ─────────────────────────────────────────────────────────

def remove_background(src: str, dest: str) -> str:
    from rembg import remove
    with open(src, "rb") as f:
        data = f.read()
    result = remove(data)
    png_dest = dest if dest.lower().endswith(".png") else dest.rsplit(".", 1)[0] + ".png"
    with open(png_dest, "wb") as f:
        f.write(result)
    return png_dest
