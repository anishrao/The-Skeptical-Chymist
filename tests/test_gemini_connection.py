"""Verify OpenAlex (via isolated curl) and Gemini API key."""

import os
from pathlib import Path
from dotenv import load_dotenv
from src.llm.gemini_client import GeminiLLMClient
from src.ingestion.literature_snowball import safe_curl_get_json
from pydantic import BaseModel


class QuickPing(BaseModel):
    status: str


def main():
    project_env = Path(__file__).resolve().parents[1] / ".env"
    if project_env.exists():
        load_dotenv(project_env, override=True)

    oa_key = os.environ.get("OPENALEX_API_KEY", "").strip().strip('"').strip("'")
    print(f"1. [OpenAlex] Key present in project .env: {bool(oa_key)} (length={len(oa_key)})", flush=True)

    data = safe_curl_get_json(
        "https://api.openalex.org/works",
        {"search": "gold nanobipyramids", "per-page": 2, "api_key": oa_key},
        max_time_s=8,
    )
    if data and "results" in data:
        hits = data["results"]
        print(f"2. [OpenAlex curl] SUCCESS! Found {len(hits)} works (e.g., '{hits[0].get('display_name')[:65]}')", flush=True)
    else:
        print(f"2. [OpenAlex curl] Response: {str(data)[:200]}", flush=True)

    print("3. [Gemini] Testing structured output...", flush=True)
    llm = GeminiLLMClient()
    res = llm.generate_structured(prompt="Return status='OK'", schema_cls=QuickPing)
    print(f"4. [Gemini] SUCCESS! {res.model_dump()}", flush=True)


if __name__ == "__main__":
    main()
