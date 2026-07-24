"""Инлайн-клавиатуры и рендер текста экранов."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

EXPORT_LABELS = {
    "2ps_xlsx": "📊 2ПС (xlsx)",
    "kp_docx": "📄 КП (docx)",
    "kp_pdf": "📕 КП (pdf)",
}


def fmt_money(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):,.0f}".replace(",", " ") + " ₽"
    except (TypeError, ValueError):
        return "—"


def calc_status_label(calc: dict) -> str:
    if calc.get("status") == "final":
        return "✅ Расчёт окончен"
    ext = calc.get("extraction_status")
    if ext == "running":
        return "⏳ идёт анализ ТЗ…"
    if ext == "error":
        return "⚠️ ошибка анализа"
    return "✏️ черновик"


# ── Проекты ───────────────────────────────────────────────────────────────────

def projects_kb(projects: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in projects:
        kb.row(InlineKeyboardButton(text=f"📁 {p['name']}", callback_data=f"proj:{p['id']}"))
    # Выделенная кнопка добавления — внизу
    kb.row(InlineKeyboardButton(text="➕  Добавить проект", callback_data="proj_new"))
    return kb.as_markup()


def project_kb(pid: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="📎 Файлы ТЗ", callback_data=f"files:{pid}"))
    kb.row(InlineKeyboardButton(text="🧮 Расчёты", callback_data=f"calcs:{pid}"))
    kb.row(InlineKeyboardButton(text="🗑 Удалить проект", callback_data=f"proj_del:{pid}"))
    kb.row(InlineKeyboardButton(text="◀ Назад", callback_data="menu"))
    return kb.as_markup()


def confirm_delete_project_kb(pid: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="Да, удалить", callback_data=f"proj_del_yes:{pid}"),
        InlineKeyboardButton(text="Отмена", callback_data=f"proj:{pid}"),
    )
    return kb.as_markup()


# ── Файлы ─────────────────────────────────────────────────────────────────────

def files_kb(pid: int, files: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for f in files:
        kb.row(InlineKeyboardButton(
            text=f"🗑 {f['filename'][:40]}",
            callback_data=f"file_del:{pid}:{f['id']}"))
    kb.row(InlineKeyboardButton(text="➕  Добавить файл", callback_data=f"file_add:{pid}"))
    kb.row(InlineKeyboardButton(text="◀ Назад", callback_data=f"proj:{pid}"))
    return kb.as_markup()


# ── Расчёты ───────────────────────────────────────────────────────────────────

def calcs_kb(pid: int, calcs: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for c in calcs:
        label = f"#{c['id']} v{c.get('version_num', 1)} · {calc_status_label(c)}"
        kb.row(InlineKeyboardButton(text=label, callback_data=f"calc:{pid}:{c['id']}"))
    # Новый расчёт — перед кнопкой Назад
    kb.row(InlineKeyboardButton(text="➕  Новый расчёт", callback_data=f"calc_new:{pid}"))
    kb.row(InlineKeyboardButton(text="◀ Назад", callback_data=f"proj:{pid}"))
    return kb.as_markup()


def calc_kb(pid: int, cid: int, calc: dict) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    exports = {e["kind"] for e in calc.get("exports", [])}
    if calc.get("status") == "final" and exports:
        for kind in ("2ps_xlsx", "kp_docx", "kp_pdf"):
            if kind in exports:
                kb.row(InlineKeyboardButton(
                    text=f"⬇ {EXPORT_LABELS[kind]}",
                    callback_data=f"calc_dl:{pid}:{cid}:{kind}"))
    else:
        kb.row(InlineKeyboardButton(text="🔄 Обновить статус",
                                    callback_data=f"calc:{pid}:{cid}"))
    kb.row(InlineKeyboardButton(text="◀ К расчётам", callback_data=f"calcs:{pid}"))
    return kb.as_markup()


def back_kb(callback: str, text: str = "◀ Назад") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=text, callback_data=callback))
    return kb.as_markup()
