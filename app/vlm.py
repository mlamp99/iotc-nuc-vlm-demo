"""Slow-path Vision-Language Model via OpenVINO GenAI.

The VLM is heavy (a few seconds per answer), so it is NEVER run inline with the
camera loop — main.py drives it from a dedicated worker thread. This module just
wraps load + generate, with GPU->CPU fallback so a driver mismatch on the target
device degrades gracefully instead of crashing the demo.
"""
from __future__ import annotations

import gc
import logging
import os
import threading

import numpy as np
from PIL import Image

log = logging.getLogger("vlm")


class VLM:
    def __init__(self, model_path: str, device: str, max_new_tokens: int):
        import openvino as ov
        import openvino_genai as ov_genai

        self._ov = ov
        self._genai = ov_genai
        self.max_new_tokens = max_new_tokens
        self.device = self._load_with_fallback(model_path, device)

    def _load_with_fallback(self, model_path: str, preferred: str):
        candidates = [preferred]
        if preferred not in ("CPU",):
            candidates.append("CPU")
        last_err: Exception | None = None
        for dev in candidates:
            try:
                self.pipe = self._genai.VLMPipeline(model_path, dev)
                if dev != preferred:
                    log.warning("VLM device %s unavailable; using %s", preferred, dev)
                else:
                    log.info("VLM ready: model=%s device=%s", model_path, dev)
                return dev
            except Exception as e:  # noqa: BLE001
                last_err = e
                log.warning("VLM load on %s failed (%s); trying next", dev, e)
        raise RuntimeError(f"Could not load VLM on any device: {last_err}")

    def _to_tensor(self, frame_bgr: np.ndarray):
        # OpenCV gives BGR; models expect RGB.
        rgb = frame_bgr[:, :, ::-1]
        pil = Image.fromarray(rgb).convert("RGB")
        return self._ov.Tensor(np.array(pil))

    def describe(self, frame_bgr: np.ndarray, prompt: str) -> str:
        cfg = self._genai.GenerationConfig()
        cfg.max_new_tokens = self.max_new_tokens
        tensor = self._to_tensor(frame_bgr)
        result = self.pipe.generate(prompt, images=[tensor], generation_config=cfg)
        return str(result).strip()


class VlmManager:
    """Holds the active VLM and supports hot-swapping the model at runtime
    (e.g. from a cloud command). Only one model is resident at a time: a switch
    loads the new one, swaps it in, and frees the old to keep memory bounded.

    `aliases` maps friendly names (e.g. "2b", "7b") to model directories; an
    unknown name is treated as a literal path.
    """

    def __init__(self, initial: str, device: str, max_new_tokens: int, aliases: dict | None = None):
        self.device = device
        self.max_new_tokens = max_new_tokens
        self.aliases = {k.lower(): v for k, v in (aliases or {}).items()}
        self._lock = threading.Lock()
        self._vlm: VLM | None = None
        self._path: str | None = None
        self.load(initial)

    def resolve(self, name: str) -> str:
        if not name:
            return self._path or ""
        return self.aliases.get(name.strip().lower(), name.strip())

    @property
    def name(self) -> str:
        return os.path.basename(self._path) if self._path else "?"

    @property
    def device_used(self) -> str:
        with self._lock:
            return self._vlm.device if self._vlm else self.device

    def load(self, name: str) -> str:
        """Load the named/aliased model and make it active. Blocking."""
        path = self.resolve(name)
        log.info("Loading VLM: %s", path)
        new = VLM(path, self.device, self.max_new_tokens)
        with self._lock:
            old = self._vlm
            self._vlm = new
            self._path = path
        del old
        gc.collect()
        log.info("VLM active: %s on %s", self.name, new.device)
        return self.name

    def describe(self, frame_bgr: np.ndarray, prompt: str) -> str:
        with self._lock:
            v = self._vlm
        return v.describe(frame_bgr, prompt)
