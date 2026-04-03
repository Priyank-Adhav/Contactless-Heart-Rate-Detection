"""
Interactive Landmark Picker for MediaPipe Face Mesh

Click on landmarks to select them for your ROI polygon.
The selected indices are printed in order as you click.

Usage:
    python pick_landmarks.py --video path/to/video.mp4
    python pick_landmarks.py --camera 0          # use webcam

Controls:
    Left click   - select nearest landmark (highlighted in green)
    Right click  - deselect nearest landmark
    U            - undo last selection
    R            - reset all selections
    S            - save / print current indices to console
    Q / Esc      - quit
"""

import argparse
import sys
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np

# ---------------------------------------------------------------------------
# Resolve model path (same logic as roi_extraction.py)
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent
_DEFAULT_MODEL_PATH = _PROJECT_ROOT / "models" / "face_landmarker.task"


def _resolve_model_path(model_path=None):
    import os
    if model_path and Path(model_path).is_file():
        return str(model_path)
    if _DEFAULT_MODEL_PATH.is_file():
        return str(_DEFAULT_MODEL_PATH)
    env_path = os.environ.get("PULSEGUARD_MODEL_PATH")
    if env_path and Path(env_path).is_file():
        return env_path
    raise FileNotFoundError(
        f"Model not found at {_DEFAULT_MODEL_PATH}.\n"
        "Download with:\n"
        "  wget -O models/face_landmarker.task "
        "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
        "face_landmarker/float16/latest/face_landmarker.task"
    )


# ---------------------------------------------------------------------------
# Detect landmarks on a single frame
# ---------------------------------------------------------------------------

def detect_landmarks(frame, model_path=None):
    resolved = _resolve_model_path(model_path)
    BaseOptions = mp.tasks.BaseOptions
    FaceLandmarker = mp.tasks.vision.FaceLandmarker
    FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
    RunningMode = mp.tasks.vision.RunningMode

    options = FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=resolved),
        running_mode=RunningMode.IMAGE,
        num_faces=1,
        min_face_detection_confidence=0.5,
    )
    with FaceLandmarker.create_from_options(options) as lm:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = lm.detect(mp_image)

    if not result.face_landmarks:
        return None
    return result.face_landmarks[0]


# ---------------------------------------------------------------------------
# Convert landmarks to pixel coords
# ---------------------------------------------------------------------------

def landmarks_to_pixels(landmarks, w, h):
    pts = []
    for lm in landmarks:
        x = int(np.clip(lm.x * w, 0, w - 1))
        y = int(np.clip(lm.y * h, 0, h - 1))
        pts.append((x, y))
    return pts  # list of (x, y), index == landmark index


# ---------------------------------------------------------------------------
# Find nearest landmark to a mouse click
# ---------------------------------------------------------------------------

def nearest_landmark(click_x, click_y, pixel_coords, threshold=20):
    best_idx = None
    best_dist = float("inf")
    for i, (x, y) in enumerate(pixel_coords):
        d = np.hypot(click_x - x, click_y - y)
        if d < best_dist:
            best_dist = d
            best_idx = i
    if best_dist <= threshold:
        return best_idx
    return None


# ---------------------------------------------------------------------------
# Render the frame with all landmarks and current selection
# ---------------------------------------------------------------------------

