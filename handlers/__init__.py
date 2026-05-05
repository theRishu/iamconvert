from .start import router as start_router
from .help import router as help_router
from .trim import router as trim_router
from .compress import router as compress_router
from .merge import router as merge_router
from .screenshot import router as screenshot_router
from .watermark import router as watermark_router
from .speed import router as speed_router
from .subtitle import router as subtitle_router
from .resize import router as resize_router
from .ocr import router as ocr_router
from .archive import router as archive_router
from .download import router as download_router
from .rotate import router as rotate_router
from .crop import router as crop_router
from .filter import router as filter_router
from .enhance import router as enhance_router
from .removebg import router as removebg_router
from .meme import router as meme_router
from .makegif import router as makegif_router
from .audioedit import router as audioedit_router
from .videoedit2 import router as videoedit2_router
from .qr import router as qr_router
from .mediainfo import router as mediainfo_router
from .pdftools import router as pdftools_router
from .convert import router as convert_router   # LAST — catches files when no state active

routers_list = [
    start_router,
    help_router,
    # Video tools
    trim_router,
    compress_router,
    merge_router,
    screenshot_router,
    watermark_router,
    speed_router,
    subtitle_router,
    videoedit2_router,   # reverse, loop, split, videonote
    audioedit_router,    # mute, addaudio, volume, normalize, pitch
    # Image tools
    resize_router,
    rotate_router,
    crop_router,
    filter_router,
    enhance_router,
    removebg_router,
    meme_router,
    makegif_router,
    ocr_router,
    # File/misc tools
    archive_router,
    download_router,
    qr_router,
    mediainfo_router,
    pdftools_router,
    # Base conversion — must be last
    convert_router,
]
