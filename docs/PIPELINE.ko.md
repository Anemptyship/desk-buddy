# DESK BUDDY

촬영한 책상 영상 위에 오리지널 블록 장난감 아바타를 합성하는 프로젝트입니다. 사용자가 정한 순서대로 **1단계만 진행**했습니다. 현재 상태는 **실제 영상 분석 및 진단 렌더 완료, 합성 품질 검증 미통과**입니다. 플레이어나 캐릭터를 완성했다고 간주하지 않습니다.

## 바로 확인할 결과

- `scenes/IMG_5803/debug_track.mp4`: 실제 영상 위 1cm 격자와 빨간 2.5cm 큐브 3개. 추정 기하라는 표시를 영상에 넣었습니다.
- `scenes/IMG_5803/report.json`: 측정 결과와 미충족 항목. `advance_to_stage_2: false`.
- `scenes/IMG_5803/reconstruction/keyframes_8_224/depth_preview.jpg`: 실제 모델 추론 결과의 RGB/상대 깊이 비교.
- `scenes/IMG_5803/cameras.json`: 506프레임의 내·외부 파라미터, 원본 프레임별 타임스탬프.
- `scenes/IMG_5803/depth/`: 원시·시간 안정화 깊이, 16비트 PNG. **픽셀값 × 0.001 = 추정 미터**. 0은 무효입니다.

## 실제로 실행한 내용

입력은 `/Users/ben/Downloads/IMG_5803.mov`, 1920×1080, 16.878초, iPhone HLG/Dolby Vision 영상입니다. 컨테이너의 프레임 수 표기와 실제 디코딩 프레임 수가 달라 **실제 디코딩된 506프레임**과 presentation timestamp를 사용했습니다. 프레임 번호를 명목 30fps로 곱하지 않습니다. 실제 간격은 약 33.333~35ms입니다.

HLG BT.2020을 선형화한 뒤 고정 Hable 변환과 sRGB 출력으로 960×540 분석 이미지를 만들었습니다. 노출을 프레임마다 임의 보정하지 않았습니다. 이 경로는 Dolby Vision RPU를 적용한 정식 마스터링 변환이 아닙니다. 원본은 수정하지 않았습니다.

**모델 선택:** 공식 Depth Anything 3 Small을 Apple MPS에서 실행했습니다. 설치 후 실제 8뷰 추론과 506프레임 포즈 조건부 깊이 계산을 확인했습니다. 이 모델은 상대 깊이·카메라를 함께 예측하면서 더 큰 모델보다 로컬 시험 부담이 작아 선택했습니다. 작은 모델의 초점거리 추정은 그대로 신뢰하지 않고 실물 기준으로 다시 보정했습니다. 모델 가중치는 로컬에 캐시했습니다. SAM 3는 공식 CUDA 요구사항 때문에 이 Mac에서 실행했다고 보고하지 않습니다.

사용자가 확인한 **맥북 프로 14인치**의 공식 가로 31.26cm·세로 22.12cm를 기준으로 삼았습니다. 30번 프레임의 노트북 모서리는 수동 표시입니다. 노트북 표면의 SIFT 특징점을 기준 프레임에 직접 정합하고, 실패한 14프레임만 기준 프레임에 이미 등록된 인접 뷰를 거쳐 한 번 재매칭했습니다. 이전 포즈 고정이나 단순 보간으로 실패를 숨기지 않았습니다.

노트북 평면에서 공유 초점거리·방사 왜곡과 뷰별 포즈를 공동 최적화하고 PnP로 각 프레임을 구했습니다. **노트북 표면 기준 포즈 재투영 RMS 약 0.47px**, 정합 추정에 사용하지 않은 특징점의 중앙 오차 약 **0.33px**입니다. 이는 책상 전체의 정확도나 드리프트 0을 증명하지 않습니다. 카메라 보정은 수동 모서리와 평면 가정에 의존합니다. 전체 장면의 3D 번들 조정은 수행하지 않았습니다.

깊이는 노트북 크기를 이용해 미터 스케일로 보정했습니다. 포즈로 이전 깊이를 재투영하고 z-buffer·깊이 차이·색 차이로 이력을 거부하는 필터를 적용했습니다. 무효 픽셀은 배경 깊이로 채우지 않습니다. 단안 깊이에서 나온 책상 평면은 물리적으로 맞지 않아 최종 기준으로 사용하지 않았습니다. 실제 책상 나뭇결을 다중 뷰 삼각측량한 점들에 RANSAC을 적용해 별도의 책상 평면 후보를 구했습니다.

## 아직 통과하지 못한 항목

깊이 해상도는 224×126이며 노트북 평면 기준 깊이 중앙 절대 오차는 약 **1.8cm**입니다. 4cm 캐릭터의 정밀 합성용으로는 부족합니다. 이 수치는 독립적인 전체 장면 실측 오차가 아닙니다. 격자/큐브 영상은 진단용이며 접촉 그림자·캐릭터·최종 오클루전 합성이 아닙니다.

SAM 영상 마스크, 물건별 프록시 기하와 검증된 행동 지점, 물리적으로 보정된 조명·환경맵, 전체 3D 번들 조정, Argon 품질 평가는 남아 있습니다. `.env`에 Gemini 키가 없어 모델 목록 조회나 Gemini 호출을 실행하지 않았습니다. `objects.json`은 실제 프레임을 보고 작성한 수동 물건 목록이며 AI 분석 결과가 아닙니다. 알 수 없는 조명/노출/초점 값은 `null`로 기록합니다.

