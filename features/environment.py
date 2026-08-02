"""Окружение behave: разрешаем тестового пользователя для allowed_callback."""

TEST_UID = 424242


def before_all(context):
    import config

    config.ALLOWED_IDS = {TEST_UID}
