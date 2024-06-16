from datetime import datetime, timezone, timedelta

from typing import Dict, Any, Union

from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardRemove, InputMediaPhoto, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.filters import StateFilter, Command
from aiogram.exceptions import TelegramAPIError

from src.callbacks.place import PlaceCallbackFactory
from src.db import cached_places
from src.db.queries.dao.dao import AsyncOrm
from src.fsm.fsm import FSMFinishShift
from src.lexicon.lexicon_ru import LEXICON_RU
from src.keyboards.keyboard import create_cancel_kb, create_places_kb, create_yes_no_kb
from src.middlewares.album_middleware import AlbumsMiddleware
from src.config import settings

from decimal import Decimal
import re
import logging

router_finish = Router()
router_finish.message.middleware(middleware=AlbumsMiddleware(2))
logger = logging.getLogger(__name__)


async def report(dictionary: Dict[str, Any], date: str, user_id: Union[str, int]) -> str:
    return "📝Закрытие смены:\n\n"\
           f"Дата: {date}\n" \
           f"Точка: {dictionary['place']}\n" \
           f"Имя: {await AsyncOrm.get_current_name(user_id=user_id)}\n\n" \
           f"Льготники: <em>{dictionary['beneficiaries']}</em>\n" \
           f"Общая выручка: <em>{dictionary['summary']}</em>\n" \
           f"Наличные: <em>{dictionary['cash']}</em>\n" \
           f"Безнал: <em>{dictionary['online_cash']}</em>\n" \
           f"QR-код: <em>{dictionary['qr_code']}</em>\n" \
           f"Расход: <em>{dictionary['expenditure']}</em>\n" \
           f"Зарплата: <em>{dictionary['salary']}</em>\n" \
           f"В конверт: <em>{dictionary['convert']}</em>\n\n" \
           f"Общее количество прокатов на карусели: <em>{dictionary['count_rentals_carous']}</em>\n\n" \
           f"Количество проката машинок 5 минут (7): <em>{dictionary['count_cars_5']}</em>\n" \
           f"Количество проката машинок 10 минут (20): <em>{dictionary['count_cars_10']}</em>\n\n" \
           f"Количество прокатов тележек: <em>{dictionary['count_rentals_cart']}</em>\n\n" \
           f"Количество проданного доп.товара: <em>{dictionary['count_additional']}</em>\n"


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

        necessary_photos = [
            InputMediaPhoto(
                media=photo_file_id,
                caption="Необходимые фото за смену (чеки о закрытии смены, оплата QR-кода, "
                        "чек расхода)" if i == 0 else ""
            ) for i, photo_file_id in enumerate(data["necessary_photos"])
        ]

        await message.bot.send_media_group(
            media=necessary_photos,
            chat_id=chat_id,
        )

        photos_object = [
            InputMediaPhoto(
                media=photo_file_id,
                caption="Фото объекта" if i == 0 else ""
            ) for i, photo_file_id in enumerate(data["object_photo"])
        ]

        await message.bot.send_media_group(
            media=photos_object,
            chat_id=chat_id,
        )

        if "photo_of_beneficiaries" in data:
            photo_of_beneficiaries = [
                InputMediaPhoto(
                    media=photo_file_id,
                    caption="Необходимые фото льготников" if i == 0 else ""
                ) for i, photo_file_id in enumerate(data["photo_of_beneficiaries"])
            ]

            await message.bot.send_media_group(
                media=photo_of_beneficiaries,
                chat_id=chat_id,
            )

        await AsyncOrm.set_data_to_reports(
            user_id=message.chat.id,
            place=data['place'],
            visitors=int(data['visitors']),
            revenue=int(data['summary'].replace('.', '').replace(',', '')),
        )

        await message.answer(
            text="Отлично! Формирую отчёт...\nОтправляю начальству!",
            reply_markup=ReplyKeyboardRemove(),
        )

        await message.answer(
            text="Вы вернулись в главное меню",
        )
    except Exception as e:
        logger.exception("Ошибка не с телеграм в finish_shift.py")
        await message.bot.send_message(
            text=f"Finish shift report error: {e}\n"
                 f"User_id: {message.from_user.id}",
            chat_id=settings.ADMIN_ID,
            reply_markup=ReplyKeyboardRemove(),
        )
        await message.answer(
            text="Упс... что-то пошло не так, сообщите руководству!",
            reply_markup=ReplyKeyboardRemove(),
        )
    except TelegramAPIError as e:
        logger.exception("Ошибка с телеграм в finish_shift.py")
        await message.bot.send_message(
            text=f"Finish shift report error: {e}\n"
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


@router_finish.message(Command(commands="finish_shift"), StateFilter(default_state))
async def process_start_command(message: Message, state: FSMContext):
    await message.answer(
        text="Пожалуйста, выберите свою рабочую точку из списка <b>ниже</b>",
        reply_markup=create_places_kb(),
        parse_mode="html",
    )
    await state.set_state(FSMFinishShift.place)


@router_finish.callback_query(StateFilter(FSMFinishShift.place), PlaceCallbackFactory.filter())
async def process_place_command(callback: CallbackQuery, callback_data: PlaceCallbackFactory, state: FSMContext):
    await state.update_data(place=callback_data.title)
    await callback.message.delete_reply_markup()
    await callback.message.edit_text(
        text="Пожалуйста, выберите свою рабочую точку из списка <b>ниже</b>\n\n"
             f"➢ {callback_data.title}",
        parse_mode="html",
    )
    await callback.message.answer(
        text="Напишите общее количество посетителей за сегодня",
        reply_markup=create_cancel_kb(),
    )
    await callback.answer()
    await state.set_state(FSMFinishShift.visitors)


@router_finish.message(StateFilter(FSMFinishShift.place))
async def warning_place_command(message: Message):
    await message.answer(
        text="Выберите рабочую точку ниже из выпадающего списка",
        reply_markup=create_cancel_kb(),
    )


@router_finish.message(StateFilter(FSMFinishShift.visitors), F.text.isdigit())
async def process_visitors_command(message: Message, state: FSMContext):
    await state.update_data(visitors=int(message.text))
    await message.answer(
        text="Напишите общую выручку за сегодня",
        reply_markup=create_cancel_kb(),
    )
    await state.set_state(FSMFinishShift.summary)


@router_finish.message(StateFilter(FSMFinishShift.visitors))
async def warning_visitors_command(message: Message):
    await message.answer(
        text="Напишите количество посетителей за день <b>ЦЕЛЫМ числом</b>",
        reply_markup=create_cancel_kb(),
        parse_mode="html",
    )


@router_finish.message(StateFilter(FSMFinishShift.summary), F.text)
async def process_summary_command(message: Message, state: FSMContext):
    money_message = message.text.lower()
    pattern = r'\b\w*рубл[ьяей]?\w*\b'

    if "," in message.text:
        money_message = message.text.replace(",", ".")

    money_message = re.sub(pattern, '', money_message)

    await state.update_data(summary=str(Decimal(money_message)))
    await message.answer(
        text="Были ли льготники сегодня?",
        reply_markup=create_yes_no_kb(),
    )
    await state.set_state(FSMFinishShift.beneficiaries)


@router_finish.message(StateFilter(FSMFinishShift.summary))
async def warning_summary_command(message: Message):
    await message.answer(
        text="Напишите общую выручку за сегодня <b>числом</b>",
        reply_markup=create_cancel_kb(),
        parse_mode="html",
    )


@router_finish.callback_query(StateFilter(FSMFinishShift.beneficiaries), F.data == "yes")
async def process_beneficiaries_yes_command(callback: CallbackQuery, state: FSMContext):
    await state.update_data(beneficiaries="yes")
    await callback.message.delete_reply_markup()
    await callback.message.edit_text(
        text="Были ли льготники сегодня?\n\n"
             f"➢ Да",
        parse_mode="html",
    )
    await callback.message.answer(
        text="Прикрепите подтвреждающее фото (справка, паспорт родителей)",
        reply_markup=create_cancel_kb(),
    )
    await callback.answer()
    await state.set_state(FSMFinishShift.photo_of_beneficiaries)


@router_finish.callback_query(StateFilter(FSMFinishShift.beneficiaries), F.data == "no")
async def process_beneficiaries_no_command(callback: CallbackQuery, state: FSMContext):
    await state.update_data(beneficiaries="no")
    await callback.message.delete_reply_markup()
    await callback.message.edit_text(
        text="Были ли льготники сегодня?\n\n"
             f"➢ Нет",
        parse_mode="html",
    )
    await callback.message.answer(
        text="Напишите сумму наличных за сегодня",
        reply_markup=create_cancel_kb(),
    )
    await callback.answer()
    await state.set_state(FSMFinishShift.cash)


@router_finish.message(StateFilter(FSMFinishShift.photo_of_beneficiaries))
async def process_photo_beneficiaries_command(message: Message, state: FSMContext):
    if message.photo:
        if "photo_beneficiaries" not in await state.get_data():
            await state.update_data(photo_of_beneficiaries=[message.photo[-1].file_id])

        await message.answer(
            text="Напишите сумму наличных за сегодня",
            reply_markup=create_cancel_kb(),
        )
        await state.set_state(FSMFinishShift.cash)
    else:
        await message.answer(
            text="Это не похоже на фото!\nПрикрепите подтвреждающее фото (справка, паспорт родителей)",
            reply_markup=create_cancel_kb(),
        )


@router_finish.message(StateFilter(FSMFinishShift.cash), F.text)
async def process_cash_command(message: Message, state: FSMContext):
    await state.update_data(cash=message.text)
    await message.answer(
        text="Напишите сумму безнала за сегодня",
        reply_markup=create_cancel_kb(),
    )
    await state.set_state(FSMFinishShift.online_cash)


@router_finish.message(StateFilter(FSMFinishShift.cash))
async def warning_cash_command(message: Message):
    await message.answer(
        text="Напишите сумму наличных за сегодня <b>числом</b>",
        reply_markup=create_cancel_kb(),
        parse_mode="html",
    )


@router_finish.message(StateFilter(FSMFinishShift.online_cash), F.text)
async def process_online_cash_command(message: Message, state: FSMContext):
    await state.update_data(online_cash=message.text)
    await message.answer(
        text="Напишите сумму по QR-коду за сегодня",
        reply_markup=create_cancel_kb(),
    )
    await state.set_state(FSMFinishShift.qr_code)


@router_finish.message(StateFilter(FSMFinishShift.online_cash))
async def warning_online_cash_command(message: Message):
    await message.answer(
        text="Напишите сумму безнала за сегодня <b>числом</b>",
        reply_markup=create_cancel_kb(),
        parse_mode="html",
    )


@router_finish.message(StateFilter(FSMFinishShift.qr_code), F.text)
async def process_qr_code_command(message: Message, state: FSMContext):
    await state.update_data(qr_code=message.text)
    await message.answer(
        text="Введите сумму расхода за сегодня",
        reply_markup=create_cancel_kb(),
    )
    await state.set_state(FSMFinishShift.expenditure)


@router_finish.message(StateFilter(FSMFinishShift.qr_code))
async def warning_qr_code_command(message: Message):
    await message.answer(
        text="Введите сумму по QR-коду за сегодня <b>числом</b>",
        reply_markup=create_cancel_kb(),
        parse_mode="html",
    )


@router_finish.message(StateFilter(FSMFinishShift.expenditure), F.text)
async def process_expenditure_command(message: Message, state: FSMContext):
    await state.update_data(expenditure=message.text)
    await message.answer(
        text="Напишите, сколько вы взяли ЗП за сегодня\n\n"
             "Если вы <b>не</b> брали ЗП, напишите 0",
        reply_markup=create_cancel_kb(),
        parse_mode="html",
    )
    await state.set_state(FSMFinishShift.salary)


@router_finish.message(StateFilter(FSMFinishShift.expenditure))
async def warning_expenditure_command(message: Message):
    await message.answer(
        text="Введите сумму расхода за сегодня <b>числом</b>",
        reply_markup=create_cancel_kb(),
        parse_mode="html",
    )


@router_finish.message(StateFilter(FSMFinishShift.salary), F.text)
async def process_salary_command(message: Message, state: FSMContext):
    await state.update_data(salary=message.text)
    await message.answer(
        text="Напишите, сколько положено в конверт",
        reply_markup=create_cancel_kb(),
    )
    await state.set_state(FSMFinishShift.convert)


@router_finish.message(StateFilter(FSMFinishShift.salary))
async def warning_salary_command(message: Message):
    await message.answer(
        text="Напишите, сколько вы взяли ЗП за сегодня\n\n"
             "Если вы <b>не</b> брали ЗП, напишите 0",
        reply_markup=create_cancel_kb(),
        parse_mode="html",
    )


@router_finish.message(StateFilter(FSMFinishShift.convert), F.text)
async def process_convert_command(message: Message, state: FSMContext):
    await state.update_data(convert=message.text)
    await message.answer(
        text="Напишите количество прокатов на карусели",
        reply_markup=create_cancel_kb(),
    )
    await state.set_state(FSMFinishShift.count_rentals_carous)


@router_finish.message(StateFilter(FSMFinishShift.convert))
async def warning_convert_command(message: Message):
    await message.answer(
        text="Напишите, сколько положено в конверт",
        reply_markup=create_cancel_kb(),
    )


@router_finish.message(StateFilter(FSMFinishShift.count_rentals_carous), F.text.isdigit())
async def process_count_rentals_carous_command(message: Message, state: FSMContext):
    await state.update_data(count_rentals_carous=message.text)
    await message.answer(
        text="Напишите количество проката машинок 5 минут (7 минут)",
        reply_markup=create_cancel_kb(),
    )
    await state.set_state(FSMFinishShift.count_cars_5)


@router_finish.message(StateFilter(FSMFinishShift.count_rentals_carous))
async def warning_count_rentals_carous_command(message: Message):
    await message.answer(
        text="Напишите количество прокатов на карусели <b>числом</b>",
        reply_markup=create_cancel_kb(),
        parse_mode="html",
    )


@router_finish.message(StateFilter(FSMFinishShift.count_cars_5), F.text.isdigit())
async def process_count_cars_5_command(message: Message, state: FSMContext):
    await state.update_data(count_cars_5=message.text)
    await message.answer(
        text="Напишите количество проката машинок 10 минут (20 минут)",
        reply_markup=create_cancel_kb(),
    )
    await state.set_state(FSMFinishShift.count_cars_10)


@router_finish.message(StateFilter(FSMFinishShift.count_cars_5))
async def warning_count_cars_5_command(message: Message):
    await message.answer(
        text="Напишите количество проката машинок 5 минут (7 минут) <b>числом</b>",
        reply_markup=create_cancel_kb(),
        parse_mode="html",
    )


@router_finish.message(StateFilter(FSMFinishShift.count_cars_10), F.text.isdigit())
async def process_count_cars_10_command(message: Message, state: FSMContext):
    await state.update_data(count_cars_10=message.text)
    await message.answer(
        text="Напишите количество проката тележек",
        reply_markup=create_cancel_kb(),
    )
    await state.set_state(FSMFinishShift.count_rentals_cart)


@router_finish.message(StateFilter(FSMFinishShift.count_cars_10))
async def warning_count_cars_10_command(message: Message):
    await message.answer(
        text="Напишите количество проката машинок 10 минут (20 минут) <b>числом</b>",
        reply_markup=create_cancel_kb(),
        parse_mode="html",
    )


@router_finish.message(StateFilter(FSMFinishShift.count_rentals_cart), F.text.isdigit())
async def process_count_rantals_cart_command(message: Message, state: FSMContext):
    await state.update_data(count_rentals_cart=message.text)
    await message.answer(
        text="Напишите общее количество продаж доп.товара за день (шарики, слаймы и т.д)",
        reply_markup=create_cancel_kb(),
    )
    await state.set_state(FSMFinishShift.count_additional)


@router_finish.message(StateFilter(FSMFinishShift.count_rentals_cart))
async def warning_count_rentals_cart_command(message: Message):
    await message.answer(
        text="Напишите количество проката тележек <b>числом</b>",
        reply_markup=create_cancel_kb(),
        parse_mode="html",
    )


@router_finish.message(StateFilter(FSMFinishShift.count_additional), F.text)
async def process_count_additional_command(message: Message, state: FSMContext):
    await state.update_data(count_additional=message.text)
    await message.answer(
        text="Пришлите необходимые фото за смену (чеки, льготы, тетрадь и т.д)",
        reply_markup=create_cancel_kb(),
    )
    await state.set_state(FSMFinishShift.necessary_photos)


@router_finish.message(StateFilter(FSMFinishShift.count_additional))
async def warning_count_additional_command(message: Message):
    await message.answer(
        text="Напишите общее количество продаж доп.товара за день (шарики, слаймы и т.д)",
        reply_markup=create_cancel_kb(),
    )


@router_finish.message(StateFilter(FSMFinishShift.necessary_photos), F.photo)
async def process_necessary_photos_command(message: Message, state: FSMContext):
    if "necessary_photos" not in await state.get_data():
        await state.update_data(necessary_photos=[message.photo[-1].file_id])

    await message.answer(
        text="Сфотографируйте объект (1 фото)",
        reply_markup=create_cancel_kb(),
    )
    await state.set_state(FSMFinishShift.object_photo)


@router_finish.message(StateFilter(FSMFinishShift.necessary_photos))
async def warning_necessary_photos_command(message: Message):
    await message.answer(
        text="Пришлите необходимые фото за смену (чеки, льготы, тетрадь и т.д)",
        reply_markup=create_cancel_kb(),
    )


@router_finish.message(StateFilter(FSMFinishShift.object_photo))
async def process_object_photo_command(message: Message, state: FSMContext):
    if message.photo:
        if "object_photo" not in await state.get_data():
            await state.update_data(object_photo=[message.photo[-1].file_id])

        finish_shift_dict = await state.get_data()

        day_of_week = datetime.now(tz=timezone(timedelta(hours=3.0))).strftime('%A')
        current_date = datetime.now(tz=timezone(timedelta(hours=3.0))).strftime(f'%d/%m/%Y - {LEXICON_RU[day_of_week]}')

        await send_report(
            message=message,
            state=state,
            data=finish_shift_dict,
            date=current_date,
            chat_id=cached_places[finish_shift_dict['place']],
        )

    else:
        await message.answer(
            text="Сфотографируйте объект (1 фото)",
            reply_markup=create_cancel_kb(),
        )
