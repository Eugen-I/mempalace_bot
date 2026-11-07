"""services/palace_visualizer.py
Генератор интерактивной визуальной HTML-карты Дворца памяти.

Создает автономный HTML5-виджет с визуализацией:
- Крыльев (узлы-хабы)
- Комнат (листовые узлы с количеством записей)
- Туннелей (межкомнатные связи с метками причин)
- Поиском, зумом, панорамированием и детальной панелью.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("PalaceVisualizer")

PALACE_MAP_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{palace_name} — Интерактивная карта</title>
  <style>
    :root {{
      --bg: #0d1117;
      --panel-bg: rgba(22, 27, 34, 0.85);
      --text: #e6edf3;
      --text-muted: #8b949e;
      --border: #30363d;
      --accent: #58a6ff;
      --tunnel: #f0883e;
      --wing: #bc8cff;
      --room: #3fb950;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                   Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      overflow: hidden;
      width: 100vw;
      height: 100vh;
    }}
    #header {{
      position: absolute;
      top: 16px;
      left: 16px;
      z-index: 10;
      background: var(--panel-bg);
      backdrop-filter: blur(10px);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px 20px;
      display: flex;
      gap: 16px;
      align-items: center;
      box-shadow: 0 8px 24px rgba(0,0,0,0.5);
    }}
    h1 {{ font-size: 16px; font-weight: 600; display: flex; align-items: center; gap: 8px; }}
    .badge {{
      background: rgba(88, 166, 255, 0.15);
      color: var(--accent);
      padding: 2px 8px;
      border-radius: 20px;
      font-size: 12px;
    }}
    #search {{
      background: #161b22;
      border: 1px solid var(--border);
      color: var(--text);
      padding: 6px 12px;
      border-radius: 6px;
      outline: none;
      font-size: 13px;
      width: 200px;
    }}
    #search:focus {{ border-color: var(--accent); }}
    #controls {{
      position: absolute;
      bottom: 20px;
      right: 20px;
      z-index: 10;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}
    .btn {{
      background: var(--panel-bg);
      backdrop-filter: blur(8px);
      border: 1px solid var(--border);
      color: var(--text);
      width: 36px;
      height: 36px;
      border-radius: 8px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 18px;
      transition: background 0.2s, border-color 0.2s;
    }}
    .btn:hover {{ background: #21262d; border-color: var(--accent); }}
    #info-panel {{
      position: absolute;
      top: 16px;
      right: 16px;
      width: 280px;
      background: var(--panel-bg);
      backdrop-filter: blur(10px);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px;
      z-index: 10;
      display: none;
      box-shadow: 0 8px 24px rgba(0,0,0,0.5);
    }}
    #info-title {{ font-size: 15px; font-weight: 600; margin-bottom: 8px; }}
    #info-desc {{ font-size: 13px; color: var(--text-muted); line-height: 1.4; }}
    #graph-canvas {{ width: 100%; height: 100%; display: block; }}
  </style>
</head>
<body>
  <div id="header">
    <h1>🏰 {palace_name}</h1>
    <span class="badge">Крыльев: {wing_count}</span>
    <span class="badge">Комнат: {room_count}</span>
    <span class="badge">Туннелей: {tunnel_count}</span>
    <input type="text" id="search" placeholder="🔍 Найти комнату или крыло..." />
  </div>

  <div id="info-panel">
    <div id="info-title"></div>
    <div id="info-desc"></div>
  </div>

  <div id="controls">
    <button class="btn" id="zoom-in" title="Приблизить">+</button>
    <button class="btn" id="zoom-out" title="Отдалить">−</button>
    <button class="btn" id="reset-view" title="Сбросить масштаб">⟲</button>
  </div>

  <canvas id="graph-canvas"></canvas>

  <script>
    const data = {graph_data_json};

    const canvas = document.getElementById('graph-canvas');
    const ctx = canvas.getContext('2d');
    const searchInput = document.getElementById('search');
    const infoPanel = document.getElementById('info-panel');
    const infoTitle = document.getElementById('info-title');
    const infoDesc = document.getElementById('info-desc');

    let width, height;
    function resize() {{
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    }}
    window.addEventListener('resize', resize);
    resize();

    let transform = {{ x: width / 2, y: height / 2, k: 0.85 }};
    let isDragging = false;
    let dragStart = {{ x: 0, y: 0 }};
    let hoveredNode = null;
    let searchQuery = '';

    // Initialize node positions in orbital layout
    const nodes = data.nodes;
    const links = data.links;

    const wingNodes = nodes.filter(n => n.type === 'wing');
    const wingRadius = Math.min(width, height) * 0.32;

    wingNodes.forEach((w, idx) => {{
      const angle = (idx / wingNodes.length) * 2 * Math.PI;
      w.x = Math.cos(angle) * wingRadius;
      w.y = Math.sin(angle) * wingRadius;
      w.vx = 0; w.vy = 0;

      const rooms = nodes.filter(r => r.type === 'room' && r.wing === w.id);
      const roomRadius = 70 + rooms.length * 5;
      rooms.forEach((r, rIdx) => {{
        const rAngle = (rIdx / (rooms.length || 1)) * 2 * Math.PI;
        r.x = w.x + Math.cos(rAngle) * roomRadius;
        r.y = w.y + Math.sin(rAngle) * roomRadius;
        r.vx = 0; r.vy = 0;
      }});
    }});

    function draw() {{
      ctx.clearRect(0, 0, width, height);
      ctx.save();
      ctx.translate(transform.x, transform.y);
      ctx.scale(transform.k, transform.k);

      // 1. Draw Links
      links.forEach(link => {{
        const source = nodes.find(n => n.id === link.source);
        const target = nodes.find(n => n.id === link.target);
        if (!source || !target) return;

        ctx.beginPath();
        ctx.moveTo(source.x, source.y);
        ctx.lineTo(target.x, target.y);

        if (link.type === 'tunnel') {{
          ctx.strokeStyle = '#f0883e';
          ctx.lineWidth = 2.5;
          ctx.setLineDash([6, 6]);
        }} else {{
          ctx.strokeStyle = 'rgba(88, 166, 255, 0.25)';
          ctx.lineWidth = 1.2;
          ctx.setLineDash([]);
        }}
        ctx.stroke();
      }});
      ctx.setLineDash([]);

      // 2. Draw Nodes
      nodes.forEach(node => {{
        const isHovered = hoveredNode === node;
        const isMatch = searchQuery && node.label.toLowerCase().includes(searchQuery);

        ctx.beginPath();
        if (node.type === 'wing') {{
          ctx.arc(node.x, node.y, 22, 0, 2 * Math.PI);
          ctx.fillStyle = isMatch ? '#f1e05a' : (isHovered ? '#d2a8ff' : '#bc8cff');
          ctx.fill();
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = isHovered ? 3 : 1.5;
          ctx.stroke();
        }} else {{
          ctx.arc(node.x, node.y, 10 + Math.min(node.records || 1, 10), 0, 2 * Math.PI);
          ctx.fillStyle = isMatch ? '#f1e05a' : (isHovered ? '#7ee787' : '#3fb950');
          ctx.fill();
          ctx.strokeStyle = isHovered ? '#ffffff' : 'rgba(255,255,255,0.3)';
          ctx.lineWidth = isHovered ? 2 : 1;
          ctx.stroke();
        }}

        // Label
        ctx.fillStyle = isMatch ? '#f1e05a' : '#e6edf3';
        ctx.font = node.type === 'wing' ? 'bold 13px sans-serif' : '11px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(node.label, node.x, node.y + (node.type === 'wing' ? 36 : 24));
      }});

      ctx.restore();
      requestAnimationFrame(draw);
    }}

    // Mouse & Touch Interaction
    canvas.addEventListener('mousedown', e => {{
      isDragging = true;
      dragStart = {{ x: e.clientX - transform.x, y: e.clientY - transform.y }};
    }});

    window.addEventListener('mouseup', () => isDragging = false);

    canvas.addEventListener('mousemove', e => {{
      if (isDragging) {{
        transform.x = e.clientX - dragStart.x;
        transform.y = e.clientY - dragStart.y;
      }}

      // Find hovered node
      const mx = (e.clientX - transform.x) / transform.k;
      const my = (e.clientY - transform.y) / transform.k;

      hoveredNode = nodes.find(n => {{
        const r = n.type === 'wing' ? 24 : 16;
        const dx = n.x - mx;
        const dy = n.y - my;
        return (dx * dx + dy * dy) <= r * r;
      }}) || null;

      if (hoveredNode) {{
        canvas.style.cursor = 'pointer';
        infoPanel.style.display = 'block';
        if (hoveredNode.type === 'wing') {{
          infoTitle.textContent = '🕸️ Крыло: ' + hoveredNode.label;
          infoDesc.textContent = `Записей в крыле: ${{hoveredNode.records || 0}}`;
        }} else {{
          infoTitle.textContent = '📁 Комната: ' + hoveredNode.label;
          const recCount = hoveredNode.records || 0;
          infoDesc.textContent = `Крыло: ${{hoveredNode.wing}}\\nЗаписей: ${{recCount}}`;
        }}
      }} else {{
        canvas.style.cursor = isDragging ? 'grabbing' : 'grab';
        if (!searchQuery) infoPanel.style.display = 'none';
      }}
    }});

    canvas.addEventListener('wheel', e => {{
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
      transform.k = Math.max(0.2, Math.min(3.0, transform.k * zoomFactor));
    }});

    document.getElementById('zoom-in').onclick = () => {{
      transform.k = Math.min(3.0, transform.k * 1.2);
    }};
    document.getElementById('zoom-out').onclick = () => {{
      transform.k = Math.max(0.2, transform.k / 1.2);
    }};
    document.getElementById('reset-view').onclick = () => {{
      transform = {{ x: width / 2, y: height / 2, k: 0.85 }};
      searchInput.value = '';
      searchQuery = '';
      infoPanel.style.display = 'none';
    }};

    searchInput.addEventListener('input', e => {{
      searchQuery = e.target.value.trim().toLowerCase();
      if (searchQuery) {{
        const found = nodes.find(n => n.label.toLowerCase().includes(searchQuery));
        if (found) {{
          transform.x = width / 2 - found.x * transform.k;
          transform.y = height / 2 - found.y * transform.k;
        }}
      }}
    }});

    draw();
  </script>
</body>
</html>
"""


