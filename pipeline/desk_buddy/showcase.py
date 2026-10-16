"""Provider-specific DESK BUDDY concept films. Does not claim calibrated AR output."""
from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import mimetypes
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

from dotenv import load_dotenv

from .media import write_json

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "showcase"
BASE = "https://generativelanguage.googleapis.com/v1beta/"
CHARACTER = """Bricki is an ORIGINAL adorable 4-centimeter-tall chunky block-toy companion.
A wide softly chamfered pale apricot barrel-shaped head without a top stud; two glossy black bead-like
painted eyes, tiny friendly curved mouth, small warm blush cheeks. A compact rounded trapezoid mint-teal
torso with a small simple coral square on the chest, very short cream legs and broad cream boot-shaped
feet. Rounded mitten hands and simple toy shoulder/hip pivots. Big head approximately 42% of total
height. Glossy injection-molded ABS, subtle seams, fine realistic micro-scratches, soft clearcoat highlights.
Unique proportions, no LEGO minifigure anatomy, no studs, no logos, no letters, no human skin on the toy.
Keep exactly this identity, proportions, face, colors and materials across every shot."""


def content(path: Path, kind="image"):
    return {"type": kind, "mime_type": mimetypes.guess_type(path.name)[0] or "image/png",
            "data": base64.b64encode(path.read_bytes()).decode()}


