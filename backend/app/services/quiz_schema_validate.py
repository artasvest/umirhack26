"""Проверка схемы квиза перед публикацией (активацией на сайте)."""

from __future__ import annotations

from typing import Any

# Маркер конца потока (как в default_quiz_schema: у form в nextStep), не отдельный блок на канвасе.
TERMINAL_STEP_IDS: frozenset[str] = frozenset({"done", "end", "finish"})


def validate_quiz_schema_for_publish(schema: Any) -> list[str]:
    """Возвращает список ошибок (пустой = можно активировать)."""
    errors: list[str] = []
    if not isinstance(schema, dict):
        return ["Схема должна быть объектом JSON"]

    nodes_raw = schema.get("nodes")
    if not isinstance(nodes_raw, list) or not nodes_raw:
        return ["Добавьте хотя бы один блок (nodes)"]

    node_by_id: dict[str, dict[str, Any]] = {}
    for raw in nodes_raw:
        if not isinstance(raw, dict) or not raw.get("id"):
            errors.append("У каждого блока должен быть id")
            continue
        nid = str(raw["id"])
        if nid in node_by_id:
            errors.append(f"Повтор id блока: {nid}")
        node_by_id[nid] = raw

    if errors:
        return errors

    edges = [e for e in (schema.get("edges") or []) if isinstance(e, dict) and e.get("from") and e.get("to")]

    pointed: set[str] = set()
    for e in edges:
        t = str(e["to"])
        if t not in TERMINAL_STEP_IDS:
            pointed.add(t)
    for n in node_by_id.values():
        if n.get("type") == "single" and isinstance(n.get("options"), list):
            for o in n["options"]:
                if isinstance(o, dict) and o.get("nextStep"):
                    ts = str(o["nextStep"])
                    if ts not in TERMINAL_STEP_IDS:
                        pointed.add(ts)
        if n.get("nextStep"):
            ns = str(n["nextStep"])
            if ns not in TERMINAL_STEP_IDS:
                pointed.add(ns)

    roots = [nid for nid in node_by_id if nid not in pointed]
    if not roots:
        errors.append("Не найдено начало квиза (все блоки куда-то ведут)")
        return errors
    if len(roots) > 1:
        roots.sort()
        errors.append(f"Несколько начальных блоков ({', '.join(roots)}); оставьте один вход в граф")
        return errors

    start_id = roots[0]

    def outgoing(nid: str) -> set[str]:
        n = node_by_id.get(nid)
        if not n:
            return set()
        out: set[str] = set()
        for e in edges:
            if str(e.get("from")) == nid:
                to = str(e["to"])
                if to not in TERMINAL_STEP_IDS:
                    out.add(to)
        if n.get("type") == "single" and isinstance(n.get("options"), list):
            for o in n["options"]:
                if isinstance(o, dict) and o.get("nextStep"):
                    ts = str(o["nextStep"])
                    if ts not in TERMINAL_STEP_IDS:
                        out.add(ts)
        if n.get("nextStep"):
            ns = str(n["nextStep"])
            if ns not in TERMINAL_STEP_IDS:
                out.add(ns)
        return out

    visited: set[str] = set()
    stack = [start_id]
    while stack:
        u = stack.pop()
        if u in visited:
            continue
        if u not in node_by_id:
            errors.append(f"Ссылка на несуществующий блок: {u}")
            continue
        visited.add(u)
        for v in outgoing(u):
            if v in TERMINAL_STEP_IDS:
                continue
            if v not in visited:
                stack.append(v)

    missing = set(node_by_id.keys()) - visited
    if missing:
        errors.append(f"Блоки недостижимы с начала квиза (висят отдельно): {', '.join(sorted(missing))}")

    form_ids = {nid for nid, n in node_by_id.items() if n.get("type") == "form"}
    if not form_ids:
        errors.append("Нет финального блока типа «форма» (form)")
    elif not (form_ids & visited):
        errors.append("Блок формы недостижим с начала квиза")

    for nid in visited:
        n = node_by_id[nid]
        if n.get("type") == "form":
            continue
        outs = outgoing(nid)
        if not outs:
            errors.append(f"Тупик на блоке «{nid}» ({n.get('title') or n.get('type')}): нет перехода к форме")

    return errors
