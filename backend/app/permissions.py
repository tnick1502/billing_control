"""Права доступа: разделы, уровни, таблица правил «метод + URL → раздел + уровень».

Модель:
- у роли для каждого раздела один из 4 упорядоченных уровней: none < view < edit < full;
  ``edit`` — создание и изменение без удаления документов, ``full`` — ещё и удаление/архивация;
- суперпользователь (системная роль ``admin``) проходит любые проверки;
- путь, для которого нет правила, для не-суперпользователя ЗАПРЕЩЁН (запрет по умолчанию).
  Тест ``test_every_route_has_permission_rule`` не даст добавить эндпоинт без правила;
- «зависимые права чтения»: раздел даёт право ЧИТАТЬ конкретные справочные эндпоинты,
  нужные его странице (например, планам — список деталей). Запись по зависимостям — никогда.

Таблица правил компилируется один раз при импорте; разобранные права ролей кешируются
по ключу (код роли, ревизия роли), поэтому правка роли сразу даёт новый ключ и новую
политику без какой-либо инвалидации (корректно и при нескольких процессах).
"""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass, field
from threading import Lock
from typing import Iterable

# --- Уровни ---------------------------------------------------------------------------

NONE, VIEW, EDIT, FULL = 0, 1, 2, 3
LEVELS: dict[str, int] = {"none": NONE, "view": VIEW, "edit": EDIT, "full": FULL}
LEVEL_NAMES: dict[int, str] = {v: k for k, v in LEVELS.items()}
LEVEL_LABELS: dict[str, str] = {
    "none": "Нет доступа",
    "view": "Просмотр",
    "edit": "Изменение",
    "full": "Полный",
}
LEVEL_HINTS: dict[str, str] = {
    "none": "Раздел скрыт",
    "view": "Только чтение и выгрузки",
    "edit": "Создание и правка, без удаления",
    "full": "Всё, включая удаление",
}

# --- Разделы (порядок = порядок в меню и в редакторе ролей) ---------------------------

SECTIONS: list[dict[str, str]] = [
    {"key": "monthly_plans", "label": "Месячные планы", "group": "Планы", "path": "/monthly-plans"},
    {"key": "parts", "label": "Детали", "group": "Производство", "path": "/parts"},
    {"key": "devices", "label": "Приборы", "group": "Производство", "path": "/devices"},
    {"key": "bom", "label": "Спецификации", "group": "Производство", "path": "/bom"},
    {"key": "import", "label": "Загрузка спецификаций", "group": "Производство", "path": "/import"},
    {"key": "orders", "label": "Заказы клиентов", "group": "Финансы", "path": "/orders"},
    {"key": "invoices", "label": "Счета от поставщиков", "group": "Финансы", "path": "/invoices"},
    {"key": "statistics", "label": "Статистика", "group": "Финансы", "path": "/statistics"},
]
SECTION_KEYS: tuple[str, ...] = tuple(s["key"] for s in SECTIONS)

ADMIN_ROLE = "admin"
EMPLOYEE_ROLE = "employee"

# Ровно текущие права сотрудника (как было в employee_may_write):
# планы — всё, счета — всё кроме удаления, остальное — чтение, импорт — закрыт.
EMPLOYEE_PRESET: dict[str, str] = {
    "monthly_plans": "full",
    "invoices": "edit",
    "parts": "view",
    "devices": "view",
    "bom": "view",
    "orders": "view",
    "statistics": "view",
    "import": "none",
}


def normalize_permissions(raw: object) -> dict[str, str]:
    """Привести права к полному виду: все разделы, только допустимые уровни.

    Неизвестные разделы отбрасываются, отсутствующие и некорректные — ``none``.
    """
    src = raw if isinstance(raw, dict) else {}
    result: dict[str, str] = {}
    for key in SECTION_KEYS:
        value = src.get(key)
        result[key] = value if isinstance(value, str) and value in LEVELS else "none"
    return result


def validate_permissions(raw: object) -> dict[str, str]:
    """Строгая проверка входа API: неизвестный раздел или уровень — ошибка ValueError."""
    if not isinstance(raw, dict):
        raise ValueError("permissions должен быть объектом {раздел: уровень}")
    unknown = [k for k in raw if k not in SECTION_KEYS]
    if unknown:
        raise ValueError(f"Неизвестные разделы: {', '.join(map(str, unknown))}")
    bad = [f"{k}={v}" for k, v in raw.items() if v not in LEVELS]
    if bad:
        raise ValueError(f"Недопустимые уровни: {', '.join(bad)} (допустимо: {', '.join(LEVELS)})")
    return normalize_permissions(raw)


# --- Таблица правил -------------------------------------------------------------------

AUTHENTICATED = "authenticated"  # любой вошедший пользователь
SUPERUSER = "superuser"          # только суперпользователь


@dataclass(frozen=True)
class Rule:
    methods: frozenset[str]
    pattern: str
    regex: re.Pattern[str]
    kind: str                      # "section" | AUTHENTICATED | SUPERUSER
    sections: tuple[str, ...] = ()  # для "section": достаточно уровня в ЛЮБОМ из разделов
    level: int = NONE


