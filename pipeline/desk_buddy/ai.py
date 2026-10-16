from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

from .media import write_json


def available_models(output: Path):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise ValueError("GEMINI_API_KEY is unset. No model availability or AI result can be reported.")
    models, token = [], None
    while True:
        from urllib.parse import urlencode
        query = urlencode({"pageSize": 1000, **({"pageToken": token} if token else {})})
        request = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models?" + query,
                                        headers={"x-goog-api-key": key})
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.load(response)
        models.extend(data.get("models", []))
        token = data.get("nextPageToken")
        if not token:
            break
    write_json(output, {"models": models})
    return [{"name": m["name"], "methods": m.get("supportedGenerationMethods", [])} for m in models]
