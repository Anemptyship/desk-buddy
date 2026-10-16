"""Actual multimodal review of generated motion and native dialogue; no fabricated scores."""
import base64
import json
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

from .media import run, write_json
from .showcase import request


def main():
    root = Path(__file__).resolve().parents[2]
    output = root / "showcase"
    load_dotenv(root / ".env")
    scenarios = json.loads((output / "scenarios.json").read_text())
    def reduced(s):
        source = output / "videos" / (s["id"]+".mp4")
        target = output / "qa" / (s["id"]+".review.mp4")
        if not source.exists():
            return None
        run(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",source,
             "-vf","scale=384:216,fps=8","-c:v","libx264","-preset","ultrafast","-crf","28",
             "-c:a","aac","-b:a","48k",target])
        return s,target
    with ThreadPoolExecutor(max_workers=3) as pool:
        clips = [v for v in pool.map(reduced,scenarios) if v]
    parts = [{"text":"Review these SIX ACTUAL generated toy AR concept videos. Watch each entire motion and listen to the native audio. Return strict JSON {clips:[{id,requested_action_visible:boolean,observed_action,spoken_korean_transcript,dialogue_matches_intent:boolean,identity_consistent:boolean,obvious_artifacts:[]}],overall_notes:[]}. Be candid: do not infer speech from an expected line, transcribe only audible words. Do not claim pixel-perfect tracking or metric accuracy. Videos are low-resolution review copies, with original audio. Requested scenarios and intended lines: "+json.dumps(scenarios,ensure_ascii=False)}]
    for scenario,path in clips:
        parts.extend([{"text":"Next video ID: "+scenario["id"]},
            {"inlineData":{"mimeType":"video/mp4","data":base64.b64encode(path.read_bytes()).decode()}}])
    model = os.environ["GEMINI_VISION_MODEL"]
    data = request("models/"+model+":generateContent", {"contents":[{"role":"user","parts":parts}],
        "generationConfig":{"responseMimeType":"application/json"}},timeout=80)
    text = "".join(p.get("text","") for c in data.get("candidates",[]) for p in c.get("content",{}).get("parts",[]) if not p.get("thought"))
    review = json.loads(text)
    write_json(output / "qa/argon_review.json", {"model":model,"type":"AI review of actual generated videos; not physical ground truth","review":review,"usage":data.get("usageMetadata")})
    print(json.dumps(review,ensure_ascii=False,indent=2),flush=True)


if __name__ == "__main__":
    main()