def _compile(pattern: str) -> re.Pattern[str]:
    """``/parts/{id}`` → один сегмент; ``/parts/**`` → сам путь и всё под ним. Хвостовой «/» допустим."""
    if pattern.endswith("/**"):
        base, tail = pattern[:-3], r"(?:/.*)?"
    else:
        base, tail = pattern, ""
    out = ""
    for piece in re.split(r"(\{[^}]+\})", base):
        if piece.startswith("{") and piece.endswith("}"):
            out += r"[^/]+"
        else:
            out += re.escape(piece)
    return re.compile(f"^{out}{tail}/?$")


def _methods(spec: str) -> frozenset[str]:
    items = {m.strip().upper() for m in spec.split(",") if m.strip()}
    if "GET" in items:
        items.add("HEAD")
    return frozenset(items)


def R(methods: str, pattern: str, section: str | tuple[str, ...], level: str) -> Rule:
    sections = (section,) if isinstance(section, str) else tuple(section)
    for s in sections:
        assert s in SECTION_KEYS, s
    return Rule(_methods(methods), pattern, _compile(pattern), "section", sections, LEVELS[level])


def SPECIAL(methods: str, pattern: str, kind: str) -> Rule:
    return Rule(_methods(methods), pattern, _compile(pattern), kind)


ANY = "GET,POST,PUT,PATCH,DELETE"

# Порядок важен: побеждает ПЕРВОЕ подходящее правило (конкретные — раньше общих).
RULES: tuple[Rule, ...] = (
    # --- служебное ---
    SPECIAL("GET", "/auth/me", AUTHENTICATED),
    SPECIAL("POST", "/auth/logout", AUTHENTICATED),
    SPECIAL(ANY, "/admin/**", SUPERUSER),
    SPECIAL(ANY, "/imports/db/**", SUPERUSER),  # полный дамп БД (включая хэши паролей)
    # --- спецификации (часть путей живёт под /devices) ---
    R("GET", "/devices/{id}/bom", "bom", "view"),
    R("POST", "/devices/{id}/bom", "bom", "edit"),
    R("GET", "/bom/**", "bom", "view"),
    R("POST", "/bom/{id}/items", "bom", "edit"),
    R("PATCH", "/bom/{id}", "bom", "edit"),
    R("PATCH", "/bom/{id}/items/{item}", "bom", "edit"),
    R("DELETE", "/bom/{id}/items/{item}", "bom", "edit"),
    R("DELETE", "/bom/{id}", "bom", "full"),
    # --- приборы ---
    R("GET", "/devices/**", "devices", "view"),
    R("POST", "/devices", "devices", "edit"),
    R("PATCH", "/devices/{id}/archive", "devices", "full"),
    R("PATCH", "/devices/{id}", "devices", "edit"),
    R("POST", "/devices/{id}/aliases", "devices", "edit"),
    R("DELETE", "/devices/{id}/aliases/{alias}", "devices", "edit"),
    R("DELETE", "/devices/{id}", "devices", "full"),
    # --- детали ---
    R("GET", "/parts/**", "parts", "view"),
    R("POST", "/parts", "parts", "edit"),
    R("PATCH", "/parts/{id}/archive", "parts", "full"),
    R("PATCH", "/parts/{id}", "parts", "edit"),
    R("DELETE", "/parts/{id}", "parts", "full"),
    # --- заказы ---
    R("GET", "/orders/**", "orders", "view"),
    R("POST,PATCH", "/orders/**", "orders", "edit"),
    R("DELETE", "/orders/{id}/items/{item}", "orders", "edit"),
    R("DELETE", "/orders/{id}/part-items/{item}", "orders", "edit"),
    R("DELETE", "/orders/{id}", "orders", "full"),
    # --- месячные планы (вместе с инвентаризацией) ---
    R("GET", "/monthly-plans/**", "monthly_plans", "view"),
    R("POST,PATCH", "/monthly-plans/**", "monthly_plans", "edit"),
    R("DELETE", "/monthly-plans/{id}/invoice-links/{link}", "monthly_plans", "edit"),
    R("DELETE", "/monthly-plans/{id}/parts/{pp}/files/{file}", "monthly_plans", "edit"),
    R("DELETE", "/monthly-plans/inventory/{month}", "monthly_plans", "full"),
    R("DELETE", "/monthly-plans/{id}", "monthly_plans", "full"),
    # --- счета ---
    R("GET", "/invoices/**", "invoices", "view"),
    R("POST,PATCH", "/invoices/**", "invoices", "edit"),
    # Удаление строки «деталь в счёте» сотруднику было запрещено — сохраняем как «полный».
    R("DELETE", "/invoices/{id}/parts/{link}", "invoices", "full"),
    R("DELETE", "/invoices/{id}", "invoices", "full"),
    # --- файлы (вложения счетов и строк планов) ---
    R("GET", "/files/{id}/download", ("invoices", "monthly_plans"), "view"),
    # --- статистика ---
    R("GET", "/stats/**", "statistics", "view"),
    # --- загрузка спецификаций ---
    R("GET", "/imports/bom/export", "import", "view"),
    R("POST", "/imports/bom", "import", "edit"),
)

