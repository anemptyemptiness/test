from typing import Dict, Any, Union
from datetime import datetime, timezone, timedelta

from aiogram import Router, F
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message, ReplyKeyboardRemove, InputMediaPhoto, CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import default_state
from aiogram.fsm.context import FSMContext

from src.callbacks.place import PlaceCallbackFactory
from src.db.queries.dao.dao import AsyncOrm
from src.fsm.fsm import FSMStartShift
from src.keyboards.keyboard import create_cancel_kb, create_places_kb, create_yes_no_kb, create_rules_kb
from src.middlewares.album_middleware import AlbumsMiddleware
from src.config import settings
from src.lexicon.lexicon_ru import LEXICON_RU, rules
from src.db import cached_places
import logging


router_start_shift = Router()
router_start_shift.message.middleware(middleware=AlbumsMiddleware(2))
logger = logging.getLogger(__name__)


async def report(dictionary: Dict[str, Any], date: str, user_id: Union[str, int]) -> str:
    return f"📝Открытие смены\n\n" \
           f"Дата: {date}\n" \
           f"Точка: {dictionary['place']}\n" \
           f"Имя: {await AsyncOrm.get_current_name(user_id=user_id)}\n\n" \
           f"Есть ли дефекты: <em>{dictionary['is_defects']}</em>\n" \
           f"Чистая ли карусель: <em>{dictionary['is_clear']}</em>\n" \
           f"Включен ли свет: <em>{dictionary['is_light']}</em>\n" \
           f"Играет ли музыка: <em>{dictionary['is_music']}</em>\n" \
           f"Есть ли скрип: <em>{dictionary['is_scream']}</em>\n"


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

        object_photos = [
            InputMediaPhoto(
                media=photo_file_id,
                caption="Фото объекта" if i == 0 else ""
            ) for i, photo_file_id in enumerate(data['object_photo'])
        ]

        await message.bot.send_media_group(
            chat_id=chat_id,
            media=object_photos,
        )

        await message.bot.send_photo(
            chat_id=chat_id,
            photo=data['my_photo'],
            caption='Фото сотрудника',
        )

        if "defects_photo" in data:
            defects_photo = [
                InputMediaPhoto(
                    media=photo_file_id,
                    caption="Фото дефектов" if i == 0 else ""
                ) for i, photo_file_id in enumerate(data['defects_photo'])
            ]

            await message.bot.send_media_group(
                chat_id=chat_id,
                media=defects_photo,
            )

        await message.answer(
            text="Данные успешно записаны!\n"
                 "Передаю отчёт руководству...",
            reply_markup=ReplyKeyboardRemove(),
        )

        await message.answer(
            text="Вы вернулись в главное меню",
        )

    except Exception as e:
        logger.exception("Ошибка не с телеграм в start_shift.py")
        await message.answer(
            text="Упс... что-то пошло не так, сообщите руководству!",
            reply_markup=ReplyKeyboardRemove(),
        )
        await message.answer(
            text="Вы вернулись в главное меню",
        )
        await message.bot.send_message(
            chat_id=settings.ADMIN_ID,
            text=f"Start shift report error:\n\n{e}",
            reply_markup=ReplyKeyboardRemove(),
        )
    except TelegramAPIError as e:
        logger.exception("Ошибка с телеграм в start_shift.py")
        await message.answer(
            text="Упс... что-то пошло не так, сообщите руководству!",
            reply_markup=ReplyKeyboardRemove(),
        )
        await message.answer(
            text="Вы вернулись в главное меню",
        )
        await message.bot.send_message(
            chat_id=settings.ADMIN_ID,
            text=f"Start shift report error:\n\n{e}",
            reply_markup=ReplyKeyboardRemove(),
        )
    finally:
        await state.clear()


