"""Package real generated clips, preserving each original and its native audio."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .media import run, write_json

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "showcase"
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"


def label(scenario):
    canvas = Image.new("RGBA", (1280,720), (0,0,0,0))
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle((25,23,500,91),16,fill=(15,29,28,204))
    d.text((45,36),scenario["id"][:2]+"  "+scenario["title"],font=ImageFont.truetype(FONT,31),fill=(237,251,242))
    d.rounded_rectangle((1030,25,1250,63),10,fill=(15,29,28,180))
    d.text((1046,31),"AI 생성 콘셉트 영상",font=ImageFont.truetype(FONT,20),fill=(197,224,212))
    # Exact readable Korean caption; the underlying native voice remains intact.
    text = scenario["line"]
    font = ImageFont.truetype(FONT,31)
    box = d.textbbox((0,0),text,font=font)
    width = box[2]-box[0]
    left = (1280-width)//2
    d.rounded_rectangle((left-24,650,left+width+24,701),12,fill=(15,29,28,200))
    d.text((left,659),text,font=font,fill=(255,255,250))
    path = OUT / "qa" / (scenario["id"]+".overlay.png")
    canvas.save(path)
    return path


def package_one(scenario):
    source = OUT / "videos" / (scenario["id"]+".mp4")
    if not source.exists():
        return None
    overlay = label(scenario)
    target = OUT / "final" / (scenario["id"]+".mp4")
    info = json.loads(run(["ffprobe","-v","error","-show_streams","-show_format","-of","json",source]))
    audio = any(s["codec_type"]=="audio" for s in info["streams"])
    command = ["ffmpeg","-hide_banner","-loglevel","error","-y","-i",source,"-i",overlay,
         "-filter_complex","[0:v]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1[v];[v][1:v]overlay=0:0:enable='gte(t,0)'[out]",
         "-map","[out]","-map","0:a?","-r","24","-c:v","libx264","-preset","veryfast","-crf","18",
         "-pix_fmt","yuv420p","-c:a","aac","-ar","48000","-ac","2","-movflags","+faststart",target]
    run(command)
    cap = cv2.VideoCapture(str(source))
    count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    images=[]
    for fraction in (.12,.50,.88):
        cap.set(cv2.CAP_PROP_POS_FRAMES,int(count*fraction))
        ok,frame = cap.read()
        if ok:
            images.append(cv2.resize(frame,(480,270)))
    cap.release()
    if images:
        sheet = np.concatenate(images,axis=1)
        cv2.imwrite(str(OUT / "qa" / (scenario["id"]+".contact.jpg")),sheet)
    return {"id":scenario["id"],"title":scenario["title"],"file":str(target.relative_to(ROOT)),
            "duration_s":float(info["format"]["duration"]),"native_audio_present":audio,
            "generated_by":"Gemini Omni; actual provider output preserved in showcase/videos",
            "caption":scenario["line"]}


def main():
    scenarios = json.loads((OUT / "scenarios.json").read_text())
    (OUT / "final").mkdir(exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = [r for r in pool.map(package_one,scenarios) if r]
    concat = OUT / "final/concat.txt"
    concat.write_text("\n".join("file "+r["id"]+".mp4" for r in results)+"\n")
    if results:
        run(["ffmpeg","-hide_banner","-loglevel","error","-y","-f","concat","-safe","0","-i",concat,
             "-c","copy","-movflags","+faststart",OUT / "DESK_BUDDY_scenarios.mp4"])
    write_json(OUT / "manifest.json",{"type":"AI-generated scenario concept films; not a calibrated AR player recording",
        "image_model_env":"GEMINI_IMAGE_MODEL","video_model_env":"GEMINI_VIDEO_MODEL",
        "clips":results,"completed_clips":len(results),"target_clips":6})
    lines=["# DESK BUDDY — 시나리오 영상", "", "실제 책상 영상과 Nano Banana 캐릭터·장면 이미지를 입력으로 사용한 Omni 생성 콘셉트 영상입니다.",
           "프레임 단위 AR 합성 플레이어의 정확도를 검증한 영상은 아닙니다.","", "- 합본: [DESK_BUDDY_scenarios.mp4](DESK_BUDDY_scenarios.mp4)",
           "- 캐릭터: [bricki_reference.jpg](character/bricki_reference.jpg)",""]
    lines.extend(f"- [{r['title']}](final/{r['id']}.mp4) — {r['duration_s']:.1f}초" for r in results)
    lines.extend(["","원본 생성 파일은 videos/, 장면별 기준 이미지는 keyframes/, 실제 프롬프트는 prompts/, API 결과 메타데이터와 샘플 프레임은 qa/에 있습니다.",
                  "한글 자막은 후처리로 추가했으며 영상의 원래 생성 음성은 보존했습니다. 자막이 있다고 해당 음성 대사가 정확히 발화되었다고 보장하지 않습니다."])
    (OUT / "README.md").write_text("\n".join(lines)+"\n")
    print(json.dumps(results,ensure_ascii=False,indent=2),flush=True)


if __name__ == "__main__":
    main()
