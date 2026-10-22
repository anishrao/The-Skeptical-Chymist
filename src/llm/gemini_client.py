"""Gemini API Client using isolated /usr/bin/curl subprocesses with Automatic Free-Tier Model Pool Rotation.
When a model hits the Free Tier 20 requests/day limit (429 too_many_requests), it automatically rotates
to the next available Gemini / Gemma 4 model on the API key without stalling.
"""

import os
import json
import time
import subprocess
from pathlib import Path
from typing import Type, TypeVar, List, Optional, Dict, Any
from dotenv import load_dotenv
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

# Ordered pool of current models (following gemini-api-dev skill guidelines)
MODEL_ROTATION_POOL = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemini-3.1-pro-preview",
    "gemma-4-31b-it",
    "gemma-4-26b-a4b-it",
    "gemini-3.8-flash",
]


class GeminiLLMClient:
    """Hang-free Gemini API client with automatic daily-quota model rotation."""

    def __init__(
        self,
        default_model: str = "gemini-3.5-flash-lite",
        embedding_model: str = "gemini-embedding-2",
        max_time_s: int = 65,
    ):
        home_env = Path.home() / ".env"
        project_env = Path(__file__).resolve().parents[2] / ".env"
        if home_env.exists():
            load_dotenv(home_env, override=True)
        if project_env.exists():
            load_dotenv(project_env, override=True)

        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if api_key:
            api_key = api_key.strip().strip('"').strip("'")
        if not api_key:
            raise EnvironmentError(
                "Missing GEMINI_API_KEY in environment or ~/.env. "
                "Please add GEMINI_API_KEY to ~/.env or project .env before running LLM calls."
            )

        self.api_key = api_key
        self.default_model = default_model
        self.embedding_model = embedding_model
        self.max_time_s = max_time_s
        self.exhausted_models: set[str] = set()

        self._header_file = Path(
            "/Users/anishrao/.gemini/antigravity/brain/3cdd7724-1da1-4f0b-86a3-264634a6c257/scratch/.gemini_headers"
        )
        self._header_file.parent.mkdir(parents=True, exist_ok=True)
        self._header_file.write_text(
            f"x-goog-api-key: {self.api_key}\nContent-Type: application/json\nAccept: application/json\n"
        )
        os.chmod(self._header_file, 0o600)

    def _pick_active_model(self, requested_model: Optional[str] = None) -> str:
        preferred = requested_model or self.default_model
        if preferred not in self.exhausted_models:
            return preferred
        for m in MODEL_ROTATION_POOL:
            if m not in self.exhausted_models:
                return m
        # If all tried, clear and retry pool
        self.exhausted_models.clear()
        return MODEL_ROTATION_POOL[0]

    def _curl_post_json(
        self, url: str, payload: Dict[str, Any], timeout_s: Optional[int] = None
    ) -> Dict[str, Any]:
        t_s = timeout_s or self.max_time_s
        body_str = json.dumps(payload)
        cmd = [
            "/usr/bin/curl",
            "-sL",
            "--connect-timeout",
            "6",
            "--max-time",
            str(t_s),
            "-X",
            "POST",
            "-H",
            f"@{self._header_file}",
            "--data-binary",
            "@-",
            url,
        ]
        proc = subprocess.run(
            cmd,
            input=body_str,
            capture_output=True,
            text=True,
            timeout=t_s + 5,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"curl exited with code {proc.returncode}: {proc.stderr[:200]}")
        if not proc.stdout.strip():
            raise RuntimeError("Empty response from Gemini API")
        data = json.loads(proc.stdout)
        if isinstance(data, list) and data and "error" in data[0]:
            raise RuntimeError(f"Gemini API Error: {json.dumps(data[0]['error'])[:350]}")
        if isinstance(data, dict) and "error" in data:
            raise RuntimeError(f"Gemini API Error: {json.dumps(data['error'])[:350]}")
        return data

    @staticmethod
    def _extract_interaction_text(resp_data: Dict[str, Any]) -> str:
        """Extract trailing model_output text from an Interactions API response."""
        if "output_text" in resp_data and resp_data["output_text"]:
            return resp_data["output_text"]
        texts: List[str] = []
        for step in resp_data.get("steps", []):
            if step.get("type") == "model_output":
                for part in step.get("content", []):
                    if part.get("type") == "text" and part.get("text"):
                        texts.append(part["text"])
        if texts:
            return "".join(texts)
        for cand in resp_data.get("candidates", []):
            for part in cand.get("content", {}).get("parts", []):
                if "text" in part:
                    texts.append(part["text"])
        return "".join(texts)

    def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        previous_interaction_id: Optional[str] = None,
        thinking_level: Optional[str] = None,
    ) -> tuple[str, str]:
        """Generate free-form text via `/v1beta/interactions` with automatic model rotation on 429 RPD limits."""
        url = "https://generativelanguage.googleapis.com/v1beta/interactions"
        for attempt in range(len(MODEL_ROTATION_POOL) + 2):
            active_model = self._pick_active_model(model)
            payload: Dict[str, Any] = {
                "model": active_model,
                "input": prompt,
            }
            if system_instruction:
                payload["system_instruction"] = system_instruction
            if previous_interaction_id:
                payload["previous_interaction_id"] = previous_interaction_id
            if thinking_level:
                payload["generation_config"] = {"thinking_level": thinking_level}

            try:
                data = self._curl_post_json(url, payload)
                text = self._extract_interaction_text(data)
                return text, data.get("id", "")
            except Exception as e:
                err_str = str(e)
                if (
                    "per day" in err_str.lower()
                    or "too_many_requests" in err_str.lower()
                    or "quota" in err_str.lower()
                    or "not found" in err_str.lower()
                    or "not supported" in err_str.lower()
                ):
                    print(
                        f"  [Quota/Model rotation: '{active_model}' exhausted or unavailable -> rotating to next model]",
                        flush=True,
                    )
                    self.exhausted_models.add(active_model)
                    continue
                if attempt >= len(MODEL_ROTATION_POOL):
                    raise
                time.sleep(3)
        raise RuntimeError("All models in rotation pool exhausted their Free Tier daily limit.")

    def generate_structured(
        self,
        prompt: str,
        schema_cls: Type[T],
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        thinking_level: Optional[str] = None,
    ) -> T:
        """Generate a strictly typed Pydantic object via `/v1beta/interactions` with automatic model rotation."""
        url = "https://generativelanguage.googleapis.com/v1beta/interactions"
        for attempt in range(len(MODEL_ROTATION_POOL) + 2):
            active_model = self._pick_active_model(model)
            payload: Dict[str, Any] = {
                "model": active_model,
                "input": prompt,
                "response_format": [
                    {
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": schema_cls.model_json_schema(),
                    }
                ],
            }
            if system_instruction:
                payload["system_instruction"] = system_instruction
            if thinking_level:
                payload["generation_config"] = {"thinking_level": thinking_level}

            try:
                data = self._curl_post_json(url, payload)
                raw_text = self._extract_interaction_text(data) or "{}"
                return schema_cls.model_validate_json(raw_text)
            except Exception as e:
                err_str = str(e)
                if (
                    "per day" in err_str.lower()
                    or "too_many_requests" in err_str.lower()
                    or "quota" in err_str.lower()
                    or "not found" in err_str.lower()
                    or "not supported" in err_str.lower()
                ):
                    print(
                        f"  [Quota/Model rotation: '{active_model}' hit limit -> switching to next model]",
                        flush=True,
                    )
                    self.exhausted_models.add(active_model)
                    continue
                if attempt >= len(MODEL_ROTATION_POOL):
                    raise
                time.sleep(3)
        raise RuntimeError("All models in rotation pool exhausted their Free Tier daily limit.")

    def embed_texts(self, texts: List[str], output_dimensionality: int = 768) -> List[List[float]]:
        """Embed text chunks using `gemini-embedding-2` (or fallback `gemini-embedding-001`) via `/usr/bin/curl`."""
        if not texts:
            return []
        batch_size = 50
        all_embeddings: List[List[float]] = []
        for emb_model in [self.embedding_model, "gemini-embedding-001"]:
            try:
                all_embeddings = []
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{emb_model}:batchEmbedContents"
                for i in range(0, len(texts), batch_size):
                    batch = texts[i : i + batch_size]
                    payload = {
                        "requests": [
                            {
                                "model": f"models/{emb_model}",
                                "content": {"parts": [{"text": t}]},
                                "outputDimensionality": output_dimensionality,
                            }
                            for t in batch
                        ]
                    }
                    data = self._curl_post_json(url, payload, timeout_s=30)
                    for emb in data.get("embeddings", []):
                        all_embeddings.append(list(emb.get("values", [])))
                if len(all_embeddings) == len(texts):
                    return all_embeddings
            except Exception:
                continue
        raise RuntimeError("Embedding models exhausted or unavailable")
