"""Резюме по ответам квиза: GigaChat (если настроен) или шаблон; скрипт звонка — шаблон."""

import logging
import re

from app.config import settings
from app.services.gigachat_client import get_gigachat_client

logger = logging.getLogger(__name__)

_AREA_RE = re.compile(r"(\d+)")


def _format_step_value(val) -> str:
    if val is None:
        return "—"
    if isinstance(val, list):
        return ", ".join(str(x) for x in val) if val else "—"
    return str(val)


def _step_block_type(raw: dict) -> str:
    return str(raw.get("blockType") or raw.get("block_type") or "").lower()


def _is_summary_meta_step(raw: dict) -> bool:
    """Блок ai_summary — value это готовый текст; не участвует в выводе фактов."""
    if _step_block_type(raw) == "ai_summary":
        return True
    # Без blockType (старые клиенты): только id экрана резюме из дефолтной схемы.
    # Не используем substring в title — иначе обычный вопрос «…резюме…» выпадает из цепочки
    # и все позиционные эвристики дают пустой вывод.
    sid = str(raw.get("id") or "").lower()
    return sid == "summary"


def _scalar_answer(val):
    if isinstance(val, list) and val:
        return val[0]
    return val


def _coerce_zones(z) -> list[str]:
    if z is None:
        return []
    if isinstance(z, list):
        return [str(x) for x in z]
    if isinstance(z, str):
        return [s.strip() for s in z.split(",") if s.strip()] or [z]
    return [str(z)]


def _parse_area_sqm(val) -> int | None:
    if val is None:
        return None
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return int(val)
    s = _format_step_value(val)
    m = _AREA_RE.search(s)
    return int(m.group(1)) if m else None


def _quiz_chain(steps: list) -> list[dict]:
    out: list[dict] = []
    for raw in steps:
        if isinstance(raw, dict) and not _is_summary_meta_step(raw):
            bt = _step_block_type(raw)
            if bt == "form":
                continue
            out.append(raw)
    return out


def _derive_from_steps(answers: dict) -> tuple[str | None, list | None, int | None, str | None, str | None]:
    """Достаёт room_type, zones, area, style, budget из steps и плоских полей."""
    room = answers.get("room_type")
    zones = answers.get("zones")
    area = answers.get("area_sqm")
    style = answers.get("style")
    budget = answers.get("budget")

    steps = answers.get("steps")
    if not isinstance(steps, list):
        return room, zones, area, style, budget

    chain = _quiz_chain(steps)

    # 1) Эвристики по id / заголовку (стандартная схема step1..step5)
    for raw in chain:
        sid = str(raw.get("id") or "")
        tit = (raw.get("title") or "").lower()
        val = raw.get("value")

        if room is None and (sid == "step1" or "помещ" in tit):
            sval = _scalar_answer(val)
            if sval is not None:
                room = str(sval)

        if zones is None and (sid == "step2" or "зон" in tit):
            zones = val

        if area is None and (sid == "step3" or "площад" in tit):
            area = _parse_area_sqm(val)

        if style is None and (sid == "step4" or "стил" in tit):
            sval = _scalar_answer(val)
            if sval is not None:
                style = str(sval)

        if budget is None and (sid == "step5" or "бюджет" in tit):
            bval = _scalar_answer(val)
            if bval is not None:
                budget = str(bval)

    # 2) По blockType с фронта: multi → зоны, slider → площадь, single → 1-й/2-й/3-й одиночный выбор
    single_values: list = []
    for raw in chain:
        bt = _step_block_type(raw)
        val = raw.get("value")
        if bt == "multi" and zones is None:
            zones = val
        elif bt == "slider" and area is None:
            area = _parse_area_sqm(val)
        elif bt == "single":
            single_values.append(val)

    if room is None and single_values:
        v0 = _scalar_answer(single_values[0])
        if v0 is not None:
            room = str(v0)
    if style is None and len(single_values) >= 2:
        v1 = _scalar_answer(single_values[1])
        if v1 is not None:
            style = str(v1)
    if budget is None and len(single_values) >= 3:
        v2 = _scalar_answer(single_values[2])
        if v2 is not None:
            budget = str(v2)

    # 3) Запасной вариант: порядок шагов в цепочке (типичный квиз из 5 блоков)
    if len(chain) >= 1 and room is None:
        v = _scalar_answer(chain[0].get("value"))
        if v is not None:
            room = str(v)
    if len(chain) >= 2 and zones is None:
        z = chain[1].get("value")
        if z is not None:
            zones = z
    if len(chain) >= 3 and area is None:
        area = _parse_area_sqm(chain[2].get("value"))
    if len(chain) >= 4 and style is None:
        v = _scalar_answer(chain[3].get("value"))
        if v is not None:
            style = str(v)
    if len(chain) >= 5 and budget is None:
        v = _scalar_answer(chain[4].get("value"))
        if v is not None:
            budget = str(v)

    return room, zones, area, style, budget


