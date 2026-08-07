import asyncio
import re
import time
from uuid import uuid4

from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from app.utils.logger_handler import get_logger


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
logger = get_logger("api_http")


class HTTPRequestMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        timeout_seconds: int,
        max_body_bytes: int,
    ):
        super().__init__(app)
        self.timeout_seconds = timeout_seconds
        self.max_body_bytes = max_body_bytes

    @staticmethod
    def _request_id(request: Request) -> str:
        candidate = (request.headers.get("X-Request-ID") or "").strip()
        if REQUEST_ID_PATTERN.fullmatch(candidate):
            return candidate
        return uuid4().hex

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = self._request_id(request)
        request.state.request_id = request_id
        started_at = time.perf_counter()
        response: Response

        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                too_large = int(content_length) > self.max_body_bytes
            except ValueError:
                too_large = True
            if too_large:
                response = JSONResponse(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    content={"detail": "请求体过大", "request_id": request_id},
                )
                return self._finish(request, response, request_id, started_at)

        try:
            async with asyncio.timeout(self.timeout_seconds):
                response = await call_next(request)
        except TimeoutError:
            response = JSONResponse(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                content={"detail": "请求处理超时", "request_id": request_id},
            )
        return self._finish(request, response, request_id, started_at)

    @staticmethod
    def _finish(
        request: Request,
        response: Response,
        request_id: str,
        started_at: float,
    ) -> Response:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = str(duration_ms)
        logger.info(
            "event=http_request request_id=%s method=%s path=%s status=%s duration_ms=%s",
            request_id,
            request.method,
            route_path,
            response.status_code,
            duration_ms,
        )
        return response
