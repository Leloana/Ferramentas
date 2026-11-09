import numpy as np

BATIDAS = None  # segundos; preenchido por pop2piano.py antes de chamar o modelo
SR = 44100


class RhythmExtractor2013:
    def __init__(self, method="multifeature"):
        pass

    def __call__(self, audio):
        if BATIDAS is not None:
            bt = np.asarray(BATIDAS, dtype=float)
        else:
            import librosa
            _, fr = librosa.beat.beat_track(y=np.asarray(audio, dtype=float), sr=SR)
            bt = librosa.frames_to_time(fr, sr=SR)
        bt = bt[(bt >= 0) & (bt <= len(audio) / SR)]
        iv = np.diff(bt)
        bpm = 60.0 / float(np.median(iv))
        return bpm, bt, 3.0, np.array([bpm]), iv
