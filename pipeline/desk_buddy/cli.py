from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
from pathlib import Path

from dotenv import load_dotenv

from .media import prepare


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="DESK BUDDY stage 1 matchmove pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    p = sub.add_parser("prepare")
    p.add_argument("video", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--width", type=int, default=960)
    p = sub.add_parser("models")
    p.add_argument("--output", type=Path, default=Path("artifacts/gemini_models.json"))
    p = sub.add_parser("reconstruct")
    p.add_argument("scene", type=Path)
    p.add_argument("--device", choices=["mps", "cuda", "cpu"], default="mps")
    p.add_argument("--keyframes", type=int, default=48)
    p.add_argument("--resolution", type=int, default=280)
    p = sub.add_parser("track")
    p.add_argument("scene", type=Path)
    p.add_argument("--annotations", type=Path, required=True)
    p = sub.add_parser("calibrate")
    p.add_argument("scene", type=Path)
    p.add_argument("--prediction", type=Path, required=True)
    p = sub.add_parser("depth")
    p.add_argument("scene", type=Path)
    p.add_argument("--device", choices=["mps", "cuda", "cpu"], default="mps")
    p.add_argument("--resolution", type=int, default=224)
    p.add_argument("--batch-size", type=int, default=12)
    p.add_argument("--limit", type=int)
    p = sub.add_parser("debug")
    p.add_argument("scene", type=Path)
    p = sub.add_parser("report")
    p.add_argument("scene", type=Path)
    p = sub.add_parser("surfaces")
    p.add_argument("scene", type=Path)
    p = sub.add_parser("perceive", help="Map desk objects and affordances with Gemini 4 Argon")
    p.add_argument("--scene", type=Path, default=Path("player/public/scene"))
    p.add_argument("--times", type=float, nargs="+", default=[1.5, 6.5, 13.0, 15.5])
    p.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            import importlib.util
            status = {"machine": platform.machine(), "ffmpeg": shutil.which("ffmpeg"),
                      "ffprobe": shutil.which("ffprobe"), "gemini_key_set": bool(os.getenv("GEMINI_API_KEY")),
                      "da3_source": os.getenv("DA3_SOURCE")}
            if importlib.util.find_spec("torch"):
                import torch
                status.update(torch=torch.__version__, mps_available=torch.backends.mps.is_available(), cuda_available=torch.cuda.is_available())
            print(json.dumps(status, indent=2))
        elif args.command == "perceive":
            from .perceive import perceive
            print(json.dumps(perceive(args.scene, args.times, args.output), indent=2))
        elif args.command == "prepare":
            print(json.dumps(prepare(args.video, args.output, args.width), indent=2))
        elif args.command == "models":
            from .ai import available_models
            print(json.dumps(available_models(args.output), indent=2))
        elif args.command == "reconstruct":
            from .reconstruction import reconstruct
            reconstruct(args.scene, args.device, args.keyframes, args.resolution)
        elif args.command == "track":
            from .tracking import track
            track(args.scene, args.annotations)
        elif args.command == "calibrate":
            from .calibration import calibrate
            calibrate(args.scene, args.prediction)
        elif args.command == "depth":
            from .dense import dense
            dense(args.scene, args.device, args.resolution, args.batch_size, args.limit)
        elif args.command == "debug":
            from .debug import render_debug
            render_debug(args.scene)
        elif args.command == "report":
            from .report import summarize
            summarize(args.scene)
        elif args.command == "surfaces":
            from .surfaces import reconstruct_desk
            reconstruct_desk(args.scene)
    except (ValueError, FileNotFoundError, FileExistsError) as e:
        parser.exit(2, f"Error: {e}\n")


if __name__ == "__main__":
    main()
