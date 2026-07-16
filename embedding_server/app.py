from __future__ import annotations

import asyncio
import base64
import os
import struct
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import torch
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from transformers import AutoModel, AutoTokenizer


MODEL_ID = "ai-sage/Giga-Embeddings-instruct"
MODEL_REVISION = "2cf0fdc97194aaedf10ac0e6bf798834acd31042"
SERVED_MODEL_NAME = "giga-embeddings-instruct"
EMBEDDING_DIMENSIONS = 2048
MAX_MODEL_LEN = 4096
MAX_INPUTS = 64
MAX_INPUT_CHARS = 100_000
MAX_REQUEST_BYTES = 1_048_576


def error_response(status_code: int, message: str, error_type: str, param: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "message": message,
                "type": error_type,
                "param": param,
                "code": None,
            }
        },
    )


class EmbeddingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: str | list[str]
    model: str = SERVED_MODEL_NAME
    encoding_format: Literal["float", "base64"] = "float"
    dimensions: int | None = None
    user: str | None = None


@dataclass
class EmbeddingResult:
    values: list[float]
    token_count: int


class EmbeddingEngine(Protocol):
    model_name: str

    def embed(self, inputs: list[str]) -> list[EmbeddingResult]: ...


class GigaEmbeddingEngine:
    model_name = SERVED_MODEL_NAME

    def __init__(self) -> None:
        model_path = os.environ.get("GIGA_MODEL_PATH", MODEL_ID)
        model_revision = None if os.path.exists(model_path) else MODEL_REVISION

        if not torch.cuda.is_available():
            raise RuntimeError("A CUDA GPU is required for Giga Embeddings")

        self.tokenizer = AutoTokenizer.from_pretrained(
            model_path,
            revision=model_revision,
            trust_remote_code=True,
        )
        self.model = AutoModel.from_pretrained(
            model_path,
            revision=model_revision,
            trust_remote_code=True,
            torch_dtype=torch.bfloat16,
            attn_implementation="flash_attention_2",
        )
        self.model.eval().cuda()

        if os.environ.get("GIGA_TORCH_COMPILE", "0") == "1":
            self.model = torch.compile(self.model, mode="reduce-overhead")

        implementation = getattr(self.model.config, "_attn_implementation", None)
        if implementation != "flash_attention_2":
            raise RuntimeError(f"FlashAttention 2 was requested but model selected {implementation!r}")

        self._warm_up()

    def _tokenize(self, text: str) -> dict[str, torch.Tensor]:
        encoded = self.tokenizer(
            text,
            padding=False,
            truncation=False,
            return_tensors="pt",
        )
        token_count = int(encoded["attention_mask"].sum().item())
        if token_count > MAX_MODEL_LEN:
            raise InputTooLongError(token_count)
        return {key: value.cuda(non_blocking=True) for key, value in encoded.items()}

    def _embed_one(self, text: str) -> EmbeddingResult:
        encoded = self._tokenize(text)
        token_count = int(encoded["attention_mask"].sum().item())
        with torch.inference_mode():
            output = self.model(**encoded, return_embeddings=True)
        values = output[0].float().cpu().tolist()
        return EmbeddingResult(values=values, token_count=token_count)

    def embed(self, inputs: list[str]) -> list[EmbeddingResult]:
        results = []
        for index, text in enumerate(inputs):
            try:
                results.append(self._embed_one(text))
            except InputTooLongError as exc:
                exc.input_index = index
                raise
        return results

    def _warm_up(self) -> None:
        lengths = os.environ.get("GIGA_WARMUP_TOKENS", "32,128,512,2048,4096")
        for raw_length in lengths.split(","):
            target = int(raw_length.strip())
            if target < 1 or target > MAX_MODEL_LEN:
                raise ValueError(f"Invalid warm-up token length: {target}")
            encoded = self.tokenizer(
                "warmup " * target,
                padding=False,
                truncation=True,
                max_length=target,
                return_tensors="pt",
            )
            encoded = {key: value.cuda(non_blocking=True) for key, value in encoded.items()}
            with torch.inference_mode():
                self.model(**encoded, return_embeddings=True)
        torch.cuda.synchronize()


