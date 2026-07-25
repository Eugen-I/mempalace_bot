from pathlib import Path

from behave import given, then, when


@given("the project root is available")
def step_project_root_available(context) -> None:
    context.project_root = Path(__file__).resolve().parents[2]


@when("I check the core files")
def step_check_core_files(context) -> None:
    context.files = {
        "main.py": (context.project_root / "main.py").exists(),
        "README.md": (context.project_root / "README.md").exists(),
        "AGENTS.md": (context.project_root / "AGENTS.md").exists(),
    }


@then("main.py should exist")
def step_main_exists(context) -> None:
    assert context.files["main.py"] is True


@then("README.md should exist")
def step_readme_exists(context) -> None:
    assert context.files["README.md"] is True


@then("AGENTS.md should exist")
def step_agents_exists(context) -> None:
    assert context.files["AGENTS.md"] is True