@router_start_shift.message(Command(commands="start_shift"), StateFilter(default_state))
async def process_start_shift_command(message: Message, state: FSMContext):
    await message.answer(
        text="Пожалуйста, выберите свою рабочую точку из списка <b>ниже</b>",
        reply_markup=create_places_kb(),
        parse_mode="html",
    )
    await state.set_state(FSMStartShift.place)


@router_start_shift.callback_query(StateFilter(FSMStartShift.place), PlaceCallbackFactory.filter())
async def process_place_command(callback: CallbackQuery, callback_data: PlaceCallbackFactory, state: FSMContext):
    await state.update_data(place=callback_data.title)
    await callback.message.delete_reply_markup()
    await callback.message.edit_text(
        text="Пожалуйста, выберите свою рабочую точку из списка <b>ниже</b>\n\n"
             f"➢ {callback_data.title}",
        parse_mode="html",
    )
    await callback.message.answer(
        text=f"{rules}",
        reply_markup=create_rules_kb(),
    )
    await callback.answer()
    await state.set_state(FSMStartShift.rules)


@router_start_shift.message(StateFilter(FSMStartShift.place))
async def warning_start_shift_command(message: Message):
    await message.answer(
        text="Пожалуйста, выберите рабочую точку из списка",
        reply_markup=create_cancel_kb(),
    )


