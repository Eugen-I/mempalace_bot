"""services/copilot_mindmap.py — Интерактивная ментальная карта фотопроекта (MP-3).

Генерирует автономный HTML5 Canvas force-directed граф (ментальную карту) фотопроекта:
- Центральный узел: Тема / Название проекта
- Узлы локации: Чертог и крыло Дворца Памяти
- Узлы стиля: Стилистическая триада
- Узлы снаряжения: Fujifilm X-T4, оптика, фильтры, свет
- Узлы механик: Фотомеханики, выдержка, физика съемки
- Узлы референсов: Художники и мастера
- Узлы резонансов: Ассоциативные мысли из Apple Notes
- Полная автономность: работает локально по file:// без CDN и интернета, 60 FPS Canvas.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from typing import TYPE_CHECKING, Any

from config import DATA_DIR
from services.copilot_kg_linker import extract_project_kg_entities, link_project_to_palace_kg
from services.text_formatter import safe_html_format

if TYPE_CHECKING:
    from services.copilot_session import CopilotSession  # noqa: F401

logger = logging.getLogger("CopilotMindmap")

MINDMAP_DIR = os.path.join(DATA_DIR, "copilot_mindmaps")
os.makedirs(MINDMAP_DIR, exist_ok=True)

# Палитра цветовой схемы графа
NODE_COLORS = {
    "project": "#58a6ff",    # Акцентный синий
    "palace": "#f0883e",     # Оранжево-золотой
    "style": "#bc8cff",      # Фиолетовый
    "gear": "#39d353",       # Изумрудный / бирюзовый
    "mechanic": "#2ea043",   # Зеленый
    "reference": "#f85149",  # Коралловый
    "resonance": "#79c0ff",  # Небесно-голубой
}

MINDMAP_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <title>{project_title_esc} — Ментальная карта концепта</title>
  <style>
    :root {{
      --bg: #0d1117;
      --panel-bg: rgba(22, 27, 34, 0.92);
      --panel-border: rgba(48, 54, 61, 0.8);
      --text: #e6edf3;
      --text-muted: #8b949e;
      --accent: #58a6ff;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html, body {{
      width: 100%;
      height: 100%;
      overflow: hidden;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      user-select: none;
      -webkit-user-select: none;
    }}
    #canvas {{
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      cursor: grab;
    }}
    #canvas:active {{ cursor: grabbing; }}
    .header {{
      position: absolute;
      top: 16px;
      left: 16px;
      z-index: 10;
      background: var(--panel-bg);
      border: 1px solid var(--panel-border);
      padding: 12px 18px;
      border-radius: 12px;
      backdrop-filter: blur(8px);
      box-shadow: 0 8px 24px rgba(0,0,0,0.4);
    }}
    .header h1 {{
      font-size: 16px;
      font-weight: 600;
      color: var(--accent);
      margin-bottom: 4px;
    }}
    .header p {{
      font-size: 12px;
      color: var(--text-muted);
    }}
    .info-card {{
      position: absolute;
      bottom: 20px;
      right: 20px;
      z-index: 10;
      width: 320px;
      max-width: calc(100% - 40px);
      background: var(--panel-bg);
      border: 1px solid var(--panel-border);
      padding: 14px 18px;
      border-radius: 12px;
      display: none;
      backdrop-filter: blur(8px);
      box-shadow: 0 8px 24px rgba(0,0,0,0.5);
    }}
    .info-card h3 {{
      font-size: 14px;
      color: var(--accent);
      margin-bottom: 6px;
    }}
    .info-card .category {{
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--text-muted);
      margin-bottom: 8px;
    }}
    .info-card p {{
      font-size: 12px;
      line-height: 1.4;
      color: var(--text);
    }}
    .legend {{
      position: absolute;
      bottom: 20px;
      left: 20px;
      z-index: 10;
      background: var(--panel-bg);
      border: 1px solid var(--panel-border);
      padding: 10px 14px;
      border-radius: 10px;
      font-size: 11px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    .legend-item {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .legend-color {{
      width: 10px;
      height: 10px;
      border-radius: 50%;
    }}
  </style>
</head>
<body>
  <div class="header">
    <h1>{project_title_esc}</h1>
    <p>Ментальная карта концепта • {nodes_count} узлов, {links_count} связей</p>
  </div>

  <div class="legend">
    <div class="legend-item"><div class="legend-color" style="background:#58a6ff;"></div>
      Проект</div>
    <div class="legend-item"><div class="legend-color" style="background:#f0883e;"></div>
      Дворец</div>
    <div class="legend-item"><div class="legend-color" style="background:#bc8cff;"></div>
      Стили</div>
    <div class="legend-item"><div class="legend-color" style="background:#39d353;"></div>
      Техника</div>
    <div class="legend-item"><div class="legend-color" style="background:#2ea043;"></div>
      Механики</div>
    <div class="legend-item"><div class="legend-color" style="background:#f85149;"></div>
      Ссылки</div>
    <div class="legend-item"><div class="legend-color" style="background:#79c0ff;"></div>
      Резонанс</div>
  </div>

  <div id="infoCard" class="info-card">
    <div id="infoCategory" class="category">Категория</div>
    <h3 id="infoTitle">Заголовок узла</h3>
    <p id="infoDesc">Описание связи</p>
  </div>

  <canvas id="canvas"></canvas>

  <script>
    const DATA = {graph_data_json};

    const canvas = document.getElementById('canvas');
    const ctx = canvas.getContext('2d');
    const infoCard = document.getElementById('infoCard');
    const infoTitle = document.getElementById('infoTitle');
    const infoCategory = document.getElementById('infoCategory');
    const infoDesc = document.getElementById('infoDesc');

    let width = 0, height = 0;
    let panX = 0, panY = 0;
    let zoom = 1.0;
    let isDragging = false;
    let startX = 0, startY = 0;
    let hoveredNode = null;
    let selectedNode = null;

    function resize() {{
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
      if (panX === 0 && panY === 0) {{
        panX = width / 2;
        panY = height / 2;
      }}
    }}
    window.addEventListener('resize', resize);
    resize();

    // Инициализация координат узлов по кругу
    const nodes = DATA.nodes;
    const links = DATA.links;
    const nodeMap = {{}};

    nodes.forEach((n, idx) => {{
      nodeMap[n.id] = n;
      if (n.type === 'project') {{
        n.x = 0;
        n.y = 0;
      }} else {{
        const angle = (idx / nodes.length) * Math.PI * 2;
        const radius = n.type === 'palace' ? 120 : (160 + (idx % 3) * 40);
        n.x = Math.cos(angle) * radius;
        n.y = Math.sin(angle) * radius;
      }}
      n.vx = 0;
      n.vy = 0;
    }});

    // Простая симуляция сил
    function simulate() {{
      for (let i = 0; i < nodes.length; i++) {{
        const n1 = nodes[i];
        for (let j = i + 1; j < nodes.length; j++) {{
          const n2 = nodes[j];
          const dx = n2.x - n1.x;
          const dy = n2.y - n1.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          if (dist < 180) {{
            const force = (180 - dist) / dist * 0.05;
            n1.vx -= dx * force;
            n1.vy -= dy * force;
            n2.vx += dx * force;
            n2.vy += dy * force;
          }}
        }}
      }}

      links.forEach(l => {{
        const s = nodeMap[l.source];
        const t = nodeMap[l.target];
        if (s && t) {{
          const dx = t.x - s.x;
          const dy = t.y - s.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const targetDist = 130;
          const force = (dist - targetDist) * 0.015;
          s.vx += (dx / dist) * force;
          s.vy += (dy / dist) * force;
          t.vx -= (dx / dist) * force;
          t.vy -= (dy / dist) * force;
        }}
      }});

      nodes.forEach(n => {{
        if (n.type === 'project') {{
          n.vx *= 0.5;
          n.vy *= 0.5;
        }} else {{
          n.vx *= 0.88;
          n.vy *= 0.88;
          n.x += n.vx;
          n.y += n.vy;
        }}
      }});
    }}

    function render() {{
      simulate();
      ctx.clearRect(0, 0, width, height);

      ctx.save();
      ctx.translate(panX, panY);
      ctx.scale(zoom, zoom);

      // Отрисовка связей
      links.forEach(l => {{
        const s = nodeMap[l.source];
        const t = nodeMap[l.target];
        if (!s || !t) return;

        const isHighlighted = (hoveredNode && (hoveredNode.id === s.id || hoveredNode.id === t.id));
        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.lineTo(t.x, t.y);
        ctx.strokeStyle = isHighlighted ? '#58a6ff' : 'rgba(48, 54, 61, 0.6)';
        ctx.lineWidth = isHighlighted ? 2.5 : 1.2;
        ctx.stroke();

        // Подпись ребра при наведении
        if (isHighlighted && l.label) {{
          const midX = (s.x + t.x) / 2;
          const midY = (s.y + t.y) / 2;
          ctx.font = '10px sans-serif';
          ctx.fillStyle = '#8b949e';
          ctx.fillText(l.label, midX + 6, midY - 6);
        }}
      }});

      // Отрисовка узлов
      nodes.forEach(n => {{
        const isHovered = hoveredNode && hoveredNode.id === n.id;
        const radius = n.size || 14;

        // Внешнее свечение
        if (isHovered) {{
          ctx.beginPath();
          ctx.arc(n.x, n.y, radius + 6, 0, Math.PI * 2);
          ctx.fillStyle = 'rgba(88, 166, 255, 0.25)';
          ctx.fill();
        }}

        ctx.beginPath();
        ctx.arc(n.x, n.y, radius, 0, Math.PI * 2);
        ctx.fillStyle = n.color || '#58a6ff';
        ctx.fill();
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = isHovered ? 2.5 : 1.0;
        ctx.stroke();

        // Метка узла
        ctx.font = (n.type === 'project' ? 'bold 13px' : '11px') + ' -apple-system, sans-serif';
        ctx.fillStyle = '#e6edf3';
        ctx.textAlign = 'center';
        ctx.fillText(n.label, n.x, n.y + radius + 15);
      }});

      ctx.restore();
      requestAnimationFrame(render);
    }}
    requestAnimationFrame(render);

    // Взаимодействие (Drag, Zoom, Hover)
    canvas.addEventListener('mousedown', e => {{
      isDragging = true;
      startX = e.clientX - panX;
      startY = e.clientY - panY;
    }});
    window.addEventListener('mouseup', () => isDragging = false);

    canvas.addEventListener('mousemove', e => {{
      if (isDragging) {{
        panX = e.clientX - startX;
        panY = e.clientY - startY;
      }}

      const mouseX = (e.clientX - panX) / zoom;
      const mouseY = (e.clientY - panY) / zoom;

      let found = null;
      for (const n of nodes) {{
        const dx = n.x - mouseX;
        const dy = n.y - mouseY;
        if (Math.sqrt(dx * dx + dy * dy) <= (n.size || 14) + 6) {{
          found = n;
          break;
        }}
      }}

      hoveredNode = found;
      if (found) {{
        infoTitle.textContent = found.label;
        infoCategory.textContent = found.category || found.type;
        infoDesc.textContent = found.desc || 'Связанный узел проекта';
        infoCard.style.display = 'block';
      }} else if (!selectedNode) {{
        infoCard.style.display = 'none';
      }}
    }});

    canvas.addEventListener('wheel', e => {{
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
      zoom = Math.max(0.4, Math.min(2.5, zoom * zoomFactor));
    }}, {{ passive: false }});
  </script>
</body>
</html>
"""


