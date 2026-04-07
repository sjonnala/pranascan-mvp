import numpy as np
from scipy import signal
from app.services.rppg_processor import process_frames, _make_signal

if __name__ == "__main__":
    import warnings
    warnings.simplefilter("error")
    # this will crash if scipy detrends warns
    from tests.test_rppg import _make_signal
    try:
        process_frames(_make_signal(hr_bpm=72.0))
        print("clean_process_frames no error")
    except Exception as e:
        print("clean ERROR", repr(e))
    from tests.test_rppg import _make_low_fps_signal
    try:
        process_frames(_make_low_fps_signal(hr_bpm=72.0))
        print("low_fps no error")
    except Exception as e:
        print("low_fps ERROR", repr(e))