def request(path, payload=None, timeout=350):
    key = os.environ["GEMINI_API_KEY"]
    req = urllib.request.Request(BASE+path, data=json.dumps(payload).encode() if payload is not None else None,
        headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        message = e.read().decode().replace(key, "[REDACTED]")
        raise ValueError(f"Gemini HTTP {e.code}: {message[:1500]}") from None


def output_blocks(data):
    for step in data.get("steps", []):
        if step.get("type") == "model_output":
            yield from step.get("content", [])


def upload_reference():
    cached = OUT / "reference/source_file.json"
    if cached.exists():
        return json.loads(cached.read_text())
    path = OUT / "reference/desk_8s.mp4"
    req = urllib.request.Request("https://generativelanguage.googleapis.com/upload/v1beta/files",
        data=json.dumps({"file":{"display_name":"DESK BUDDY original desk 8-second reference"}}).encode(),
        headers={"x-goog-api-key":os.environ["GEMINI_API_KEY"], "Content-Type":"application/json",
            "X-Goog-Upload-Protocol":"resumable", "X-Goog-Upload-Command":"start",
            "X-Goog-Upload-Header-Content-Length":str(path.stat().st_size),
            "X-Goog-Upload-Header-Content-Type":"video/mp4"})
    with urllib.request.urlopen(req,timeout=45) as r:
        url = r.headers["X-Goog-Upload-URL"]
    if urllib.parse.urlparse(url).hostname != "generativelanguage.googleapis.com":
        raise ValueError("Unexpected reference upload host")
    req = urllib.request.Request(url,data=path.read_bytes(),headers={
        "X-Goog-Upload-Offset":"0", "X-Goog-Upload-Command":"upload, finalize", "Content-Type":"video/mp4"})
    with urllib.request.urlopen(req,timeout=60) as r:
        info = json.load(r)["file"]
    deadline = time.time()+60
    while info.get("state") == "PROCESSING" and time.time() < deadline:
        time.sleep(2)
        info = request(info["name"],timeout=30)
    if info.get("state") != "ACTIVE":
        raise ValueError("Reference video not ready")
    write_json(cached,{"name":info["name"],"uri":info["uri"],"state":info["state"]})
    return info


def create_media(name, kind, inputs, destination: Path, previous=None):
    if destination.exists():
        print(f"Using existing {destination.name}", flush=True)
        return destination
    if kind == "video" and not (OUT / "approval.json").exists():
        raise ValueError("Video calls require the recorded user approval")
    model = os.environ["GEMINI_IMAGE_MODEL" if kind == "image" else "GEMINI_VIDEO_MODEL"]
    format_ = {"type": kind, "aspect_ratio": "16:9"}
    format_.update({"image_size": "2K", "mime_type": "image/jpeg"} if kind == "image" else {"resolution": "720p"})
    payload = {"model": model, "input": inputs, "response_format": format_, "background": False, "stream": False}
    if previous:
        payload["previous_interaction_id"] = previous
    started = time.time()
    write_json(OUT / "qa" / f"{name}.request.json", {"model": model, "kind": kind,
        "response_format": format_, "submitted_at_epoch": started,
        "prompt": [v["text"] for v in inputs if v["type"] == "text"], "status": "submitted"})
    print(f"Requesting {kind}: {name}", flush=True)
    data = request("interactions", payload)
    deadline = time.time()+300
    while data.get("status") in ("in_progress", "requires_action"):
        if data["status"] == "requires_action":
            raise ValueError("Unexpected action requested; no resubmission performed")
        if time.time() > deadline:
            raise ValueError(f"Generation pending: {data.get('id')}; no duplicate request submitted")
        time.sleep(4)
        data = request("interactions/"+urllib.parse.quote(data["id"], safe=""), timeout=60)
    blocks = [b for b in output_blocks(data) if b.get("type") == kind]
    if not blocks:
        summary = {"id": data.get("id"), "status": data.get("status"), "steps": [s.get("type") for s in data.get("steps", [])]}
        write_json(OUT / "qa" / f"{name}.failure.json", summary)
        raise ValueError(f"No {kind} output: {summary}")
    block = blocks[0]
    destination.parent.mkdir(parents=True, exist_ok=True)
    if block.get("data"):
        destination.write_bytes(base64.b64decode(block["data"]))
    elif block.get("uri"):
        uri = block["uri"]
        if not uri.startswith("https://generativelanguage.googleapis.com/"):
            raise ValueError("Media URI is not on the authenticated Google API host")
        req = urllib.request.Request(uri, headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]})
        with urllib.request.urlopen(req, timeout=120) as response:
            destination.write_bytes(response.read())
    else:
        raise ValueError("Output had no downloadable media")
    meta = {"interaction_id": data.get("id"), "status": data.get("status"), "model": model,
            "elapsed_s": time.time()-started, "bytes": destination.stat().st_size,
            "mime_type": block.get("mime_type"), "usage": data.get("usage"),
            "origin": "actual Gemini API generation", "file": str(destination.relative_to(ROOT))}
    write_json(OUT / "qa" / f"{name}.result.json", meta)
    print(f"Saved {name}: {meta['bytes']} bytes in {meta['elapsed_s']:.1f}s", flush=True)
    return destination


def make_character():
    prompt = f"""Produce ONE polished photorealistic character reference sheet for a tiny desk companion.
{CHARACTER}
Warm off-white studio background. Large front three-quarter hero view on the left; clean front,
side and rear orthographic views on the right, with six small expressive head studies along the bottom:
neutral, delighted, surprised, sleepy, curious, concerned. Precisely the SAME single character in all views.
Toy product photography, tactile, charming, friendly and premium. No scene, no desk, no extra characters,
no labels, no typography, no watermark text. Every limb clearly separated and readable."""
    (OUT / "prompts/character.txt").write_text(prompt)
    return create_media("character", "image", [{"type":"text", "text":prompt}], OUT / "character/bricki_reference.jpg")


