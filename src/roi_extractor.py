"""
ROI Extraction Module

Detects facial landmarks using MediaPipe FaceLandmarker (tasks API)
and extracts spatially averaged color channel intensity from three
regions of interest: forehead, left cheek, and right cheek.

The three ROIs were chosen for high blood perfusion and low
occlusion probability. Each ROI is defined as a polygon of
MediaPipe landmark indices, and the mean green channel (plus
full RGB) is extracted per frame for downstream rPPG processing.
"""

import os
import time
from pathlib import Path
from typing import Optional

import cv2
import mediapipe as mp
import numpy as np

from src.models import ROIResult

# ---------------------------------------------------------------------------
# Model path resolution
# ---------------------------------------------------------------------------

_MODULE_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _MODULE_DIR.parent
_DEFAULT_MODEL_PATH = _PROJECT_ROOT / "models" / "face_landmarker.task"


def _resolve_model_path(model_path=None):
    """Find the face_landmarker.task model file.

    Checks in order: explicit path, project models/ dir, environment variable.
    """
    if model_path and os.path.isfile(model_path):
        return str(model_path)
    if _DEFAULT_MODEL_PATH.is_file():
        return str(_DEFAULT_MODEL_PATH)
    env_path = os.environ.get("PULSEGUARD_MODEL_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path
    raise FileNotFoundError(
        f"Face landmarker model not found. Expected at: {_DEFAULT_MODEL_PATH}\n"
        "Download it with:\n"
        "  wget -O models/face_landmarker.task "
        "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
        "face_landmarker/float16/latest/face_landmarker.task"
    )


# ---------------------------------------------------------------------------
# ROI definitions: landmark index sets that form convex polygons
# on the face. Selected from the MediaPipe 468-point canonical mesh.
#
# Forehead: upper central region between eyebrows and hairline.
# Left cheek: area below the left eye, lateral to the nose.
# Right cheek: mirror of left cheek on the right side.
#
# Note: "left" and "right" follow the MediaPipe convention, which
# uses the subject's perspective (i.e., left cheek = viewer's right).
# ---------------------------------------------------------------------------

FOREHEAD_INDICES = [21, 54, 103, 67, 109, 10, 338, 297, 332, 284, 251, 301, 293, 334, 296, 336, 9, 107, 66, 105, 63]

LEFT_CHEEK_INDICES = [43, 204, 211, 170, 150, 136, 172, 58, 215, 177, 93, 137, 234, 227, 116, 111, 118, 119, 36, 203, 206, 92, 186, 57]

RIGHT_CHEEK_INDICES = [422, 430, 394, 365, 397, 367, 435, 361, 401, 323, 366, 454, 447, 345, 372, 265, 261, 448, 449, 450, 329, 371, 266, 423, 426, 436, 287, 432]

ROI_DEFINITIONS = [
    ("forehead", FOREHEAD_INDICES),
    ("left_cheek", LEFT_CHEEK_INDICES),
    ("right_cheek", RIGHT_CHEEK_INDICES),
]


def _create_landmarker(model_path=None, running_mode="IMAGE"):
    """Create a MediaPipe FaceLandmarker instance using the tasks API.

    Args:
        model_path: Optional path to the .task model file.
        running_mode: One of "IMAGE" or "VIDEO".

    Returns:
        A FaceLandmarker instance.
    """
    resolved_path = _resolve_model_path(model_path)

    BaseOptions = mp.tasks.BaseOptions
    FaceLandmarker = mp.tasks.vision.FaceLandmarker
    FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
    RunningMode = mp.tasks.vision.RunningMode

    mode = RunningMode.VIDEO if running_mode == "VIDEO" else RunningMode.IMAGE

    options = FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=resolved_path),
        running_mode=mode,
        num_faces=3,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5,
        output_face_blendshapes=False,
        output_facial_transformation_matrixes=False,
    )
    return FaceLandmarker.create_from_options(options)