def _extra_step_lines(answers: dict) -> list[str]:
    """Доп. вопросы после первых пяти шагов основного потока."""
    steps = answers.get("steps")
    if not isinstance(steps, list):
        return []

    chain = _quiz_chain(steps)
    lines: list[str] = []
    for raw in chain[5:]:
        tit = (raw.get("title") or raw.get("id") or "?").strip()
        val = _format_step_value(raw.get("value"))
        lines.append(f"• {tit}: {val}")
    return lines


def _flat_fallback_for_llm(answers: dict) -> str:
    parts: list[str] = []
    for key, label in (
        ("room_type", "Тип помещения"),
        ("zones", "Зоны"),
        ("area_sqm", "Площадь"),
        ("style", "Стиль"),
        ("budget", "Бюджет"),
    ):
        if answers.get(key) is not None:
            parts.append(f"• {label}: {_format_step_value(answers.get(key))}")
    return "\n".join(parts) if parts else "(в анкете нет структурированных полей)"


def format_quiz_answers_for_llm(answers: dict) -> str:
    """Текст анкеты для промпта: шаги квиза по порядку (без формы и экрана ИИ-резюме)."""
    steps = answers.get("steps")
    if not isinstance(steps, list):
        return _flat_fallback_for_llm(answers)

    lines: list[str] = []
    for raw in _quiz_chain(steps):
        if not isinstance(raw, dict):
            continue
        tit = (raw.get("title") or raw.get("id") or "?").strip()
        val = _format_step_value(raw.get("value"))
        lines.append(f"• {tit}: {val}")

    if not lines:
        return _flat_fallback_for_llm(answers)
    return "\n".join(lines)


_LLM_BASE_SYSTEM = (
    "Ты помощник дизайн-студии интерьеров. Отвечаешь кратко на русском языке. "
    "Используй только факты из текста анкеты: не придумывай имя, телефон, адрес и детали, которых нет в данных. "
    "Если поле не заполнено — так и отрази или напиши «не указано»."
)

_MANAGER_SUMMARY_SYSTEM = _LLM_BASE_SYSTEM + " Тон: деловой, для внутреннего пользования."

_CLIENT_SUMMARY_SYSTEM = (
    _LLM_BASE_SYSTEM
    + " Тон: тёплый, обращение на «вы». Текст читает сам человек, заполнивший квиз. "
    "Не давай советов менеджеру по продажам, не пиши фраз вроде «в разговоре важно», "
    "«менеджер уточнит», «подчеркните возможность» — только краткое человеческое резюме их выбора."
)


def _gigachat_manager_prompt_user(facts_block: str) -> str:
    return f"""Ниже ответы клиента из онлайн-квиза (ремонт или дизайн интерьера).

Составь краткое деловое резюме для менеджера, который будет звонить клиенту:
- 1 абзац или 4–8 коротких предложений;
- объект и масштаб: тип помещения, зоны, площадь (если есть в данных);
- стиль и ориентир по бюджету (если есть);
- на что обратить внимание в разговоре и с чего логично начать (1–2 предложения).

Не дублируй дословно весь список — обобщи для человека, который читает за 15 секунд.

Данные анкеты:
{facts_block}
"""


def _gigachat_client_prompt_user(facts_block: str) -> str:
    return f"""Ниже ответы человека из онлайн-квиза о проекте интерьера.

Составь короткое резюме (1 абзац, 3–6 предложений) для самого этого человека: поблагодари за ответы,
кратко перескажи что они выбрали (тип помещения, зоны, площадь, стиль, бюджет — только если есть в данных).
Заверши нейтрально-дружелюбно (например, что команда учтёт пожелания при подготовке предложения).

Запрещено: советы продавцу, «менеджер», «звонок», «в разговоре важно уточнить», любые внутренние инструкции.

Данные анкеты:
{facts_block}
"""


