import base64
import math
import struct

from fastapi.testclient import TestClient

from embedding_server.app import (
    EMBEDDING_DIMENSIONS,
    MAX_INPUTS,
    MAX_MODEL_LEN,
    EmbeddingResult,
    InputTooLongError,
    SERVED_MODEL_NAME,
    create_app,
)


class FakeEngine:
    model_name = SERVED_MODEL_NAME

    def embed(self, inputs: list[str]) -> list[EmbeddingResult]:
        results = []
        for index, text in enumerate(inputs):
            if text == "too long":
                error = InputTooLongError(MAX_MODEL_LEN + 1)
                error.input_index = index
                raise error
            vector = [0.0] * EMBEDDING_DIMENSIONS
            vector[index % EMBEDDING_DIMENSIONS] = 1.0
            results.append(EmbeddingResult(values=vector, token_count=len(text.split()) + 1))
        return results


def client() -> TestClient:
    return TestClient(create_app(FakeEngine()))


def test_health_and_models() -> None:
    with client() as api:
        assert api.get("/health").json() == {"status": "ok", "model": SERVED_MODEL_NAME}
        response = api.get("/v1/models")
        assert response.status_code == 200
        assert response.json()["data"][0]["id"] == SERVED_MODEL_NAME


def test_float_embeddings_preserve_order_and_usage() -> None:
    with client() as api:
        response = api.post(
            "/v1/embeddings",
            json={"model": SERVED_MODEL_NAME, "input": ["first text", "second text"]},
        )
    assert response.status_code == 200
    payload = response.json()
    assert [item["index"] for item in payload["data"]] == [0, 1]
    assert len(payload["data"][0]["embedding"]) == EMBEDDING_DIMENSIONS
    assert payload["data"][0]["embedding"][0] == 1.0
    assert payload["data"][1]["embedding"][1] == 1.0
    assert payload["usage"] == {"prompt_tokens": 6, "total_tokens": 6}


def test_base64_embeddings_are_little_endian_float32() -> None:
    with client() as api:
        response = api.post(
            "/v1/embeddings",
            json={"model": SERVED_MODEL_NAME, "input": "hello", "encoding_format": "base64"},
        )
    encoded = response.json()["data"][0]["embedding"]
    values = struct.unpack(f"<{EMBEDDING_DIMENSIONS}f", base64.b64decode(encoded))
    assert math.isclose(values[0], 1.0)


def test_rejects_invalid_requests() -> None:
    cases = [
        ({"model": "missing", "input": "text"}, 404),
        ({"model": SERVED_MODEL_NAME, "input": "text", "dimensions": 1024}, 400),
        ({"model": SERVED_MODEL_NAME, "input": []}, 400),
        ({"model": SERVED_MODEL_NAME, "input": ["x"] * (MAX_INPUTS + 1)}, 400),
        ({"model": SERVED_MODEL_NAME, "input": [1, 2, 3]}, 400),
        ({"model": SERVED_MODEL_NAME, "input": ["ok", "too long"]}, 400),
    ]
    with client() as api:
        for body, status_code in cases:
            response = api.post("/v1/embeddings", json=body)
            assert response.status_code == status_code
            assert "error" in response.json()
        assert "index 1" in cases_response(api).json()["error"]["message"]


def cases_response(api: TestClient):
    return api.post(
        "/v1/embeddings",
        json={"model": SERVED_MODEL_NAME, "input": ["ok", "too long"]},
    )


def test_rejects_oversized_body() -> None:
    with client() as api:
        response = api.post(
            "/v1/embeddings",
            content=b"x" * 1_048_577,
            headers={"content-type": "application/json"},
        )
    assert response.status_code == 413
