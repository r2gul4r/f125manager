"""WASAPI audio timestamps are in 100 ns QPC units, on the perf_counter clock."""

import struct
import subprocess
import threading

import numpy as np


class Endpoint:
    def __init__(self, exe, kind):
        self.done = threading.Event()
        self.blocks = []
        self.proc = subprocess.Popen(
            [exe, kind],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        header = self.proc.stdout.read(4)
        if len(header) != 4:
            self.close()
            raise RuntimeError(f"Windows default {kind} audio endpoint unavailable")
        (self.rate,) = struct.unpack("<I", header)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            while head := self.proc.stdout.read(12):
                if len(head) != 12:
                    break
                stamp, n = struct.unpack("<QI", head)
                raw = self.proc.stdout.read(n * 4)
                if len(raw) != n * 4:
                    break
                self.blocks.append((stamp / 1e7, np.frombuffer(raw, dtype="<f4")))
        finally:
            self.done.set()

    def close(self):
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait()
        if hasattr(self, "reader"):
            self.reader.join(timeout=2)

    def signal(self):
        blocks = self.blocks.copy()
        if not blocks:
            return None, None
        start = blocks[0][0]
        pcm = np.zeros(
            round((blocks[-1][0] - start) * self.rate) + len(blocks[-1][1]), np.float32
        )
        for t, b in blocks:
            i = round((t - start) * self.rate)
            if 0 <= i <= len(pcm) - len(b):
                pcm[i : i + len(b)] = b
        return start, pcm


def listen(exe, vad):
    mic = Endpoint(exe, "mic")
    try:
        while not mic.done.wait(0.13):
            base, pcm = mic.signal()
            if pcm is None:
                continue
            audio = np.interp(
                np.arange(0, len(pcm), mic.rate / 16000), np.arange(len(pcm)), pcm
            ).astype(np.float32)
            n = len(audio) // 512 * 512
            if n < 4096:
                continue
            probs = vad(audio[:n].copy()).ravel()
            voiced = np.flatnonzero(probs >= 0.43)
            if len(voiced) < 4:
                if len(audio) > 16000 * 8:
                    break
                continue
            last = (int(voiced[-1]) + 1) * 512
            if (len(audio) - last) >= 10400 or len(audio) >= 16000 * 15:
                return audio[: last + 3200], base + last / 16000
        raise ValueError("음성을 못 들었어. UDP 3번을 다시 누르고 말해줘.")
    finally:
        mic.close()


def output_onset(endpoint, samples, src, earliest):
    base, pcm = endpoint.signal()
    if pcm is None or len(samples) < src * 0.08:
        return None
    rate = endpoint.rate
    v = np.interp(
        np.arange(round(len(samples) * rate / src)) * src / rate,
        np.arange(len(samples)),
        samples,
    )
    step = rate // 200
    bins = np.sqrt(np.mean(v[: len(v) // step * step].reshape(-1, step) ** 2, axis=1))
    active = np.flatnonzero((bins[:-1] > 0.00316) & (bins[1:] > 0.00316))
    if not len(active):
        return None
    onset = int(active[0]) * step
    # Only compare waveform matches close to the first payload submitted for playback.
    lo = max(0, round((earliest - base - 0.03) * rate))
    hi = min(len(pcm), lo + rate * 2)
    mix = pcm[lo:hi]
    if len(mix) < rate * 0.2:
        return None

    def band(x):
        spectrum = np.fft.rfft(x)
        hz = np.fft.rfftfreq(len(x), 1 / rate)
        return np.fft.irfft(spectrum * ((hz > 300) & (hz < 4300)), n=len(x))

    mix = band(mix)
    v = band(v)
    anchors = []
    for offset in (0, 0.006, 0.013, 0.019, 0.025, 0.031):
        idx = onset + round(offset * rate)
        ref = v[idx : idx + round(0.037 * rate)].copy()
        ref -= np.mean(ref)
        n = len(ref)
        fft = 1 << (len(mix) + n - 2).bit_length()
        corr = np.fft.irfft(np.fft.rfft(mix, fft) * np.fft.rfft(ref[::-1], fft), fft)[
            n - 1 : len(mix)
        ]
        ss = np.r_[0, np.cumsum(mix**2)]
        score = corr / np.maximum(
            1e-10, np.linalg.norm(ref) * np.sqrt(np.maximum(0, ss[n:] - ss[:-n]))
        )
        best = int(np.argmax(score))
        if score[best] >= 0.3:
            anchors.append(base + (lo + best - idx + onset) / rate)
    for anchor in anchors:
        consistent = [x for x in anchors if abs(x - anchor) < 0.004]
        if len(consistent) >= 3:
            return float(np.median(consistent))
    return None
