---
title: PranaScan rPPG POS vs I30 vs C3
emoji: 🫀
colorFrom: indigo
colorTo: pink
sdk: gradio
app_file: app_gradio_space.py
pinned: false
license: other
---

# PranaScan rPPG demo Space (CPU)

A reviewer-facing demo that compares three heart-rate estimators on simulated budget-phone
captures:

| Method | What it is |
|---|---|
| `pos` | Classical POS (Phase 1 baselines) on the mean of the 16 patches |
| `pbv_i30` | Cycle-1 winner I30: windowed PBV, exposure-step repair, logistic abstention (τ 0.584) |
| `c3_onnx` | Cycle-2 C3 PatchAttnSpec: (6, 16, 300) STMap at 10 Hz → 141 HR bins + abstain |
| `cascade` | C3 when it answers, else I30 when it answers, else abstain |

The coaching panel maps I30's quality features onto the PRD's 4-rung ladder:
1 Answer, 2 Answer flagged (HRV withheld), 3 Coach & retry (one tip, free retry),
4 Abstain ("We couldn't read your glow today", never a number).

**Not a medical device. Not for diagnosis.** Signals are synthetic approximations of the
shootout's `mp_data` sessions, so the numbers are illustrative, not benchmark results.

## Run locally

```bash
cd service-intelligence
pip install -r learning/hf_space/requirements.txt
export PRANASCAN_C3_ONNX=/path/to/C3_patch_attn_spec_int8_static_convonly.onnx  # optional
python learning/hf_space/app_gradio_space.py
```

Without the ONNX file the app still runs and shows C3 as "not loaded". Model binaries are not
committed: copy the C3 export from the Drive `FastAI-CV-Shootout` folder
into `learning/hf_space/models/` or point `PRANASCAN_C3_ONNX` at it.

## Feedback log (open coding)

The Feedback accordion appends one row per judgement to
`learning/hf_space/feedback/feedback_log.csv` (override with `PRANASCAN_FEEDBACK_CSV`):
verdict (`pass` / `fail` / `unsure`), an optional failure tag and a short note, next to each
estimator's HR and confidence. Rows hold no raw signal, image or personal data. Read them
weekly, cluster the notes into failure modes, then turn the top modes into eval-kit slices.

## Deploying to a Space (not done in this PR)

Publishing is a separate decision. When approved, the Space repo needs this folder plus the
pure-numpy modules it imports, laid out flat:

```
app_gradio_space.py  README.md  requirements.txt  models/C3_...onnx
app/__init__.py  app/services/__init__.py  app/services/rppg_processor.py
learning/__init__.py  learning/eval_kit/  learning/phase1/  learning/phase2_fastai/
```

`app_gradio_space.py` finds `learning/` either two levels up (this repo) or next to itself
(a flat Space bundle). The free CPU Basic hardware is enough: one comparison takes about 2 s.
