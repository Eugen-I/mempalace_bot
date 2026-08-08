"""Окружение behave: разрешаем тестового пользователя для allowed_callback."""
import os
import tempfile

TEST_UID = 424242


def before_all(context):
    import config

    config.ALLOWED_IDS = {TEST_UID}


def before_scenario(context, scenario):
    if "agent" in scenario.effective_tags:
        from services import agent_settings

        context.agent_settings_module = agent_settings
        context.agent_settings_orig_data_dir = agent_settings.DATA_DIR
        agent_settings.DATA_DIR = tempfile.mkdtemp(prefix="agent_bdd_")
        agent_settings.AGENT_SETTINGS_FILE = os.path.join(
            agent_settings.DATA_DIR, "agent_settings.json",
        )


def after_scenario(context, scenario):
    if "agent" in scenario.effective_tags:
        mod = context.agent_settings_module
        mod.DATA_DIR = context.agent_settings_orig_data_dir
        mod.AGENT_SETTINGS_FILE = os.path.join(
            mod.DATA_DIR, "agent_settings.json",
        )
