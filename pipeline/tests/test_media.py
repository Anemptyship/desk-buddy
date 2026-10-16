import json
import shutil

import cv2
import numpy as np
import pytest

from desk_buddy.media import encode_vfr, run, write_json


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg required")
def test_vfr_encoding_keeps_pts_and_last_frame_duration(tmp_path):
    output = tmp_path / "frames"
    output.mkdir()
    times = [0., .04, .11]
    write_json(tmp_path / "frames.json", [{"index":i,"timestamp_s":t} for i,t in enumerate(times)])
    write_json(tmp_path / "source.json", {"duration_s":.21})
    for i in range(3):
        cv2.imwrite(str(output / f"{i:06d}.png"), np.full((90,160,3),i*70,np.uint8))
    target = tmp_path / "debug.mp4"
    encode_vfr(tmp_path, output, target)
    data = json.loads(run(["ffprobe","-v","error","-select_streams","v:0","-show_frames",
        "-show_entries","frame=best_effort_timestamp_time:stream=duration:frame_side_data=","-of","json",target]))
    pts = [float(f["best_effort_timestamp_time"]) for f in data["frames"]]
    np.testing.assert_allclose(pts[:3],times,atol=1e-6)
    assert len(pts) == 4
    assert abs(float(data["streams"][0]["duration"])-.21) < 1e-6
