import os

import torch


def resolve_device() -> str:
    mode = os.getenv("AGENT_DEVICE", "auto").strip().lower()

    if mode == "cpu":
        return "cpu"

    cuda_available = torch.cuda.is_available()

    if mode == "cuda":
        if not cuda_available:
            raise RuntimeError("AGENT_DEVICE=cuda, but CUDA is not available")
        return "cuda"

    if mode == "auto":
        return "cuda" if cuda_available else "cpu"

    raise ValueError(f"Unsupported AGENT_DEVICE={mode}")


def use_cuda() -> bool:
    return resolve_device() == "cuda"
