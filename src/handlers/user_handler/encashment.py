from datetime import datetime, timedelta, timezone

from aiogram import Router, F
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message, ReplyKeyboardRemove, InputMediaPhoto, CallbackQuery
from aiogram.filters import StateFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state

from typing import Dict, Any, Union

from src.callbacks.place import PlaceCallbackFactory
from src.config import settings
from src.db.queries.dao.dao import AsyncOrm
from src.fsm.fsm import FSMEncashment
from src.lexicon.lexicon_ru import LEXICON_RU
from src.keyboards.keyboard import create_cancel_kb, create_places_kb
from src.middlewares.album_middleware import AlbumsMiddleware
from src.db import cached_places
import logging

router_encashment = Router()
router_encashment.message.middleware(middleware=AlbumsMiddleware(2))
logger = logging.getLogger(__name__)


async def report(dictionary: Dict[str, Any], date: str, user_id: Union[str, int]) -> str:
    return "📝Инкассация:\n\n" \
           f"Точка: {dictionary['place']}\n" \
           f"Дата: {date}\n" \
           f"Имя: {await AsyncOrm.get_current_name(user_id=user_id)}\n\n" \
           f"Кто инкассировал: <em>{dictionary['who']}</em>\n" \
           f"Дата инкассации: <em>{dictionary['date']}</em>\n" \
           f"Сумма инкассации: <em>{dictionary['summary']}</em>"


async def send_report(message: Message, state: FSMContext, data: dict, date: str, chat_id: Union[str, int]):
    try:
        await message.bot.send_message(
            chat_id=chat_id,
            text=await report(
                dictionary=data,
                date=date,
                user_id=message.chat.id,
            ),
            parse_mode="html",
        )

        photos = [
            InputMediaPhoto(
                media=photo_file_id,
                caption="Фото тетради" if i == 0 else ""
            ) for i, photo_file_id in enumerate(data['photos'])
        ]

        await message.bot.send_media_group(
            media=photos,
            chat_id=chat_id,
        )

        await message.answer(
            text="Отлично! Формирую отчёт...\nОтправляю начальству!",
            reply_markup=ReplyKeyboardRemove(),
        )

        await message.answer(
            text="Вы вернулись в главное меню",
        )
    except Exception as e:
        logger.exception("Ошибка не с телеграм в encashment.py")
        await message.bot.send_message(
            text=f"Encashment report error: {e}\n"
                 f"User_id: {message.from_user.id}",
            chat_id=settings.ADMIN_ID,
            reply_markup=ReplyKeyboardRemove(),
        )
        await message.answer(
            text="Упс... что-то пошло не так, сообщите руководству!",
            reply_markup=ReplyKeyboardRemove(),
        )
    except TelegramAPIError as e:
        logger.exception("Ошибка с телеграм в encashment.py")
        await message.bot.send_message(
            text=f"Encashment report error: {e}\n"
                 f"User_id: {message.from_user.id}",
            chat_id=settings.ADMIN_ID,
            reply_markup=ReplyKeyboardRemove(),
        )
        await message.answer(
            text="Упс... что-то пошло не так, сообщите руководству!",
            reply_markup=ReplyKeyboardRemove(),
        )
    finally:
        await state.clear()


@router_encashment.message(Command(commands="encashment"), StateFilter(default_state))
async def process_start_command(message: Message, state: FSMContext):
    await message.answer(
        text="Пожалуйста, выберите свою рабочую точку из списка <b>ниже</b>",
        reply_markup=create_places_kb(),
        parse_mode="html",
    )
    await state.set_state(FSMEncashment.place)


@router_encashment.callback_query(StateFilter(FSMEncashment.place), PlaceCallbackFactory.filter())
async def process_place_command(callback: CallbackQuery, callback_data: PlaceCallbackFactory, state: FSMContext):
    await state.update_data(place=callback_data.title)
    await callback.message.delete_reply_markup()
    await callback.message.edit_text(
        text="Пожалуйста, выберите свою рабочую точку из списка <b>ниже</b>\n\n"
             f"➢ {callback_data.title}",
        parse_mode="html",
    )
    await callback.message.answer(
        text="Кто инкассировал?",
        reply_markup=create_cancel_kb(),
    )
    await callback.answer()
    await state.set_state(FSMEncashment.who)


@router_encashment.message(StateFilter(FSMEncashment.place))
async def warning_place_command(message: Message):
    await message.answer(
        text="Выберите рабочую точку из выпадающего списка",
        reply_markup=create_cancel_kb(),
    )


@router_encashment.message(StateFilter(FSMEncashment.who), F.text)
async def process_who_command(message: Message, state: FSMContext):
    await state.update_data(who=message.text)
    await message.answer(
        text="Напишите дату инкассации",
        reply_markup=create_cancel_kb(),
    )
    await state.set_state(FSMEncashment.date)


@router_encashment.message(StateFilter(FSMEncashment.who))
async def warning_who_command(message: Message):
    await message.answer(
        text="Напишите, кто инкассировал",
        reply_markup=create_cancel_kb(),
    )


@router_encashment.message(StateFilter(FSMEncashment.date), F.text)
async def process_date_command(message: Message, state: FSMContext):
    await state.update_data(date=message.text)
    await message.answer(
        text="Напишите сумму инкассации",
        reply_markup=create_cancel_kb(),
    )
    await state.set_state(FSMEncashment.summary)


@router_encashment.message(StateFilter(FSMEncashment.date))
async def warning_date_command(message: Message):
    await message.answer(
        text="Напишите дату инкассации",
        reply_markup=create_cancel_kb(),
    )


@router_encashment.message(StateFilter(FSMEncashment.summary), F.text)
async def process_summary_command(message: Message, state: FSMContext):
    await state.update_data(summary=message.text)
    await message.answer(
        text="Пришлите фото тетради с подписью отв. лица",
        reply_markup=create_cancel_kb(),
    )
    await state.set_state(FSMEncashment.photos)


@router_encashment.message(StateFilter(FSMEncashment.summary))
async def warning_summary_command(message: Message):
    await message.answer(
        text="Напишите сумму инкассации",
        reply_markup=create_cancel_kb(),
    )


@router_encashment.message(StateFilter(FSMEncashment.photos), F.photo)
async def process_photos_command(message: Message, state: FSMContext):
    if "photos" not in await state.get_data():
        await state.update_data(photos=[message.photo[-1].file_id])

    encashment_dict = await state.get_data()

    day_of_week = datetime.now(tz=timezone(timedelta(hours=3.0))).strftime('%A')
    date = datetime.now(tz=timezone(timedelta(hours=3.0))).strftime(f'%d/%m/%Y - {LEXICON_RU[day_of_week]}')

    await send_report(
        message=message,
        state=state,
        data=encashment_dict,
        date=date,
        chat_id=cached_places[encashment_dict['place']],
    )


@router_encashment.message(StateFilter(FSMEncashment.photos))
async def warning_photos_command(message: Message):
    await message.answer(
        text="Пришлите фото тетради с подписью отв. лица",
        reply_markup=create_cancel_kb(),
    )
