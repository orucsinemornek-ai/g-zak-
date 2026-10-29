from __future__ import annotations

import os
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)


def _cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME")
    root = Path(base) if base else Path.home() / ".cache"
    return root / "eye-scroll" / "models"


CACHE_DIR = _cache_dir()
MODEL_PATH = CACHE_DIR / "face_landmarker.task"
CASCADE_DIR = CACHE_DIR / "haarcascades"
CASCADE_URL = "https://raw.githubusercontent.com/opencv/opencv/4.x/data/haarcascades/{name}.xml"

LEFT_EYE = (33, 160, 158, 133, 153, 144)
RIGHT_EYE = (362, 385, 387, 263, 373, 380)


@dataclass
class EyeState:
    face: bool = False
    ear: float | None = None
    left_eye: list[tuple[int, int]] = field(default_factory=list)
    right_eye: list[tuple[int, int]] = field(default_factory=list)


def eye_aspect_ratio(points: list[tuple[float, float]]) -> float:
    (x1, y1), (x2, y2), (x3, y3), (x4, y4), (x5, y5), (x6, y6) = points
    vertical = np.hypot(x2 - x6, y2 - y6) + np.hypot(x3 - x5, y3 - y5)
    horizontal = np.hypot(x1 - x4, y1 - y4)
    if horizontal <= 1e-6:
        return 0.0
    return float(vertical / (2.0 * horizontal))


class BaseDetector:
    name = "base"

    def detect(self, frame_bgr: np.ndarray) -> EyeState:
        raise NotImplementedError

    def close(self) -> None:
        pass


class MediaPipeDetector(BaseDetector):
    name = "mediapipe"

    def __init__(self, model_path: Path = MODEL_PATH, num_faces: int = 1):
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        self._mp = mp
        path = ensure_model(model_path)
        options = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_buffer=path.read_bytes()),
            running_mode=vision.RunningMode.IMAGE,
            num_faces=num_faces,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)
        self._vision = vision

    def detect(self, frame_bgr: np.ndarray) -> EyeState:
        rgb = np.ascontiguousarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect(image)
        if not result.face_landmarks:
            return EyeState(face=False)

        landmarks = result.face_landmarks[0]
        height, width = frame_bgr.shape[:2]

        def to_pixels(indices: tuple[int, ...]) -> list[tuple[int, int]]:
            return [
                (int(landmarks[i].x * width), int(landmarks[i].y * height))
                for i in indices
            ]

        left = to_pixels(LEFT_EYE)
        right = to_pixels(RIGHT_EYE)
        ear = (eye_aspect_ratio([(float(x), float(y)) for x, y in left])
               + eye_aspect_ratio([(float(x), float(y)) for x, y in right])) / 2.0
        return EyeState(face=True, ear=ear, left_eye=left, right_eye=right)

    def close(self) -> None:
        self._landmarker.close()


class HaarDetector(BaseDetector):
    """Fallback that needs no model download.

    OpenCV's cascades cannot give eye landmarks, so the EAR is approximated:
    a detected face with zero detected eyes is reported as closed.
    """

    name = "haar"

    def __init__(self):
        self._face = cv2.CascadeClassifier(str(ensure_cascade("haarcascade_frontalface_default")))
        self._eyes = cv2.CascadeClassifier(str(ensure_cascade("haarcascade_eye")))
        if self._face.empty() or self._eyes.empty():
            raise RuntimeError("OpenCV Haar cascade files could not be loaded")

    def detect(self, frame_bgr: np.ndarray) -> EyeState:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        faces = self._face.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=5, minSize=(80, 80))
        if len(faces) == 0:
            return EyeState(face=False)

        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        roi = gray[y : y + int(h * 0.65), x : x + w]
        eyes = self._eyes.detectMultiScale(roi, scaleFactor=1.1, minNeighbors=10, minSize=(15, 15))
        found = [
            (x + int(ex), y + int(ey), int(ew), int(eh))
            for ex, ey, ew, eh in eyes
        ]
        found.sort(key=lambda e: e[0])
        left = [(found[0][0], found[0][1]), (found[0][0] + found[0][2], found[0][1] + found[0][3])] if found else []
        right = [(found[-1][0], found[-1][1]), (found[-1][0] + found[-1][2], found[-1][1] + found[-1][3])] if len(found) > 1 else []
        ear = 1.0 if len(found) >= 2 else 0.05
        return EyeState(face=True, ear=ear, left_eye=left, right_eye=right)


def _download(url: str, dest: Path, min_bytes: int) -> Path:
    if dest.exists() and dest.stat().st_size >= min_bytes:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        urllib.request.urlretrieve(url, tmp)
        if tmp.stat().st_size < min_bytes:
            raise RuntimeError(f"downloaded file is too small: {tmp.stat().st_size} bytes")
        tmp.replace(dest)
    except Exception as exc:  # noqa: BLE001
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"download failed ({url}): {exc}") from exc
    return dest


def ensure_model(path: Path = MODEL_PATH) -> Path:
    return _download(MODEL_URL, path, 1_000_000)


def ensure_cascade(name: str) -> Path:
    return _download(CASCADE_URL.format(name=name), CASCADE_DIR / f"{name}.xml", 10_000)


def create_detector(preference: str = "auto") -> BaseDetector:
    preference = (preference or "auto").lower()
    if preference == "haar":
        return HaarDetector()
    if preference == "mediapipe":
        return MediaPipeDetector()
    try:
        return MediaPipeDetector()
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] mediapipe unavailable ({exc}); falling back to haar", flush=True)
        return HaarDetector()
