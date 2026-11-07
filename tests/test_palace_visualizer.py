"""tests/test_palace_visualizer.py
Тесты генератора интерактивной карты Дворца памяти.
"""

from services.palace_visualizer import generate_palace_map_html


def test_generate_palace_map_html():
    wings = {"Наука": 42, "Искусство": 15}
    rooms = {
        "Наука": {"Физика": 20, "Математика": 22},
        "Искусство": {"Живопись": 15},
    }
    tunnels = [
        {
            "id": "t1",
            "source": {"wing": "Наука", "room": "Математика"},
            "target": {"wing": "Искусство", "room": "Живопись"},
            "label": "Геометрия в композиции",
        }
    ]

    html = generate_palace_map_html(wings, rooms, tunnels, palace_name="Тестовый Дворец")

    assert "<!DOCTYPE html>" in html
    assert "Тестовый Дворец" in html
    assert "Крыльев: 2" in html
    assert "Комнат: 3" in html
    assert "Туннелей: 1" in html
    assert "Геометрия в композиции" in html
    assert "graph-canvas" in html
