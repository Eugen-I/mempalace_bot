#!/usr/bin/env python3
"""Обновляет wing-метаданные всех drawers в ChromaDB по таблице room→wing."""

import os, sys, json, time

sys.path.insert(0, os.path.expanduser("~/Documents/mempalace"))
os.environ["PALACE_DIR"] = os.path.expanduser("~/.mempalace/palace")

import chromadb

ROOM_WING = {
    'философия': 'philosophy',
    'мысли_из_книг': 'philosophy',
    'высказывание': 'philosophy',
    'сны_и_отрывки_снов': 'dreams',
    'мои_стихи': 'creative',
    'сценарии': 'creative',
    'манифесты': 'creative',
    'идеи': 'creative',
    'названия_фото': 'photography',
    'экспликации_к_фотографиям': 'photography',
    'фотографы': 'photography',
    'фототрансцендентная_терапия': 'photography',
    'идеи_для_фотопроектов_с_chatgpt': 'photography',
    'кураторский_текст': 'photography',
    'расходы_на_выставку': 'photography',
    'проект_архитипы_юнга_социальная_маска': 'psychology',
    'архитипы': 'psychology',
    'цитаты_юнга_по_архитирам': 'psychology',
    'психоаналитическая_модель_опыта_в_творчестве_фотографа': 'psychology',
    'визуальный_дневник_b_элементов_и_a_функций': 'psychology',
    'заметки_для_докторской_диссертации': 'personal',
    'мои_мысли_и_размышления': 'personal',
    'тренировки': 'personal',
    'daily': 'personal',
    'it_разработка': 'tech',
    'project_mask': 'projects',
    'general': 'my_notes',
}

client = chromadb.PersistentClient(path=os.environ["PALACE_DIR"])
col = client.get_or_create_collection('mempalace_drawers')

print(f"Drawers in DB: {col.count()}")

offset = 0
batch_size = 200
updated = 0

while True:
    batch = col.get(limit=batch_size, offset=offset, include=['metadatas'])
    if not batch['ids']:
        break
    ids = batch['ids']
    metas = batch['metadatas']
    
    new_metas = []
    for m in metas:
        room = m.get('room', '')
        new_wing = ROOM_WING.get(room, 'my_notes')
        m['wing'] = new_wing
        new_metas.append(m)
    
    col.update(ids=ids, metadatas=new_metas)
    updated += len(ids)
    offset += len(ids)
    print(f"  Updated {updated}/{col.count()}")

print(f"\nDone! Total updated: {updated}")
