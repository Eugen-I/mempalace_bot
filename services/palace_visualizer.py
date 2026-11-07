"""services/palace_visualizer.py
Генератор интерактивной визуальной 3D/2D HTML-карты Дворца памяти.

Создает автономный HTML5-виджет с визуализацией:
- 3D-пространственная карта Чертогов с орбитальным вращением и перспективой
- Крыльев (крупные световые сферы-хабы)
- Комнат (орбитальные сферические узлы с метриками записей)
- Туннелей (светящиеся 3D-лучи межкомнатных связей с метками)
- Поиском, зумом, панорамированием, авто-вращением и детальной панелью.
- 100% автономный: работает офлайн без внешних CDN в Chrome, Safari, Firefox.
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
  <title>{palace_name} — 3D Интерактивная карта</title>
  <style>
    :root {{
      --bg: #070a0f;
      --panel-bg: rgba(15, 23, 42, 0.85);
      --text: #f1f5f9;
      --text-muted: #94a3b8;
      --border: rgba(148, 163, 184, 0.2);
      --accent: #38bdf8;
      --tunnel: #fb923c;
      --wing: #c084fc;
      --room: #4ade80;
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
      user-select: none;
    }}
    #header {{
      position: absolute;
      top: 16px;
      left: 16px;
      z-index: 10;
      background: var(--panel-bg);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px 20px;
      display: flex;
      gap: 14px;
      align-items: center;
      box-shadow: 0 8px 32px rgba(0,0,0,0.6);
    }}
    h1 {{ font-size: 15px; font-weight: 600; display: flex; align-items: center; gap: 8px; }}
    .badge {{
      background: rgba(56, 189, 248, 0.15);
      color: var(--accent);
      padding: 3px 10px;
      border-radius: 20px;
      font-size: 12px;
      font-weight: 500;
    }}
    #search {{
      background: rgba(15, 23, 42, 0.7);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 6px 12px;
      border-radius: 8px;
      outline: none;
      font-size: 13px;
      width: 210px;
      transition: border-color 0.2s, box-shadow 0.2s;
    }}
    #search:focus {{
      border-color: var(--accent);
      box-shadow: 0 0 10px rgba(56, 189, 248, 0.3);
    }}
    #controls {{
      position: absolute;
      bottom: 24px;
      right: 24px;
      z-index: 10;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}
    .btn {{
      background: var(--panel-bg);
      backdrop-filter: blur(10px);
      -webkit-backdrop-filter: blur(10px);
      border: 1px solid var(--border);
      color: var(--text);
      min-width: 40px;
      height: 40px;
      padding: 0 8px;
      border-radius: 10px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 16px;
      box-shadow: 0 4px 16px rgba(0,0,0,0.4);
      transition: all 0.2s;
    }}
    .btn:hover {{
      background: rgba(30, 41, 59, 0.95);
      border-color: var(--accent);
      transform: translateY(-1px);
    }}
    .btn.active {{
      background: rgba(56, 189, 248, 0.25);
      border-color: var(--accent);
      color: var(--accent);
    }}
    #info-panel {{
      position: absolute;
      top: 16px;
      right: 16px;
      width: 320px;
      background: var(--panel-bg);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 18px;
      z-index: 10;
      display: none;
      box-shadow: 0 12px 36px rgba(0,0,0,0.6);
      max-height: calc(100vh - 120px);
      overflow-y: auto;
    }}
    #info-title {{ font-size: 16px; font-weight: 600; margin-bottom: 8px; }}
    #info-desc {{
      font-size: 13px;
      color: var(--text-muted);
      line-height: 1.5;
      white-space: pre-line;
    }}
    #info-close {{
      position: absolute;
      top: 12px;
      right: 14px;
      background: none;
      border: none;
      color: var(--text-muted);
      font-size: 18px;
      cursor: pointer;
    }}
    #info-close:hover {{ color: var(--text); }}
    #graph-canvas {{
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      display: block;
    }}
    #hint {{
      position: absolute;
      bottom: 24px;
      left: 24px;
      font-size: 12px;
      color: var(--text-muted);
      pointer-events: none;
      z-index: 5;
      background: rgba(15, 23, 42, 0.6);
      padding: 6px 12px;
      border-radius: 8px;
      border: 1px solid rgba(148, 163, 184, 0.15);
    }}
  </style>
</head>
<body>
  <div id="header">
    <h1>🏰 {palace_name}</h1>
    <span class="badge">Крыльев: {wing_count}</span>
    <span class="badge">Комнат: {room_count}</span>
    <span class="badge">Туннелей: {tunnel_count}</span>
    <input type="text" id="search" placeholder="🔍 Поиск комнат и крыльев..." />
  </div>

  <div id="info-panel">
    <button id="info-close">&times;</button>
    <div id="info-title"></div>
    <div id="info-desc"></div>
  </div>

  <div id="controls">
    <button class="btn active" id="toggle-3d" title="Режим 3D Космос / 2D Схема">🌐 3D</button>
    <button class="btn active" id="toggle-rotate" title="Авто-вращение 3D">🔄</button>
    <button class="btn" id="zoom-in" title="Приблизить">+</button>
    <button class="btn" id="zoom-out" title="Отдалить">−</button>
    <button class="btn" id="reset-view" title="Сбросить вид">⟲</button>
  </div>

  <div id="hint">🖱️ Левая кнопка: вращение 3D | Колёсико: зум | Правая / Shift: перемещение</div>

  <canvas id="graph-canvas"></canvas>

  <script>
    const data = {graph_data_json};

    const canvas = document.getElementById('graph-canvas');
    const ctx = canvas.getContext('2d');
    const searchInput = document.getElementById('search');
    const infoPanel = document.getElementById('info-panel');
    const infoTitle = document.getElementById('info-title');
    const infoDesc = document.getElementById('info-desc');
    const infoClose = document.getElementById('info-close');
    const btnToggle3D = document.getElementById('toggle-3d');
    const btnToggleRotate = document.getElementById('toggle-rotate');

    let width, height, dpr;
    function resize() {{
      dpr = window.devicePixelRatio || 1;
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }}
    window.addEventListener('resize', resize);
    resize();

    let is3D = true;
    let autoRotate = true;
    let rotX = 0.35;
    let rotY = 0.5;
    let rotZ = 0;
    let velRotX = 0;
    let velRotY = 0;
    let zoom = 1.0;
    let panX = 0;
    let panY = 0;

    let isDragging = false;
    let isPanning = false;
    let lastMouseX = 0;
    let lastMouseY = 0;
    let hoveredNode = null;
    let selectedNode = null;
    let searchQuery = '';
    let animTime = 0;

    // Palette per wing
    const PALETTE = [
      '#a855f7', '#38bdf8', '#34d399', '#fbbf24',
      '#f43f5e', '#ec4899', '#6366f1', '#14b8a6',
      '#f97316', '#84cc16', '#06b6d4', '#eab308'
    ];
    const wingColorMap = {{}};

    const nodes = data.nodes || [];
    const links = data.links || [];

    const wingNodes = nodes.filter(n => n.type === 'wing');
    wingNodes.forEach((w, idx) => {{
      wingColorMap[w.id] = PALETTE[idx % PALETTE.length];
    }});

    // 3D Spatial Layout
    const wingRadius = Math.min(width, height) * 0.42;
    wingNodes.forEach((w, idx) => {{
      const angle = (idx / (wingNodes.length || 1)) * 2 * Math.PI;
      const elevation = Math.sin(idx * 2) * 80;
      w.x3D = Math.cos(angle) * wingRadius;
      w.z3D = Math.sin(angle) * wingRadius;
      w.y3D = elevation;
      w.color = wingColorMap[w.id] || '#c084fc';

      const rooms = nodes.filter(r => r.type === 'room' && r.wing === w.id);
      const roomOrbitRadius = 90 + Math.min(rooms.length * 4, 180);
      rooms.forEach((r, rIdx) => {{
        const rAngle = (rIdx / (rooms.length || 1)) * 2 * Math.PI;
        const tilt = ((rIdx % 5) - 2) * 0.35;
        r.x3D = w.x3D + Math.cos(rAngle) * roomOrbitRadius;
        r.z3D = w.z3D + Math.sin(rAngle) * roomOrbitRadius * Math.cos(tilt);
        r.y3D = w.y3D + Math.sin(rAngle) * roomOrbitRadius * Math.sin(tilt);
        r.color = w.color;
      }});
    }});

    // Ambient 3D Starfield particles
    const stars = [];
    for (let i = 0; i < 140; i++) {{
      const rad = 400 + Math.random() * 900;
      const theta = Math.random() * 2 * Math.PI;
      const phi = (Math.random() - 0.5) * Math.PI;
      stars.push({{
        x: rad * Math.cos(phi) * Math.cos(theta),
        y: rad * Math.sin(phi),
        z: rad * Math.cos(phi) * Math.sin(theta),
        size: 0.8 + Math.random() * 1.5,
        alpha: 0.2 + Math.random() * 0.6
      }});
    }}

    function project(x, y, z) {{
      if (!is3D) {{
        return {{
          x: width / 2 + (x + panX) * zoom * 0.8,
          y: height / 2 + (y + panY) * zoom * 0.8,
          z: 0,
          scale: zoom * 0.8,
          visible: true
        }};
      }}

      // Rotate Y
      const cosY = Math.cos(rotY), sinY = Math.sin(rotY);
      const x1 = x * cosY + z * sinY;
      const z1 = -x * sinY + z * cosY;

      // Rotate X
      const cosX = Math.cos(rotX), sinX = Math.sin(rotX);
      const y2 = y * cosX - z1 * sinX;
      const z2 = y * sinX + z1 * cosX;

      const fov = 750;
      const depth = fov + z2 * zoom;
      if (depth <= 15) return {{ x: -9999, y: -9999, z: -9999, scale: 0, visible: false }};
      const scale = (fov / depth) * zoom;

      return {{
        x: width / 2 + (x1 + panX) * scale,
        y: height / 2 + (y2 + panY) * scale,
        z: z2,
        scale: scale,
        visible: true
      }};
    }}

    function draw() {{
      animTime += 0.02;

      if (autoRotate && !isDragging && !isPanning && is3D) {{
        rotY += 0.0018;
      }} else {{
        rotY += velRotY;
        rotX += velRotX;
        velRotY *= 0.92;
        velRotX *= 0.92;
      }}

      ctx.clearRect(0, 0, width, height);

      // Deep Space background gradient
      const maxDim = Math.max(width, height) * 0.7;
      const bgGrad = ctx.createRadialGradient(
        width / 2, height / 2, 50, width / 2, height / 2, maxDim
      );
      bgGrad.addColorStop(0, '#0c1222');
      bgGrad.addColorStop(1, '#05070a');
      ctx.fillStyle = bgGrad;
      ctx.fillRect(0, 0, width, height);

      // 1. Draw Starfield
      if (is3D) {{
        stars.forEach(st => {{
          const p = project(st.x, st.y, st.z);
          if (p.visible && p.x >= 0 && p.x <= width && p.y >= 0 && p.y <= height) {{
            ctx.beginPath();
            ctx.arc(p.x, p.y, st.size * p.scale, 0, 2 * Math.PI);
            ctx.fillStyle = `rgba(255, 255, 255, ${{st.alpha * Math.min(1, p.scale)}})`;
            ctx.fill();
          }}
        }});
      }}

      // Project all nodes
      nodes.forEach(n => {{
        n.proj = project(n.x3D || 0, n.y3D || 0, n.z3D || 0);
      }});

      // Collect render items for depth sorting
      const renderItems = [];

      // Links
      links.forEach(link => {{
        const src = nodes.find(n => n.id === link.source);
        const tgt = nodes.find(n => n.id === link.target);
        if (!src || !tgt || !src.proj.visible || !tgt.proj.visible) return;
        renderItems.push({{
          type: 'link',
          z: (src.proj.z + tgt.proj.z) / 2,
          src: src.proj,
          tgt: tgt.proj,
          linkType: link.type,
          label: link.label || '',
          srcNode: src,
          tgtNode: tgt
        }});
      }});

      // Nodes
      nodes.forEach(node => {{
        if (!node.proj.visible) return;
        renderItems.push({{
          type: 'node',
          z: node.proj.z,
          node: node,
          proj: node.proj
        }});
      }});

      // Depth sort: furthest first
      renderItems.sort((a, b) => b.z - a.z);

      // Render sorted items
      renderItems.forEach(item => {{
        if (item.type === 'link') {{
          const isTunnel = item.linkType === 'tunnel';
          const isHighlighted = (
            (hoveredNode && (item.srcNode === hoveredNode || item.tgtNode === hoveredNode)) ||
            (selectedNode && (item.srcNode === selectedNode || item.tgtNode === selectedNode))
          );

          ctx.beginPath();
          ctx.moveTo(item.src.x, item.src.y);
          ctx.lineTo(item.tgt.x, item.tgt.y);

          if (isTunnel) {{
            ctx.strokeStyle = isHighlighted ? '#fb923c' : 'rgba(251, 146, 60, 0.65)';
            ctx.lineWidth = (isHighlighted ? 3.5 : 2.0) * Math.max(0.6, item.src.scale);
            ctx.setLineDash([8, 6]);
            ctx.lineDashOffset = -animTime * 15;
          }} else {{
            ctx.strokeStyle = isHighlighted
              ? 'rgba(56, 189, 248, 0.7)'
              : 'rgba(56, 189, 248, 0.18)';
            ctx.lineWidth = (isHighlighted ? 2.0 : 1.0) * Math.max(0.5, item.src.scale);
            ctx.setLineDash([]);
          }}
          ctx.stroke();
          ctx.setLineDash([]);

          // Tunnel label in 3D
          if (isTunnel && item.label && (isHighlighted || item.src.scale > 0.8)) {{
            const mx = (item.src.x + item.tgt.x) / 2;
            const my = (item.src.y + item.tgt.y) / 2;
            ctx.fillStyle = '#fb923c';
            ctx.font = '10px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(`⚡ ${{item.label}}`, mx, my - 6);
          }}
        }} else if (item.type === 'node') {{
          const n = item.node;
          const p = item.proj;
          const isHovered = (hoveredNode === n);
          const isSelected = (selectedNode === n);
          const isMatch = searchQuery && n.label.toLowerCase().includes(searchQuery);

          const isWing = n.type === 'wing';
          const baseRadius = isWing ? 22 : (8 + Math.min(n.records || 1, 14));
          const r = Math.max(4, baseRadius * p.scale * (isHovered || isSelected ? 1.25 : 1.0));

          // 3D Spherical Radial Gradient
          const lightX = p.x - r * 0.35;
          const lightY = p.y - r * 0.35;
          const sphereGrad = ctx.createRadialGradient(lightX, lightY, r * 0.1, p.x, p.y, r);

          if (isMatch) {{
            sphereGrad.addColorStop(0, '#ffffff');
            sphereGrad.addColorStop(0.3, '#fde047');
            sphereGrad.addColorStop(1, '#ca8a04');
          }} else if (isWing) {{
            sphereGrad.addColorStop(0, '#ffffff');
            sphereGrad.addColorStop(0.3, n.color || '#c084fc');
            sphereGrad.addColorStop(1, '#581c87');
          }} else {{
            sphereGrad.addColorStop(0, '#ffffff');
            sphereGrad.addColorStop(0.3, n.color || '#4ade80');
            sphereGrad.addColorStop(1, '#064e3b');
          }}

          // Glowing Halo for active / hovered
          if (isHovered || isSelected || isMatch) {{
            ctx.beginPath();
            ctx.arc(p.x, p.y, r + 6 * p.scale, 0, 2 * Math.PI);
            ctx.fillStyle = isMatch ? 'rgba(253, 224, 71, 0.3)' : 'rgba(56, 189, 248, 0.35)';
            ctx.fill();
          }}

          // Sphere body
          ctx.beginPath();
          ctx.arc(p.x, p.y, r, 0, 2 * Math.PI);
          ctx.fillStyle = sphereGrad;
          ctx.fill();
          ctx.strokeStyle = isHovered || isSelected ? '#ffffff' : 'rgba(255, 255, 255, 0.35)';
          ctx.lineWidth = (isHovered || isSelected ? 2.5 : 1.0) * p.scale;
          ctx.stroke();

          // Label
          if (p.scale > 0.45 || isWing || isHovered || isSelected || isMatch) {{
            ctx.fillStyle = isMatch ? '#fde047' : '#f8fafc';
            ctx.font = isWing
              ? `bold ${{Math.max(10, Math.round(13 * p.scale))}}px -apple-system, sans-serif`
              : `${{Math.max(9, Math.round(11 * p.scale))}}px -apple-system, sans-serif`;
            ctx.textAlign = 'center';
            ctx.shadowColor = 'rgba(0, 0, 0, 0.85)';
            ctx.shadowBlur = 6;
            ctx.fillText(n.label, p.x, p.y + r + (isWing ? 14 : 11) * p.scale);
            ctx.shadowBlur = 0;
          }}
        }}
      }});

      requestAnimationFrame(draw);
    }}

    // Mouse & Touch Interaction
    canvas.addEventListener('mousedown', e => {{
      if (e.button === 2 || e.shiftKey) {{
        isPanning = true;
      }} else {{
        isDragging = true;
        autoRotate = false;
        btnToggleRotate.classList.remove('active');
      }}
      lastMouseX = e.clientX;
      lastMouseY = e.clientY;
    }});

    window.addEventListener('mouseup', () => {{
      isDragging = false;
      isPanning = false;
    }});

    canvas.addEventListener('contextmenu', e => e.preventDefault());

    canvas.addEventListener('mousemove', e => {{
      const dx = e.clientX - lastMouseX;
      const dy = e.clientY - lastMouseY;
      lastMouseX = e.clientX;
      lastMouseY = e.clientY;

      if (isDragging) {{
        velRotY = dx * 0.005;
        velRotX = dy * 0.005;
        rotY += velRotY;
        rotX += velRotX;
        rotX = Math.max(-Math.PI / 2 + 0.05, Math.min(Math.PI / 2 - 0.05, rotX));
      }} else if (isPanning) {{
        panX += dx / (zoom * 0.8);
        panY += dy / (zoom * 0.8);
      }}

      // Find hovered node
      hoveredNode = nodes.find(n => {{
        if (!n.proj || !n.proj.visible) return false;
        const r = (n.type === 'wing' ? 24 : 16) * n.proj.scale;
        const distSq = (n.proj.x - e.clientX) ** 2 + (n.proj.y - e.clientY) ** 2;
        return distSq <= Math.max(r * r, 144);
      }}) || null;

      canvas.style.cursor = hoveredNode ? 'pointer' : (isDragging ? 'grabbing' : 'grab');
    }});

    canvas.addEventListener('click', e => {{
      if (hoveredNode) {{
        selectedNode = hoveredNode;
        showInfoPanel(selectedNode);
      }}
    }});

    function showInfoPanel(n) {{
      infoPanel.style.display = 'block';
      if (n.type === 'wing') {{
        infoTitle.textContent = '🏛️ Крыло: ' + n.label;
        const rooms = nodes.filter(r => r.type === 'room' && r.wing === n.id);
        const total = rooms.reduce((acc, r) => acc + (r.records || 0), 0) || (n.records || 0);
        infoDesc.textContent =
          `Всего комнат: ${{rooms.length}}\\n` +
          `Всего записей: ${{total}}\\n\\n` +
          `Комнаты крыла:\\n` +
          rooms.slice(0, 15).map(r => `• ${{r.label}} (${{r.records || 0}})`).join('\\n') +
          (rooms.length > 15 ? `\\n… и ещё ${{rooms.length - 15}} комнат` : '');
      }} else {{
        infoTitle.textContent = '🚪 Комната: ' + n.label;
        const wing = wingNodes.find(w => w.id === n.wing);
        const wingName = wing ? wing.label : n.wing;
        const connectedTunnels = links.filter(
          l => l.type === 'tunnel' && (l.source === n.id || l.target === n.id)
        );
        let tunStr = '';
        if (connectedTunnels.length > 0) {{
          tunStr = '\\n\\n🔗 Связанные туннели:\\n' +
            connectedTunnels.map(l => `• ${{l.label || 'Связь'}}`).join('\\n');
        }}
        infoDesc.textContent =
          `Крыло: ${{wingName}}\\n` +
          `Записей в комнате: ${{n.records || 0}}` +
          tunStr;
      }}
    }}

    infoClose.onclick = () => {{
      infoPanel.style.display = 'none';
      selectedNode = null;
    }};

    canvas.addEventListener('wheel', e => {{
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.12 : 0.88;
      zoom = Math.max(0.15, Math.min(4.0, zoom * factor));
    }}, {{ passive: false }});

    // Touch support for iPad / Trackpads
    let touchStartDist = 0;
    canvas.addEventListener('touchstart', e => {{
      if (e.touches.length === 1) {{
        isDragging = true;
        autoRotate = false;
        btnToggleRotate.classList.remove('active');
        lastMouseX = e.touches[0].clientX;
        lastMouseY = e.touches[0].clientY;
      }} else if (e.touches.length === 2) {{
        touchStartDist = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY
        );
      }}
    }});

    canvas.addEventListener('touchmove', e => {{
      if (e.touches.length === 1 && isDragging) {{
        const dx = e.touches[0].clientX - lastMouseX;
        const dy = e.touches[0].clientY - lastMouseY;
        lastMouseX = e.touches[0].clientX;
        lastMouseY = e.touches[0].clientY;
        rotY += dx * 0.005;
        rotX += dy * 0.005;
      }} else if (e.touches.length === 2) {{
        const dist = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY
        );
        if (touchStartDist > 0) {{
          zoom *= dist / touchStartDist;
          zoom = Math.max(0.15, Math.min(4.0, zoom));
        }}
        touchStartDist = dist;
      }}
    }});

    canvas.addEventListener('touchend', () => {{
      isDragging = false;
      touchStartDist = 0;
    }});

    btnToggle3D.onclick = () => {{
      is3D = !is3D;
      btnToggle3D.textContent = is3D ? '🌐 3D' : '🗺️ 2D';
      btnToggle3D.classList.toggle('active', is3D);
    }};

    btnToggleRotate.onclick = () => {{
      autoRotate = !autoRotate;
      btnToggleRotate.classList.toggle('active', autoRotate);
    }};

    document.getElementById('zoom-in').onclick = () => {{
      zoom = Math.min(4.0, zoom * 1.25);
    }};
    document.getElementById('zoom-out').onclick = () => {{
      zoom = Math.max(0.15, zoom / 1.25);
    }};
    document.getElementById('reset-view').onclick = () => {{
      rotX = 0.35;
      rotY = 0.5;
      zoom = 1.0;
      panX = 0;
      panY = 0;
      velRotX = 0;
      velRotY = 0;
      searchInput.value = '';
      searchQuery = '';
      infoPanel.style.display = 'none';
      selectedNode = null;
    }};

    searchInput.addEventListener('input', e => {{
      searchQuery = e.target.value.trim().toLowerCase();
      if (searchQuery) {{
        const found = nodes.find(n => n.label.toLowerCase().includes(searchQuery));
        if (found) {{
          showInfoPanel(found);
          selectedNode = found;
          if (is3D) {{
            // Rotate towards node
            const targetAngle = Math.atan2(found.x3D, found.z3D);
            rotY = targetAngle;
          }} else {{
            panX = -(found.x3D || 0);
            panY = -(found.y3D || 0);
          }}
        }}
      }}
    }});

    requestAnimationFrame(draw);
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
    """Генерирует автономную интерактивную 3D/2D HTML-карту Дворца памяти."""
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
