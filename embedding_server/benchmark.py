from __future__ import annotations

import argparse
import statistics
import time

import torch

from embedding_server.app import GigaEmbeddingEngine


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--lengths", default="32,128,512,2048,4096")
    args = parser.parse_args()

    engine = GigaEmbeddingEngine()
    for length in (int(item) for item in args.lengths.split(",")):
        text = "x " * max(1, length - 2)
        samples = []
        actual_tokens = 0
        for _ in range(args.runs):
            started = time.perf_counter()
            result = engine.embed([text])[0]
            torch.cuda.synchronize()
            samples.append((time.perf_counter() - started) * 1000)
            actual_tokens = result.token_count
        print(
            f"tokens_target={length} tokens_actual={actual_tokens} "
            f"median_ms={statistics.median(samples):.2f} "
            f"min_ms={min(samples):.2f} max_ms={max(samples):.2f}"
        )


if __name__ == "__main__":
    main()
