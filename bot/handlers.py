"""Хендлеры бота: меню проектов → файлы / расчёты, привязка аккаунта.

Логика зеркалит веб-кабинет, но действия пользователя над расчётом сведены
к одному: «Новый расчёт» с необязательным комментарием-уточнением. После
анализа ТЗ расчёт сразу финализируется (как кнопка «Финализировать» в вебе),
и пользователю отдаются готовые файлы 2ПС и КП (docx/pdf).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile, CallbackQuery, Message, TelegramObject,
)

from backend import BackendError, backend
from config import config
from keyboards import (
    EXPORT_LABELS, back_kb, calc_kb, calc_status_label, calcs_kb,
    confirm_delete_project_kb, files_kb, fmt_money, project_kb, projects_kb,
)
from states import AddFile, CreateProject, NewCalc

log = logging.getLogger("bot.handlers")

public_router = Router(name="public")
app_router = Router(name="app")

NOT_LINKED = (
    "🔒 <b>Telegram не привязан к аккаунту.</b>\n\n"
    "Откройте личный кабинет на <b>pir.i-build.tech</b> → блок «Telegram» → "
    "нажмите «Подключить» и перейдите по появившейся ссылке.\n\n"
    "После привязки отправьте /start."
)


# ── Middleware авторизации ────────────────────────────────────────────────────

class AuthMiddleware(BaseMiddleware):
    """Резолвит telegram_id → JWT пользователя; непривязанных не пускает."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None:
            return None
        try:
            ctx = await backend.resolve(tg_user.id)
        except BackendError as e:
            ctx = None
            log.warning("resolve failed: %s", e)

        if not ctx:
            if isinstance(event, CallbackQuery):
                await event.answer("Аккаунт не привязан", show_alert=True)
                if event.message:
                    await event.message.answer(NOT_LINKED)
            elif isinstance(event, Message):
                await event.answer(NOT_LINKED)
            return None

        data["ctx"] = ctx
        data["token"] = ctx["access_token"]
        return await handler(event, data)


app_router.message.middleware(AuthMiddleware())
app_router.callback_query.middleware(AuthMiddleware())


# ── /start (public: привязка + меню) ──────────────────────────────────────────

@public_router.message(CommandStart(deep_link=True))
async def start_with_code(message: Message, command: CommandObject, state: FSMContext):
    await state.clear()
    code = (command.args or "").strip()
    tg = message.from_user
    try:
        res = await backend.link(code, tg.id, tg.username or "")
    except BackendError as e:
        await message.answer(f"❌ Не удалось привязать аккаунт: {e.detail}\n\n"
                             "Получите свежую ссылку в кабинете и попробуйте снова.")
        return
    await message.answer(
        f"✅ Аккаунт <b>{res['email']}</b> привязан к этому Telegram.")
    await _show_menu_message(message)


@public_router.message(CommandStart())
async def start_plain(message: Message, state: FSMContext):
    await state.clear()
    ctx = await backend.resolve(message.from_user.id)
    if not ctx:
        await message.answer(NOT_LINKED)
        return
    await _show_menu_message(message, token=ctx["access_token"])


@public_router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    ctx = await backend.resolve(message.from_user.id)
    if not ctx:
        await message.answer(NOT_LINKED)
        return
    await _show_menu_message(message, token=ctx["access_token"])


async def _show_menu_message(message: Message, token: str | None = None):
    if token is None:
        ctx = await backend.resolve(message.from_user.id)
        if not ctx:
            await message.answer(NOT_LINKED)
            return
        token = ctx["access_token"]
    projects = await backend.list_projects(token)
    await message.answer(_menu_text(projects), reply_markup=projects_kb(projects))


def _menu_text(projects: list[dict]) -> str:
    if not projects:
        return ("📁 <b>Ваши проекты</b>\n\nПока нет ни одного проекта. "
                "Нажмите «Добавить проект».")
    return f"📁 <b>Ваши проекты</b> ({len(projects)})\n\nВыберите проект:"


