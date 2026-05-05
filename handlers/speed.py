import os
import uuid
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from utils.helpers import workdir, dl, cleanup, ext
from utils.video_tools import change_speed

router = Router()

SPEEDS = [
    ("0.25×", "0.25"), ("0.5×", "0.5"), ("0.75×", "0.75"),
    ("1.25×", "1.25"), ("1.5×", "1.5"), ("2×", "2.0"), ("4×", "4.0"),
]


class SpeedState(StatesGroup):
    waiting_file = State()
    waiting_speed = State()


def _speed_kb(src_key: str) -> InlineKeyboardMarkup:
    row1 = [InlineKeyboardButton(text=label, callback_data=f"spd:{src_key}:{val}")
            for label, val in SPEEDS[:4]]
    row2 = [InlineKeyboardButton(text=label, callback_data=f"spd:{src_key}:{val}")
            for label, val in SPEEDS[4:]]
    return InlineKeyboardMarkup(inline_keyboard=[row1, row2])


@router.message(Command("speed"), StateFilter("*"))
async def cmd_speed(msg: Message, state: FSMContext):
    await state.set_state(SpeedState.waiting_file)
    await msg.answer("⚡ <b>Change Speed</b>\n\nSend the video.", parse_mode="HTML")


@router.callback_query(F.data.regexp(r"^tool:[^:]+:speed$"))
async def cb_speed(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    _, src_key, _ = cb.data.split(":", 2)
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return
    if data.get("kind") != "video":
        await cb.answer("Speed change only works with videos.", show_alert=True)
        return
    await cb.message.edit_reply_markup()
    await state.set_state(SpeedState.waiting_speed)
    await cb.answer()
    await cb.message.reply("⚡ <b>Speed</b>\n\nChoose speed:",
                           reply_markup=_speed_kb(src_key), parse_mode="HTML")


@router.message(SpeedState.waiting_file, F.video | F.document)
async def speed_got_file(msg: Message, state: FSMContext):
    if msg.video:
        fid, fname = msg.video.file_id, "video.mp4"
    else:
        fid, fname = msg.document.file_id, msg.document.file_name

    src_key = str(uuid.uuid4())[:8]
    wd = workdir(msg.from_user.id)
    src = os.path.join(wd, f"spd_in_{src_key}.{ext(fname)}")
    await dl(msg.bot, fid, src)
    await state.update_data(src_path=src, src_key=src_key, filename=fname, file_id=fid)
    await state.set_state(SpeedState.waiting_speed)
    await msg.reply("Choose speed:", reply_markup=_speed_kb(src_key))


@router.callback_query(F.data.startswith("spd:"), SpeedState.waiting_speed)
async def speed_do(cb: CallbackQuery, state: FSMContext):
    _, src_key, speed_str = cb.data.split(":", 2)
    data = await state.get_data()
    if data.get("src_key") != src_key:
        await cb.answer("Session expired.", show_alert=True)
        return

    speed = float(speed_str)
    await cb.message.edit_reply_markup()
    await cb.answer()
    status = await cb.message.reply(f"⚡ Changing speed to {speed}×…")

    src = data.get("src_path")
    if not src:
        wd = workdir(cb.from_user.id)
        fname = data.get("filename", "video.mp4")
        src = os.path.join(wd, f"spd_in_{src_key}.{ext(fname)}")
        await dl(cb.bot, data["file_id"], src)

    wd = workdir(cb.from_user.id)
    dest = os.path.join(wd, f"speed_{src_key}.mp4")

    try:
        await change_speed(src, speed, dest)
        await status.edit_text(f"✅ Speed {speed}×! Sending…")
        with open(dest, "rb") as f:
            await cb.message.reply_document(f, filename=f"speed_{speed}x.mp4")
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n<code>{e}</code>", parse_mode="HTML")
    finally:
        cleanup(src, dest)
        await state.clear()
