"""services/palace_visualizer.py
Генератор автономной интерактивной карты-графа знаний «Дворец памяти».

Включает 3 слоя:
- Слой B: «Созвездия» (force-directed граф на 2D Canvas, 60 fps, spatial grid 64px, LOD 1-4,
  раскрытие ящиков на графе и интерактивный список заметок)
- Слой A: «Атлас» (Sunburst миникарта в углу 200x200 с адаптивным мобильным режимом)
- Автономный, без CDN, без внешних скриптов, работает при двойном клике и в Telegram WebView.
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
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <title>{palace_name} — Граф знаний «Созвездия»</title>
  <style>
    :root {{
      --bg: #0d1117;
      --panel-bg: rgba(22, 27, 34, 0.88);
      --panel-border: rgba(48, 54, 61, 0.8);
      --text: #e6edf3;
      --text-muted: #8b949e;
      --accent: #58a6ff;
      --tunnel: #f0883e;
      --danger: #f85149;
      --halo: rgba(13, 17, 23, 0.85);
      --card-bg: rgba(30, 41, 59, 0.7);
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
    #main-canvas {{
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      display: block;
      cursor: grab;
    }}
    #main-canvas.grabbing {{ cursor: grabbing; }}

    /* Хедер (верхний левый угол) */
    #header {{
      position: absolute;
      top: calc(16px + env(safe-area-inset-top));
      left: calc(16px + env(safe-area-inset-left));
      z-index: 20;
      background: var(--panel-bg);
      backdrop-filter: blur(14px);
      -webkit-backdrop-filter: blur(14px);
      border: 1px solid var(--panel-border);
      border-radius: 12px;
      padding: 10px 16px;
      display: flex;
      gap: 12px;
      align-items: center;
      box-shadow: 0 8px 24px rgba(0,0,0,0.5);
    }}
    h1 {{
      font-size: 15px;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 8px;
      white-space: nowrap;
    }}
    .badge {{
      background: rgba(88, 166, 255, 0.15);
      color: var(--accent);
      padding: 3px 8px;
      border-radius: 12px;
      font-size: 11px;
      font-weight: 500;
    }}
    #search-box {{
      position: relative;
      display: flex;
      align-items: center;
    }}
    #search-input {{
      background: rgba(13, 17, 23, 0.8);
      border: 1px solid var(--panel-border);
      color: var(--text);
      padding: 6px 12px;
      border-radius: 8px;
      font-size: 12px;
      outline: none;
      width: 180px;
      transition: all 0.2s;
    }}
    #search-input:focus {{
      border-color: var(--accent);
      width: 240px;
      box-shadow: 0 0 10px rgba(88, 166, 255, 0.3);
    }}

    /* Панель управления (правый нижний угол) */
    #controls {{
      position: absolute;
      bottom: calc(20px + env(safe-area-inset-bottom));
      right: calc(20px + env(safe-area-inset-right));
      z-index: 20;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}
    .btn {{
      background: var(--panel-bg);
      backdrop-filter: blur(10px);
      -webkit-backdrop-filter: blur(10px);
      border: 1px solid var(--panel-border);
      color: var(--text);
      min-width: 36px;
      height: 36px;
      padding: 0 10px;
      border-radius: 8px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 14px;
      font-weight: 500;
      box-shadow: 0 4px 12px rgba(0,0,0,0.4);
      transition: all 0.2s;
    }}
    .btn:hover {{
      background: rgba(48, 54, 61, 0.9);
      border-color: var(--accent);
      transform: translateY(-1px);
    }}
    .btn.active {{
      background: rgba(56, 189, 248, 0.25) !important;
      border-color: #38bdf8 !important;
      color: #38bdf8 !important;
      box-shadow: 0 0 12px rgba(56, 189, 248, 0.35);
    }}

    /* Панель инспектора (десктоп: справа, мобилка: bottom-sheet) */
    #inspector {{
      position: absolute;
      top: calc(16px + env(safe-area-inset-top));
      right: calc(16px + env(safe-area-inset-right));
      width: 340px;
      max-height: calc(100vh - 40px - env(safe-area-inset-top) - env(safe-area-inset-bottom));
      background: var(--panel-bg);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid var(--panel-border);
      border-radius: 14px;
      padding: 16px;
      z-index: 25;
      display: none;
      flex-direction: column;
      box-shadow: 0 12px 36px rgba(0,0,0,0.6);
      overflow-y: auto;
    }}
    #inspector-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 12px;
    }}
    #inspector-title {{
      font-size: 16px;
      font-weight: 600;
      color: var(--text);
      line-height: 1.3;
    }}
    #inspector-close {{
      background: none;
      border: none;
      color: var(--text-muted);
      font-size: 20px;
      cursor: pointer;
      line-height: 1;
      padding: 2px 6px;
    }}
    #inspector-close:hover {{ color: var(--text); }}
    .meta-row {{
      display: flex;
      justify-content: space-between;
      margin-bottom: 8px;
      font-size: 12px;
      color: var(--text-muted);
    }}
    .meta-val {{
      color: var(--text);
      font-weight: 500;
    }}
    .freshness-bar-bg {{
      width: 100%;
      height: 6px;
      background: rgba(255,255,255,0.1);
      border-radius: 3px;
      margin: 6px 0 12px 0;
      overflow: hidden;
    }}
    .freshness-bar-fill {{
      height: 100%;
      border-radius: 3px;
      background: linear-gradient(90deg, #f85149, #e3b341, #3fb950);
      transition: width 0.3s;
    }}
    .tags-container {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin: 10px 0;
    }}
    .tag-chip {{
      background: rgba(88, 166, 255, 0.12);
      color: #79c0ff;
      border: 1px solid rgba(88, 166, 255, 0.2);
      border-radius: 6px;
      padding: 2px 8px;
      font-size: 11px;
    }}
    .section-title {{
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      margin: 12px 0 6px 0;
      letter-spacing: 0.5px;
    }}
    .notes-list {{
      max-height: 220px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 6px;
      margin-top: 6px;
      padding-right: 4px;
    }}
    .note-card {{
      background: var(--card-bg);
      border: 1px solid rgba(255,255,255,0.06);
      border-radius: 8px;
      padding: 8px 10px;
      font-size: 12px;
      cursor: pointer;
      transition: border-color 0.2s, background 0.2s;
    }}
    .note-card:hover {{
      border-color: var(--accent);
      background: rgba(48, 54, 61, 0.8);
    }}
    .note-card-title {{
      font-weight: 600;
      color: var(--text);
      margin-bottom: 2px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .note-card-date {{
      font-size: 10px;
      color: var(--text-muted);
      margin-bottom: 4px;
    }}
    .note-card-preview {{
      font-size: 11px;
      color: var(--text-muted);
      line-height: 1.3;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
      transition: color 0.2s;
    }}
    .note-card.expanded .note-card-preview {{
      display: block;
      -webkit-line-clamp: unset;
      white-space: pre-wrap;
      color: #e6edf3;
      margin-top: 4px;
    }}
    .note-card.highlighted {{
      border-color: #38bdf8 !important;
      background: rgba(56, 189, 248, 0.18) !important;
      box-shadow: 0 0 12px rgba(56, 189, 248, 0.3);
    }}
    .actions-row {{
      display: flex;
      gap: 8px;
      margin-top: 14px;
    }}
    .actions-row .btn {{
      flex: 1;
      font-size: 12px;
      height: 32px;
    }}

    /* Слой A: Атлас (Sunburst миникарта, левый нижний угол) */
    #atlas-container {{
      position: absolute;
      bottom: calc(20px + env(safe-area-inset-bottom));
      left: calc(20px + env(safe-area-inset-left));
      width: 200px;
      height: 200px;
      z-index: 20;
      background: var(--panel-bg);
      backdrop-filter: blur(14px);
      -webkit-backdrop-filter: blur(14px);
      border: 1px solid var(--panel-border);
      border-radius: 14px;
      padding: 8px;
      box-shadow: 0 8px 24px rgba(0,0,0,0.5);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      transition: all 0.3s;
    }}
    #atlas-canvas {{
      width: 184px;
      height: 184px;
      cursor: pointer;
    }}
    #atlas-title {{
      position: absolute;
      top: 6px;
      left: 10px;
      font-size: 10px;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      pointer-events: none;
    }}
    #atlas-toggle-btn {{
      display: none;
    }}

    /* Мобильная адаптивность */
    @media (max-width: 640px) {{
      #header {{
        max-width: calc(100vw - 32px);
        flex-wrap: wrap;
        gap: 8px;
      }}
      #search-input {{ width: 130px; }}
      #search-input:focus {{ width: 160px; }}
      #inspector {{
        top: auto;
        bottom: 0;
        right: 0;
        left: 0;
        width: 100vw;
        max-height: 65vh;
        border-radius: 20px 20px 0 0;
        border-bottom: none;
        padding-bottom: calc(16px + env(safe-area-inset-bottom));
      }}
      #atlas-container {{
        display: none;
        bottom: 70px;
        left: 16px;
      }}
      #atlas-container.mobile-open {{
        display: flex;
      }}
      #atlas-toggle-btn {{
        display: flex;
        position: absolute;
        bottom: calc(20px + env(safe-area-inset-bottom));
        left: calc(20px + env(safe-area-inset-left));
        z-index: 21;
      }}
    }}
  </style>
</head>
<body>
  <canvas id="graph-canvas"></canvas>

  <div id="header">
    <h1>🏰 {palace_name}</h1>
    <span class="badge" id="badge-wings">Крыльев: {wing_count}</span>
    <span class="badge" id="badge-rooms">Комнат: {room_count}</span>
    <span class="badge" id="badge-records">Записей: {record_count}</span>
    <span class="badge" id="badge-tunnels">Туннелей: {tunnel_count}</span>
    <div id="search-box">
      <input type="text" id="search-input" placeholder="🔍 Поиск комнат / крыльев..." />
    </div>
  </div>

  <div id="controls">
    <button class="btn" id="btn-zoom-in" title="Приблизить">+</button>
    <button class="btn" id="btn-zoom-out" title="Отдалить">−</button>
    <button class="btn" id="btn-reset" title="Сбросить вид">⟲</button>
    <button class="btn" id="btn-forgotten" title="Забытое (без обновлений 30+ дней)">⏳</button>
    <button class="btn" id="btn-export-png" title="Экспорт PNG">📷</button>
  </div>

  <!-- Атлас (Sunburst мини-карта) -->
  <button class="btn" id="atlas-toggle-btn">🧭 Атлас</button>
  <div id="atlas-container">
    <div id="atlas-title">🧭 Атлас</div>
    <canvas id="atlas-canvas" width="184" height="184"></canvas>
  </div>

  <!-- Панель инспектора -->
  <div id="inspector">
    <div id="inspector-header">
      <div id="inspector-title">Комната</div>
      <button id="inspector-close">&times;</button>
    </div>
    <div class="meta-row">
      <span>Крыло:</span>
      <span class="meta-val" id="meta-wing">—</span>
    </div>
    <div class="meta-row">
      <span>Записей:</span>
      <span class="meta-val" id="meta-records">0</span>
    </div>
    <div class="meta-row">
      <span>Свежесть:</span>
      <span class="meta-val" id="meta-freshness">—</span>
    </div>
    <div class="freshness-bar-bg">
      <div class="freshness-bar-fill" id="freshness-fill" style="width: 50%;"></div>
    </div>
    <div class="meta-row">
      <span>Связей (туннелей):</span>
      <span class="meta-val" id="meta-tunnels">0</span>
    </div>

    <div class="section-title">Ключевые темы / сущности</div>
    <div class="tags-container" id="inspector-tags"></div>

    <div class="section-title">Заметки и ящики (<span id="notes-count">0</span>)</div>
    <div class="notes-list" id="inspector-notes"></div>

    <div class="actions-row">
      <button class="btn" id="btn-inspect-expand">🌐 Раскрыть ящики</button>
      <button class="btn" id="btn-inspect-focus">🎯 Фокус</button>
    </div>
  </div>

  <script>
    // 1. Встраивание данных Дворца памяти (PALACE)
    const PALACE = {palace_data_json};

    // 2. Интеграция с Telegram WebApp
    const tg = window.Telegram?.WebApp;
    if (tg) {{
      try {{
        tg.expand();
        if (tg.themeParams?.bg_color) {{
          document.documentElement.style.setProperty('--bg', tg.themeParams.bg_color);
        }}
        if (tg.themeParams?.text_color) {{
          document.documentElement.style.setProperty('--text', tg.themeParams.text_color);
        }}
      }} catch (e) {{}}
    }}

    // 3. Безопасное хранилище (SafeStorage) против SecurityError в file://
    const safeStorage = {{
      getItem(k) {{
        try {{ return localStorage.getItem(k); }} catch(e) {{ return null; }}
      }},
      setItem(k, v) {{
        try {{ localStorage.setItem(k, v); }} catch(e) {{}}
      }}
    }};

    // 4. Детерминированный FNV-1a хеш для цветов и стартовых координат
    function fnv1a(str) {{
      let hash = 2166136261;
      for (let i = 0; i < str.length; i++) {{
        hash ^= str.charCodeAt(i);
        hash = Math.imul(hash, 16777619);
      }}
      return hash >>> 0;
    }}

    const canvas = document.getElementById('graph-canvas');
    const ctx = canvas.getContext('2d');
    const atlasCanvas = document.getElementById('atlas-canvas');
    const atlasCtx = atlasCanvas.getContext('2d');

    const searchInput = document.getElementById('search-input');
    const inspector = document.getElementById('inspector');
    const inspectorTitle = document.getElementById('inspector-title');
    const metaWing = document.getElementById('meta-wing');
    const metaRecords = document.getElementById('meta-records');
    const metaFreshness = document.getElementById('meta-freshness');
    const freshnessFill = document.getElementById('freshness-fill');
    const metaTunnels = document.getElementById('meta-tunnels');
    const inspectorTags = document.getElementById('inspector-tags');
    const inspectorNotes = document.getElementById('inspector-notes');
    const notesCount = document.getElementById('notes-count');
    const btnInspectExpand = document.getElementById('btn-inspect-expand');
    const btnInspectFocus = document.getElementById('btn-inspect-focus');

    let width = window.innerWidth;
    let height = window.innerHeight;
    let dpr = window.devicePixelRatio || 1;

    function resize() {{
      dpr = window.devicePixelRatio || 1;
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      draw();
    }}
    window.addEventListener('resize', resize);

    // Подготовка узлов и связей
    const nodes = PALACE.nodes || [];
    const links = PALACE.links || [];
    const nodeMap = new Map();
    const wingNodes = [];
    const roomNodes = [];

    // Привязка радиусов и стилей
    nodes.forEach(n => {{
      nodeMap.set(n.id, n);
      n.records = n.records || 1;
      n.vx = 0;
      n.vy = 0;

      if (n.type === 'wing') {{
        wingNodes.push(n);
        n.r = 20 + 1.5 * Math.log2(1 + n.records);
        n.hue = fnv1a(n.id) % 360;
        n.color = `hsl(${{n.hue}}, 65%, 62%)`;
      }} else {{
        roomNodes.push(n);
        n.r = 5 + 3.2 * Math.log2(1 + n.records);
        const wNode = nodeMap.get(n.wing);
        n.hue = wNode ? wNode.hue : (fnv1a(n.wing || '') % 360);
        n.color = n.service ? '#6e7681' : `hsl(${{n.hue}}, 55%, 55%)`;
      }}
    }});

    // Связи по комнатам
    const neighborsMap = new Map();
    nodes.forEach(n => neighborsMap.set(n.id, new Set()));

    links.forEach(l => {{
      const s = typeof l.source === 'object' ? l.source.id : l.source;
      const t = typeof l.target === 'object' ? l.target.id : l.target;
      l.sourceNode = nodeMap.get(s);
      l.targetNode = nodeMap.get(t);
      if (neighborsMap.has(s) && neighborsMap.has(t)) {{
        neighborsMap.get(s).add(t);
        neighborsMap.get(t).add(s);
      }}
    }});

    // Восстановление координат из safeStorage или детерминированная инициализация
    let savedPos = null;
    try {{
      const raw = safeStorage.getItem('palace:pos:v1');
      if (raw) savedPos = JSON.parse(raw);
    }} catch(e) {{}}

    const initRadius = Math.min(width, height) * 0.38;
    wingNodes.forEach((w, idx) => {{
      if (savedPos && savedPos[w.id]) {{
        w.x = savedPos[w.id].x;
        w.y = savedPos[w.id].y;
      }} else {{
        const angle = (idx / (wingNodes.length || 1)) * 2 * Math.PI;
        w.x = width / 2 + Math.cos(angle) * initRadius;
        w.y = height / 2 + Math.sin(angle) * initRadius;
      }}

      const rooms = roomNodes.filter(r => r.wing === w.id);
      rooms.forEach((r, rIdx) => {{
        if (savedPos && savedPos[r.id]) {{
          r.x = savedPos[r.id].x;
          r.y = savedPos[r.id].y;
        }} else {{
          const rAngle = (rIdx / (rooms.length || 1)) * 2 * Math.PI;
          const rDist = 45 + Math.min(rooms.length * 4, 140);
          r.x = w.x + Math.cos(rAngle) * rDist;
          r.y = w.y + Math.sin(rAngle) * rDist;
        }}
      }});
    }});

    // 5. Физическая симуляция (Force-directed, ~120 строк)
    let simAlpha = 1.0;
    const alphaDecay = 0.022;
    const velocityDecay = 0.4;
    let simTickCount = 0;
    let isSimRunning = true;

    function stepSimulation() {{
      if (simAlpha < 0.02) {{
        if (isSimRunning) {{
          isSimRunning = false;
          // Сохраняем раскладку после стабилизации
          const posMap = {{}};
          nodes.forEach(n => {{ posMap[n.id] = {{ x: Math.round(n.x), y: Math.round(n.y) }}; }});
          safeStorage.setItem('palace:pos:v1', JSON.stringify(posMap));
        }}
        return;
      }}

      simTickCount++;
      simAlpha *= (1 - alphaDecay);

      // Гравитация к центру
      const cx = width / 2;
      const cy = height / 2;
      for (let i = 0; i < nodes.length; i++) {{
        const n = nodes[i];
        if (n.pinned) continue;
        n.vx += (cx - n.x) * 0.02 * simAlpha;
        n.vy += (cy - n.y) * 0.02 * simAlpha;
      }}

      // Силы связей (links)
      for (let i = 0; i < links.length; i++) {{
        const l = links[i];
        const s = l.sourceNode;
        const t = l.targetNode;
        if (!s || !t) continue;
        const dx = t.x - s.x;
        const dy = t.y - s.y;
        const dist = Math.hypot(dx, dy) || 1;
        const targetDist = l.type === 'tunnel' ? 140 : 55;
        const force = (dist - targetDist) / dist * 0.12 * simAlpha;
        const fx = dx * force;
        const fy = dy * force;
        if (!s.pinned) {{ s.vx += fx; s.vy += fy; }}
        if (!t.pinned) {{ t.vx -= fx; t.vy -= fy; }}
      }}

      // Отталкивание (charge) и коллизии (collide)
      for (let i = 0; i < nodes.length; i++) {{
        const n1 = nodes[i];
        for (let j = i + 1; j < nodes.length; j++) {{
          const n2 = nodes[j];
          const dx = n2.x - n1.x;
          const dy = n2.y - n1.y;
          const distSq = dx * dx + dy * dy || 1;
          const dist = Math.sqrt(distSq);

          // Charge
          const repForce = (-180 / distSq) * simAlpha;
          const rx = (dx / dist) * repForce;
          const ry = (dy / dist) * repForce;
          if (!n1.pinned) {{ n1.vx += rx; n1.vy += ry; }}
          if (!n2.pinned) {{ n2.vx -= rx; n2.vy -= ry; }}

          // Collide (r + 6)
          const minDist = n1.r + n2.r + 6;
          if (dist < minDist) {{
            const overlap = (minDist - dist) / dist * 0.5 * simAlpha;
            const ox = dx * overlap;
            const oy = dy * overlap;
            if (!n1.pinned) {{ n1.x -= ox; n1.y -= oy; }}
            if (!n2.pinned) {{ n2.x += ox; n2.y += oy; }}
          }}
        }}
      }}

      // Интеграция скоростей
      for (let i = 0; i < nodes.length; i++) {{
        const n = nodes[i];
        if (n.pinned) continue;
        n.vx *= velocityDecay;
        n.vy *= velocityDecay;
        n.x += n.vx;
        n.y += n.vy;
      }}

      updateSpatialGrid();
    }}

    // 6. Пространственная хэш-сетка 64px (Spatial Grid Hash)
    const CELL_SIZE = 64;
    const grid = new Map();

    function updateSpatialGrid() {{
      grid.clear();
      for (let i = 0; i < nodes.length; i++) {{
        const n = nodes[i];
        const gx = Math.floor(n.x / CELL_SIZE);
        const gy = Math.floor(n.y / CELL_SIZE);
        const key = `${{gx}},${{gy}}`;
        let list = grid.get(key);
        if (!list) {{ list = []; grid.set(key, list); }}
        list.push(n);
      }}
    }}

    function findNodeAt(worldX, worldY, hitScale) {{
      const gx = Math.floor(worldX / CELL_SIZE);
      const gy = Math.floor(worldY / CELL_SIZE);
      let bestNode = null;
      let bestDist = Infinity;

      for (let dx = -1; dx <= 1; dx++) {{
        for (let dy = -1; dy <= 1; dy++) {{
          const list = grid.get(`${{gx + dx}},${{gy + dy}}`);
          if (!list) continue;
          for (let i = 0; i < list.length; i++) {{
            const n = list[i];
            const dist = Math.hypot(n.x - worldX, n.y - worldY);
            const r = Math.max(n.r, 10 / hitScale);
            if (dist <= r && dist < bestDist) {{
              bestDist = dist;
              bestNode = n;
            }}
          }}
        }}
      }}
      return bestNode;
    }}

    // 7. Камера, зум и панорамирование
    let zoom = 0.9;
    let panX = 0;
    let panY = 0;
    let hoveredNode = null;
    let selectedNode = null;
    let expandedNodeId = null;
    let expandedWingId = null;
    let activeSatellites = [];
    let showForgotten = false;
    let searchQuery = '';

    // Центрирование камеры
    panX = width / 2 * (1 - zoom);
    panY = height / 2 * (1 - zoom);

    // 8. Отрисовка Слоя B «Созвездия»
    function draw() {{
      ctx.clearRect(0, 0, width, height);
      activeSatellites = [];
      ctx.save();
      ctx.translate(panX, panY);
      ctx.scale(zoom, zoom);

      // Фон: тонкая сетка звезд
      drawStarsBackground();

      // 8.1 Отрисовка связей (Links)
      for (let i = 0; i < links.length; i++) {{
        const l = links[i];
        const s = l.sourceNode;
        const t = l.targetNode;
        if (!s || !t) continue;

        let alpha = 1.0;
        if (hoveredNode) {{
          const isConnected = (s.id === hoveredNode.id || t.id === hoveredNode.id);
          alpha = isConnected ? 1.0 : 0.12;
        }}

        ctx.save();
        ctx.globalAlpha = alpha;

        if (l.type === 'tunnel') {{
          // Дуга туннеля (квадратичная кривая со смещением 0.15)
          const dx = t.x - s.x;
          const dy = t.y - s.y;
          const dist = Math.hypot(dx, dy) || 1;
          const midX = (s.x + t.x) / 2;
          const midY = (s.y + t.y) / 2;
          const normX = -dy / dist;
          const normY = dx / dist;
          const cpX = midX + normX * dist * 0.15;
          const cpY = midY + normY * dist * 0.15;

          ctx.beginPath();
          ctx.setLineDash([5, 5]);
          ctx.strokeStyle = '#f0883e';
          const isConn = (hoveredNode && (s.id === hoveredNode.id || t.id === hoveredNode.id));
          ctx.lineWidth = isConn ? 2.5 : 1.6;
          ctx.moveTo(s.x, s.y);
          ctx.quadraticCurveTo(cpX, cpY, t.x, t.y);
          ctx.stroke();
          ctx.setLineDash([]);
        }} else if (l.type === 'containment') {{
          ctx.beginPath();
          ctx.strokeStyle = 'rgba(255, 255, 255, 0.10)';
          ctx.lineWidth = 1;
          ctx.moveTo(s.x, s.y);
          ctx.lineTo(t.x, t.y);
          ctx.stroke();
        }}
        ctx.restore();
      }}

      // 8.2 Отрисовка узлов (Nodes)
      const drawnLabelBoxes = [];

      // Сортировка: крылья рисуются под комнатами, выбранные поверх
      const sortedNodes = [...nodes].sort((a, b) => {{
        if (a.id === selectedNode?.id) return 1;
        if (b.id === selectedNode?.id) return -1;
        return a.type === 'wing' ? -1 : 1;
      }});

      for (let i = 0; i < sortedNodes.length; i++) {{
        const n = sortedNodes[i];
        let alpha = 1.0;

        if (hoveredNode) {{
          const isDirectNeighbor = neighborsMap.get(hoveredNode.id)?.has(n.id);
          alpha = (n.id === hoveredNode.id || isDirectNeighbor) ? 1.0 : 0.12;
        }}

        if (searchQuery) {{
          const match = n.label.toLowerCase().includes(searchQuery);
          if (!match) alpha = Math.min(alpha, 0.15);
        }}

        ctx.save();
        ctx.globalAlpha = alpha;

        if (n.type === 'wing') {{
          // Крыло: большой светящийся узел
          const grad = ctx.createRadialGradient(n.x, n.y, n.r * 0.2, n.x, n.y, n.r * 1.5);
          grad.addColorStop(0, n.color);
          grad.addColorStop(0.6, n.color.replace(')', ', 0.35)').replace('hsl', 'hsla'));
          grad.addColorStop(1, 'rgba(0,0,0,0)');

          ctx.beginPath();
          ctx.fillStyle = grad;
          ctx.arc(n.x, n.y, n.r * 1.5, 0, 2 * Math.PI);
          ctx.fill();

          ctx.beginPath();
          ctx.arc(n.x, n.y, n.r, 0, 2 * Math.PI);
          ctx.fillStyle = n.color;
          ctx.fill();
          ctx.lineWidth = 2;
          ctx.strokeStyle = 'rgba(255,255,255,0.5)';
          ctx.stroke();

          // Подпись крыла с бейджем (LOD 1+)
          drawHaloText(n.label, n.x, n.y + n.r + 14, 12, true);
          drawBadgeText(`${{n.records}}`, n.x, n.y + n.r + 28);

          // Если раскрыто это крыло — рисуем ауру
          if (expandedWingId === n.id) {{
            ctx.beginPath();
            ctx.arc(n.x, n.y, n.r * 2.2, 0, 2 * Math.PI);
            ctx.strokeStyle = 'rgba(56, 189, 248, 0.4)';
            ctx.lineWidth = 1.5;
            ctx.setLineDash([6, 6]);
            ctx.stroke();
            ctx.setLineDash([]);
          }}

        }} else {{
          // Комната: круговой узел
          ctx.beginPath();
          ctx.arc(n.x, n.y, n.r, 0, 2 * Math.PI);
          ctx.fillStyle = n.color;
          ctx.fill();
          ctx.lineWidth = 1.5;
          ctx.strokeStyle = n.id === selectedNode?.id ? '#ffffff' : 'rgba(255,255,255,0.3)';
          ctx.stroke();

          // Режим «Забытое»: подсветка комнат без обновлений
          if (showForgotten && n.freshness < 0.35) {{
            ctx.beginPath();
            ctx.arc(n.x, n.y, n.r + 5, 0, 2 * Math.PI);
            ctx.strokeStyle = '#f59e0b';
            ctx.lineWidth = 2;
            ctx.stroke();
          }}

          // Поиск: пульсирующее кольцо
          if (searchQuery && n.label.toLowerCase().includes(searchQuery)) {{
            ctx.beginPath();
            ctx.arc(n.x, n.y, n.r + 6, 0, 2 * Math.PI);
            ctx.strokeStyle = '#38bdf8';
            ctx.lineWidth = 2.5;
            ctx.stroke();
          }}

          // LOD 4 (k >= 2.4): россыпь ящиков по спирали Фибоначчи
          if (zoom >= 2.4) {{
            const count = Math.min(n.records || 1, 40);
            for (let dIdx = 0; dIdx < count; dIdx++) {{
              const rDist = (n.r - 3) * Math.sqrt((dIdx + 1) / count);
              const theta = dIdx * 2.39996; // 137.5 градусов
              const dx = n.x + rDist * Math.cos(theta);
              const dy = n.y + rDist * Math.sin(theta);
              ctx.beginPath();
              ctx.arc(dx, dy, 1.2, 0, 2 * Math.PI);
              ctx.fillStyle = 'rgba(255,255,255,0.7)';
              ctx.fill();
            }}
          }}

          // LOD 3 (k >= 1.1) и LOD 2: подписи комнат с де-клаттерингом
          if (zoom >= 1.1) {{
            const text = n.label;
            const fontSize = 11;
            ctx.font = `${{fontSize}}px -apple-system, sans-serif`;
            const textWidth = ctx.measureText(text).width;
            const bbox = {{
              x: n.x - textWidth / 2 - 2,
              y: n.y + n.r + 2,
              w: textWidth + 4,
              h: fontSize + 4
            }};

            // Де-клаттеринг: проверка пересечений
            let overlaps = false;
            for (let b = 0; b < drawnLabelBoxes.length; b++) {{
              const o = drawnLabelBoxes[b];
              if (bbox.x < o.x + o.w && bbox.x + bbox.w > o.x &&
                  bbox.y < o.y + o.h && bbox.y + bbox.h > o.y) {{
                overlaps = true;
                break;
              }}
            }}

            if (!overlaps || n.id === selectedNode?.id) {{
              drawHaloText(text, n.x, n.y + n.r + 12, fontSize, false);
              drawnLabelBoxes.push(bbox);
            }}
          }}

          // Раскрытие ящиков на графе (по запросу пользователя!)
          const isRoomExpanded = (expandedNodeId === n.id) ||
            (expandedWingId && (n.wing === expandedWingId || n.wing_name === selectedNode?.label));
          if (isRoomExpanded) {{
            drawExpandedSatelliteNotes(n);
          }}
        }}
        ctx.restore();
      }}

      ctx.restore();

      // Отрисовка миникарты Атласа
      drawAtlasSunburst();

      if (isSimRunning) {{
        stepSimulation();
        requestAnimationFrame(draw);
      }}
    }}

    // Раскрытие спутниковых ящиков вокруг выбранной комнаты
    function drawExpandedSatelliteNotes(roomNode) {{
      let notes = (roomNode.notes && roomNode.notes.length > 0)
        ? roomNode.notes
        : [];
      if (notes.length === 0 && (roomNode.records || 0) > 0) {{
        const cnt = Math.min(roomNode.records, 16);
        notes = Array.from({{ length: cnt }}, (_, i) => ({{
          t: 'Запись #' + (i + 1),
          d: '',
          p: 'Запись в комнате «' + roomNode.label + '»'
        }}));
      }}

      const count = Math.min(notes.length, 20);
      if (count === 0) return;

      const orbitR = Math.max(roomNode.r + 50, 36 + count * 4.5);

      // Орбитальное кольцо
      ctx.beginPath();
      ctx.arc(roomNode.x, roomNode.y, orbitR, 0, 2 * Math.PI);
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.25)';
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.stroke();
      ctx.setLineDash([]);

      for (let i = 0; i < count; i++) {{
        const item = notes[i];
        const angle = (i / count) * 2 * Math.PI - Math.PI / 2;
        const sx = roomNode.x + Math.cos(angle) * orbitR;
        const sy = roomNode.y + Math.sin(angle) * orbitR;
        const satR = 6;

        activeSatellites.push({{
          x: sx,
          y: sy,
          r: satR + 4,
          note: item,
          room: roomNode,
          idx: i
        }});

        // Связь со спутником
        ctx.beginPath();
        ctx.strokeStyle = 'rgba(56, 189, 248, 0.45)';
        ctx.lineWidth = 1.2;
        ctx.moveTo(roomNode.x, roomNode.y);
        ctx.lineTo(sx, sy);
        ctx.stroke();

        // Спутник-ящик (кружок)
        ctx.beginPath();
        ctx.arc(sx, sy, satR, 0, 2 * Math.PI);
        ctx.fillStyle = '#38bdf8';
        ctx.fill();
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1.4;
        ctx.stroke();

        // Сердцевина
        ctx.beginPath();
        ctx.arc(sx, sy, 2, 0, 2 * Math.PI);
        ctx.fillStyle = '#ffffff';
        ctx.fill();

        // Подпись ящика
        const rawTitle = item.t || item.title || ('Заметка #' + (i + 1));
        const labelText = rawTitle.length > 22 ? rawTitle.slice(0, 20) + '…' : rawTitle;
        const textY = sy + (Math.sin(angle) >= 0 ? 14 : -14);
        drawPillText(labelText, sx, textY, 10);
      }}
    }}

    // Текст плашки для спутников
    function drawPillText(text, x, y, size) {{
      ctx.save();
      ctx.font = size + 'px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      const tw = ctx.measureText(text).width;
      const pw = tw + 12;
      const ph = size + 8;

      ctx.fillStyle = 'rgba(13, 17, 23, 0.90)';
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.55)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      if (ctx.roundRect) {{
        ctx.roundRect(x - pw / 2, y - ph / 2, pw, ph, 4);
      }} else {{
        ctx.rect(x - pw / 2, y - ph / 2, pw, ph);
      }}
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = '#ffffff';
      ctx.fillText(text, x, y);
      ctx.restore();
    }}

    // Текст с обводкой (halo)
    function drawHaloText(text, x, y, size, isBold) {{
      ctx.save();
      ctx.font = `${{isBold ? 'bold ' : ''}}${{size}}px -apple-system, sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.strokeStyle = 'rgba(13, 17, 23, 0.88)';
      ctx.lineWidth = 3;
      ctx.strokeText(text, x, y);
      ctx.fillStyle = '#ffffff';
      ctx.fillText(text, x, y);
      ctx.restore();
    }}

    function drawBadgeText(text, x, y) {{
      ctx.save();
      ctx.font = '10px -apple-system, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      const w = ctx.measureText(text).width + 8;
      ctx.fillStyle = 'rgba(88, 166, 255, 0.2)';
      ctx.fillRect(x - w / 2, y - 6, w, 12);
      ctx.fillStyle = '#58a6ff';
      ctx.fillText(text, x, y);
      ctx.restore();
    }}

    function drawStarsBackground() {{
      // Псевдо-звезды
      ctx.fillStyle = 'rgba(255, 255, 255, 0.15)';
      for (let i = 0; i < 70; i++) {{
        const sx = (fnv1a(`star_x_${{i}}`) % 3000) - 1000;
        const sy = (fnv1a(`star_y_${{i}}`) % 3000) - 1000;
        ctx.fillRect(sx, sy, 1.2, 1.2);
      }}
    }}

    // 9. Слой A: Sunburst Атлас (200x200 canvas)
    function drawAtlasSunburst() {{
      atlasCtx.clearRect(0, 0, 184, 184);
      const cx = 92;
      const cy = 92;
      const totalRooms = roomNodes.length || 1;

      let currentAngle = 0;
      wingNodes.forEach(w => {{
        const rooms = roomNodes.filter(r => r.wing === w.id);
        const wingAngle = (rooms.length / totalRooms) * 2 * Math.PI;

        // Внутреннее кольцо (Крылья)
        atlasCtx.beginPath();
        atlasCtx.arc(cx, cy, 54, currentAngle, currentAngle + wingAngle);
        atlasCtx.arc(cx, cy, 26, currentAngle + wingAngle, currentAngle, true);
        atlasCtx.closePath();
        atlasCtx.fillStyle = w.color;
        atlasCtx.fill();
        atlasCtx.strokeStyle = 'rgba(13, 17, 23, 0.6)';
        atlasCtx.lineWidth = 1;
        atlasCtx.stroke();

        // Внешнее кольцо (Комнаты)
        let roomAngleStart = currentAngle;
        const rStep = wingAngle / (rooms.length || 1);
        rooms.forEach(r => {{
          const thickness = 58 + Math.min(Math.log2(1 + r.records) * 3, 26);
          atlasCtx.beginPath();
          atlasCtx.arc(cx, cy, thickness, roomAngleStart, roomAngleStart + rStep);
          atlasCtx.arc(cx, cy, 56, roomAngleStart + rStep, roomAngleStart, true);
          atlasCtx.closePath();
          atlasCtx.fillStyle = r.color;
          atlasCtx.fill();
          atlasCtx.stroke();
          roomAngleStart += rStep;
        }});

        currentAngle += wingAngle;
      }});
    }}

    // 10. Обработка событий мыши и тача (включая перемещение крыльев и узлов)
    let isDragging = false;
    let draggedNode = null;
    let dragOffset = {{ x: 0, y: 0 }};
    let dragStartX = 0;
    let dragStartY = 0;
    let didDragNode = false;
    let startMouseX = 0;
    let startMouseY = 0;

    canvas.addEventListener('mousedown', e => {{
      startMouseX = e.clientX;
      startMouseY = e.clientY;
      didDragNode = false;

      const worldX = (e.clientX - panX) / zoom;
      const worldY = (e.clientY - panY) / zoom;
      const hit = findNodeAt(worldX, worldY, zoom);

      if (hit) {{
        // Зажимаем узел (крыло или комнату) для перетаскивания!
        draggedNode = hit;
        draggedNode.pinned = true;
        dragOffset.x = draggedNode.x - worldX;
        dragOffset.y = draggedNode.y - worldY;
        canvas.classList.add('grabbing');
      }} else {{
        // Панорамирование камеры
        isDragging = true;
        dragStartX = e.clientX - panX;
        dragStartY = e.clientY - panY;
        canvas.classList.add('grabbing');
      }}
    }});

    window.addEventListener('mousemove', e => {{
      const worldX = (e.clientX - panX) / zoom;
      const worldY = (e.clientY - panY) / zoom;

      if (draggedNode) {{
        const targetX = worldX + dragOffset.x;
        const targetY = worldY + dragOffset.y;
        const deltaX = targetX - draggedNode.x;
        const deltaY = targetY - draggedNode.y;

        if (Math.hypot(e.clientX - startMouseX, e.clientY - startMouseY) > 4) {{
          didDragNode = true;
        }}

        draggedNode.x = targetX;
        draggedNode.y = targetY;
        draggedNode.vx = 0;
        draggedNode.vy = 0;

        // Если перетаскиваем крыло — сдвигаем вместе с ним всю его гроздь комнат!
        if (draggedNode.type === 'wing') {{
          for (let i = 0; i < roomNodes.length; i++) {{
            const r = roomNodes[i];
            if (r.wing === draggedNode.id) {{
              r.x += deltaX;
              r.y += deltaY;
              r.vx = 0;
              r.vy = 0;
            }}
          }}
        }}

        // Подогреваем симуляцию для мягкой адаптации связей
        simAlpha = Math.max(simAlpha, 0.25);
        if (!isSimRunning) {{
          isSimRunning = true;
          requestAnimationFrame(draw);
        }}

        updateSpatialGrid();
        draw();
        return;
      }}

      if (isDragging) {{
        panX = e.clientX - dragStartX;
        panY = e.clientY - dragStartY;
        draw();
        return;
      }}

      // Проверка наведения на спутники ящиков
      let satHovered = null;
      for (let i = 0; i < activeSatellites.length; i++) {{
        const sat = activeSatellites[i];
        if (Math.hypot(sat.x - worldX, sat.y - worldY) <= (sat.r / zoom) * 1.5 + 4) {{
          satHovered = sat;
          break;
        }}
      }}

      if (satHovered) {{
        canvas.style.cursor = 'pointer';
        return;
      }}

      // Определение узла под курсором (через пространственный хэш)
      const hit = findNodeAt(worldX, worldY, zoom);

      if (hit !== hoveredNode) {{
        hoveredNode = hit;
        if (hit) {{
          canvas.style.cursor = hit.type === 'wing' ? 'move' : 'pointer';
        }} else {{
          canvas.style.cursor = 'grab';
        }}
        draw();
      }}
    }});

    window.addEventListener('mouseup', () => {{
      if (draggedNode) {{
        draggedNode.pinned = true;
        // Сохраняем новые координаты в хранилище
        const posMap = {{}};
        nodes.forEach(n => {{ posMap[n.id] = {{ x: Math.round(n.x), y: Math.round(n.y) }}; }});
        safeStorage.setItem('palace:pos:v1', JSON.stringify(posMap));
        draggedNode = null;
      }}
      isDragging = false;
      canvas.classList.remove('grabbing');
    }});

    canvas.addEventListener('wheel', e => {{
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.15 : 0.87;
      const newZoom = Math.max(0.2, Math.min(4.5, zoom * zoomFactor));

      // Центрирование зума в точку курсора
      const mouseX = e.clientX;
      const mouseY = e.clientY;
      panX = mouseX - (mouseX - panX) * (newZoom / zoom);
      panY = mouseY - (mouseY - panY) * (newZoom / zoom);
      zoom = newZoom;
      draw();
    }}, {{ passive: false }});

    // Клик по узлу — открытие панели инспектора (только если не было сдвига)
    canvas.addEventListener('click', e => {{
      if (didDragNode) return;
      const worldX = (e.clientX - panX) / zoom;
      const worldY = (e.clientY - panY) / zoom;

      // Проверка клика по спутнику-ящику
      for (let i = 0; i < activeSatellites.length; i++) {{
        const sat = activeSatellites[i];
        if (Math.hypot(sat.x - worldX, sat.y - worldY) <= (sat.r / zoom) * 1.5 + 6) {{
          const noteCards = inspectorNotes.querySelectorAll('.note-card');
          if (noteCards[sat.idx]) {{
            noteCards.forEach(c => c.classList.remove('highlighted'));
            noteCards[sat.idx].classList.add('highlighted');
            noteCards[sat.idx].classList.add('expanded');
            noteCards[sat.idx].scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
          }}
          return;
        }}
      }}

      const hit = findNodeAt(worldX, worldY, zoom);

      if (hit) {{
        selectNode(hit);
      }} else {{
        selectedNode = null;
        expandedNodeId = null;
        expandedWingId = null;
        btnInspectExpand.classList.remove('active');
        inspector.style.display = 'none';
        draw();
      }}
    }});

    // Двойной клик — Zoom to fit поддерева
    canvas.addEventListener('dblclick', e => {{
      const worldX = (e.clientX - panX) / zoom;
      const worldY = (e.clientY - panY) / zoom;
      const hit = findNodeAt(worldX, worldY, zoom);
      if (hit) {{
        if (hit.type === 'wing') focusOnWing(hit);
        else focusOnNode(hit);
      }}
    }});

    function selectNode(n) {{
      selectedNode = n;
      const isWing = n.type === 'wing';
      const prefix = isWing ? '🏛️ Крыло' : '📁 Комната';
      inspectorTitle.textContent = prefix + ': ' + n.label;
      metaWing.textContent = n.wing_name || n.wing || n.label;
      metaRecords.textContent = n.records + ' записей';

      const fVal = Math.round((n.freshness || 0.5) * 100);
      metaFreshness.textContent = fVal + '%';
      freshnessFill.style.width = fVal + '%';

      const tunnelCount = links.filter(l =>
        l.type === 'tunnel' && (l.sourceNode?.id === n.id || l.targetNode?.id === n.id)
      ).length;
      metaTunnels.textContent = '' + tunnelCount;

      // Теги
      inspectorTags.innerHTML = '';
      const tags = n.tags || [];
      if (tags.length === 0) {{
        inspectorTags.innerHTML =
          '<span style="font-size:11px; color:var(--text-muted);">Теги не заданы</span>';
      }} else {{
        tags.forEach(t => {{
          const chip = document.createElement('span');
          chip.className = 'tag-chip';
          chip.textContent = '#' + t;
          inspectorTags.appendChild(chip);
        }});
      }}

      // Список заметок и ящиков
      inspectorNotes.innerHTML = '';

      if (isWing) {{
        const wingRooms = roomNodes.filter(r => r.wing === n.id || r.wing_name === n.label);
        const allNotesCount = wingRooms.reduce(
          (acc, r) => acc + (r.notes?.length || r.records || 0), 0
        );
        notesCount.textContent = wingRooms.length + ' комнат, ' + allNotesCount + ' ящиков';

        if (wingRooms.length === 0) {{
          inspectorNotes.innerHTML =
            '<div style="font-size:11px; color:var(--text-muted); padding:4px;">' +
            'Нет комнат в этом крыле</div>';
        }} else {{
          wingRooms.forEach(room => {{
            const card = document.createElement('div');
            card.className = 'note-card';
            const roomNotes = room.notes || [];
            const previewText = roomNotes.length > 0
              ? roomNotes.map(nt => '• ' + (nt.t || nt.title)).join('<br>')
              : (room.tags || []).slice(0, 4).map(t => '#' + t).join(' ');
            card.innerHTML =
              '<div class="note-card-title">📁 ' + room.label + '</div>' +
              '<div class="note-card-date">' + room.records + ' записей • свежесть ' +
              Math.round((room.freshness || 0.5) * 100) + '%</div>' +
              '<div class="note-card-preview">' + previewText + '</div>';
            card.onclick = () => {{
              selectNode(room);
              focusOnNode(room);
            }};
            inspectorNotes.appendChild(card);
          }});
        }}

        const isExpanded = (expandedWingId === n.id);
        btnInspectExpand.textContent = isExpanded
          ? 'Свернуть комнаты'
          : '🌐 Раскрыть комнаты и ящики';
        btnInspectExpand.classList.toggle('active', isExpanded);

      }} else {{
        // Комната
        let notes = (n.notes && n.notes.length > 0) ? n.notes : [];
        if (notes.length === 0 && (n.records || 0) > 0) {{
          const cnt = Math.min(n.records, 16);
          notes = Array.from({{ length: cnt }}, (_, i) => ({{
            t: 'Запись #' + (i + 1),
            d: '',
            p: 'Запись в комнате «' + n.label + '».'
          }}));
        }}

        notesCount.textContent = '' + notes.length;

        if (notes.length === 0) {{
          inspectorNotes.innerHTML =
            '<div style="font-size:11px; color:var(--text-muted); padding:4px;">Нет записей</div>';
        }} else {{
          notes.forEach((item, idx) => {{
            const card = document.createElement('div');
            card.className = 'note-card';
            const title = item.t || item.title || ('Заметка #' + (idx + 1));
            const date = item.d || item.date || '';
            const prev = item.p || item.preview || '';
            card.innerHTML =
              '<div class="note-card-title">🗂️ ' + title + '</div>' +
              '<div class="note-card-date">' + date + '</div>' +
              '<div class="note-card-preview">' + prev + '</div>';
            card.onclick = () => {{
              expandedNodeId = n.id;
              card.classList.toggle('expanded');
              focusOnNode(n);
              btnInspectExpand.classList.add('active');
              btnInspectExpand.textContent = 'Свернуть ящики';
              draw();
            }};
            inspectorNotes.appendChild(card);
          }});
        }}

        const isExpanded = (expandedNodeId === n.id);
        btnInspectExpand.textContent = isExpanded ? 'Свернуть ящики' : '🌐 Раскрыть ящики';
        btnInspectExpand.classList.toggle('active', isExpanded);
      }}

      inspector.style.display = 'flex';
      draw();
    }}

    function focusOnNode(n) {{
      zoom = 1.6;
      const offsetX = (window.innerWidth > 768) ? 170 : 0;
      panX = (width / 2 - offsetX) - n.x * zoom;
      panY = height / 2 - n.y * zoom;
      draw();
    }}

    function focusOnWing(w) {{
      const rooms = roomNodes.filter(r => r.wing === w.id || r.wing_name === w.label);
      if (rooms.length === 0) {{
        focusOnNode(w);
        return;
      }}
      let minX = w.x, maxX = w.x, minY = w.y, maxY = w.y;
      rooms.forEach(r => {{
        minX = Math.min(minX, r.x);
        maxX = Math.max(maxX, r.x);
        minY = Math.min(minY, r.y);
        maxY = Math.max(maxY, r.y);
      }});
      const bbW = Math.max(maxX - minX + 160, 240);
      const bbH = Math.max(maxY - minY + 160, 240);
      const midX = (minX + maxX) / 2;
      const midY = (minY + maxY) / 2;
      const availW = window.innerWidth > 768 ? (width - 360) : width;
      const availH = height - 100;
      zoom = Math.max(0.6, Math.min(1.8, Math.min(availW / bbW, availH / bbH)));
      const offsetX = window.innerWidth > 768 ? 170 : 0;
      panX = (width / 2 - offsetX) - midX * zoom;
      panY = height / 2 - midY * zoom;
      draw();
    }}

    btnInspectExpand.onclick = () => {{
      if (!selectedNode) return;
      if (selectedNode.type === 'wing') {{
        if (expandedWingId === selectedNode.id) {{
          expandedWingId = null;
          btnInspectExpand.classList.remove('active');
          btnInspectExpand.textContent = '🌐 Раскрыть комнаты и ящики';
        }} else {{
          expandedWingId = selectedNode.id;
          expandedNodeId = null;
          btnInspectExpand.classList.add('active');
          btnInspectExpand.textContent = 'Свернуть комнаты';
          focusOnWing(selectedNode);
        }}
      }} else {{
        if (expandedNodeId === selectedNode.id) {{
          expandedNodeId = null;
          btnInspectExpand.classList.remove('active');
          btnInspectExpand.textContent = '🌐 Раскрыть ящики';
        }} else {{
          expandedNodeId = selectedNode.id;
          expandedWingId = null;
          btnInspectExpand.classList.add('active');
          btnInspectExpand.textContent = 'Свернуть ящики';
          focusOnNode(selectedNode);
        }}
      }}
      const noteCards = inspectorNotes.querySelectorAll('.note-card');
      const isExp = (expandedNodeId === selectedNode.id || expandedWingId === selectedNode.id);
      noteCards.forEach(c => c.classList.toggle('expanded', isExp));
      draw();
    }};

    btnInspectFocus.onclick = () => {{
      if (!selectedNode) return;
      if (selectedNode.type === 'wing') focusOnWing(selectedNode);
      else focusOnNode(selectedNode);
    }};

    document.getElementById('inspector-close').onclick = () => {{
      inspector.style.display = 'none';
      selectedNode = null;
      expandedNodeId = null;
      expandedWingId = null;
      btnInspectExpand.classList.remove('active');
      draw();
    }};

    // Кнопки управления
    document.getElementById('btn-zoom-in').onclick = () => {{
      zoom = Math.min(4.5, zoom * 1.25);
      draw();
    }};
    document.getElementById('btn-zoom-out').onclick = () => {{
      zoom = Math.max(0.2, zoom / 1.25);
      draw();
    }};
    document.getElementById('btn-reset').onclick = () => {{
      zoom = 0.9;
      panX = width / 2 * (1 - zoom);
      panY = height / 2 * (1 - zoom);
      searchQuery = '';
      searchInput.value = '';
      showForgotten = false;
      document.getElementById('btn-forgotten').classList.remove('active');
      selectedNode = null;
      expandedNodeId = null;
      expandedWingId = null;
      btnInspectExpand.classList.remove('active');
      inspector.style.display = 'none';
      draw();
    }};

    document.getElementById('btn-forgotten').onclick = e => {{
      showForgotten = !showForgotten;
      e.target.classList.toggle('active', showForgotten);
      draw();
    }};

    document.getElementById('btn-export-png').onclick = () => {{
      const dataUrl = canvas.toDataURL('image/png');
      const a = document.createElement('a');
      a.href = dataUrl;
      a.download = 'palace-graph.png';
      a.click();
    }};

    // Поиск
    searchInput.addEventListener('input', e => {{
      searchQuery = e.target.value.trim().toLowerCase();
      draw();
    }});

    searchInput.addEventListener('keydown', e => {{
      if (e.key === 'Enter' && searchQuery) {{
        const found = nodes.find(n => n.label.toLowerCase().includes(searchQuery));
        if (found) {{
          selectNode(found);
          focusOnNode(found);
        }}
      }}
    }});

    // Атлас на мобилке
    const atlasToggleBtn = document.getElementById('atlas-toggle-btn');
    const atlasContainer = document.getElementById('atlas-container');
    atlasToggleBtn.onclick = () => {{
      atlasContainer.classList.toggle('mobile-open');
    }};

    // Клик по Атласу
    atlasCanvas.addEventListener('click', e => {{
      const rect = atlasCanvas.getBoundingClientRect();
      const ax = e.clientX - rect.left - 92;
      const ay = e.clientY - rect.top - 92;
      const dist = Math.hypot(ax, ay);
      let angle = Math.atan2(ay, ax);
      if (angle < 0) angle += 2 * Math.PI;

      const totalRooms = roomNodes.length || 1;
      let curAngle = 0;
      for (const w of wingNodes) {{
        const rooms = roomNodes.filter(r => r.wing === w.id);
        const wAngle = (rooms.length / totalRooms) * 2 * Math.PI;
        if (angle >= curAngle && angle < curAngle + wAngle) {{
          selectNode(w);
          focusOnNode(w);
          break;
        }}
        curAngle += wAngle;
      }}
    }});

    // Deep-links
    const urlParams = new URLSearchParams(window.location.search);
    const focusId = urlParams.get('focus');
    if (focusId && nodeMap.has(focusId)) {{
      const n = nodeMap.get(focusId);
      selectNode(n);
      focusOnNode(n);
    }}

    // Запуск
    resize();
    updateSpatialGrid();
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
    drawers_data: list[dict[str, Any]] | None = None,
) -> str:
    """Генерирует автономную интерактивную HTML-карту Дворца памяти."""
    nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []

    wing_dict = wings if isinstance(wings, dict) else {w: 0 for w in wings}
    total_records = sum(wing_dict.values())

    for wing_name, wing_records in wing_dict.items():
        nodes.append({
            "id": f"wing_{wing_name}",
            "label": wing_name,
            "type": "wing",
            "records": wing_records,
            "wing": wing_name,
        })

    total_rooms = 0
    for wing_name, rooms in rooms_by_wing.items():
        for room_name, room_cnt in rooms.items():
            total_rooms += 1
            room_id = f"room_{wing_name}_{room_name}"
            is_service = (room_name == "_registry") or (
                room_name == "general" and room_cnt > 500
            )
            nodes.append({
                "id": room_id,
                "label": room_name,
                "type": "room",
                "wing": f"wing_{wing_name}",
                "wing_name": wing_name,
                "records": room_cnt,
                "freshness": 0.5,
                "service": is_service,
                "tags": [],
                "notes": [],
            })
            links.append({
                "source": f"wing_{wing_name}",
                "target": room_id,
                "type": "containment",
            })

    for t in tunnels:
        src = t.get("source", {})
        dst = t.get("target", {})
        if isinstance(src, dict):
            src_id = f"room_{src.get('wing', '')}_{src.get('room', '')}"
        else:
            src_id = str(src)
        if isinstance(dst, dict):
            dst_id = f"room_{dst.get('wing', '')}_{dst.get('room', '')}"
        else:
            dst_id = str(dst)

        links.append({
            "source": src_id,
            "target": dst_id,
            "type": "tunnel",
            "weight": t.get("weight", 2),
            "reason": t.get("reason", t.get("label", "")),
        })

    # Если есть обогащенные данные из palace_graph_data.json, дополняем узлы тегами и заметками
    import os
    json_path = os.path.join(os.path.dirname(__file__), "..", "palace_graph_data.json")
    if os.path.exists(json_path) and len(nodes) > 10:
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            saved_nodes_map = {n["id"]: n for n in saved.get("nodes", [])}
            for n in nodes:
                s_node = saved_nodes_map.get(n["id"])
                if s_node:
                    n["tags"] = s_node.get("tags", [])
                    n["freshness"] = s_node.get("freshness", 0.5)
                    n["notes"] = [
                        {
                            "t": item["title"][:50],
                            "d": item.get("date", ""),
                            "p": (item.get("preview") or "")[:90],
                        }
                        for item in s_node.get("notes", [])[:35]
                    ]
        except Exception as e:
            logger.warning("[MAP] Ошибка дополнения заметок: %s", e)

    data = {"nodes": nodes, "links": links}
    palace_json = json.dumps(data, ensure_ascii=False)

    return PALACE_MAP_TEMPLATE.format(
        palace_name=palace_name,
        wing_count=len(wing_dict),
        room_count=total_rooms,
        record_count=total_records,
        tunnel_count=len(tunnels),
        palace_data_json=palace_json,
    )