**눈으로 확인할 지점:** 시작 부분의 손, 약 10~11초의 빠른 카메라 이동, 큐브 발밑과 노트북 모서리에서 격자 고정 여부, 물병·지갑 주변에서 깊이가 물체 윤곽을 따라가는지 확인하세요. 이 구간 검증을 통과하기 전에는 2단계를 시작하지 않습니다.

## 설치와 재실행

Apple Silicon, Python 3.12, `uv`, `ffmpeg`, `ffprobe`가 필요합니다. 아래 명령은 프로젝트 루트에서 실행합니다. 모델 다운로드와 최초 설치에는 네트워크가 필요하며 유료 생성 API는 사용하지 않습니다.

```sh
export UV_CACHE_DIR="$PWD/.cache/uv"
uv sync --extra geometry --extra test
.venv/bin/python pipeline/setup_geometry.py
cp .env.example .env
.venv/bin/desk-buddy doctor
```

DA3 코드는 공식 저장소의 특정 커밋에 고정됩니다. 사용하지 않는 COLMAP exporter가 macOS에서 OpenMP 런타임을 중복 로드하는 문제를 피하도록 해당 import만 지연시켰습니다. 네트워크 수식·가중치는 변경하지 않았습니다. CUDA 전용 `xformers`·`gsplat`은 이 추론 경로에 사용하지 않습니다.

현재 결과를 보존하려면 새 scene 폴더를 사용하세요. 같은 영상을 재분석할 때 아래 예시의 `IMG_5803_rerun`을 사용하면 기존 결과를 덮어쓰지 않습니다.

```sh
.venv/bin/desk-buddy prepare /Users/ben/Downloads/IMG_5803.mov --output scenes/IMG_5803_rerun
.venv/bin/desk-buddy reconstruct scenes/IMG_5803_rerun --device mps --keyframes 8 --resolution 224
.venv/bin/desk-buddy track scenes/IMG_5803_rerun --annotations pipeline/IMG_5803.annotations.json
.venv/bin/desk-buddy calibrate scenes/IMG_5803_rerun --prediction scenes/IMG_5803_rerun/reconstruction/keyframes_8_224/prediction.npz
.venv/bin/desk-buddy depth scenes/IMG_5803_rerun --device mps --batch-size 8 --resolution 224
.venv/bin/desk-buddy surfaces scenes/IMG_5803_rerun
.venv/bin/desk-buddy debug scenes/IMG_5803_rerun
.venv/bin/desk-buddy report scenes/IMG_5803_rerun
.venv/bin/python -m pytest -q
```

다른 영상에는 현재 수동 주석을 재사용하면 안 됩니다. 현재 노트북 모서리·책상 패치는 이 영상과 분석 해상도에만 맞습니다. `surfaces` 단계의 책상 ROI 역시 이 촬영본 전용입니다. 이것은 임의의 책상 영상을 자동으로 이해하는 완성 파이프라인이 아닙니다.

CUDA 호스트에서는 동일한 추론 명령의 `--device cuda`를 사용할 수 있습니다. 이 경로는 현재 Mac에서 실제 실행하지 않았으며 클라우드 연결이나 과금 작업은 수행하지 않았습니다.

Gemini를 연결할 때는 키를 `.env`에 넣고 **먼저 사용 가능한 모델을 조회**합니다. 모델 닉네임을 API ID로 가정하지 않습니다.

```sh
.venv/bin/desk-buddy models --output artifacts/gemini_models.json
```

## 좌표와 깊이 계약

- 세계 좌표: 미터, 원점은 노트북 앞쪽 왼쪽. X 오른쪽, Y 힌지 방향, Z 노트북 표면 위쪽.
- 카메라 좌표: OpenCV, X 오른쪽·Y 아래·Z 앞쪽. JSON 행렬은 행 우선 4×4입니다.
- 깊이: 광학축 Z 깊이이며 광선 길이가 아닙니다. 16비트 PNG × 0.001m. 0은 무효.
- 깊이의 영상 도메인: **렌즈 왜곡을 제거한 RGB**. 원본 영상에 그대로 샘플링하면 맞지 않습니다. 렌더러는 RGB를 같은 내부 파라미터로 rectification하거나 렌더 레이어를 다시 왜곡해야 합니다.
- 프레임 시각: `frames.json`의 원본 PTS. 진단 MP4도 같은 시간 간격을 사용합니다.
- `lighting.json`의 `null`, `objects.json`의 비어 있는 기하·행동 배열은 미측정을 뜻합니다. 기본값이나 완성된 캐시로 해석하면 안 됩니다.

## 참고한 공식 자료

- [Depth Anything 3](https://github.com/ByteDance-Seed/Depth-Anything-3), [Python API](https://github.com/ByteDance-Seed/Depth-Anything-3/blob/main/docs/API.md)
- [SAM 3 설치 요구사항](https://github.com/facebookresearch/sam3#installation)
- [MacBook Pro 14인치 치수](https://support.apple.com/en-ie/121552)
- [Gemini 모델 목록 API](https://ai.google.dev/api/models)
- [ITU-R BT.2100 HLG 규격](https://www.itu.int/rec/R-REC-BT.2100)
