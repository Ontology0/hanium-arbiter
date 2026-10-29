"""Single-worker public example sandbox, isolated by a signed visitor cookie.

Cookies identify disposable sandboxes, never people or authenticated owners.
Run one ASGI worker per persistent volume. A volume lock rejects a second worker
instead of allowing concurrent app caches/background runners for the same DB.
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
import fcntl
import hashlib
import hmac
from http.cookies import CookieError, SimpleCookie
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from urllib.parse import urlsplit

from starlette.responses import JSONResponse


COOKIE_NAME = "culturefit_visitor"
IDENTIFIER = re.compile(r"^[a-f0-9]{48}$")
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
MIB = 1024 * 1024
BODY_TIMEOUT_SECONDS = 15


@dataclass(frozen=True)
class DemoConfig:
    ttl_seconds: int = 86400
    max_visitors: int = 200
    max_resident: int = 32
    body_limit: int = 256 * 1024
    visitor_bytes: int = 8 * MIB
    total_bytes: int = 256 * MIB
    requests_per_minute: int = 120
    new_visitors_per_minute: int = 30
    new_visitors_per_ip_minute: int = 10
    secure_cookie: bool = False

    def __post_init__(self):
        limits = {"ttl_seconds": 86400 * 7, "max_visitors": 1000, "max_resident": 64,
                  "body_limit": MIB, "visitor_bytes": 32 * MIB, "total_bytes": 1024 * MIB,
                  "requests_per_minute": 1000, "new_visitors_per_minute": 200,
                  "new_visitors_per_ip_minute": 100}
        for name, maximum in limits.items():
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= maximum:
                raise ValueError(f"Invalid demo limit: {name}")

    @classmethod
    def from_env(cls):
        names = {"ttl_seconds": "TTL_SECONDS", "max_visitors": "MAX_VISITORS", "max_resident": "MAX_RESIDENT",
                 "body_limit": "BODY_LIMIT", "visitor_bytes": "VISITOR_BYTES", "total_bytes": "TOTAL_BYTES",
                 "requests_per_minute": "REQUESTS_PER_MINUTE", "new_visitors_per_minute": "NEW_VISITORS_PER_MINUTE",
                 "new_visitors_per_ip_minute": "NEW_VISITORS_PER_IP_MINUTE"}
        values = {field: int(os.environ[f"ARBITER_DEMO_{suffix}"]) for field, suffix in names.items()
                  if f"ARBITER_DEMO_{suffix}" in os.environ}
        values["secure_cookie"] = bool(os.environ.get("RAILWAY_ENVIRONMENT_ID")) or os.environ.get("ARBITER_DEMO_SECURE_COOKIE") == "1"
        return cls(**values)


@dataclass
class Resident:
    app: object
    lifespan: object
    references: int = 0
    mutation_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def busy(self) -> bool:
        return self.references > 0 or any(state.get("busy") or state.get("brief_status") == "generating"
                                          for state in self.app.state.store.list())


class DemoLimit(Exception):
    def __init__(self, status: int, detail: str):
        self.status, self.detail = status, detail


class VisitorDeployment:
    def __init__(self, data_dir: str | Path | None = None, *, config: DemoConfig | None = None):
        self.data_dir = Path(data_dir or os.environ.get("ARBITER_DEMO_DATA_DIR", "/data"))
        self.config = config or DemoConfig.from_env()
        self.residents: OrderedDict[str, Resident] = OrderedDict()
        self.rates: OrderedDict[str, tuple[int, int]] = OrderedDict()
        self.lock = asyncio.Lock()
        self.registry = None
        self.secret = None
        self.volume_lock = None
        self.cleaner = None

    async def startup(self):
        async with self.lock:
            if self.registry is not None:
                return
            self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            (self.data_dir / "visitors").mkdir(exist_ok=True, mode=0o700)
            self.volume_lock = (self.data_dir / ".worker.lock").open("a")
            try:
                fcntl.flock(self.volume_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                self.volume_lock.close()
                self.volume_lock = None
                raise RuntimeError("Public demo requires one worker per data directory") from None
            try:
                secret_path = self.data_dir / ".visitor-secret"
                if not secret_path.exists():
                    descriptor = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(descriptor, "wb") as stream:
                        stream.write(secrets.token_bytes(32))
                self.secret = secret_path.read_bytes()
                if len(self.secret) != 32:
                    raise RuntimeError("Invalid persistent visitor signing secret")
                self.registry = sqlite3.connect(self.data_dir / "visitors.sqlite3", check_same_thread=False)
                self.registry.execute("CREATE TABLE IF NOT EXISTS visitors (id TEXT PRIMARY KEY, created_at REAL NOT NULL)")
                self.registry.commit()
            except BaseException:
                if self.registry is not None:
                    self.registry.close()
                    self.registry = None
                self.volume_lock.close()
                self.volume_lock = None
                raise
            self.cleaner = asyncio.create_task(self._cleanup_loop())

    async def shutdown(self):
        if self.cleaner:
            self.cleaner.cancel()
            try:
                await self.cleaner
            except asyncio.CancelledError:
                pass
            self.cleaner = None
        async with self.lock:
            for visitor_id in list(self.residents):
                await self._close_resident(visitor_id)
            if self.registry is not None:
                self.registry.close()
                self.registry = None
            if self.volume_lock:
                self.volume_lock.close()
                self.volume_lock = None

    def _db_path(self, visitor_id: str) -> Path:
        if not IDENTIFIER.fullmatch(visitor_id):
            raise ValueError("Invalid internal visitor identifier")
        return self.data_dir / "visitors" / f"{visitor_id}.sqlite3"

    def _signed(self, visitor_id: str) -> str:
        return visitor_id + "." + hmac.new(self.secret, visitor_id.encode(), hashlib.sha256).hexdigest()

    def _cookie_id(self, headers: dict[str, str]) -> str | None:
        try:
            cookies = SimpleCookie()
            cookies.load(headers.get("cookie", ""))
            value = cookies[COOKIE_NAME].value if COOKIE_NAME in cookies else ""
            visitor_id, signature = value.split(".", 1)
            if IDENTIFIER.fullmatch(visitor_id) and len(signature) == 64 and hmac.compare_digest(value, self._signed(visitor_id)):
                return visitor_id
        except (CookieError, ValueError, TypeError):
            pass
        return None

    def _cookie(self, visitor_id: str, secure: bool) -> bytes:
        value = f"{COOKIE_NAME}={self._signed(visitor_id)}; Path=/; Max-Age={self.config.ttl_seconds}; HttpOnly; SameSite=Lax"
        if secure:
            value += "; Secure"
        return value.encode("ascii")

    def _rate(self, key: str, maximum: int):
        minute = int(time.time() // 60)
        previous, count = self.rates.get(key, (minute, 0))
        count = count + 1 if previous == minute else 1
        self.rates[key] = (minute, count)
        self.rates.move_to_end(key)
        while len(self.rates) > 2048:
            self.rates.popitem(last=False)
        if count > maximum:
            raise DemoLimit(429, "Too many demo requests. Please try again in one minute.")

    def _disk_bytes(self, visitor_id: str | None = None) -> int:
        if visitor_id:
            path = self._db_path(visitor_id)
            paths = [path, Path(str(path) + "-wal"), Path(str(path) + "-shm")]
        else:
            paths = list((self.data_dir / "visitors").glob("*.sqlite3*"))
        total = 0
        for path in paths:
            try:
                total += path.stat().st_size
            except FileNotFoundError:
                pass
        return total

    async def _close_resident(self, visitor_id: str):
        resident = self.residents.pop(visitor_id)
        try:
            await resident.lifespan.__aexit__(None, None, None)
        finally:
            await asyncio.to_thread(resident.app.state.workers.shutdown, wait=True, cancel_futures=True)

    async def _remove(self, visitor_id: str):
        resident = self.residents.get(visitor_id)
        if resident and resident.busy():
            return False
        if resident:
            await self._close_resident(visitor_id)
        path = self._db_path(visitor_id)
        for suffix in ("", "-wal", "-shm"):
            Path(str(path) + suffix).unlink(missing_ok=True)
        self.registry.execute("DELETE FROM visitors WHERE id = ?", (visitor_id,))
        self.registry.commit()
        return True

    async def _cleanup(self):
        expired = self.registry.execute("SELECT id FROM visitors WHERE created_at <= ?",
                                        (time.time() - self.config.ttl_seconds,)).fetchall()
        for (visitor_id,) in expired:
            await self._remove(visitor_id)

    async def _cleanup_loop(self):
        while True:
            await asyncio.sleep(min(60, self.config.ttl_seconds))
            async with self.lock:
                await self._cleanup()

    async def _acquire(self, headers, scope, *, reset=False):
        await self.startup()
        async with self.lock:
            await self._cleanup()
            visitor_id = self._cookie_id(headers)
            row = (self.registry.execute("SELECT created_at FROM visitors WHERE id = ?", (visitor_id,)).fetchone()
                   if visitor_id else None)
            valid = bool(row and row[0] > time.time() - self.config.ttl_seconds)
            created = not valid or reset
            if created:
                client_ip = str((scope.get("client") or ("unknown", 0))[0])
                self._rate("new:global", self.config.new_visitors_per_minute)
                self._rate("new:" + client_ip, self.config.new_visitors_per_ip_minute)
                if reset and valid:
                    # Invalidates only the cookie's own sandbox; active work is not deleted.
                    if not await self._remove(visitor_id):
                        raise DemoLimit(409, "Wait for the current demo operation to finish before resetting.")
                count = self.registry.execute("SELECT COUNT(*) FROM visitors").fetchone()[0]
                if count >= self.config.max_visitors or self._disk_bytes() >= self.config.total_bytes:
                    raise DemoLimit(503, "Demo storage is full. Please try again later.")
                visitor_id = secrets.token_hex(24)
            self._rate("visitor:" + visitor_id, self.config.requests_per_minute)
            if visitor_id not in self.residents:
                while len(self.residents) >= self.config.max_resident:
                    candidate = next((key for key, item in self.residents.items() if not item.busy()), None)
                    if candidate is None:
                        raise DemoLimit(503, "Too many demos are running at once. Please try again later.")
                    await self._close_resident(candidate)
                from .app import create_app
                from .demo_seed import seed_demo
                child = create_app(self._db_path(visitor_id), demo_mode=True)
                lifespan = child.router.lifespan_context(child)
                try:
                    await lifespan.__aenter__()
                    if created:
                        seed_demo(child.state.store)
                        self.registry.execute("INSERT INTO visitors(id, created_at) VALUES (?, ?)", (visitor_id, time.time()))
                        self.registry.commit()
                except BaseException:
                    await lifespan.__aexit__(None, None, None)
                    child.state.workers.shutdown(wait=False, cancel_futures=True)
                    if created:
                        await self._remove(visitor_id)
                    raise
                self.residents[visitor_id] = Resident(child, lifespan)
            resident = self.residents[visitor_id]
            resident.references += 1
            self.residents.move_to_end(visitor_id)
            return visitor_id, resident, created

    async def _body(self, scope, receive, headers):
        try:
            length = int(headers.get("content-length", "0"))
        except ValueError:
            raise DemoLimit(400, "The request body length is invalid.") from None
        if length < 0:
            raise DemoLimit(400, "The request body length is invalid.")
        if length > self.config.body_limit:
            raise DemoLimit(413, "Demo request bodies must not exceed 256 KiB.")
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                raise DemoLimit(400, "The request connection was closed.")
            body.extend(message.get("body", b""))
            if len(body) > self.config.body_limit:
                raise DemoLimit(413, "The demo request body exceeds the allowed size.")
            if not message.get("more_body", False):
                return bytes(body)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    try:
                        await self.startup()
                    except Exception as exc:
                        await send({"type": "lifespan.startup.failed", "message": str(exc)})
                        return
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await self.shutdown()
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        if scope["type"] != "http":
            await send({"type": "websocket.close", "code": 1008})
            return
        path, method = scope.get("path", ""), scope.get("method", "GET")
        headers = {key.decode("latin1"): value.decode("latin1") for key, value in scope.get("headers", [])}
        if path == "/api/health":
            await JSONResponse({"status": "ok", "mode": "visitor_demo"}, headers={"Cache-Control": "no-store"})(scope, receive, send)
            return
        visitor_id, resident, created = None, None, False
        try:
            if method in MUTATING:
                origin = headers.get("origin")
                try:
                    invalid_origin = origin and urlsplit(origin).netloc != headers.get("host")
                except ValueError:
                    invalid_origin = True
                if invalid_origin or headers.get("sec-fetch-site") == "cross-site":
                    raise DemoLimit(403, "Cross-origin requests cannot modify the demo.")
            try:
                body = await asyncio.wait_for(self._body(scope, receive, headers), BODY_TIMEOUT_SECONDS)
            except TimeoutError:
                raise DemoLimit(408, "Receiving the request body timed out.") from None
            visitor_id, resident, created = await self._acquire(headers, scope, reset=path == "/api/demo/reset" and method == "POST")

            async def wrapped_send(message):
                if message["type"] == "http.response.start":
                    response_headers = [(key, value) for key, value in message.get("headers", []) if key.lower() not in {b"cache-control", b"vary"}]
                    vary = [value.decode("latin1") for key, value in message.get("headers", []) if key.lower() == b"vary"]
                    response_headers.extend([(b"cache-control", b"private, no-store, max-age=0"),
                                             (b"vary", ", ".join([*vary, "Cookie"]).encode("latin1"))])
                    if created:
                        response_headers.append((b"set-cookie", self._cookie(visitor_id, self.config.secure_cookie or scope.get("scheme") == "https")))
                    message = {**message, "headers": response_headers}
                await send(message)

            if path == "/api/demo/reset":
                result = {"reset": True, "mode": "visitor_demo", "identity_authenticated": False} if method == "POST" else {"detail": "Use a POST request to reset the demo."}
                await JSONResponse(result, status_code=200 if method == "POST" else 405)(scope, receive, wrapped_send)
                return

            received = False
            async def replay():
                nonlocal received
                if not received:
                    received = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            if method in MUTATING:
                async with resident.mutation_lock:
                    if self._disk_bytes(visitor_id) >= self.config.visitor_bytes or self._disk_bytes() >= self.config.total_bytes:
                        raise DemoLimit(429, "Your demo storage limit has been reached. Reset your demo and try again.")
                    await resident.app(scope, replay, wrapped_send)
            else:
                await resident.app(scope, replay, wrapped_send)
        except DemoLimit as exc:
            response_headers = {"Cache-Control": "private, no-store, max-age=0", "Vary": "Cookie"}
            if exc.status in {429, 503}:
                response_headers["Retry-After"] = "60"
            if created and visitor_id:
                response_headers["Set-Cookie"] = self._cookie(visitor_id, self.config.secure_cookie or scope.get("scheme") == "https").decode()
            await JSONResponse({"detail": exc.detail}, status_code=exc.status, headers=response_headers)(scope, receive, send)
        finally:
            if resident is not None:
                async with self.lock:
                    resident.references -= 1


def create_deployment_app(data_dir: str | Path | None = None, *, config: DemoConfig | None = None) -> VisitorDeployment:
    return VisitorDeployment(data_dir, config=config)


# No filesystem, executor, provider, or local application side effect on import.
app = create_deployment_app()