class InputTooLongError(ValueError):
    def __init__(self, token_count: int):
        self.token_count = token_count
        self.input_index: int | None = None
        super().__init__(f"Input has {token_count} tokens; maximum is {MAX_MODEL_LEN}")


def encode_embedding(values: list[float], encoding_format: str) -> list[float] | str:
    if encoding_format == "float":
        return values
    packed = struct.pack(f"<{len(values)}f", *values)
    return base64.b64encode(packed).decode("ascii")


def create_app(engine: EmbeddingEngine | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = engine or await asyncio.to_thread(GigaEmbeddingEngine)
        app.state.inference_lock = asyncio.Lock()
        yield

    app = FastAPI(title="Local Giga Embeddings API", lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(400, str(exc), "invalid_request_error")

    @app.middleware("http")
    async def limit_request_size(request: Request, call_next):
        content_length = request.headers.get("content-length")
        try:
            declared_size = int(content_length) if content_length else 0
        except ValueError:
            return error_response(400, "Invalid Content-Length header", "invalid_request_error")
        if declared_size > MAX_REQUEST_BYTES:
            return error_response(413, "Request body is too large", "invalid_request_error")
        if request.method in {"POST", "PUT", "PATCH"} and len(await request.body()) > MAX_REQUEST_BYTES:
            return error_response(413, "Request body is too large", "invalid_request_error")
        return await call_next(request)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "model": app.state.engine.model_name}

    @app.get("/v1/models")
    async def models() -> dict[str, Any]:
        return {
            "object": "list",
            "data": [
                {
                    "id": app.state.engine.model_name,
                    "object": "model",
                    "created": 0,
                    "owned_by": "ai-sage",
                }
            ],
        }

    @app.post("/v1/embeddings")
    async def embeddings(payload: EmbeddingRequest):
        if payload.model != app.state.engine.model_name:
            return error_response(404, f"Model {payload.model!r} does not exist", "model_not_found", "model")
        if payload.dimensions not in (None, EMBEDDING_DIMENSIONS):
            return error_response(
                400,
                f"This model only supports dimensions={EMBEDDING_DIMENSIONS}",
                "invalid_request_error",
                "dimensions",
            )

        inputs = [payload.input] if isinstance(payload.input, str) else payload.input
        if not inputs:
            return error_response(400, "input must not be empty", "invalid_request_error", "input")
        if len(inputs) > MAX_INPUTS:
            return error_response(400, f"At most {MAX_INPUTS} inputs are allowed", "invalid_request_error", "input")
        for index, text in enumerate(inputs):
            if len(text) > MAX_INPUT_CHARS:
                return error_response(
                    400,
                    f"Input at index {index} is too large to tokenize",
                    "invalid_request_error",
                    "input",
                )

        try:
            async with app.state.inference_lock:
                results = await asyncio.to_thread(app.state.engine.embed, inputs)
        except InputTooLongError as exc:
            location = f" at index {exc.input_index}" if exc.input_index is not None else ""
            message = f"Input{location} has {exc.token_count} tokens; maximum is {MAX_MODEL_LEN}"
            return error_response(400, message, "invalid_request_error", "input")
        total_tokens = sum(result.token_count for result in results)
        return {
            "object": "list",
            "data": [
                {
                    "object": "embedding",
                    "embedding": encode_embedding(result.values, payload.encoding_format),
                    "index": index,
                }
                for index, result in enumerate(results)
            ],
            "model": app.state.engine.model_name,
            "usage": {"prompt_tokens": total_tokens, "total_tokens": total_tokens},
        }

    return app


app = create_app()