def render(frame, pixel_coords, selected_indices):
    vis = frame.copy()
    h, w = vis.shape[:2]

    # Draw all landmarks as small grey dots
    for i, (x, y) in enumerate(pixel_coords):
        cv2.circle(vis, (x, y), 2, (180, 180, 180), -1)

    # Draw selected landmarks + their index labels
    for order, idx in enumerate(selected_indices):
        x, y = pixel_coords[idx]
        cv2.circle(vis, (x, y), 6, (0, 220, 80), -1)
        cv2.circle(vis, (x, y), 6, (0, 0, 0), 1)
        label = str(idx)
        cv2.putText(vis, label, (x + 7, y - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 220, 80), 1, cv2.LINE_AA)

    # Draw polygon outline if 3+ points selected
    if len(selected_indices) >= 3:
        pts = np.array([pixel_coords[i] for i in selected_indices], dtype=np.int32)
        overlay = vis.copy()
        cv2.fillPoly(overlay, [pts], (0, 200, 80))
        cv2.addWeighted(overlay, 0.18, vis, 0.82, 0, vis)
        cv2.polylines(vis, [pts], isClosed=True, color=(0, 220, 80), thickness=2)

    # HUD
    lines = [
        "Left click: select   Right click: deselect",
        "U: undo  R: reset  S: print indices  Q: quit",
        f"Selected ({len(selected_indices)}): {list(selected_indices)}",
    ]
    for i, line in enumerate(lines):
        cv2.putText(vis, line, (10, h - 60 + i * 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(vis, line, (10, h - 60 + i * 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(vis, line, (10, h - 60 + i * 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1, cv2.LINE_AA)

    return vis


# ---------------------------------------------------------------------------
# Main picker loop
# ---------------------------------------------------------------------------

def run_picker(frame, model_path=None):
    h, w = frame.shape[:2]
    print("Detecting landmarks...")
    landmarks = detect_landmarks(frame, model_path)
    if landmarks is None:
        print("ERROR: No face detected in frame. Try a different frame.")
        sys.exit(1)

    pixel_coords = landmarks_to_pixels(landmarks, w, h)
    print(f"Detected {len(pixel_coords)} landmarks.")

    selected = []   # ordered list of selected landmark indices
    selected_set = set()

    window = "Landmark Picker"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, min(w, 1280), min(h, 800))

    def on_mouse(event, mx, my, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            idx = nearest_landmark(mx, my, pixel_coords)
            if idx is not None and idx not in selected_set:
                selected.append(idx)
                selected_set.add(idx)
        elif event == cv2.EVENT_RBUTTONDOWN:
            idx = nearest_landmark(mx, my, pixel_coords)
            if idx is not None and idx in selected_set:
                selected.remove(idx)
                selected_set.discard(idx)

    cv2.setMouseCallback(window, on_mouse)

    while True:
        vis = render(frame, pixel_coords, selected)
        cv2.imshow(window, vis)
        key = cv2.waitKey(30) & 0xFF

        if key in (ord("q"), 27):  # Q or Esc
            break
        elif key == ord("u") and selected:
            removed = selected.pop()
            selected_set.discard(removed)
        elif key == ord("r"):
            selected.clear()
            selected_set.clear()
        elif key == ord("s"):
            print("\n--- Selected landmark indices (in click order) ---")
            print(f"FOREHEAD_INDICES = {selected}")
            print("--------------------------------------------------\n")

    cv2.destroyAllWindows()

    if selected:
        print("\n--- Final selected indices ---")
        print(f"FOREHEAD_INDICES = {selected}")
        print("------------------------------\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="MediaPipe landmark picker")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--video", type=str, help="Path to video file")
    group.add_argument("--camera", type=int, help="Camera index (e.g. 0)")
    parser.add_argument("--frame", type=int, default=30,
                        help="Frame number to use from video (default: 30)")
    parser.add_argument("--model", type=str, default=None,
                        help="Path to face_landmarker.task")
    args = parser.parse_args()

    if args.video:
        cap = cv2.VideoCapture(args.video)
        if not cap.isOpened():
            print(f"ERROR: Cannot open video: {args.video}")
            sys.exit(1)
        cap.set(cv2.CAP_PROP_POS_FRAMES, args.frame)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            print(f"ERROR: Could not read frame {args.frame} from video.")
            sys.exit(1)
    else:
        cap = cv2.VideoCapture(args.camera)
        if not cap.isOpened():
            print(f"ERROR: Cannot open camera {args.camera}")
            sys.exit(1)
        print("Press SPACE to capture frame...")
        while True:
            ret, frame = cap.read()
            if not ret:
                continue
            cv2.imshow("Press SPACE to capture", frame)
            if cv2.waitKey(1) & 0xFF == ord(" "):
                break
        cap.release()
        cv2.destroyAllWindows()

    run_picker(frame, model_path=args.model)


if __name__ == "__main__":
    main()
