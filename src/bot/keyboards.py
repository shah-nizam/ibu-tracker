from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def metric_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Glucose", callback_data="metric:glucose")],
            [InlineKeyboardButton("Blood Pressure", callback_data="metric:bp")],
            [InlineKeyboardButton("Insulin", callback_data="metric:insulin")],
        ]
    )