# ── Меню / проекты ────────────────────────────────────────────────────────────

@app_router.callback_query(F.data == "menu")
async def cb_menu(cb: CallbackQuery, token: str, state: FSMContext):
    await state.clear()
    projects = await backend.list_projects(token)
    await _safe_edit(cb, _menu_text(projects), projects_kb(projects))
    await cb.answer()


@app_router.callback_query(F.data == "proj_new")
async def cb_proj_new(cb: CallbackQuery, state: FSMContext):
    await state.set_state(CreateProject.name)
    await cb.message.answer("📝 Введите название нового проекта:",
                            reply_markup=back_kb("menu", "Отмена"))
    await cb.answer()


@app_router.message(CreateProject.name, F.text)
async def create_project_name(message: Message, token: str, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Слишком короткое название. Введите ещё раз:")
        return
    await state.clear()
    proj = await backend.create_project(token, name)
    await message.answer(f"✅ Проект «{proj['name']}» создан.")
    await _render_project_message(message, token, proj["id"])


@app_router.callback_query(F.data.startswith("proj:"))
async def cb_project(cb: CallbackQuery, token: str, state: FSMContext):
    await state.clear()
    pid = int(cb.data.split(":")[1])
    text = await _project_text(token, pid)
    await _safe_edit(cb, text, project_kb(pid))
    await cb.answer()


@app_router.callback_query(F.data.startswith("proj_del:"))
async def cb_project_del(cb: CallbackQuery):
    pid = int(cb.data.split(":")[1])
    await _safe_edit(cb, "🗑 Удалить проект со всеми файлами и расчётами?",
                     confirm_delete_project_kb(pid))
    await cb.answer()


@app_router.callback_query(F.data.startswith("proj_del_yes:"))
async def cb_project_del_yes(cb: CallbackQuery, token: str):
    pid = int(cb.data.split(":")[1])
    await backend.delete_project(token, pid)
    projects = await backend.list_projects(token)
    await _safe_edit(cb, "🗑 Проект удалён.\n\n" + _menu_text(projects),
                     projects_kb(projects))
    await cb.answer("Удалён")


async def _project_text(token: str, pid: int) -> str:
    proj = await backend.get_project(token, pid)
    calcs = await backend.list_calculations(token, pid)
    n_final = sum(1 for c in calcs if c.get("status") == "final")
    return (
        f"📁 <b>{proj['name']}</b>\n\n"
        f"📎 Файлов ТЗ: {len(proj.get('files', []))}\n"
        f"🧮 Расчётов: {len(calcs)} (готовых: {n_final})"
    )


async def _render_project_message(message: Message, token: str, pid: int):
    text = await _project_text(token, pid)
    await message.answer(text, reply_markup=project_kb(pid))


# ── Файлы ─────────────────────────────────────────────────────────────────────

@app_router.callback_query(F.data.startswith("files:"))
async def cb_files(cb: CallbackQuery, token: str, state: FSMContext):
    await state.clear()
    pid = int(cb.data.split(":")[1])
    await _safe_edit(cb, *(await _files_view(token, pid)))
    await cb.answer()


async def _files_view(token: str, pid: int):
    proj = await backend.get_project(token, pid)
    files = proj.get("files", [])
    if files:
        lines = "\n".join(f"• {f['filename']}" for f in files)
        text = (f"📎 <b>Файлы ТЗ · {proj['name']}</b>\n\n{lines}\n\n"
                "Файлы хранятся в проекте — повторно отправлять их для каждого "
                "расчёта не нужно. Нажмите на файл, чтобы удалить.")
    else:
        text = (f"📎 <b>Файлы ТЗ · {proj['name']}</b>\n\nФайлов пока нет. "
                "Добавьте PDF или DOCX с техническим заданием.")
    return text, files_kb(pid, files)


@app_router.callback_query(F.data.startswith("file_add:"))
async def cb_file_add(cb: CallbackQuery, state: FSMContext):
    pid = int(cb.data.split(":")[1])
    await state.set_state(AddFile.waiting)
    await state.update_data(project_id=pid)
    await cb.message.answer(
        "📎 Отправьте файл ТЗ (PDF или DOCX) документом.",
        reply_markup=back_kb(f"files:{pid}", "Отмена"))
    await cb.answer()


@app_router.message(AddFile.waiting, F.document)
async def add_file_document(message: Message, token: str, state: FSMContext, bot: Bot):
    data = await state.get_data()
    pid = data.get("project_id")
    doc = message.document
    ext = (doc.file_name or "").lower().rsplit(".", 1)[-1] if "." in (doc.file_name or "") else ""
    if ext not in ("pdf", "docx", "doc"):
        await message.answer("⚠️ Допустимы только PDF или DOCX. Отправьте другой файл.")
        return
    if doc.file_size and doc.file_size > config.max_file_mb * 1024 * 1024:
        await message.answer(f"⚠️ Файл больше {config.max_file_mb} МБ — "
                             "Telegram не даёт боту его скачать. Загрузите через веб-кабинет.")
        return
    await message.answer("⏳ Загружаю файл…")
    buf = await bot.download(doc)
    content = buf.read()
    try:
        await backend.upload_file(token, pid, doc.file_name or "tz.pdf",
                                  content, doc.mime_type or "")
    except BackendError as e:
        await message.answer(f"❌ Не удалось загрузить: {e.detail}")
        return
    await state.clear()
    await message.answer(f"✅ Файл «{doc.file_name}» добавлен.")
    text, kb = await _files_view(token, pid)
    await message.answer(text, reply_markup=kb)


@app_router.message(AddFile.waiting)
async def add_file_wrong(message: Message):
    await message.answer("Отправьте файл именно <b>документом</b> (PDF/DOCX), "
                         "а не текстом или фото.")


@app_router.callback_query(F.data.startswith("file_del:"))
async def cb_file_del(cb: CallbackQuery, token: str):
    _, pid, fid = cb.data.split(":")
    await backend.delete_file(token, int(pid), int(fid))
    await _safe_edit(cb, *(await _files_view(token, int(pid))))
    await cb.answer("Файл удалён")


# ── Расчёты ───────────────────────────────────────────────────────────────────

@app_router.callback_query(F.data.startswith("calcs:"))
async def cb_calcs(cb: CallbackQuery, token: str, state: FSMContext):
    await state.clear()
    pid = int(cb.data.split(":")[1])
    calcs = await backend.list_calculations(token, pid)
    await _safe_edit(cb, _calcs_text(calcs), calcs_kb(pid, calcs))
    await cb.answer()


def _calcs_text(calcs: list[dict]) -> str:
    if not calcs:
        return ("🧮 <b>Расчёты</b>\n\nПока нет расчётов. Нажмите «Новый расчёт» — "
                "бот проанализирует ТЗ и сформирует смету 2ПС и КП.")
    return f"🧮 <b>Расчёты</b> ({len(calcs)})\n\nВыберите расчёт или создайте новый:"


@app_router.callback_query(F.data.startswith("calc_new:"))
async def cb_calc_new(cb: CallbackQuery, ctx: dict, state: FSMContext):
    pid = int(cb.data.split(":")[1])
    if not ctx.get("can_calculate"):
        await cb.answer("Расчёты вам не разрешены администратором", show_alert=True)
        return
    # нужны файлы
    proj = await backend.get_project(ctx["access_token"], pid)
    if not proj.get("files"):
        await cb.answer(show_alert=True,
                        text="Сначала добавьте хотя бы один файл ТЗ в проект.")
        return
    await state.set_state(NewCalc.comment)
    await state.update_data(project_id=pid)
    await cb.message.answer(
        "💬 <b>Комментарий к расчёту</b> (необязательно).\n\n"
        "Это ваша единственная возможность повлиять на расчёт: укажите величину "
        "измерения, стадию, уточнение по объекту и т.п.\n\n"
        "Отправьте комментарий одним сообщением или нажмите «Без комментария».",
        reply_markup=back_kb(f"calc_start_nocomment:{pid}", "Без комментария"))
    await cb.answer()


@app_router.callback_query(F.data.startswith("calc_start_nocomment:"))
async def cb_calc_start_nocomment(cb: CallbackQuery, token: str, state: FSMContext, bot: Bot):
    pid = int(cb.data.split(":")[1])
    await state.clear()
    await cb.answer()
    await _launch_calc(bot, cb.message.chat.id, token, pid, comment="")


@app_router.message(NewCalc.comment, F.text)
async def calc_comment(message: Message, token: str, state: FSMContext, bot: Bot):
    data = await state.get_data()
    pid = data.get("project_id")
    comment = message.text.strip()
    await state.clear()
    await _launch_calc(bot, message.chat.id, token, pid, comment=comment)


async def _launch_calc(bot: Bot, chat_id: int, token: str, pid: int, comment: str):
    try:
        calc = await backend.create_calculation(token, pid)
    except BackendError as e:
        await bot.send_message(chat_id, f"❌ Не удалось создать расчёт: {e.detail}")
        return
    cid = calc["id"]
    status = await bot.send_message(
        chat_id,
        f"🚀 Расчёт #{cid} запущен.\n\n① Анализ ТЗ…\n\n"
        "Это может занять несколько минут. Можно закрыть чат — "
        "результат придёт сюда.")
    asyncio.create_task(
        _run_pipeline(bot, chat_id, status.message_id, token, pid, cid, comment))


async def _run_pipeline(bot: Bot, chat_id: int, msg_id: int, token: str,
                        pid: int, cid: int, comment: str):
    async def edit(text: str, kb=None):
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id,
                                        reply_markup=kb)
        except Exception:
            pass

    try:
        await backend.start_extraction(token, pid, cid)
        # опрос статуса
        elapsed = 0.0
        while elapsed < config.poll_timeout_s:
            st = await backend.extraction_status(token, pid, cid)
            s = st.get("status")
            if s == "done":
                break
            if s == "error":
                raise BackendError(500, st.get("error") or "Анализ ТЗ не удался")
            prog = st.get("progress") or {}
            msg = prog.get("message", "")
            await edit(f"🚀 Расчёт #{cid}\n\n① Анализ ТЗ… {msg}")
            await asyncio.sleep(config.poll_interval_s)
            elapsed += config.poll_interval_s
        else:
            raise BackendError(504, "Анализ ТЗ превысил время ожидания")

        if comment:
            await edit(f"🚀 Расчёт #{cid}\n\n② Применяю комментарий…")
            try:
                await backend.clarify(token, pid, cid, comment)
            except BackendError as e:
                # уточнение не критично — сообщаем, но продолжаем к финализации
                await bot.send_message(
                    chat_id, f"⚠️ Комментарий не удалось применить автоматически: "
                             f"{e.detail}. Расчёт финализирую без него.")

        await edit(f"🚀 Расчёт #{cid}\n\n③ Финализация и генерация файлов…")
        fin = await backend.finalize(token, pid, cid)

        total = fin.get("total_with_vat")
        warnings = fin.get("warnings") or []
        text = (f"✅ <b>Расчёт #{cid} готов.</b>\n\n"
                f"Итог с НДС: <b>{fmt_money(total)}</b>")
        if warnings:
            wl = "\n".join(f"• {w}" for w in warnings[:8])
            text += f"\n\n⚠️ Обратите внимание:\n{wl}"
        await edit(text)

        # отдать файлы
        await _send_exports(bot, chat_id, token, pid, cid, fin.get("exports", []))

        calc = await _get_calc(token, pid, cid)
        if calc:
            await bot.send_message(chat_id,
                                   f"Расчёт #{cid} · {calc_status_label(calc)}",
                                   reply_markup=calc_kb(pid, cid, calc))
    except BackendError as e:
        await edit(f"⚠️ Расчёт #{cid}: {e.detail}\n\n"
                   "Откройте расчёт в списке, чтобы посмотреть статус.")
    except Exception as e:  # noqa: BLE001
        log.exception("pipeline failed")
        await edit(f"⚠️ Расчёт #{cid}: непредвиденная ошибка ({e}).")


