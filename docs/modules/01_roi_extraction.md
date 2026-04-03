# Module 1: ROI Extraction

Owner: P1 (Pipeline Lead)

## Purpose

Detect facial landmarks in each video frame and extract the spatially averaged
green channel intensity from three regions of interest: forehead, left cheek,
and right cheek. This module is the first stage of the pipeline and its output
feeds directly into the signal processing stage.

## Inputs and Outputs

**Input:** Path to a video file (MP4, WebM, AVI) or a live webcam stream.

**Output:** An `ROIResult` dataclass containing:
- `green_signals`: list of 3 lists, each containing per-frame green channel means
- `face_detected`: boolean indicating whether a face was found
- `fps`: frames per second of the source video
- `frame_count`: total number of frames processed
- `landmarks_per_frame`: (optional) raw landmark coordinates for visualization

## Dependencies

- `opencv-python` for video reading and image operations
- `mediapipe` for Face Mesh landmark detection
- `numpy` for array operations

## Implementation Guide

### Step 1: Video Frame Extraction

Use OpenCV to read frames from the video file or webcam:

```python
import cv2

cap = cv2.VideoCapture(video_path)  # or cv2.VideoCapture(0) for webcam
fps = cap.get(cv2.CAP_PROP_FPS)

frames = []
while True:
    ret, frame = cap.read()
    if not ret:
        break
    frames.append(frame)
cap.release()
```

For webcam mode, capture for a fixed duration (default 30 seconds) and store frames
in a buffer. Use `time.time()` to track elapsed time.

### Step 2: Face Mesh Detection

Initialize MediaPipe Face Mesh and process each frame:

```python
import mediapipe as mp

mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    static_image_mode=False,
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
)

for frame in frames:
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = face_mesh.process(rgb_frame)
    if results.multi_face_landmarks:
        landmarks = results.multi_face_landmarks[0]
        # Extract landmark coordinates...
```

### Step 3: Define ROI Landmark Indices

The following landmark index groups define the three ROIs. These were selected
based on anatomical regions with high blood perfusion and minimal occlusion.

```
FOREHEAD_INDICES = [10, 338, 297, 332, 284, 251, 389, 356, 454,
                    323, 361, 288, 397, 365, 379, 378, 400, 377,
                    152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234]
# Note: Use a subset that forms a clean polygon. The exact set should
# be refined during testing. Start with the upper forehead region:
FOREHEAD = [10, 338, 297, 332, 284, 251, 389, 356, 127]

LEFT_CHEEK = [234, 93, 132, 58, 172, 136, 150, 149, 176, 148]
RIGHT_CHEEK = [454, 323, 361, 288, 397, 365, 379, 378, 400, 377]
```

### Step 4: Extract Green Channel per ROI

For each frame and each ROI:

1. Convert landmark indices to pixel coordinates.
2. Create a polygon mask using `cv2.fillPoly`.
3. Apply the mask to the green channel of the frame.
4. Compute the spatial mean of the masked green channel pixels.

```python
import numpy as np

def extract_roi_mean(frame, landmarks, roi_indices, frame_w, frame_h):
    """Extract the mean green channel value within an ROI polygon."""
    points = []
    for idx in roi_indices:
        lm = landmarks.landmark[idx]
        x = int(lm.x * frame_w)
        y = int(lm.y * frame_h)
        points.append([x, y])
    points = np.array(points, dtype=np.int32)

    mask = np.zeros((frame_h, frame_w), dtype=np.uint8)
    cv2.fillPoly(mask, [points], 255)

    green_channel = frame[:, :, 1]  # BGR format, index 1 is green
    roi_pixels = green_channel[mask == 255]

    if len(roi_pixels) == 0:
        return None
    return float(np.mean(roi_pixels))
```

### Step 5: Handle Missing Faces

Some frames may not contain a detectable face. Options:
- **Interpolation**: fill gaps using linear interpolation from neighboring frames.
- **Skip and track**: record which frames had no face, report the percentage,
  and let downstream modules handle shorter signals.

The recommended approach for the hackathon is interpolation for gaps of up to
5 consecutive frames, and truncation for longer gaps.

### Step 6: Webcam Mode

For webcam capture, the function signature should be:

```python
def extract_rois_webcam(duration_seconds: int = 30, camera_index: int = 0) -> ROIResult:
```

Use the same frame processing logic but read from camera index 0 (or user-specified).
Display a preview window so the user can position their face. Close the window
after the specified duration.

## Testing

Run the ROI extractor tests:
```bash
pytest tests/unit/test_roi_extractor.py -v
```

Key things to verify:
- Three signals are returned with consistent lengths
- Green channel values are in [0, 255]
- Face detection works on a known test video
- Graceful handling when no face is present

## Common Pitfalls

1. **BGR vs RGB**: OpenCV reads frames in BGR order. MediaPipe expects RGB.
   Always convert before passing to Face Mesh.
2. **Landmark coordinate space**: MediaPipe returns normalized coordinates
   (0.0 to 1.0). Multiply by frame width/height to get pixel coordinates.
3. **Empty ROI mask**: If the face is partially out of frame, some ROI polygons
   may fall outside the image bounds. Clip coordinates to frame dimensions.
4. **FPS accuracy**: Some video files report inaccurate FPS via OpenCV. If
   possible, cross-check by dividing frame count by duration.
