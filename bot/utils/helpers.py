"""Вспомогательные функции для навигации и безопасного редактирования сообщений."""

from __future__ import annotations

import logging

from telegram import InlineKeyboardMarkup, Message, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes, ConversationHandler

from bot.utils.keyboards import (
    MAIN_MENU_BUTTONS,
    REMOVE_KEYBOARD,
    get_cancel_keyboard,
    get_main_reply_keyboard,
)

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4096


async def safe_edit_message(
    update: Update,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str = "HTML",
):
    """Безопасно редактирует callback-сообщение, с fallback на отправку нового."""
    query = update.callback_query
    if not query:
        return None

    try:
        await query.answer()
    except Exception:
        logger.error("Не удалось ответить на callback_query", exc_info=True)

    try:
        return await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
    except BadRequest as exc:
        message = str(exc).lower()
        if "message is not modified" in message:
            return query.message
        if "message to edit not found" in message or "message can't be edited" in message:
            return await query.message.reply_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)
        logger.error("BadRequest при редактировании сообщения", exc_info=True)
        return await query.message.reply_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception:
        logger.error("Ошибка при редактировании сообщения", exc_info=True)
        return await query.message.reply_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)


async def edit_or_send(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE | None,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str = "HTML",
):
    """
    Редактирует меню при callback-сценарии или отправляет новое сообщение,
    запоминая текущий message_id как активный экран меню.
    """
    text = text if len(text) <= MAX_MESSAGE_LENGTH else text[: MAX_MESSAGE_LENGTH - 3] + "..."
    msg = None
    if update.callback_query:
        msg = await safe_edit_message(update, text, reply_markup=reply_markup, parse_mode=parse_mode)
    elif update.effective_message:
        user_data = context.user_data if context else {}
        prev_msg_id = user_data.get("menu_message_id")
        if prev_msg_id and update.effective_chat and context:
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=prev_msg_id)
            except Exception:
                logger.debug("Не удалось удалить предыдущее меню", exc_info=True)
        msg = await update.effective_message.reply_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )

    if msg and context:
        context.user_data["menu_message_id"] = msg.message_id
    return msg


async def notify_and_return(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE | None,
    text: str,
    menu_text: str,
    menu_markup: InlineKeyboardMarkup | None,
) -> None:
    """Показывает короткое уведомление и возвращает пользователя в обновлённое меню."""
    if update.callback_query:
        try:
            await update.callback_query.answer(text=text[:200], show_alert=False)
        except Exception:
            logger.error("Не удалось показать callback-уведомление", exc_info=True)
    await edit_or_send(update, context, menu_text, reply_markup=menu_markup)


async def ask_for_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    prompt: str,
    state: int | None = None,
    cancel_callback: str = "cancel",
) -> Message | None:
    """
    Универсальный запрос ввода:
    1) скрывает reply-клавиатуру,
    2) показывает prompt,
    3) добавляет inline-кнопку "Отмена".
    """
    context.user_data["expecting_text_input"] = True
    if state is not None:
        context.user_data["input_state"] = state

    anchor = update.effective_message or (update.callback_query.message if update.callback_query else None)
    if not anchor:
        return None

    hide_msg = await anchor.reply_text("\u200b", reply_markup=REMOVE_KEYBOARD)
    try:
        await hide_msg.delete()
    except Exception:
        logger.debug("Не удалось удалить техническое сообщение скрытия клавиатуры", exc_info=True)

    return await anchor.reply_text(prompt, reply_markup=get_cancel_keyboard(cancel_callback))


async def handle_unexpected_menu_button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """
    Перехватывает случайное нажатие кнопки главного меню во время ввода.
    Сохраняет текущий state и просит отменить действие через inline-кнопку.
    """
    message = update.effective_message
    if not message or not message.text:
        return context.user_data.get("input_state", ConversationHandler.END)

    if message.text not in MAIN_MENU_BUTTONS:
        return context.user_data.get("input_state", ConversationHandler.END)

    await message.reply_text(
        "⚠️ Сейчас ожидается ввод текста.\nНажми «❌ Отмена», чтобы прервать действие.",
        reply_markup=get_cancel_keyboard(),
    )
    return context.user_data.get("input_state", ConversationHandler.END)


async def universal_cancel_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Универсальная отмена сценария с очисткой состояния и возвратом главного меню."""
    if update.callback_query:
        try:
            await update.callback_query.answer("Действие отменено", show_alert=False)
            await update.callback_query.edit_message_text("❌ Действие отменено.")
        except Exception:
            logger.debug("Не удалось обновить callback-сообщение при отмене", exc_info=True)

    context.user_data.clear()
    anchor = update.effective_message or (update.callback_query.message if update.callback_query else None)
    if anchor:
        await anchor.reply_text("Главное меню:", reply_markup=get_main_reply_keyboard())
    return ConversationHandler.END