# Зависимые права ЧТЕНИЯ: раздел (с уровнем ≥ view) → эндпоинты, которые нужны его странице.
DEPENDENCY_READS: dict[str, tuple[str, ...]] = {
    "monthly_plans": ("/devices", "/parts", "/invoices/**"),
    "invoices": ("/monthly-plans", "/parts", "/files/{id}/download"),
    "orders": ("/devices", "/parts", "/devices/{id}/bom"),
    "bom": ("/devices", "/parts"),
}
_DEPENDENCY_REGEX: dict[str, tuple[re.Pattern[str], ...]] = {
    section: tuple(_compile(p) for p in patterns) for section, patterns in DEPENDENCY_READS.items()
}


def _first_segment(path: str) -> str:
    parts = path.split("/", 2)
    return parts[1] if len(parts) > 1 else ""


def _build_index(rules: Iterable[Rule]) -> dict[str, tuple[Rule, ...]]:
    index: dict[str, list[Rule]] = {}
    for rule in rules:
        index.setdefault(_first_segment(rule.pattern), []).append(rule)
    return {k: tuple(v) for k, v in index.items()}


_RULE_INDEX = _build_index(RULES)


def find_rule(method: str, path: str) -> Rule | None:
    method = method.upper()
    for rule in _RULE_INDEX.get(_first_segment(path), ()):
        if method in rule.methods and rule.regex.match(path):
            return rule
    return None


# --- Политика роли --------------------------------------------------------------------


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str = ""


@dataclass(frozen=True)
class Policy:
    role_code: str
    is_superuser: bool
    levels: dict[str, int] = field(default_factory=dict)
    dependency_reads: tuple[re.Pattern[str], ...] = ()

    def level(self, section: str) -> int:
        if self.is_superuser:
            return FULL
        return self.levels.get(section, NONE)

    def permissions(self) -> dict[str, str]:
        return {key: LEVEL_NAMES[self.level(key)] for key in SECTION_KEYS}

    def check(self, method: str, path: str) -> Decision:
        method = method.upper()
        if self.is_superuser:
            return Decision(True)
        rule = find_rule(method, path)
        if rule is not None:
            if rule.kind == AUTHENTICATED:
                return Decision(True)
            if rule.kind == SUPERUSER:
                return Decision(False, "Доступ только для администратора")
            if any(self.levels.get(s, NONE) >= rule.level for s in rule.sections):
                return Decision(True)
        # Зависимые права — только чтение.
        if method in ("GET", "HEAD") and any(rx.match(path) for rx in self.dependency_reads):
            return Decision(True)
        if rule is None:
            return Decision(False, "Нет доступа")
        if rule.kind == "section":
            need = LEVEL_LABELS[LEVEL_NAMES[rule.level]].lower()
            names = " / ".join(_SECTION_LABELS[s] for s in rule.sections)
            return Decision(False, f"Недостаточно прав: раздел «{names}», нужен уровень «{need}»")
        return Decision(False, "Нет доступа")


_SECTION_LABELS = {s["key"]: s["label"] for s in SECTIONS}


def build_policy(role_code: str, permissions: object, is_superuser: bool) -> Policy:
    normalized = normalize_permissions(permissions)
    levels = {k: LEVELS[v] for k, v in normalized.items()}
    deps: list[re.Pattern[str]] = []
    for section, patterns in _DEPENDENCY_REGEX.items():
        if levels.get(section, NONE) >= VIEW:
            deps.extend(patterns)
    return Policy(role_code=role_code, is_superuser=bool(is_superuser), levels=levels, dependency_reads=tuple(deps))


class _PolicyCache:
    """LRU: (код роли, ревизия, содержимое прав) → Policy.

    Ключ включает сами права (нормализованные), поэтому закешированная политика всегда
    соответствует тому, что прочитано из БД, даже если ревизии вдруг совпали.
    """

    def __init__(self, max_entries: int = 64) -> None:
        self._data: OrderedDict[tuple[str, int, bool, tuple[tuple[str, str], ...]], Policy] = OrderedDict()
        self._max = max_entries
        self._lock = Lock()

    def get(self, role_code: str, revision: int, permissions: object, is_superuser: bool) -> Policy:
        normalized = normalize_permissions(permissions)
        key = (role_code, int(revision or 0), bool(is_superuser), tuple(sorted(normalized.items())))
        with self._lock:
            policy = self._data.get(key)
            if policy is not None:
                self._data.move_to_end(key)
                return policy
        policy = build_policy(role_code, normalized, is_superuser)
        with self._lock:
            self._data[key] = policy
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)
        return policy

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        return len(self._data)


policy_cache = _PolicyCache()

# Роль без записи в таблице roles (не должно случаться при FK) — ничего не разрешено.
EMPTY_POLICY = Policy(role_code="", is_superuser=False)