def _shared_derived(answers: dict) -> tuple[str, list[str], int | None, str, str]:
    room, zones_raw, area, style, budget = _derive_from_steps(answers)
    room = room or "помещение"
    zones = _coerce_zones(zones_raw if zones_raw is not None else answers.get("zones"))
    style = style or (str(answers.get("style")) if answers.get("style") else None) or "стиль уточняется"
    budget = budget or (str(answers.get("budget")) if answers.get("budget") else None) or "бюджет уточняется"
    if area is None and answers.get("area_sqm") is not None:
        try:
            area = int(answers["area_sqm"])
        except (TypeError, ValueError):
            area = None
    return room, zones, area, style, budget


def _build_template_summary_manager(answers: dict) -> str:
    room, zones, area, style, budget = _shared_derived(answers)
    zones_text = ", ".join(zones) if zones else "зоны не выбраны"
    area_text = f"{area} м²" if area is not None else "площадь не указана"

    para = (
        f"Клиент планирует проект для типа «{room}». "
        f"Зоны: {zones_text}. Площадь: {area_text}. "
        f"Предпочитаемый стиль: {style}. Ориентир по бюджету: {budget}. "
        "Рекомендуем предложить бесплатную консультацию и уточнить сроки старта работ."
    )

    extras = _extra_step_lines(answers)
    if extras:
        return para + "\n\nДополнительно:\n" + "\n".join(extras)

    return para


def _build_template_summary_client(answers: dict) -> str:
    room, zones, area, style, budget = _shared_derived(answers)
    zones_text = ", ".join(zones) if zones else "зоны не указаны"
    area_text = f"{area} м²" if area is not None else "площадь не указана"

    para = (
        f"Спасибо за ответы. Вы указали проект для «{room}», зоны: {zones_text}, площадь: {area_text}. "
        f"Стиль: {style}, ориентир по бюджету: {budget}. Мы учтём это при подготовке предложения для вас."
    )

    extras = _extra_step_lines(answers)
    if extras:
        return para + "\n\nВы также отметили:\n" + "\n".join(extras)

    return para


def build_manager_summary_fast(answers: dict) -> str:
    """Резюме для менеджера без сети."""
    return _build_template_summary_manager(answers)


def build_client_quiz_summary_fast(answers: dict) -> str:
    """Краткое резюме для клиента без сети."""
    return _build_template_summary_client(answers)


def try_gigachat_manager_summary_only(answers: dict) -> str | None:
    gc = get_gigachat_client()
    if gc is None:
        return None
    try:
        facts = format_quiz_answers_for_llm(answers)
        text = gc.complete_system_user(
            _MANAGER_SUMMARY_SYSTEM,
            _gigachat_manager_prompt_user(facts),
            read_timeout_sec=settings.GIGACHAT_SUMMARY_TIMEOUT_SEC,
        )
        if text and len(text.strip()) > 15:
            return text.strip()
    except Exception as e:
        logger.warning("GigaChat (менеджер): %s", e)
    return None


def try_gigachat_client_summary_only(answers: dict) -> str | None:
    gc = get_gigachat_client()
    if gc is None:
        return None
    try:
        facts = format_quiz_answers_for_llm(answers)
        text = gc.complete_system_user(
            _CLIENT_SUMMARY_SYSTEM,
            _gigachat_client_prompt_user(facts),
            read_timeout_sec=settings.GIGACHAT_SUMMARY_TIMEOUT_SEC,
        )
        if text and len(text.strip()) > 15:
            return text.strip()
    except Exception as e:
        logger.warning("GigaChat (клиент): %s", e)
    return None


def build_quiz_client_preview_summary(answers: dict) -> str:
    """Превью на экране квиза: LLM (клиентский тон) или шаблон."""
    text = try_gigachat_client_summary_only(answers)
    if text:
        return text
    return _build_template_summary_client(answers)


def build_manager_summary(answers: dict) -> str:
    """Полное резюме для менеджера: LLM или шаблон."""
    text = try_gigachat_manager_summary_only(answers)
    if text:
        return text
    return _build_template_summary_manager(answers)


def build_call_script(answers: dict) -> str:
    return (
        "Скрипт звонка (черновик):\n"
        "1) Поблагодарите за заявку и кратко перефразируйте выбранные параметры.\n"
        "2) Уточните желаемые сроки начала ремонта или проектирования.\n"
        "3) Предложите пакет «Стандарт» как базовый вариант сметы и сроков.\n"
        "4) Согласуйте удобный канал связи и время повторного контакта.\n"
        "5) Зафиксируйте договорённости в заметках к заявке."
    )
