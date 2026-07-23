#!/bin/bash
cd "$(dirname "$0")"

MSG=$(osascript -e 'display dialog "Опишите, что изменили:" default answer "" with title "Обновление GitHub" buttons {"Отмена", "OK"} default button 2' -e 'text returned of result' 2>/dev/null)

if [ $? -ne 0 ] || [ -z "$MSG" ]; then
    osascript -e 'display dialog "❌ Отменено" buttons {"OK"} default button 1 with icon note'
    exit 0
fi

git add -A
git commit -m "$MSG"
git push

if [ $? -eq 0 ]; then
    osascript -e 'display dialog "✅ Проект обновлён на GitHub" buttons {"OK"} default button 1 with icon note'
else
    osascript -e 'display dialog "❌ Ошибка при отправке" buttons {"OK"} default button 1'
fi
