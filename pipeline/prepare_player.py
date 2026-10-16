"""Prepare rectified real footage for the live player; does not render an avatar."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json
import shutil
import cv2
import numpy as np
from desk_buddy.media import encode_vfr,write_json

root=Path(__file__).resolve().parents[1]
scene=root/'scenes/IMG_5803'
output=root/'player/public/scene'
output.mkdir(parents=True,exist_ok=True)
cameras=json.loads((scene/'cameras.json').read_text())
frames=json.loads((scene/'frames.json').read_text())
images=scene/'player_frames'
images.mkdir(exist_ok=True)
cv2.setNumThreads(1)
def frame(pair):
    f,c=pair
    image=cv2.imread(str(scene/f['rgb']))
    K=np.float64(c['intrinsics'])
    corrected=cv2.undistort(image,K,np.float64(c['distortion']),None,K)
    cv2.imwrite(str(images/f"{f['index']:06d}.png"),corrected)
with ThreadPoolExecutor(max_workers=4) as pool:
    list(pool.map(frame,zip(frames,cameras['frames'])))
encode_vfr(scene,images,output/'desk.mp4')
write_json(output/'cameras.json',{'convention':cameras['convention'],'frames':[{'t':c['timestamp_s'],'K':c['intrinsics'],'c2w':c['camera_to_world']} for c in cameras['frames']]})
shutil.copy(scene/'surfaces.json',output/'surfaces.json')
print('Real rectified footage and 506 measured camera samples prepared.')