async def _send_exports(bot: Bot, chat_id: int, token: str, pid: int, cid: int,
                        exports: list[dict]):
    kinds = [e["kind"] for e in exports] or ["2ps_xlsx", "kp_docx", "kp_pdf"]
    for kind in ("2ps_xlsx", "kp_docx", "kp_pdf"):
        if kind not in kinds:
            continue
        try:
            content = await backend.download_export(token, pid, cid, kind)
        except BackendError as e:
            await bot.send_message(chat_id, f"⚠️ {EXPORT_LABELS.get(kind, kind)}: {e.detail}")
            continue
        fname = next((e.get("filename") for e in exports if e.get("kind") == kind), None)
        fname = fname or f"{kind}_{cid}"
        await bot.send_document(chat_id, BufferedInputFile(content, filename=fname),
                                caption=EXPORT_LABELS.get(kind, kind))


async def _get_calc(token: str, pid: int, cid: int) -> dict | None:
    calcs = await backend.list_calculations(token, pid)
    return next((c for c in calcs if c["id"] == cid), None)


@app_router.callback_query(F.data.startswith("calc:"))
async def cb_calc(cb: CallbackQuery, token: str):
    _, pid, cid = cb.data.split(":")
    pid, cid = int(pid), int(cid)
    calc = await _get_calc(token, pid, cid)
    if not calc:
        await cb.answer("Расчёт не найден", show_alert=True)
        return
    await _safe_edit(cb, _calc_text(calc), calc_kb(pid, cid, calc))
    await cb.answer()