def _landmarks_to_polygon(landmarks, indices, frame_w, frame_h):
    """Convert a set of landmark indices to pixel-space polygon points.

    Coordinates are clamped to frame dimensions to prevent out-of-bounds
    masks when the face is near the edge of the frame.

    Args:
        landmarks: List of MediaPipe NormalizedLandmark objects.
        indices: List of integer landmark indices.
        frame_w: Frame width in pixels.
        frame_h: Frame height in pixels.

    Returns:
        numpy array of shape (len(indices), 2) with integer pixel coords.
    """
    points = []
    for idx in indices:
        lm = landmarks[idx]
        x = int(np.clip(lm.x * frame_w, 0, frame_w - 1))
        y = int(np.clip(lm.y * frame_h, 0, frame_h - 1))
        points.append([x, y])
    return np.array(points, dtype=np.int32)


def _extract_roi_channels(frame, polygon, frame_h, frame_w):
    """Extract mean R, G, B values from the region defined by a polygon.

    Args:
        frame: BGR image (numpy array, shape HxWx3).
        polygon: Integer array of polygon vertices, shape (N, 2).
        frame_h: Frame height.
        frame_w: Frame width.

    Returns:
        Tuple of (green_mean, rgb_means) where rgb_means is [R, G, B],
        or (None, None) if the ROI contains no valid pixels.
    """
    mask = np.zeros((frame_h, frame_w), dtype=np.uint8)
    cv2.fillPoly(mask, [polygon], 255)

    b_channel = frame[:, :, 0]
    g_channel = frame[:, :, 1]
    r_channel = frame[:, :, 2]

    roi_mask = mask == 255
    pixel_count = np.sum(roi_mask)

    if pixel_count == 0:
        return None, None

    g_mean = float(np.mean(g_channel[roi_mask]))
    r_mean = float(np.mean(r_channel[roi_mask]))
    b_mean = float(np.mean(b_channel[roi_mask]))

    return g_mean, [r_mean, g_mean, b_mean]


def _interpolate_gaps(signal, max_gap=5):
    """Fill None gaps in a signal using linear interpolation.

    Gaps longer than max_gap consecutive frames are left as-is (filled
    with the nearest valid value to avoid large interpolation errors).

    Args:
        signal: List of floats with possible None entries.
        max_gap: Maximum gap length to interpolate across.

    Returns:
        List of floats with gaps filled.
    """
    result = list(signal)
    n = len(result)

    i = 0
    while i < n:
        if result[i] is None:
            gap_start = i
            while i < n and result[i] is None:
                i += 1
            gap_end = i
            gap_length = gap_end - gap_start

            left_val = result[gap_start - 1] if gap_start > 0 else None
            right_val = result[gap_end] if gap_end < n else None

            if gap_length <= max_gap and left_val is not None and right_val is not None:
                for j in range(gap_start, gap_end):
                    t = (j - gap_start + 1) / (gap_length + 1)
                    result[j] = left_val + t * (right_val - left_val)
            elif left_val is not None:
                for j in range(gap_start, gap_end):
                    result[j] = left_val
            elif right_val is not None:
                for j in range(gap_start, gap_end):
                    result[j] = right_val
            else:
                for j in range(gap_start, gap_end):
                    result[j] = 0.0
        else:
            i += 1

    return result


def _interpolate_rgb_gaps(rgb_signal, max_gap=5):
    """Interpolate gaps in an RGB signal (list of [R,G,B] or None)."""
    n = len(rgb_signal)
    r_vals = [v[0] if v is not None else None for v in rgb_signal]
    g_vals = [v[1] if v is not None else None for v in rgb_signal]
    b_vals = [v[2] if v is not None else None for v in rgb_signal]

    r_filled = _interpolate_gaps(r_vals, max_gap)
    g_filled = _interpolate_gaps(g_vals, max_gap)
    b_filled = _interpolate_gaps(b_vals, max_gap)

    return [[r_filled[i], g_filled[i], b_filled[i]] for i in range(n)]