def generate_palace_map_html(
    wings: dict[str, int] | list[str],
    rooms_by_wing: dict[str, dict[str, int]],
    tunnels: list[dict[str, Any]],
    palace_name: str = "Дворец памяти",
) -> str:
    """Генерирует автономную интерактивную HTML-карту Дворца памяти."""
    nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []

    # 1. Добавляем узлы крыльев
    wing_dict = wings if isinstance(wings, dict) else {w: 0 for w in wings}
    for wing_name, wing_records in wing_dict.items():
        nodes.append({
            "id": f"wing_{wing_name}",
            "label": wing_name,
            "type": "wing",
            "records": wing_records,
        })

    # 2. Добавляем узлы комнат и связи крыло -> комната
    total_rooms = 0
    for wing_name, rooms in rooms_by_wing.items():
        for room_name, room_cnt in rooms.items():
            total_rooms += 1
            room_id = f"room_{wing_name}_{room_name}"
            nodes.append({
                "id": room_id,
                "label": room_name,
                "type": "room",
                "wing": f"wing_{wing_name}",
                "records": room_cnt,
            })
            links.append({
                "source": f"wing_{wing_name}",
                "target": room_id,
                "type": "containment",
            })

    # 3. Добавляем связи туннелей
    total_tunnels = 0
    for t in tunnels:
        src = t.get("source", {})
        dst = t.get("target", {})
        src_id = f"room_{src.get('wing', '')}_{src.get('room', '')}"
        dst_id = f"room_{dst.get('wing', '')}_{dst.get('room', '')}"
        links.append({
            "source": src_id,
            "target": dst_id,
            "type": "tunnel",
            "label": t.get("label", ""),
        })
        total_tunnels += 1

    graph_data_json = json.dumps({"nodes": nodes, "links": links}, ensure_ascii=False)

    return PALACE_MAP_TEMPLATE.format(
        palace_name=palace_name,
        wing_count=len(wing_dict),
        room_count=total_rooms,
        tunnel_count=total_tunnels,
        graph_data_json=graph_data_json,
    )
