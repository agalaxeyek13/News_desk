"""
Local GPU-backed LLM for the FDE Briefing pipeline.

Loads the Gemma GGUF model once (lazily, on first use) via llama-cpp-python
with all layers offloaded to the GPU. Both fde/extractor.py and
fde/composer.py go through chat() here instead of a cloud API.

Generation is serialized behind a lock — a single llama.cpp context isn't
safe for concurrent calls, and run_daily.py processes articles/clusters
one at a time anyway.
"""

import logging
import threading

from config import FDE_LOCAL_MODEL_PATH, FDE_LOCAL_MODEL_CTX, FDE_LOCAL_MODEL_GPU_LAYERS

logger = logging.getLogger(__name__)

_llm = None
_lock = threading.Lock()


def _get_llm():
    global _llm
    if _llm is None:
        from llama_cpp import Llama  # noqa: PLC0415

        logger.info("Loading local LLM (GPU): %s", FDE_LOCAL_MODEL_PATH)
        _llm = Llama(
            model_path=FDE_LOCAL_MODEL_PATH,
            n_gpu_layers=FDE_LOCAL_MODEL_GPU_LAYERS,
            n_ctx=FDE_LOCAL_MODEL_CTX,
            verbose=False,
        )
        logger.info("Local LLM ready")
    return _llm


def chat(system_prompt: str, user_content: str, max_tokens: int = 400) -> str:
    """
    One chat completion. Returns the assistant's text, or "" on any failure
    — callers treat an empty string as "extraction/synthesis unavailable"
    rather than crashing the run.
    """
    try:
        with _lock:
            llm = _get_llm()
            result = llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=max_tokens,
                temperature=0.2,
            )
        return result["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error("Local LLM call failed: %s", e)
        return ""
