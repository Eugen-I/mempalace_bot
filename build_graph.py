#!/usr/bin/env python3
"""build_graph.py — Офлайн-скрипт анализа текстов MemPalace и генерации графа знаний.

Вычисляет TF-IDF по всем комнатам Дворца памяти, извлекает ключевые сущности,
находит межкрыльевые туннели (Jaccard >= 0.18 ИЛИ cosine >= 0.30, weight >= 2),
формирует tunnels.json и генерирует автономный файл palace-graph.html.

Работает детерминированно, без GPU и без внешних сетевых API.
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from typing import Any

# Список стоп-слов (русский + английский)
STOPWORDS_RU = {
    "это", "как", "так", "все", "она", "также", "тоже", "когда", "даже", "для",
    "что", "или", "если", "уже", "где", "там", "тут", "вот", "после", "под",
    "над", "между", "через", "без", "против", "перед", "при", "про", "чем",
    "тем", "сам", "самый", "этот", "эта", "эти", "тот", "кто", "чей", "свой",
    "своя", "свое", "свои", "себе", "собой", "очень", "еще", "более", "менее",
    "много", "мало", "один", "два", "три", "первый", "второй", "третий", "быть",
    "был", "была", "было", "были", "будет", "будут", "есть", "нет", "можно",
    "нельзя", "надо", "нужно", "мочь", "может", "могут", "стал", "стала",
    "стало", "стали", "станет", "иметь", "имеет", "делать", "делает", "сказать",
    "говорит", "время", "года", "день", "люди", "дело", "жизнь", "работа",
    "слово", "конец", "начало", "потом", "поэтому", "потому", "зачем", "почему",
    "какой", "какая", "какие", "какое", "было", "себя", "только", "всего",
    "друг", "другой", "другие", "другая", "другое", "хотя", "ведь", "почти",
    "раз", "раза", "вдруг", "сейчас", "всегда", "никогда", "лишь", "чуть",
}

STOPWORDS_EN = {
    "the", "be", "to", "of", "and", "that", "have", "with", "this", "from",
    "they", "will", "would", "there", "their", "what", "about", "which",
    "when", "make", "can", "like", "time", "just", "know", "take", "people",
    "into", "year", "your", "good", "some", "could", "them", "other", "than",
    "then", "now", "look", "only", "come", "its", "over", "think", "also",
    "back", "after", "use", "two", "how", "our", "work", "first", "well",
    "way", "even", "new", "want", "because", "any", "these", "give", "most",
}

ALL_STOPWORDS = STOPWORDS_RU | STOPWORDS_EN

TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ]{3,}")

# Нормализация синонимичных крыльев для исключения ложных туннелей внутри одной темы
WING_NORMALIZATION_MAP = {
    "philosophy": "философия",
    "философия": "философия",
    "psychology": "психология",
    "психология": "психология",
    "projects": "проекты",
    "general": "общие",
    "insights": "инсайты",
    "deutsch": "deutsch",
    "творчество": "творчество",
    "литература": "литература",
    "фотография": "фотография",
    "работа": "работа",
    "личные_мысли": "личные_мысли",
    "сны": "сны",
}


def normalize_wing_family(wing_name: str) -> str:
    """Возвращает нормализованную семью крыла для проверки межкрыльевой связи."""
    low = (wing_name or "").strip().lower()
    return WING_NORMALIZATION_MAP.get(low, low)


def tokenize(text: str) -> list[str]:
    """Разбивает текст на слова >= 3 символов без цифр и стоп-слов."""
    if not text:
        return []
    words = TOKEN_RE.findall(text.lower())
    return [w for w in words if w not in ALL_STOPWORDS and not w.isdigit()]


def load_drawers_from_chroma(chroma_path: str) -> list[dict[str, Any]]:
    """Загружает ящики напрямую из локальной базы ChromaDB."""
    try:
        import chromadb
    except ImportError:
        print("Ошибка: chromadb не установлен. Укажите --input для чтения JSON.")
        sys.exit(1)

    expanded_path = os.path.expanduser(chroma_path)
    if not os.path.isdir(expanded_path):
        raise FileNotFoundError(f"Каталог Chroma не найден: {expanded_path}")

    client = chromadb.PersistentClient(path=expanded_path)
    col = client.get_collection("mempalace_drawers")
    raw = col.get(include=["metadatas", "documents"])

    items: list[dict[str, Any]] = []
    ids = raw.get("ids", [])
    metas = raw.get("metadatas", [])
    docs = raw.get("documents", [])

    for i, did in enumerate(ids):
        m = metas[i] if i < len(metas) and metas[i] else {}
        d = docs[i] if i < len(docs) and docs[i] else ""
        items.append({
            "id": did,
            "wing": m.get("wing") or "general",
            "room": m.get("room") or "general",
            "source_file": m.get("source_file") or "",
            "filed_at": m.get("filed_at") or "",
            "content": d,
        })
    return items


def load_drawers_from_file(file_path: str) -> list[dict[str, Any]]:
    """Загружает ящики из файла JSON или JSONL."""
    expanded_path = os.path.expanduser(file_path)
    if not os.path.isfile(expanded_path):
        raise FileNotFoundError(f"Файл не найден: {expanded_path}")

    with open(expanded_path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    if content.startswith("["):
        return json.loads(content)

    items = []
    for line in content.splitlines():
        line = line.strip()
        if line:
            items.append(json.loads(line))
    return items


def calculate_room_entities_and_tfidf(
    rooms_data: dict[str, dict[str, Any]],
) -> tuple[dict[str, list[str]], dict[str, dict[str, float]]]:
    """Вычисляет TF-IDF для всех комнат и выделяет топ-8 ключевых сущностей."""
    num_rooms = len(rooms_data)
    room_term_counts: dict[str, Counter[str]] = {}
    doc_freq: Counter[str] = Counter()

    for r_id, r_info in rooms_data.items():
        all_text = " ".join(r_info["texts"])
        tokens = tokenize(all_text)
        cnt = Counter(tokens)
        room_term_counts[r_id] = cnt
        for term in cnt.keys():
            doc_freq[term] += 1

    room_top_entities: dict[str, list[str]] = {}
    room_vectors: dict[str, dict[str, float]] = {}

    for r_id, cnt in room_term_counts.items():
        total_terms = sum(cnt.values()) or 1
        tfidf_scores: dict[str, float] = {}
        for term, freq in cnt.items():
            # TF: логарифмическая частота термина
            tf = freq / total_terms
            # IDF: сглаженный обратный индекс документа
            df = doc_freq[term]
            idf = math.log((1 + num_rooms) / (1 + df)) + 1.0
            tfidf_scores[term] = tf * idf

        # Сортировка по TF-IDF и отбор топ-8 сущностей
        top_terms = sorted(tfidf_scores.items(), key=lambda x: -x[1])[:8]
        room_top_entities[r_id] = [t[0] for t in top_terms]
        room_vectors[r_id] = dict(top_terms)

    return room_top_entities, room_vectors


def cosine_similarity(v1: dict[str, float], v2: dict[str, float]) -> float:
    """Вычисляет косинусное сходство между двумя векторами TF-IDF."""
    common_keys = set(v1.keys()) & set(v2.keys())
    if not common_keys:
        return 0.0
    dot_product = sum(v1[k] * v2[k] for k in common_keys)
    norm1 = math.sqrt(sum(val * val for val in v1.values()))
    norm2 = math.sqrt(sum(val * val for val in v2.values()))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot_product / (norm1 * norm2)


def compute_tunnels(
    rooms_data: dict[str, dict[str, Any]],
    room_top_entities: dict[str, list[str]],
    room_vectors: dict[str, dict[str, float]],
) -> list[dict[str, Any]]:
    """Находит сильные семантические туннели между комнатами разных крыльев."""
    room_ids = list(rooms_data.keys())
    candidate_links: list[dict[str, Any]] = []

    # Карта туннелей по комнатам для контроля лимита (макс 3 на комнату)
    room_tunnels: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for i in range(len(room_ids)):
        r1_id = room_ids[i]
        w1_family = rooms_data[r1_id]["wing_family"]
        e1 = set(room_top_entities.get(r1_id, []))
        v1 = room_vectors.get(r1_id, {})

        for j in range(i + 1, len(room_ids)):
            r2_id = room_ids[j]
            w2_family = rooms_data[r2_id]["wing_family"]

            # Исключаем связи внутри одного крыла / нормализованного семейства
            if w1_family == w2_family:
                continue

            e2 = set(room_top_entities.get(r2_id, []))
            v2 = room_vectors.get(r2_id, {})

            shared_entities = e1 & e2
            weight = len(shared_entities)
            if weight < 2:
                continue

            union_len = len(e1 | e2) or 1
            jaccard = weight / union_len
            cosine = cosine_similarity(v1, v2)

            if jaccard >= 0.18 or cosine >= 0.30:
                top_shared = sorted(
                    shared_entities,
                    key=lambda t: (v1.get(t, 0) + v2.get(t, 0)),
                    reverse=True,
                )[:3]
                reason = ", ".join(top_shared)
                link = {
                    "source": r1_id,
                    "target": r2_id,
                    "type": "tunnel",
                    "weight": weight,
                    "jaccard": round(jaccard, 3),
                    "cosine": round(cosine, 3),
                    "reason": reason,
                }
                candidate_links.append(link)

    # Ограничение: не более 3 сильнейших туннелей на комнату
    candidate_links.sort(key=lambda x: (x["weight"], x["cosine"]), reverse=True)

    selected_links: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()

    for link in candidate_links:
        src = link["source"]
        dst = link["target"]
        pair = (min(src, dst), max(src, dst))
        if pair in seen_pairs:
            continue
        if len(room_tunnels[src]) >= 3 or len(room_tunnels[dst]) >= 3:
            continue

        seen_pairs.add(pair)
        room_tunnels[src].append(link)
        room_tunnels[dst].append(link)
        selected_links.append({
            "source": src,
            "target": dst,
            "type": "tunnel",
            "weight": link["weight"],
            "reason": link["reason"],
        })

    return selected_links


def build_graph_model(
    drawers: list[dict[str, Any]],
) -> dict[str, Any]:
    """Строит полную графовую модель (узлы, связи, свежесть, списки заметок)."""
    # 1. Группировка ящиков по комнатам и крыльям
    wings_records: dict[str, int] = defaultdict(int)
    rooms_data: dict[str, dict[str, Any]] = {}

    for d in drawers:
        wing = d.get("wing") or "general"
        room = d.get("room") or "general"
        r_id = f"room_{wing}_{room}"

        wings_records[wing] += 1

        if r_id not in rooms_data:
            rooms_data[r_id] = {
                "id": r_id,
                "label": room,
                "wing": wing,
                "wing_family": normalize_wing_family(wing),
                "texts": [],
                "dates": [],
                "notes": [],
            }

        content = d.get("content") or ""
        source_file = d.get("source_file") or ""
        filed_at = d.get("filed_at") or ""

        title = os.path.basename(source_file) if source_file else ""
        if not title:
            first_line = content.split("\n")[0].strip() if content else ""
            idx = len(rooms_data[r_id]["notes"]) + 1
            title = first_line[:50] if first_line else f"Заметка #{idx}"

        rooms_data[r_id]["texts"].append(content)
        if filed_at:
            rooms_data[r_id]["dates"].append(filed_at)

        preview = content[:220].strip() if content else ""
        rooms_data[r_id]["notes"].append({
            "id": d.get("id") or f"drawer_{len(rooms_data[r_id]['notes'])}",
            "title": title,
            "date": filed_at[:10] if filed_at else "",
            "preview": preview,
        })

    # 2. Вычисление сущностей и туннелей
    room_top_entities, room_vectors = calculate_room_entities_and_tfidf(rooms_data)
    tunnels = compute_tunnels(rooms_data, room_top_entities, room_vectors)

    # 3. Формирование узлов крыльев
    nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []

    for wing_name, rec_cnt in wings_records.items():
        w_id = f"wing_{wing_name}"
        nodes.append({
            "id": w_id,
            "label": wing_name,
            "type": "wing",
            "records": rec_cnt,
            "wing": wing_name,
        })

    # 4. Формирование узлов комнат
    now_dt = datetime.datetime.now()
    for r_id, r_info in rooms_data.items():
        rec_cnt = len(r_info["notes"])
        tags = room_top_entities.get(r_id, [])

        # Вычисление свежести (0..1)
        freshness = 0.5
        if r_info["dates"]:
            latest_date_str = max(r_info["dates"])
            try:
                dt = datetime.datetime.fromisoformat(latest_date_str.replace("Z", ""))
                age_days = (now_dt - dt).days
                freshness = max(0.0, min(1.0, 1.0 - (age_days / 180.0)))
            except Exception:
                freshness = 0.5

        # Служебные комнаты: _registry или general с >500 записей
        is_service = (r_info["label"] == "_registry") or (
            r_info["label"] == "general" and rec_cnt > 500
        )

        nodes.append({
            "id": r_id,
            "label": r_info["label"],
            "type": "room",
            "wing": f"wing_{r_info['wing']}",
            "wing_name": r_info["wing"],
            "records": rec_cnt,
            "freshness": round(freshness, 3),
            "tags": tags,
            "service": is_service,
            "notes": r_info["notes"],
        })

        links.append({
            "source": f"wing_{r_info['wing']}",
            "target": r_id,
            "type": "containment",
            "weight": 1,
        })

    # 5. Добавляем туннели к связям
    links.extend(tunnels)

    return {
        "nodes": nodes,
        "links": links,
        "meta": {
            "total_wings": len(wings_records),
            "total_rooms": len(rooms_data),
            "total_records": len(drawers),
            "total_tunnels": len(tunnels),
            "generated_at": now_dt.isoformat(),
        },
    }


def print_graph_statistics(graph_data: dict[str, Any]) -> None:
    """Выводит подробную консольную статистику графа."""
    meta = graph_data.get("meta", {})
    nodes = graph_data.get("nodes", [])
    links = graph_data.get("links", [])

    wings = [n for n in nodes if n.get("type") == "wing"]
    rooms = [n for n in nodes if n.get("type") == "room"]
    tunnels = [lk for lk in links if lk.get("type") == "tunnel"]

    print("=" * 60)
    print("  📊 Статистика Графа Дворца Памяти")
    print("=" * 60)
    print(f"Крыльев:   {len(wings)} ({meta.get('total_wings', len(wings))})")
    print(f"Комнат:    {len(rooms)} ({meta.get('total_rooms', len(rooms))})")
    print(f"Записей:   {meta.get('total_records', 0)}")
    print(f"Туннелей:  {len(tunnels)}")
    print("-" * 60)

    # Топ-10 самых связных комнат
    tunnel_degrees: Counter[str] = Counter()
    for t in tunnels:
        tunnel_degrees[t["source"]] += 1
        tunnel_degrees[t["target"]] += 1

    room_map = {r["id"]: r["label"] for r in rooms}
    print("🏆 Топ-10 комнат по числу туннелей:")
    for r_id, deg in tunnel_degrees.most_common(10):
        print(f"  • {room_map.get(r_id, r_id)}: {deg} туннелей")

    # Изолированные крылья (без туннелей)
    connected_wings: set[str] = set()
    node_wing_map = {n["id"]: n.get("wing_name") or n.get("label") for n in nodes}
    for t in tunnels:
        w_src = node_wing_map.get(t["source"])
        w_dst = node_wing_map.get(t["target"])
        if w_src:
            connected_wings.add(w_src)
        if w_dst:
            connected_wings.add(w_dst)

    all_wings = {w["label"] for w in wings}
    isolated = all_wings - connected_wings
    if isolated:
        print(f"🕸️ Изолированные крылья (без туннелей): {', '.join(sorted(isolated))}")
    else:
        print("🌐 Все крылья соединены хотя бы одним туннелем!")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Скрипт построения графа Дворца памяти")
    parser.add_argument(
        "--palace",
        default=os.path.expanduser("~/.mempalace/palace"),
        help="Путь к локальной базе ChromaDB",
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Путь к экспорту JSON/JSONL (альтернатива ChromaDB)",
    )
    parser.add_argument(
        "--output-tunnels",
        default="tunnels.json",
        help="Файл для сохранения туннелей (JSON)",
    )
    parser.add_argument(
        "--output-data",
        default="palace_graph_data.json",
        help="Файл для сохранения полной модели графа (JSON)",
    )
    args = parser.parse_args()

    if args.input:
        print(f"Чтение ящиков из файла {args.input}...")
        drawers = load_drawers_from_file(args.input)
    else:
        print(f"Чтение ящиков из базы ChromaDB ({args.palace})...")
        drawers = load_drawers_from_chroma(args.palace)

    print(f"Загружено {len(drawers)} ящиков. Построение модели графа и туннелей...")
    graph_data = build_graph_model(drawers)

    # 1. Сохраняем tunnels.json
    tunnels = [lk for lk in graph_data["links"] if lk.get("type") == "tunnel"]
    with open(args.output_tunnels, "w", encoding="utf-8") as f:
        json.dump({"links": tunnels}, f, ensure_ascii=False, indent=2)
    print(f"Туннели сохранены в {args.output_tunnels}")

    # 2. Сохраняем полную модель данных
    with open(args.output_data, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, ensure_ascii=False, indent=2)
    print(f"Полная модель графа сохранена в {args.output_data}")

    # 3. Печатаем статистику
    print_graph_statistics(graph_data)


if __name__ == "__main__":
    main()
