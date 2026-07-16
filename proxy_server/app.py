import json
import os
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse


UPSTREAM_BASE_URL = os.environ.get("UPSTREAM_BASE_URL", "http://127.0.0.1:18000").rstrip("/")
PUBLIC_API_KEY = os.environ.get("PUBLIC_API_KEY", "")
REQUEST_TIMEOUT_SECONDS = float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "600"))

app = FastAPI(title="Local LLM OpenAI Proxy")


UPSTREAM_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadError,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
    httpx.WriteError,
    httpx.WriteTimeout,
)


def require_auth(authorization: str | None) -> None:
    if not PUBLIC_API_KEY:
        raise HTTPException(status_code=500, detail="PUBLIC_API_KEY is not configured")
    expected = f"Bearer {PUBLIC_API_KEY}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/upstream/health")
async def upstream_health(authorization: str | None = Header(default=None)) -> dict[str, str]:
    require_auth(authorization)
    timeout = httpx.Timeout(10.0, connect=5.0)
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            response = await client.get(f"{UPSTREAM_BASE_URL}/health")
            response.raise_for_status()
    except UPSTREAM_ERRORS as exc:
        raise HTTPException(status_code=502, detail=f"Upstream model service is unavailable: {exc}") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream health check failed: {exc.response.status_code}") from exc
    return {"status": "ok"}


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_openai(path: str, request: Request, authorization: str | None = Header(default=None)):
    require_auth(authorization)

    upstream_url = f"{UPSTREAM_BASE_URL}/v1/{path}"
    body = await request.body()
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in {"host", "content-length", "authorization", "connection"}
    }
    timeout = httpx.Timeout(REQUEST_TIMEOUT_SECONDS, connect=30.0)
    client = httpx.AsyncClient(timeout=timeout, trust_env=False)
    upstream_request = client.build_request(
        request.method,
        upstream_url,
        params=request.query_params,
        headers=headers,
        content=body,
    )
    try:
        upstream_response = await client.send(upstream_request, stream=True)
    except UPSTREAM_ERRORS as exc:
        await client.aclose()
        return JSONResponse(
            status_code=502,
            content={
                "error": {
                    "message": f"Upstream model service is unavailable: {exc}",
                    "type": "upstream_unavailable",
                }
            },
        )

    response_headers = {
        key: value
        for key, value in upstream_response.headers.items()
        if key.lower() not in {"content-encoding", "content-length", "connection", "transfer-encoding"}
    }

    async def stream_response() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream_response.aiter_bytes():
                yield chunk
        except UPSTREAM_ERRORS as exc:
            payload = json.dumps({"error": f"Upstream model service stream failed: {exc}"})
            yield f"event: error\ndata: {payload}\n\n".encode()
        finally:
            await upstream_response.aclose()
            await client.aclose()

    content_type = upstream_response.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        return StreamingResponse(
            stream_response(),
            status_code=upstream_response.status_code,
            headers=response_headers,
            media_type="text/event-stream",
        )

    try:
        content = await upstream_response.aread()
    except UPSTREAM_ERRORS as exc:
        return JSONResponse(
            status_code=502,
            content={
                "error": {
                    "message": f"Upstream model service response failed: {exc}",
                    "type": "upstream_unavailable",
                }
            },
        )
    finally:
        if not upstream_response.is_closed:
            await upstream_response.aclose()
        await client.aclose()
    return Response(content=content, status_code=upstream_response.status_code, headers=response_headers)
