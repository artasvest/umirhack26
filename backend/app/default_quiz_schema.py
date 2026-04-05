"""Схема квиза по умолчанию.

Основной источник — файл default_quiz_schema.json (UTF-8) рядом с этим модулем.
Его можно править целиком и коммитить. Если JSON отсутствует, подставляется _BUILTIN.

GET /api/quiz-schema без активной строки в БД отдаёт загруженную схему.
При первом запуске main.py сидит её в БД.

Пересобрать JSON из встроенной копии: из каталога backend выполнить:
  python -m app.default_quiz_schema --write-json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parent / "default_quiz_schema.json"

# Встроенная копия (на случай отсутствия JSON и для команды --write-json)
_BUILTIN: dict = {
    "version": 1,
    "nodes": [
        {
            "id": "step1",
            "type": "single",
            "title": "Тип помещения",
            "options": [
                {"id": "apt", "label": "Квартира", "nextStep": "step2"},
                {"id": "house", "label": "Частный дом", "nextStep": "step2"},
                {"id": "office", "label": "Офис", "nextStep": "step2"},
                {"id": "commercial", "label": "Коммерческое помещение", "nextStep": "step2"},
                {"id": "studio", "label": "Студия/апартаменты", "nextStep": "step2"},
                {"id": "other", "label": "Другое", "nextStep": "step2"},
            ],
        },
        {
            "id": "step2",
            "type": "multi",
            "title": "Зоны",
            "options": [
                {"id": "kitchen", "label": "Кухня"},
                {"id": "living", "label": "Гостиная"},
                {"id": "bedroom", "label": "Спальня"},
                {"id": "kids", "label": "Детская"},
                {"id": "bath", "label": "Санузел"},
                {"id": "hall", "label": "Прихожая"},
                {"id": "office", "label": "Кабинет"},
                {"id": "wardrobe", "label": "Гардеробная"},
                {"id": "balcony", "label": "Балкон/лоджия"},
                {"id": "all", "label": "Полностью всё"},
            ],
            "nextStep": "step3",
        },
        {
            "id": "step3",
            "type": "slider",
            "title": "Площадь",
            "min": 20,
            "max": 300,
            "step": 5,
            "default": 60,
            "nextStep": "step4",
        },
        {
            "id": "step4",
            "type": "single",
            "title": "Стиль интерьера",
            "options": [
                {"id": "modern", "label": "Современный", "nextStep": "step5"},
                {"id": "minimal", "label": "Минимализм", "nextStep": "step5"},
                {"id": "scandi", "label": "Скандинавский", "nextStep": "step5"},
                {"id": "loft", "label": "Лофт", "nextStep": "step5"},
                {"id": "neoclassic", "label": "Неоклассика", "nextStep": "step5"},
                {"id": "classic", "label": "Классика", "nextStep": "step5"},
                {"id": "undecided", "label": "Пока не определился", "nextStep": "step5"},
            ],
        },
        {
            "id": "step5",
            "type": "single",
            "title": "Бюджет",
            "options": [
                {"id": "lt500", "label": "До 500к", "nextStep": "summary"},
                {"id": "500_1m", "label": "500к–1М", "nextStep": "summary"},
                {"id": "1m_2m", "label": "1М–2М", "nextStep": "summary"},
                {"id": "gt2m", "label": "От 2М", "nextStep": "summary"},
                {"id": "unknown", "label": "Пока не знаю", "nextStep": "summary"},
            ],
        },
        {
            "id": "summary",
            "type": "ai_summary",
            "title": "Краткое резюме",
            "nextStep": "step6",
        },
        {
            "id": "step6",
            "type": "form",
            "title": "Контакты",
            "nextStep": "done",
        },
    ],
    "edges": [
        {"from": "step1", "to": "step2"},
        {"from": "step2", "to": "step3"},
        {"from": "step3", "to": "step4"},
        {"from": "step4", "to": "step5"},
        {"from": "step5", "to": "summary"},
        {"from": "summary", "to": "step6"},
    ],
}


def _load() -> dict:
    if _PATH.is_file():
        return json.loads(_PATH.read_text(encoding="utf-8"))
    return _BUILTIN


if __name__ == "__main__" and "--write-json" in sys.argv:
    _PATH.write_text(json.dumps(_BUILTIN, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Wrote", _PATH)
    raise SystemExit(0)

DEFAULT_QUIZ_SCHEMA: dict = _load()
