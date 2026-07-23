#!/bin/bash
# MemPalace Bot — Platypus Launcher (multi-column layout)
SCRIPTS_DIR="$HOME/Documents/mempalace_bot/_scripts"
ICON_TERM="<span style=\"font-size:11px;opacity:0.5\">🪟</span>"

cat << 'HTML'
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    font-family: -apple-system, 'Helvetica Neue', sans-serif;
    background: #0a0a0f;
    color: #e0e0e0;
    padding: 24px 32px;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }
  .header {
    margin-bottom: 24px;
    flex-shrink: 0;
  }
  .header h1 {
    font-size: 22px;
    font-weight: 700;
    letter-spacing: -0.3px;
    background: linear-gradient(135deg, #00d4ff, #7b2ff7);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }
  .columns {
    display: flex;
    gap: 20px;
    flex: 1;
    min-height: 0;
  }
  .column {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }
  .col-header {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    color: #444;
    padding-bottom: 8px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    margin-bottom: 8px;
    flex-shrink: 0;
  }
  .col-scroll {
    overflow-y: auto;
    flex: 1;
    min-height: 0;
    padding-right: 4px;
  }
  .card {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 7px 12px;
    margin-bottom: 4px;
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 8px;
    text-decoration: none;
    color: #b0b0b0;
    font-size: 12px;
    font-weight: 500;
    transition: all 0.2s ease;
  }
  .card:hover {
    background: rgba(0,212,255,0.08);
    border-color: rgba(0,212,255,0.2);
    color: #fff;
    transform: translateX(2px);
  }
  .card .nm {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .card .sym {
    font-size: 10px;
    opacity: 0.3;
    flex-shrink: 0;
  }
  ::-webkit-scrollbar { width: 4px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }
</style>
</head>
<body>
<div class="header">
  <h1>🧠 MemPalace Bot</h1>
</div>
<div class="columns">
HTML

# Column 1
echo '<div class="column">'
echo '<div class="col-header">🚀 Запуск</div>'
echo '<div class="col-scroll">'
for s in Ollama_Start start_bot PalaceManager_TelegrammBot KillPalaceBot Switch_AI setup_env RestoreConfig; do
  echo "<a class=\"card\" href=\"file://$SCRIPTS_DIR/${s}.command\"><span class=\"nm\">$s</span><span class=\"sym\">🪟</span></a>"
done
echo '</div></div>'

# Column 2
echo '<div class="column">'
echo '<div class="col-header">🧠 Память</div>'
echo '<div class="col-scroll">'
for s in update_memory update_memory_insights_research update_memory_wingMode check_memory clear_memory Ask_Memory Run_Extraction; do
  echo "<a class=\"card\" href=\"file://$SCRIPTS_DIR/${s}.command\"><span class=\"nm\">$s</span><span class=\"sym\">🪟</span></a>"
done
echo '</div></div>'

# Column 3
echo '<div class="column">'
echo '<div class="col-header">🔍 Инструменты</div>'
echo '<div class="col-scroll">'
for s in find_memory go_to_memory Archive_Chat Daily_Note; do
  echo "<a class=\"card\" href=\"file://$SCRIPTS_DIR/${s}.command\"><span class=\"nm\">$s</span><span class=\"sym\">🪟</span></a>"
done
echo '</div></div>'

# Column 4
echo '<div class="column">'
echo '<div class="col-header">⚙️ Обслуживание</div>'
echo '<div class="col-scroll">'
echo "<a class=\"card\" href=\"file://$SCRIPTS_DIR/Manage_Wechsel_Models.command\"><span class=\"nm\">Manage_Wechsel_Models</span><span class=\"sym\">🪟</span></a>"
echo "<a class=\"card\" href=\"file://$SCRIPTS_DIR/Ollama_Cleaner.command\"><span class=\"nm\">Ollama_Cleaner</span><span class=\"sym\">🪟</span></a>"
echo "<a class=\"card\" href=\"file://$SCRIPTS_DIR/import_notes.command\"><span class=\"nm\">import_notes</span><span class=\"sym\">🪟</span></a>"
echo '</div></div>'

cat << 'HTML'
</div>
</body>
</html>
HTML
echo "__WAIT__"