def build_project_mindmap_data(session_or_concept: Any) -> dict[str, Any]:
    """Формирует граф узлов и связей для ментальной карты фотопроекта."""
    entities = extract_project_kg_entities(session_or_concept)
    kg_link = link_project_to_palace_kg(session_or_concept)

    subject = kg_link.get("project_title", "Фотопроект")

    nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    seen_nodes: set[str] = set()

    def add_node(node_id: str, label: str, node_type: str, category: str, desc: str, size: int):
        clean_id = re.sub(r"[^a-zA-Z0-9_\u0400-\u04FF]", "_", node_id)
        if clean_id not in seen_nodes:
            seen_nodes.add(clean_id)
            nodes.append({
                "id": clean_id,
                "label": label[:35],
                "type": node_type,
                "category": category,
                "desc": desc,
                "color": NODE_COLORS.get(node_type, "#58a6ff"),
                "size": size,
            })
        return clean_id

    # 1. Центральный узел: Проект
    root_id = add_node(
        node_id="root_project",
        label=subject,
        node_type="project",
        category="Фотопроект",
        desc=f"Главная тема и концепция: {subject}",
        size=26,
    )

    # 2. Узлы Дворца Памяти
    wing_name = kg_link.get("wing_display", "🎨 Творчество")
    room_name = kg_link.get("room", "Фотолаборатория")

    wing_id = add_node(
        node_id=f"wing_{kg_link.get('wing_key', 'creative')}",
        label=wing_name,
        node_type="palace",
        category="Крыло Дворца",
        desc=f"Крыло памяти: {wing_name}",
        size=18,
    )
    links.append({"source": root_id, "target": wing_id, "label": "крыло"})

    room_id = add_node(
        node_id=f"room_{room_name}",
        label=room_name,
        node_type="palace",
        category="Чертог Дворца",
        desc=f"Тематический зал: {room_name}",
        size=16,
    )
    links.append({"source": wing_id, "target": room_id, "label": "комната"})
    links.append({"source": root_id, "target": room_id, "label": "локация"})

    # 3. Стили
    for idx, st in enumerate(entities["styles"][:4]):
        s_id = add_node(
            node_id=f"style_{idx}_{st}",
            label=st,
            node_type="style",
            category="Стиль",
            desc=f"Стилистический элемент триады: {st}",
            size=14,
        )
        links.append({"source": root_id, "target": s_id, "label": "стиль"})

    # 4. Снаряжение и оптика
    for idx, gear in enumerate(entities["gear"][:4]):
        g_id = add_node(
            node_id=f"gear_{idx}_{gear}",
            label=gear,
            node_type="gear",
            category="Техника",
            desc=f"Оптика и оснащение: {gear}",
            size=14,
        )
        links.append({"source": root_id, "target": g_id, "label": "техника"})

    # 5. Фотомеханики и физика
    for idx, mech in enumerate(entities["mechanics"][:3]):
        m_id = add_node(
            node_id=f"mech_{idx}_{mech}",
            label=mech,
            node_type="mechanic",
            category="Механика съемки",
            desc=f"Прием и физика движения: {mech}",
            size=13,
        )
        links.append({"source": root_id, "target": m_id, "label": "прием"})

    # 6. Художники и референсы
    for idx, ref in enumerate(entities["references"][:3]):
        r_id = add_node(
            node_id=f"ref_{idx}_{ref}",
            label=ref,
            node_type="reference",
            category="Референс",
            desc=f"Вдохновение и авторский язык: {ref}",
            size=14,
        )
        links.append({"source": root_id, "target": r_id, "label": "отсылка"})

    # 7. Ассоциативные резонансы из Дворца Памяти (если кэшированы)
    resonances: list[dict[str, Any]] = []
    tp = getattr(session_or_concept, "tech_preferences", None)
    if isinstance(tp, dict):
        resonances = tp.get("palace_resonances", []) or []

    for idx, res in enumerate(resonances[:3]):
        res_title = res.get("title", f"Мысль #{idx+1}")
        res_id = add_node(
            node_id=f"res_{idx}_{res_title}",
            label=res_title,
            node_type="resonance",
            category="Резонанс",
            desc=res.get("snippet", "Заметка из личной базы знаний")[:100],
            size=13,
        )
        links.append({"source": room_id, "target": res_id, "label": "заметка"})

    return {
        "project_title": subject,
        "nodes": nodes,
        "links": links,
    }