@router_start_shift.callback_query(StateFilter(FSMStartShift.rules), F.data == "agree")
async def process_rules_command(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete_reply_markup()
    await callback.message.edit_text(
        text=f"{rules}\n\n"
             f"➢ Согласен",
        parse_mode="html",
    )
    await callback.message.answer(
        text="Пожалуйста, сфотографируйте себя\n"
             "(соответственно, 1 фото)",
        reply_markup=create_cancel_kb(),
    )
    await callback.answer()
    await state.set_state(FSMStartShift.my_photo)


@router_start_shift.message(StateFilter(FSMStartShift.rules))
async def warning_rules_command(message: Message):
    await message.answer(
        text="Нажмите на кнопку под сообщением пользовательского соглашения!",
        reply_markup=create_cancel_kb(),
    )


@router_start_shift.message(StateFilter(FSMStartShift.my_photo), F.photo)
async def process_my_photo_command(message: Message, state: FSMContext):
    await state.update_data(my_photo=message.photo[-1].file_id)
    await message.answer(
        text="Пожалуйста, сфотографируйте объект (1 фото)",
        reply_markup=create_cancel_kb(),
    )
    await state.set_state(FSMStartShift.object_photo)


@router_start_shift.message(StateFilter(FSMStartShift.my_photo))
async def warning_my_photo_command(message: Message):
    await message.answer(
        text="Нужно отправить всего одно фото себя",
        reply_markup=create_cancel_kb(),
    )


@router_start_shift.message(StateFilter(FSMStartShift.object_photo), F.photo)
async def process_object_photo_command(message: Message, state: FSMContext):
    if "object_photo" not in await state.get_data():
        await state.update_data(object_photo=[message.photo[-1].file_id])

    await message.answer(
        text="Есть ли видимые дефекты?",
        reply_markup=create_yes_no_kb(),
    )
    await state.set_state(FSMStartShift.is_defects)


@router_start_shift.message(StateFilter(FSMStartShift.object_photo))
async def warning_object_photo_command(message: Message):
    await message.answer(
        text="Нужно фото объекта",
        reply_markup=create_cancel_kb(),
    )


@router_start_shift.callback_query(StateFilter(FSMStartShift.is_defects), F.data == "yes")
async def process_defects_yes_command(callback: CallbackQuery, state: FSMContext):
    await state.update_data(is_defects="yes")
    await callback.message.delete_reply_markup()
    await callback.message.edit_text(
        text="Есть ли видимые дефекты?\n\n"
             f"➢ Да",
        parse_mode="html",
    )
    await callback.message.answer(
        text="Пожалуйста, сделайте фотографии дефектов (не более 10)",
        reply_markup=create_cancel_kb(),
    )
    await callback.answer()
    await state.set_state(FSMStartShift.defects_photo)


@router_start_shift.callback_query(StateFilter(FSMStartShift.is_defects), F.data == "no")
async def process_defects_no_command(callback: CallbackQuery, state: FSMContext):
    await state.update_data(is_defects="no")
    await callback.message.delete_reply_markup()
    await callback.message.edit_text(
        text="Есть ли видимые дефекты?\n\n"
             f"➢ Нет",
        parse_mode="html",
    )
    await callback.message.answer(
        text="Карусель чистая?",
        reply_markup=create_yes_no_kb(),
    )
    await callback.answer()
    await state.set_state(FSMStartShift.is_clear)


@router_start_shift.message(StateFilter(FSMStartShift.is_defects))
async def warning_defects_command(message: Message):
    await message.answer(
        text="Нажмите на нужную кнопку",
        reply_markup=create_cancel_kb(),
    )


@router_start_shift.message(StateFilter(FSMStartShift.defects_photo), F.photo)
async def process_defects_photo_command(message: Message, state: FSMContext):
    if "defects_photo" not in await state.get_data():
        await state.update_data(defects_photo=[message.photo[-1].file_id])

    await message.answer(
        text="Карусель чистая?",
        reply_markup=create_yes_no_kb(),
    )
    await state.set_state(FSMStartShift.is_clear)


@router_start_shift.message(StateFilter(FSMStartShift.defects_photo))
async def warning_defects_photo_command(message: Message):
    await message.answer(
        text="Нужно прислать фото дефектов (не более 10)",
        reply_markup=create_cancel_kb(),
    )


@router_start_shift.callback_query(StateFilter(FSMStartShift.is_clear), F.data == "yes")
async def process_clear_yes_command(callback: CallbackQuery, state: FSMContext):
    await state.update_data(is_clear="yes")
    await callback.message.delete_reply_markup()
    await callback.message.edit_text(
        text="Карусель чистая?\n\n"
             f"➢ Да",
        parse_mode="html",
    )
    await callback.message.answer(
        text="Горит ли на ней свет?",
        reply_markup=create_yes_no_kb(),
    )
    await callback.answer()
    await state.set_state(FSMStartShift.is_light)


@router_start_shift.callback_query(StateFilter(FSMStartShift.is_clear), F.data == "no")
async def process_clear_no_command(callback: CallbackQuery, state: FSMContext):
    await state.update_data(is_clear="no")
    await callback.message.delete_reply_markup()
    await callback.message.edit_text(
        text="Карусель чистая?\n\n"
             f"➢ Нет",
        parse_mode="html",
    )
    await callback.message.answer(
        text="Горит ли на ней свет?",
        reply_markup=create_yes_no_kb(),
    )
    await callback.answer()
    await state.set_state(FSMStartShift.is_light)


@router_start_shift.message(StateFilter(FSMStartShift.is_clear))
async def warning_clear_command(message: Message):
    await message.answer(
        text="Нажмите на нужную кнопку",
        reply_markup=create_cancel_kb(),
    )


@router_start_shift.callback_query(StateFilter(FSMStartShift.is_light), F.data == "yes")
async def process_light_yes_command(callback: CallbackQuery, state: FSMContext):
    await state.update_data(is_light="yes")
    await callback.message.delete_reply_markup()
    await callback.message.edit_text(
        text="Горит ли на ней свет?\n\n"
             f"➢ Да",
        parse_mode="html",
    )
    await callback.message.answer(
        text="Включена ли музыка?",
        reply_markup=create_yes_no_kb(),
    )
    await callback.answer()
    await state.set_state(FSMStartShift.is_music)


@router_start_shift.callback_query(StateFilter(FSMStartShift.is_light), F.data == "no")
async def process_light_no_command(callback: CallbackQuery, state: FSMContext):
    await state.update_data(is_light="no")
    await callback.message.delete_reply_markup()
    await callback.message.edit_text(
        text="Горит ли на ней свет?\n\n"
             f"➢ Нет",
        parse_mode="html",
    )
    await callback.message.answer(
        text="Включена ли музыка?",
        reply_markup=create_yes_no_kb(),
    )
    await callback.answer()
    await state.set_state(FSMStartShift.is_music)


@router_start_shift.message(StateFilter(FSMStartShift.is_light))
async def warning_light_command(message: Message):
    await message.answer(
        text="Нажмите на нужную кнопку",
        reply_markup=create_cancel_kb(),
    )


@router_start_shift.callback_query(StateFilter(FSMStartShift.is_music), F.data == "yes")
async def process_music_yes_command(callback: CallbackQuery, state: FSMContext):
    await state.update_data(is_music="yes")
    await callback.message.delete_reply_markup()
    await callback.message.edit_text(
        text="Включена ли музыка?\n\n"
             f"➢ Да",
        parse_mode="html",
    )
    await callback.message.answer(
        text="При запуске скрипит?",
        reply_markup=create_yes_no_kb(),
    )
    await callback.answer()
    await state.set_state(FSMStartShift.is_scream)


@router_start_shift.callback_query(StateFilter(FSMStartShift.is_music), F.data == "no")
async def process_music_no_command(callback: CallbackQuery, state: FSMContext):
    await state.update_data(is_music="no")
    await callback.message.delete_reply_markup()
    await callback.message.edit_text(
        text="Включена ли музыка?\n\n"
             f"➢ Нет",
        parse_mode="html",
    )
    await callback.message.answer(
        text="При запуске скрипит?",
        reply_markup=create_yes_no_kb(),
    )
    await callback.answer()
    await state.set_state(FSMStartShift.is_scream)


@router_start_shift.message(StateFilter(FSMStartShift.is_music))
async def warning_music_command(message: Message):
    await message.answer(
        text="Нажмите на нужную кнопку",
        reply_markup=create_cancel_kb(),
    )


@router_start_shift.callback_query(StateFilter(FSMStartShift.is_scream), F.data == "yes")
async def process_scream_yes_command(callback: CallbackQuery, state: FSMContext):
    await state.update_data(is_scream="yes")
    await callback.message.delete_reply_markup()
    await callback.message.edit_text(
        text="При запуске скрипит?\n\n"
             f"➢ Да",
        parse_mode="html",
    )

    start_shift_dict = await state.get_data()

    day_of_week = datetime.now(tz=timezone(timedelta(hours=3.0))).strftime('%A')
    current_date = datetime.now(tz=timezone(timedelta(hours=3.0))).strftime(f'%d/%m/%Y - {LEXICON_RU[day_of_week]}')

    await send_report(
        message=callback.message,
        state=state,
        data=start_shift_dict,
        date=current_date,
        chat_id=cached_places[start_shift_dict['place']],
    )
    await callback.answer()


@router_start_shift.callback_query(StateFilter(FSMStartShift.is_scream), F.data == "no")
async def process_scream_no_command(callback: CallbackQuery, state: FSMContext):
    await state.update_data(is_scream="no")
    await callback.message.delete_reply_markup()
    await callback.message.edit_text(
        text="При запуске скрипит?\n\n"
             f"➢ Нет",
        parse_mode="html",
    )

    start_shift_dict = await state.get_data()

    day_of_week = datetime.now(tz=timezone(timedelta(hours=3.0))).strftime('%A')
    current_date = datetime.now(tz=timezone(timedelta(hours=3.0))).strftime(f'%d/%m/%Y - {LEXICON_RU[day_of_week]}')

    await send_report(
        message=callback.message,
        state=state,
        data=start_shift_dict,
        date=current_date,
        chat_id=cached_places[start_shift_dict['place']],
    )
    await callback.answer()


@router_start_shift.message(StateFilter(FSMStartShift.is_scream))
async def warning_scream_command(message: Message):
    await message.answer(
        text="Нажмите на нужную кнопку",
        reply_markup=create_cancel_kb(),
    )
