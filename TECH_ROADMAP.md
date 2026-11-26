# PranaScan: rPPG Deep Learning Migration Roadmap (ROADMAP-AI-001)

## Executive Summary
This roadmap outlines the strategic transition from classical mathematical rPPG algorithms (POS, CHROM) to modern Deep Learning architectures (such as DeepPhys and spatial-temporal CNNs). Deep learning enables superior handling of motion artifacts, variable lighting, and generalized skin-tone accuracy, essential for clinical-grade remote vitals extraction on standard smartphones.

---

## Part 1: Three-Phase Migration Timeline

### Phase 1: Hybrid Architecture & Data Processing (Weeks 1-3)
*Goal: Establish the spatial-temporal data pipeline without removing existing DSP logic.*
- **Week 1: Data Structuring & Ground Truth**
  - Extract multi-channel video ROIs and establish raw RGB data extraction.
  - Sync classical POS/CHROM output alongside a gold-standard ground truth dataset (from medical pulse oximeters) directly in the cloud/backend.
- **Week 2: Spatial-Temporal Maps (STMaps)**
  - Implement conversion of video frames into spatial-temporal representations (e.g., separating spatial and temporal differences as required by architectures like DeepPhys).
  - *Outcome*: Build the "Signal-to-Spectrogram" / "Frame-to-STMap" preprocessing layer.
- **Week 3: Hybrid Baseline Setup**
  - Run the established classical DSP in parallel with STMap generation. Ensure the feature extraction pipeline adds less than 15ms latency per frame.

### Phase 2: AI Model Engineering & Validation (Weeks 4-7)
*Goal: Train, validate, and benchmark the DeepPhys/CNN model in a controlled environment.*
- **Week 4: PyTorch Model Prototyping**
  - Build the DeepPhys dual-convolutional architecture (Appearance Branch + Motion Branch) using PyTorch.
  - Focus on defining the loss functions (e.g., signal-to-noise ratio loss or negative Pearson correlation with ground truth).
- **Week 5: Training & Tuning (Demographic Focus)**
  - Train the model using diverse skin-tone datasets. Apply targeted augmentation (simulated lighting drops, subtle motion noise) to harden the model.
- **Week 6-7: Evaluation & "Tear-down"**
  - Benchmark the deep learning predictions against POS/CHROM using Mean Absolute Error (MAE) and Root Mean Square Error (RMSE). 
  - Goal: Achieve clinical parity (< 2-3 BPM error) across diverse conditions.

### Phase 3: On-Device Edge Inference (Weeks 8-10)
*Goal: Port the validated model to mobile environments mapping to physical hardware constraints.*
- **Week 8: Model Quantization & Export**
  - Convert PyTorch models to ONNX, then to edge-native formats: **CoreML** for iOS and **TFLite** for Android. Apply INT8 or FP16 quantization to reduce memory footprint.
- **Week 9: Mobile Integration & Expo/React Native Bridge**
  - Integrate inference engines securely within the React Native/Expo ecosystem. Build a native module bridge (using Swift/Kotlin) if JS thread bottlenecks inference.
- **Week 10: Performance Profiling & Optimization**
  - Measure thermal throttling, battery drain, and inference FPS on target baseline devices (e.g., iPhone 13, mid-range Android).

---

## Part 2: Personal Skill-Upgrade Path (Week-by-Week)

To execute this migration, the following AI/DL proficiencies must be acquired:

| Timeline | Domain Focus | Specific Skills to Master |
|---|---|---|
| **Week 1** | Python / DSP Basics | Advanced Pandas/NumPy, OpenCV for fast bounding-box ROI spatial averaging, understanding FFT/Bandpass filtering to baseline classical models. |
| **Week 2** | Image Prep / STMaps | Translating time-series RGB signals into 2D spatial-temporal maps. Signal-to-Spectrogram conversions (STFT, CWT). |
| **Week 3** | PyTorch Fundamentals | Tensors, Autograd, building custom `nn.Module`. Creating robust DataLoaders for video sequences. |
| **Week 4** | CNN Architectures | Dual-stream networks, 3D convolutions (C3D), Attention mechanisms for isolating the pulse signal from facial motion. |
| **Week 5** | Loss Functions & Training | Designing custom loss functions for periodic biological signals. Managing vanishing gradients and overfitting in physiological data. |
| **Week 6** | Model Conversion | ONNX runtime ecosystem. Exporting graphs, validating matching tensors between Python and ONNX. |
| **Week 7** | Edge ML: Quantization | Quantization-aware training (QAT), Post-training quantization (PTQ), FP32 vs INT8 trade-offs in physiological signal retention. |
| **Week 8-9** | TFLite / CoreML | Integrating `.tflite` via Android NNAPI/GPU delegates. Deploying `.mlmodel` via Apple Neural Engine (ANE). |
| **Week 10** | Mobile Optimization | React Native JSI (JavaScript Interface), native iOS/Android thread handling to prevent UI jank during 30 FPS inference. |

---

## Part 3: Hardware Constraints for On-Device Inference

Deploying sophisticated computer vision and deep learning models directly on edge devices presents unique hardware constraints that must shape our architecture:

### 1. Compute & Thermal Throttling
- **Constraint**: Running 30 FPS video through a dual-stream CNN uses significant GPU/NPU power. Prolonged usage (e.g., a 60-second continuous scan) will cause thermal throttling, abruptly slowing frame rates and degrading rPPG accuracy.
- **Mitigation**: Offload processing to dedicated AI accelerators (Apple Neural Engine on iOS, Hexagon DSP / Google Tensor TPU on Android). Limit scan duration to 30-45 seconds.

### 2. Memory (RAM) Limitations
- **Constraint**: Mid-range Android devices often kill background/foreground apps aggressively if memory footprint spikes. A heavy unoptimized PyTorch CV model can exceed 500MB of RAM.
- **Mitigation**: Target model sizes under 15MB. Utilize INT8 quantization to cut memory usage by 75% compared to standard float32 precision, ensuring safety on 4GB RAM devices.

### 3. Camera Pipeline Latency & Sync
- **Constraint**: Inference tasks can block the camera data buffer. Dropped frames completely ruin the phase alignment required for micro-color variation detection.
- **Mitigation**: Decouple the UI thread from the camera buffer thread. Inference must run async. Utilize React Native JSI or Native Modules so camera frame byte-arrays don't have to be serialized over the standard React Native bridge.

### 4. Hardware Fragmentation (Android)
- **Constraint**: Android camera APIs and internal Image Signal Processors (ISPs) apply undocumented "beauty filters", auto-white balance (AWB), and auto-exposure (AE) compensation. These ruin rPPG signals.
- **Mitigation**: Must lock AWB/AE and disable noise reduction filters aggressively via Camera2API. Testing must be prioritized on varied sensors to map the differences in RGB channel sensitivity.

---
*Generated by director-orchestrator | PranaScan Ecosystem*