def _process_frame(landmarker, frame, frame_w, frame_h, timestamp_ms=None):
    """Run face detection on a single frame and extract ROI values.

    Args:
        landmarker: MediaPipe FaceLandmarker instance.
        frame: BGR image (numpy array).
        frame_w: Frame width.
        frame_h: Frame height.
        timestamp_ms: Timestamp in milliseconds (required for VIDEO mode).

    Returns:
        Tuple of (green_values, rgb_values, landmark_coords) or
        (None, None, None) if no face is detected.
        green_values: list of 3 floats (one per ROI).
        rgb_values: list of 3 [R,G,B] lists (one per ROI).
        landmark_coords: list of (x,y,z) tuples for all 478 landmarks.
    """
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

    if timestamp_ms is not None:
        results = landmarker.detect_for_video(mp_image, int(timestamp_ms))
    else:
        results = landmarker.detect(mp_image)

    if not results.face_landmarks or len(results.face_landmarks) == 0:
        return None, None, None

    landmarks = results.face_landmarks[0]

    lm_coords = [(lm.x, lm.y, lm.z) for lm in landmarks]

    green_values = []
    rgb_values = []

    for _, indices in ROI_DEFINITIONS:
        polygon = _landmarks_to_polygon(landmarks, indices, frame_w, frame_h)
        g_mean, rgb_mean = _extract_roi_channels(frame, polygon, frame_h, frame_w)
        green_values.append(g_mean)
        rgb_values.append(rgb_mean)

    return green_values, rgb_values, lm_coords


