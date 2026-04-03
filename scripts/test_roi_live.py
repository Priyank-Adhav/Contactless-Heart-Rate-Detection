"""
Manual test script for the ROI extraction module.

Opens the webcam, detects facial landmarks, draws the three ROI
polygons on the live feed, and prints per-ROI green channel means
to the terminal. Press 'q' to quit, 'r' to run a full 10-second
capture and display the extracted signal summary.

Usage:
    python scripts/test_roi_live.py
    python scripts/test_roi_live.py --duration 15
    python scripts/test_roi_live.py --camera 1
"""

import argparse
import sys
import time

import cv2
import mediapipe as mp
import numpy as np

# Allow imports from project root
sys.path.insert(0, ".")

from src.roi_extractor import (
    ROI_DEFINITIONS,
    _landmarks_to_polygon,
    _extract_roi_channels,
    _create_landmarker,
    extract_rois_webcam,
)

# Colors for each ROI (BGR format for OpenCV)
ROI_COLORS = [
    (0, 220, 120),   # forehead - green
    (220, 160, 0),   # left cheek - blue-ish
    (0, 160, 220),   # right cheek - orange-ish
]

ROI_LABELS = ["Forehead", "L.Cheek", "R.Cheek"]


def run_live_preview(camera_index=0):
    """Open webcam and show ROI overlays with live green channel values."""
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"ERROR: Cannot open camera at index {camera_index}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    print(f"Camera opened: {frame_w}x{frame_h} @ {fps:.1f} fps")
    print("Controls:")
    print("  q - quit")
    print("  r - record 10s and show signal summary")
    print()

    landmarker = _create_landmarker(running_mode="VIDEO")
    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        timestamp_ms = (frame_count / fps) * 1000.0
        frame_count += 1

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        results = landmarker.detect_for_video(mp_image, int(timestamp_ms))

        display = frame.copy()

        if results.face_landmarks and len(results.face_landmarks) > 0:
            landmarks = results.face_landmarks[0]

            values_text = []
            for i, (name, indices) in enumerate(ROI_DEFINITIONS):
                polygon = _landmarks_to_polygon(
                    landmarks, indices, frame_w, frame_h
                )
                g_mean, rgb_mean = _extract_roi_channels(
                    frame, polygon, frame_h, frame_w
                )

                # Draw filled polygon with transparency
                overlay = display.copy()
                cv2.fillPoly(overlay, [polygon], ROI_COLORS[i])
                cv2.addWeighted(overlay, 0.2, display, 0.8, 0, display)

                # Draw polygon outline
                cv2.polylines(display, [polygon], True, ROI_COLORS[i], 2)

                # Label
                cx, cy = polygon.mean(axis=0).astype(int)
                if g_mean is not None:
                    label = f"{ROI_LABELS[i]}: G={g_mean:.1f}"
                    values_text.append(f"{ROI_LABELS[i]}: G={g_mean:.1f}")
                else:
                    label = f"{ROI_LABELS[i]}: --"
                    values_text.append(f"{ROI_LABELS[i]}: --")

                cv2.putText(
                    display, label, (cx - 40, cy),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1,
                    cv2.LINE_AA,
                )

            # Print to terminal on single line
            status = " | ".join(values_text)
            print(f"\r{status}    ", end="", flush=True)

            # Status bar on frame
            cv2.putText(
                display, "Face detected - ROIs active",
                (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (0, 220, 120), 1, cv2.LINE_AA,
            )
        else:
            cv2.putText(
                display, "No face detected",
                (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (0, 0, 255), 1, cv2.LINE_AA,
            )
            print("\rNo face detected              ", end="", flush=True)

        cv2.putText(
            display, "Press 'q' to quit | 'r' to record 10s",
            (10, frame_h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
            (180, 180, 180), 1, cv2.LINE_AA,
        )

        cv2.imshow("PulseGuard - ROI Preview", display)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        elif key == ord("r"):
            print("\n\nStarting 30-second recording...")
            cap.release()
            landmarker.close()
            cv2.destroyAllWindows()
            run_recording(camera_index, duration=10)
            return

    print()
    cap.release()
    landmarker.close()
    cv2.destroyAllWindows()


def run_recording(camera_index=0, duration=30):
    """Run a timed recording and display signal statistics."""
    print(f"Recording {duration} seconds from camera {camera_index}...")
    print()

    result = extract_rois_webcam(
        duration_seconds=duration,
        camera_index=camera_index,
        show_preview=True,
    )

    print()
    print("=" * 60)
    print("RECORDING RESULTS")
    print("=" * 60)
    print(f"  Face detected:   {result.face_detected}")
    print(f"  FPS:             {result.fps:.1f}")
    print(f"  Total frames:    {result.frame_count}")
    
    if hasattr(result, "warnings") and result.warnings:
        print()
        print("  WARNINGS OBSERVED:")
        for w in result.warnings:
            print(f"  ! {w}")
    print()

    if not result.face_detected:
        print("  No face detected in enough frames.")
        print("  Try again with better lighting and face position.")
        return

    for i, (name, _) in enumerate(ROI_DEFINITIONS):
        signal = result.green_signals[i]
        if len(signal) == 0:
            print(f"  {ROI_LABELS[i]:12s}:  no data")
            continue

        arr = np.array(signal)
        print(f"  {ROI_LABELS[i]:12s}:  "
              f"samples={len(arr):4d}  "
              f"mean={arr.mean():.1f}  "
              f"std={arr.std():.2f}  "
              f"min={arr.min():.1f}  "
              f"max={arr.max():.1f}")

    print()

    # Quick signal quality check via FFT
    for i, (name, _) in enumerate(ROI_DEFINITIONS):
        signal = result.green_signals[i]
        if len(signal) < 30:
            continue
        arr = np.array(signal)
        detrended = arr - np.mean(arr)
        freqs = np.fft.rfftfreq(len(detrended), d=1.0 / result.fps)
        spectrum = np.abs(np.fft.rfft(detrended))

        mask = (freqs >= 0.7) & (freqs <= 3.5)
        if np.any(mask):
            cardiac_spectrum = spectrum[mask]
            cardiac_freqs = freqs[mask]
            peak_idx = np.argmax(cardiac_spectrum)
            peak_freq = cardiac_freqs[peak_idx]
            peak_bpm = peak_freq * 60.0
            peak_power = cardiac_spectrum[peak_idx]
            total_power = np.sum(spectrum[1:])
            snr = peak_power / (total_power + 1e-10)

            print(f"  {ROI_LABELS[i]:12s} FFT:  "
                  f"peak={peak_bpm:.0f} BPM  "
                  f"SNR={snr:.3f}  "
                  f"{'(looks promising)' if snr > 0.05 else '(weak signal)'}")

    print()
    print("RGB signal shape per ROI:", end="")
    for i in range(3):
        if result.rgb_signals and len(result.rgb_signals[i]) > 0:
            print(f"  {ROI_LABELS[i]}=[{len(result.rgb_signals[i])} x 3]", end="")
    print()
    print()
    print("Module 1 (ROI Extraction) is working correctly.")
    print("These signals are ready to feed into Module 2 (Signal Processing).")


def main():
    parser = argparse.ArgumentParser(
        description="Manual test for PulseGuard ROI extraction"
    )
    parser.add_argument(
        "--camera", type=int, default=0,
        help="Camera index (default: 0)"
    )
    parser.add_argument(
        "--duration", type=int, default=30,
        help="Recording duration in seconds for direct record mode (default: 30)"
    )
    parser.add_argument(
        "-r", "--record", action="store_true",
        help="Skip preview, go straight to recording"
    )
    args = parser.parse_args()

    if args.record:
        run_recording(args.camera, args.duration)
    else:
        run_live_preview(args.camera)


if __name__ == "__main__":
    main()
