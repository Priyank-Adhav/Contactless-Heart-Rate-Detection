# Architecture Overview

## Pipeline

PulseGuard follows a linear pipeline architecture where each stage transforms
data and passes it to the next. All inter-stage communication uses the
dataclasses defined in `src/models.py`.

```
Video File / Webcam
        |
        v
  ROI Extractor (src/roi_extractor.py)
  - MediaPipe Face Mesh for 468 landmarks
  - Extracts green channel from 3 ROIs (forehead, left cheek, right cheek)
  - Output: ROIResult
        |
        v
  Signal Processor (src/signal_processor.py, src/ensemble.py)
  - Runs POS and CHROM algorithms on each ROI
  - Computes per-candidate SQI scores (src/sqi_engine.py)
  - Fuses 6 candidates via SNR-weighted averaging
  - Output: SignalResult
        |
        v
  Quality Gate
  - If SQI is LOW: suppress output, return warnings
  - If SQI is MEDIUM/HIGH: proceed
        |
        v
  HRV Analyzer (src/hrv_analyzer.py)
  - Converts peak indices to IBI array
  - Computes RMSSD, SDNN, pNN50, LF/HF
  - Output: HRVResult
        |
        v
  Stress Classifier (src/stress_classifier.py)
  - Rule-based scoring from HRV features
  - Output: (stress_level, confidence)
        |
        v
  API Server (src/api/main.py)
  - Packages results into JSON response
  - Serves frontend dashboard
        |
        v
  Frontend Dashboard (frontend/)
  - Renders BPM, SQI, waveform, HRV metrics, stress level
```

## Data Flow

Each stage produces a well-defined output type:

| Stage | Output Type | Consumed By |
|-------|------------|-------------|
| ROI Extraction | ROIResult | Signal Processor |
| Signal Processing | SignalResult | API Server, HRV Analyzer |
| SQI Engine | (score, level, color) | Ensemble Fusion, API Server |
| HRV Analysis | HRVResult | Stress Classifier |
| Stress Classification | (level, confidence) | API Server |
| API Server | JSON response | Frontend |

## Design Principles

1. **Modularity**: Each module has a single responsibility and communicates
   through shared dataclasses. Any module can be replaced without affecting
   others.

2. **Fail-safe output**: The SQI gate ensures that unreliable measurements
   are suppressed rather than presented as valid. The system prefers silence
   over incorrect output.

3. **No training required**: All signal processing and classification methods
   work without pre-trained models. This eliminates dependency on datasets and
   GPU availability at deployment time.

4. **Parallel development**: The shared interface definitions in `src/models.py`
   allow team members to work on different modules simultaneously, using
   synthetic test data until real inter-module data is available.