def extract_rois(video_path, model_path=None):
    """Extract multi-ROI green channel signals from a video file.

    Processes every frame of the video, detects facial landmarks via
    MediaPipe FaceLandmarker, and computes the spatial mean of the green
    channel within three facial ROIs (forehead, left cheek, right cheek).

    Args:
        video_path: Path to the video file (str or Path).
        model_path: Optional path to the face_landmarker.task file.

    Returns:
        ROIResult with green_signals, rgb_signals, and metadata.
        If no face is detected in any frame, face_detected will be False
        and signals will be empty.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video file: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0

    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cx, cy = frame_w // 2, frame_h // 2
    radius = int(min(frame_w, frame_h) * 0.35)

    landmarker = _create_landmarker(model_path, running_mode="VIDEO")

    green_buffers = [[] for _ in ROI_DEFINITIONS]
    rgb_buffers = [[] for _ in ROI_DEFINITIONS]
    landmarks_list = []
    frame_count = 0
    face_frame_count = 0
    patient_moved = False

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        timestamp_ms = (frame_count / fps) * 1000.0
        frame_count += 1

        green_vals, rgb_vals, lm_coords = _process_frame(
            landmarker, frame, frame_w, frame_h, timestamp_ms=timestamp_ms
        )

        if green_vals is not None:
            face_frame_count += 1
            landmarks_list.append(lm_coords)
            is_aligned, _ = _check_face_alignment(lm_coords, frame_w, frame_h, cx, cy, radius)
            if not is_aligned:
                patient_moved = True
            for i in range(len(ROI_DEFINITIONS)):
                green_buffers[i].append(green_vals[i])
                rgb_buffers[i].append(rgb_vals[i])
        else:
            landmarks_list.append(None)
            for i in range(len(ROI_DEFINITIONS)):
                green_buffers[i].append(None)
                rgb_buffers[i].append(None)

    cap.release()
    landmarker.close()

    warnings = []
    if patient_moved:
        warnings.append("During analysis patient movements out of circle observed, we recommend testing again to get accurate outcome")

    if frame_count == 0 or face_frame_count == 0:
        return ROIResult(
            green_signals=[[], [], []],
            face_detected=False,
            fps=fps,
            frame_count=frame_count,
            rgb_signals=[[], [], []],
            landmarks_per_frame=[],
            warnings=warnings,
        )

    detection_ratio = face_frame_count / frame_count

    if detection_ratio < 0.3:
        return ROIResult(
            green_signals=[[], [], []],
            face_detected=False,
            fps=fps,
            frame_count=frame_count,
            rgb_signals=[[], [], []],
            landmarks_per_frame=landmarks_list,
            warnings=warnings,
        )

    green_signals = [
        _interpolate_gaps(buf, max_gap=5) for buf in green_buffers
    ]
    rgb_signals = [
        _interpolate_rgb_gaps(buf, max_gap=5) for buf in rgb_buffers
    ]

    return ROIResult(
        green_signals=green_signals,
        face_detected=True,
        fps=fps,
        frame_count=frame_count,
        rgb_signals=rgb_signals,
        landmarks_per_frame=landmarks_list,
        warnings=warnings,
    )


def _check_face_alignment(lm_coords, frame_w, frame_h, cx, cy, radius):
    """Check if the face bounding box fits securely within the guide circle."""
    xs = [lm[0] * frame_w for lm in lm_coords]
    ys = [lm[1] * frame_h for lm in lm_coords]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    # Face bounding box center
    face_cx, face_cy = (min_x + max_x) / 2, (min_y + max_y) / 2

    # Check if face center is relatively close to circle center
    dist_sq = (face_cx - cx) ** 2 + (face_cy - cy) ** 2
    if dist_sq > (radius * 0.5) ** 2:
        return False, "Please center your face"

    # Check if face bounding box fits inside the circle roughly
    if min_x < cx - radius or max_x > cx + radius or min_y < cy - radius or max_y > cy + radius:
        return False, "Move back, face too large"

    face_width = max_x - min_x
    if face_width < radius * 0.6:
        return False, "Move closer"

    return True, "Perfect! Hold still..."


def extract_rois_webcam(
    duration_seconds: int = 30,
    camera_index: int = 0,
    show_preview: bool = True,
    model_path: Optional[str] = None,
) -> ROIResult:
    """Capture video from a webcam and extract multi-ROI signals.

    Opens the specified camera, initially runs an ALIGNMENT logic flow
    which ensures the patient face fits perfectly within a visual guide,
    and then captures frames for the given duration while verifying they do not step out.

    Args:
        duration_seconds: How many seconds to record. Default 30.
        camera_index: OpenCV camera index. Default 0.
        show_preview: Whether to show a live preview window.
        model_path: Optional path to the face_landmarker.task file.

    Returns:
        ROIResult with extracted signals and metadata.
    """
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise ValueError(f"Cannot open camera at index {camera_index}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0

    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    cx, cy = frame_w // 2, frame_h // 2
    radius = int(min(frame_w, frame_h) * 0.35)

    landmarker = _create_landmarker(model_path, running_mode="VIDEO")

    green_buffers = [[] for _ in ROI_DEFINITIONS]
    rgb_buffers = [[] for _ in ROI_DEFINITIONS]
    landmarks_list = []

    frame_count = 0
    face_frame_count = 0
    recorded_frames = 0

    roi_colors = [(0, 220, 120), (220, 160, 0), (0, 160, 220)]

    phase = "ALIGNING"
    patient_moved = False
    start_time = None

    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        # In order to let mediapipe deal with timeline, we use arbitrary timestamp matching the read
        timestamp_ms = (frame_count / fps) * 1000.0
        frame_count += 1

        green_vals, rgb_vals, lm_coords = _process_frame(
            landmarker, frame, frame_w, frame_h, timestamp_ms=timestamp_ms
        )

        preview = frame.copy() if show_preview else None
        is_aligned = False
        align_msg = "No face detected"

        if lm_coords is not None:
            is_aligned, align_msg = _check_face_alignment(lm_coords, frame_w, frame_h, cx, cy, radius)

        if phase == "ALIGNING":
            if show_preview:
                color = (0, 255, 0) if is_aligned else (0, 0, 255) # Green if aligned, Red out of bounds
                # Draw dark mask cleanly
                mask = np.zeros_like(preview)
                cv2.circle(mask, (cx, cy), radius, (255, 255, 255), -1)
                # Invert mask heavily to blacken sides
                preview_dim = cv2.bitwise_and(preview, mask)
                preview = cv2.addWeighted(preview, 0.3, preview_dim, 0.7, 0)

                cv2.circle(preview, (cx, cy), radius, color, 3)
                cv2.putText(preview, align_msg, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
                cv2.putText(preview, "ALIGNMENT PHASE", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

            if is_aligned:
                phase = "RECORDING"
                start_time = time.time()
                face_frame_count = 0
                recorded_frames = 0
                green_buffers = [[] for _ in ROI_DEFINITIONS]
                rgb_buffers = [[] for _ in ROI_DEFINITIONS]
                landmarks_list = []

        elif phase == "RECORDING":
            elapsed = time.time() - start_time
            if elapsed >= duration_seconds:
                break

            recorded_frames += 1
            if lm_coords is None or not is_aligned:
                patient_moved = True

            if green_vals is not None:
                face_frame_count += 1
                landmarks_list.append(lm_coords)
                for i in range(len(ROI_DEFINITIONS)):
                    green_buffers[i].append(green_vals[i])
                    rgb_buffers[i].append(rgb_vals[i])
            else:
                landmarks_list.append(None)
                for i in range(len(ROI_DEFINITIONS)):
                    green_buffers[i].append(None)
                    rgb_buffers[i].append(None)

            if show_preview:
                color = (0, 255, 0) if is_aligned else (0, 165, 255) # Orange warning if stepping out
                cv2.circle(preview, (cx, cy), radius, color, 2)

                if green_vals is not None:
                    for j, (_, idx_list) in enumerate(ROI_DEFINITIONS):
                        points = []
                        for idx in idx_list:
                            x = int(np.clip(lm_coords[idx][0] * frame_w, 0, frame_w - 1))
                            y = int(np.clip(lm_coords[idx][1] * frame_h, 0, frame_h - 1))
                            points.append([x, y])
                        poly = np.array(points, dtype=np.int32)
                        overlay = preview.copy()
                        cv2.fillPoly(overlay, [poly], roi_colors[j])
                        cv2.addWeighted(overlay, 0.2, preview, 0.8, 0, preview)
                        cv2.polylines(preview, [poly], True, roi_colors[j], 2)

                remaining = max(0, duration_seconds - elapsed)
                if not is_aligned:
                    cv2.putText(preview, "WARNING: For accurate results please stay in frame!",
                                (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

                cv2.putText(preview, "Analysis in process, please do not move for 30 sec",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                cv2.putText(preview, f"Time: {remaining:.1f}s",
                            (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        if show_preview:
            cv2.imshow("PulseGuard - Webcam Capture", preview)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cap.release()
    landmarker.close()
    if show_preview:
        cv2.destroyAllWindows()

    warnings = []
    if patient_moved:
        warnings.append("During analysis patient movements out of circle observed, we recommend testing again to get accurate outcome")

    if recorded_frames == 0 or face_frame_count == 0:
        return ROIResult(
            green_signals=[[], [], []],
            face_detected=False,
            fps=fps,
            frame_count=recorded_frames,
            rgb_signals=[[], [], []],
            landmarks_per_frame=[],
            warnings=warnings
        )

    detection_ratio = face_frame_count / recorded_frames
    if detection_ratio < 0.3:
        return ROIResult(
            green_signals=[[], [], []],
            face_detected=False,
            fps=fps,
            frame_count=recorded_frames,
            rgb_signals=[[], [], []],
            landmarks_per_frame=landmarks_list,
            warnings=warnings
        )

    green_signals = [_interpolate_gaps(buf, max_gap=5) for buf in green_buffers]
    rgb_signals = [_interpolate_rgb_gaps(buf, max_gap=5) for buf in rgb_buffers]

    return ROIResult(
        green_signals=green_signals,
        face_detected=True,
        fps=fps,
        frame_count=recorded_frames,
        rgb_signals=rgb_signals,
        landmarks_per_frame=landmarks_list,
        warnings=warnings
    )