def generate_project_mindmap_html(session_or_concept: Any) -> str:
    """Генерирует готовый автономный HTML-документ интерактивной ментальной карты."""
    data = build_project_mindmap_data(session_or_concept)
    title = data["project_title"]

    # Экранирование заголовка и безопасный JSON без открывающих тегов для HTML
    title_esc = safe_html_format(title)
    graph_json = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")

    return MINDMAP_HTML_TEMPLATE.format(
        project_title=title,
        project_title_esc=title_esc,
        nodes_count=len(data["nodes"]),
        links_count=len(data["links"]),
        graph_data_json=graph_json,
    )


def export_project_mindmap_file(session_or_concept: Any, output_dir: str | None = None) -> str:
    """Сохраняет HTML ментальной карты в файл и возвращает абсолютный путь."""
    target_dir = output_dir or MINDMAP_DIR
    os.makedirs(target_dir, exist_ok=True)

    data = build_project_mindmap_data(session_or_concept)
    raw_title = data["project_title"]
    safe_slug = re.sub(r"[^\w\s-]", "", raw_title).strip().lower()
    safe_slug = re.sub(r"[-\s]+", "_", safe_slug)[:40] or "project"

    filename = f"mindmap_{safe_slug}.html"
    file_path = os.path.join(target_dir, filename)

    html_content = generate_project_mindmap_html(session_or_concept)

    with tempfile.NamedTemporaryFile("w", dir=target_dir, delete=False, encoding="utf-8") as tmp:
        tmp.write(html_content)
        tmp_name = tmp.name

    os.replace(tmp_name, file_path)
    logger.info("[MINDMAP] Карта сохранена: %s", file_path)
    return file_path


def format_mindmap_card(session_or_concept: Any, file_name: str | None = None) -> str:
    """Форматирует информационную карточку генерации ментальной карты для Telegram UI."""
    data = build_project_mindmap_data(session_or_concept)
    title = safe_html_format(data["project_title"])
    n_count = len(data["nodes"])
    l_count = len(data["links"])
    fname = safe_html_format(file_name or f"mindmap_{title[:20]}.html")

    lines = [
        f"🗺 <b>Ментальная карта концепта «{title}»</b>",
        "",
        "📊 <b>Параметры графа визуализации:</b>",
        f"  • Узлов концепта: <b>{n_count}</b>",
        f"  • Семантических связей: <b>{l_count}</b>",
        f"  • Файл карты: <code>{fname}</code>",
        "",
        (
            "<blockquote>Автономный интерактивный граф на Canvas 60 FPS. "
            "Открывается в Chrome или Safari прямо на Mac, поддерживает зум, "
            "перетаскивание узлов и подсветку связей.</blockquote>"
        ),
    ]
    return "\n".join(lines)
