#!/bin/bash
cd "$HOME/Documents/mempalace"
source venv/bin/activate
echo "======================================="
echo "   СОСТАВ ПАМЯТИ MEMPALACE"
echo "======================================="
python3 -m mempalace status
echo "---------------------------------------"
echo "ПРОИНДЕКСИРОВАННЫЕ ФАЙЛЫ В MY_NOTES:"
# Просто выводим список файлов в папке, которые видит система
ls -R my_notes
echo "---------------------------------------"
echo "Нажмите Enter для выхода..."
read
