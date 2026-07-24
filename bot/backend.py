"""Асинхронный клиент к FastAPI-backend.

Бот сам не хранит бизнес-логику: он резолвит telegram_id → JWT пользователя
(привилегированной ручкой с общим секретом) и дальше дёргает обычные ручки API
от имени пользователя — те же, что и веб-кабинет.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from config import config


class BackendError(Exception):
    """Ошибка API с человекочитаемым detail."""

    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"[{status}] {detail}")


class Backend:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=config.backend_url,
            timeout=httpx.Timeout(120.0, connect=10.0),
        )

    async def close(self) -> None:
        await self._client.aclose()

    # ── low-level ────────────────────────────────────────────────────────────

    def _auth(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    async def _req(self, method: str, path: str, *, token: Optional[str] = None,
                   json: Any = None, headers: Optional[dict] = None,
                   files: Any = None, data: Any = None) -> Any:
        h: dict = {}
        if token:
            h.update(self._auth(token))
        if headers:
            h.update(headers)
        resp = await self._client.request(method, path, json=json, headers=h,
                                          files=files, data=data)
        if resp.status_code == 204:
            return None
        try:
            body = resp.json()
        except Exception:
            body = {}
        if resp.status_code >= 400:
            detail = body.get("detail") if isinstance(body, dict) else None
            raise BackendError(resp.status_code, detail or f"HTTP {resp.status_code}")
        return body

    # ── привязка / резолв (общий секрет) ──────────────────────────────────────

    def _secret_headers(self) -> dict:
        return {"X-Bot-Secret": config.bot_api_secret}

    async def link(self, code: str, telegram_id: int, username: str) -> dict:
        return await self._req(
            "POST", "/auth/telegram/link",
            json={"code": code, "telegram_id": telegram_id, "telegram_username": username},
            headers=self._secret_headers(),
        )

    async def resolve(self, telegram_id: int) -> Optional[dict]:
        """telegram_id → {access_token, email, can_calculate, is_active} | None."""
        try:
            return await self._req(
                "POST", "/auth/telegram/resolve",
                json={"telegram_id": telegram_id},
                headers=self._secret_headers(),
            )
        except BackendError as e:
            if e.status in (403, 404):
                return None
            raise

    # ── проекты ───────────────────────────────────────────────────────────────

    async def list_projects(self, token: str) -> list[dict]:
        return await self._req("GET", "/projects", token=token)

    async def create_project(self, token: str, name: str) -> dict:
        return await self._req("POST", "/projects", token=token, json={"name": name})

    async def get_project(self, token: str, pid: int) -> dict:
        return await self._req("GET", f"/projects/{pid}", token=token)

    async def delete_project(self, token: str, pid: int) -> None:
        await self._req("DELETE", f"/projects/{pid}", token=token)

    # ── файлы ─────────────────────────────────────────────────────────────────

    async def upload_file(self, token: str, pid: int, filename: str,
                          content: bytes, content_type: str) -> dict:
        files = {"file": (filename, content, content_type or "application/octet-stream")}
        return await self._req("POST", f"/projects/{pid}/files",
                               token=token, files=files)

    async def delete_file(self, token: str, pid: int, fid: int) -> None:
        await self._req("DELETE", f"/projects/{pid}/files/{fid}", token=token)

    # ── расчёты ───────────────────────────────────────────────────────────────

    async def list_calculations(self, token: str, pid: int) -> list[dict]:
        return await self._req("GET", f"/projects/{pid}/calculations", token=token)

    async def create_calculation(self, token: str, pid: int) -> dict:
        return await self._req("POST", f"/projects/{pid}/calculations", token=token)

    async def start_extraction(self, token: str, pid: int, cid: int) -> dict:
        return await self._req("POST", f"/projects/{pid}/calculations/{cid}/extract",
                               token=token)

    async def extraction_status(self, token: str, pid: int, cid: int) -> dict:
        return await self._req(
            "GET", f"/projects/{pid}/calculations/{cid}/extraction-status", token=token)

    async def clarify(self, token: str, pid: int, cid: int, text: str) -> dict:
        return await self._req(
            "POST", f"/projects/{pid}/calculations/{cid}/clarify",
            token=token, json={"text": text, "preview": False})

    async def finalize(self, token: str, pid: int, cid: int) -> dict:
        return await self._req(
            "POST", f"/projects/{pid}/calculations/{cid}/finalize", token=token)

    async def download_export(self, token: str, pid: int, cid: int, kind: str) -> bytes:
        resp = await self._client.get(
            f"/projects/{pid}/calculations/{cid}/exports/{kind}/download",
            headers=self._auth(token))
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail")
            except Exception:
                detail = None
            raise BackendError(resp.status_code, detail or f"HTTP {resp.status_code}")
        return resp.content


backend = Backend()