def make_keyframe(scenario):
    background = ROOT / "scenes/IMG_5803/rgb/000030.jpg"
    reference = OUT / "character/bricki_reference.jpg"
    prompt = f"""Image 1 is the EXACT desk photograph to edit. Image 2 defines the toy character identity.
Add exactly ONE tiny Bricki toy to the photographed desk. {CHARACTER}
This is a live-action AR concept still, not a cartoon environment. Keep the original wooden desk,
MacBook Pro 14-inch, bottles, lunch box, cup, card holder, camera framing and room lighting.
Physical toy height is 4cm: about 1/8 of the laptop's 31.26cm width, never a giant character.
Target pose and location: {scenario['pose']}
Feet, hands or seated hips genuinely touch the supporting surface. Add soft contact shadow,
correct perspective, real object occlusion, room reflections in plastic, matching focus and image grain.
No HUD borders, no headings, no speech bubbles, no captions, no new objects except those explicitly requested.
Only the coffee-rim scene may remove the existing lid. Otherwise preserve the real objects exactly."""
    (OUT / "prompts" / f"{scenario['id']}.image.txt").write_text(prompt)
    return create_media(scenario["id"]+"_keyframe", "image",
        [content(background), content(reference), {"type":"text", "text":prompt}], OUT / "keyframes" / f"{scenario['id']}.jpg")


def make_video(scenario):
    still = OUT / "keyframes" / f"{scenario['id']}.jpg"
    deadline = time.time()+150
    while not still.exists() or not (OUT / "reference/source_file.json").exists():
        if time.time() > deadline:
            raise ValueError("Reference generation did not finish before the video submission deadline")
        time.sleep(1)
    prompt = f"""Edit the supplied 8-second original desk video by adding the tiny toy character from the
reference sheet, using the scene concept image as the target appearance, pose, scale and interaction.
Produce ONE continuous 8-second live-action shot. Keep the source video's real camera motion.
Keep the real desk, laptop, bottles, cup and room unchanged and the tiny toy's identity perfectly consistent.
{CHARACTER}
Action: {scenario['action']}
Timing: 0-1s establish the same tiny character with breathing and blinking; 1-5s perform the requested
action with anticipation, weight, planted feet, toy-like joint motion and soft contact shadows;
5-8s let the character look directly toward the viewer and deliver the line naturally.
Spoken Korean dialogue, exactly: “{scenario['line']}”
Voice: tiny cute bright friendly high-pitched toy voice, quick but intelligible, not shrill.
Audio: quiet indoor room tone, small plastic footsteps/taps, a soft landing tick when appropriate;
no music and no unrelated voices. Paint-on mouth subtly changes for speech, with expressive eyes.
The character NEVER freezes: subtle breathing, blinking, head attention and balance continue.
Gravity must be clear: jump has crouch, takeoff, airborne arc, landing and tiny squash.
Maintain scale at 4cm, desk contact, lighting, shadows and physical occlusion throughout.
    Keep the original single smooth handheld shot. No scene cuts, no text, no subtitles,
no montage, no redesign, no extra toy, no floating feet or sliding on the surface.
This is a generated concept film based on the supplied photograph, not a tracking accuracy demonstration."""
    (OUT / "prompts" / f"{scenario['id']}.video.txt").write_text(prompt)
    video = json.loads((OUT / "reference/source_file.json").read_text())
    return create_media(scenario["id"]+"_video", "video", [{"type":"video","uri":video["uri"]},
                        content(still), content(OUT / "character/bricki_reference.jpg"), {"type":"text", "text":prompt}],
                        OUT / "videos" / f"{scenario['id']}.mp4")


def batch(function, scenarios, workers):
    failures = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(function, s):s for s in scenarios}
        for future in as_completed(futures):
            scenario = futures[future]
            try:
                future.result()
            except Exception as error:
                failures.append({"scenario":scenario["id"], "error":str(error)})
                print(f"Failed {scenario['id']}: {error}", flush=True)
    if failures:
        write_json(OUT / "qa" / f"{function.__name__}_failures.json", failures)
    return failures


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["character","keyframes","videos","upload"])
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    scenarios = json.loads((OUT / "scenarios.json").read_text())
    if args.mode == "character":
        make_character()
    elif args.mode == "keyframes":
        batch(make_keyframe, scenarios, args.workers)
    elif args.mode == "upload":
        upload_reference()
    else:
        batch(make_video, scenarios, args.workers)


if __name__ == "__main__":
    main()