def _calc_text(calc: dict) -> str:
    lines = [f"🧮 <b>Расчёт #{calc['id']}</b> · v{calc.get('version_num', 1)}",
             f"Статус: {calc_status_label(calc)}",
             f"Позиций: {calc.get('n_entities', 0)}"]
    if calc.get("total_with_vat") is not None:
        lines.append(f"Итог с НДС: <b>{fmt_money(calc['total_with_vat'])}</b>")
    if calc.get("status") == "final" and calc.get("exports"):
        lines.append("\n📎 Готовые файлы — кнопками ниже.")
    elif calc.get("extraction_status") == "running":
        lines.append("\n⏳ Идёт обработка — нажмите «Обновить статус».")
    return "\n".join(lines)


@app_router.callback_query(F.data.startswith("calc_dl:"))
async def cb_calc_dl(cb: CallbackQuery, token: str):
    _, pid, cid, kind = cb.data.split(":")
    pid, cid = int(pid), int(cid)
    await cb.answer("Готовлю файл…")
    try:
        content = await backend.download_export(token, pid, cid, kind)
    except BackendError as e:
        await cb.message.answer(f"⚠️ {e.detail}")
        return
    calc = await _get_calc(token, pid, cid)
    fname = None
    if calc:
        fname = next((e.get("filename") for e in calc.get("exports", [])
                      if e.get("kind") == kind), None)
    fname = fname or f"{kind}_{cid}"
    await cb.message.answer_document(
        BufferedInputFile(content, filename=fname),
        caption=EXPORT_LABELS.get(kind, kind))


# ── утилиты ───────────────────────────────────────────────────────────────────

async def _safe_edit(cb: CallbackQuery, text: str, kb):
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except Exception:
        # сообщение могло устареть/совпасть — шлём новое
        await cb.message.answer(text, reply_markup=kb)
