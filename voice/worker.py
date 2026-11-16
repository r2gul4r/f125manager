"""Local push-to-talk worker. Only UDP-triggered turns open the microphone."""

import ctypes
import json
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np
from answers import ask_engineer
from audio_io import Endpoint, listen, output_onset
from faster_whisper import WhisperModel
from faster_whisper.vad import get_vad_model


def report(status, **fields):
    print(json.dumps(dict(status=status, **fields)), flush=True)


def own_children():
    # Kill native audio children even if the server is stopped during a turn.
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.restype = ctypes.c_void_p
    job = kernel.CreateJobObjectW(None, None)
    limits = ctypes.create_string_buffer(
        144 if ctypes.sizeof(ctypes.c_void_p) == 8 else 112
    )
    ctypes.c_uint32.from_buffer(limits, 16).value = 0x2000
    handle = ctypes.c_void_p(job)
    if not kernel.SetInformationJobObject(
        handle, 9, limits, len(limits)
    ) or not kernel.AssignProcessToJobObject(handle, ctypes.c_void_p(-1)):
        raise ctypes.WinError(ctypes.get_last_error())


def until(speaker, prefix):
    for line in speaker.stdout:
        if line.startswith(prefix):
            return line.strip()
    raise RuntimeError("Local speech synthesizer stopped")


def main():
    runtime, port, folder = Path(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3])
    own_children()
    exe = runtime / "vk3/voice-endpoint.exe"
    if not exe.exists():
        raise RuntimeError("Audio endpoint executable missing")
    model = WhisperModel(
        str(
            next(
                (
                    runtime / "asr-model/models--Systran--faster-whisper-base/snapshots"
                ).iterdir()
            )
        ),
        device="cpu",
        compute_type="int8",
        cpu_threads=4,
    )
    vad = get_vad_model()
    vad(np.zeros(4096, np.float32))
    speaker = subprocess.Popen(
        [runtime / "vk3/voice-speaker.exe", "CPU", "1000000"],
        cwd=runtime,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        until(speaker, "READY")
        report("ready")
        for cmd in sys.stdin:
            if cmd.strip() != "listen":
                continue
            try:
                report("listening", error="", heard="", answer="", latencyMs=None)
                audio, end = listen(exe, vad)
                endpointed = time.perf_counter()
                report("transcribing")
                segments, _ = model.transcribe(
                    audio, beam_size=4, condition_on_previous_text=False
                )
                text = " ".join(s.text.strip() for s in segments).strip()
                asr = time.perf_counter()
                if not text:
                    raise ValueError("음성이 인식되지 않았어. 다시 말해줘.")
                report("thinking", heard=text)
                turn, frame, damage = ask_engineer(port, text, folder)
                line = turn["speech"]
                report(
                    "speaking",
                    heard=text,
                    answer=line,
                    lap=frame.get("lap"),
                    wingDamage=damage,
                    proposalId=turn.get("proposalId"),
                )
                out = Endpoint(exe, "output")
                try:
                    speaker.stdin.write(line + "\n")
                    speaker.stdin.flush()
                    log = until(speaker, "RUN ").split()
                    queued = float(log[log.index("queued") + 1])
                    if queued < 0:
                        raise RuntimeError("Windows playback failed")
                    first_queue = float(log[3]) + queued
                    until(speaker, "READY")
                finally:
                    out.close()
                with wave.open(str(runtime / "bono/mic-reply.wav")) as w:
                    samples = (
                        np.frombuffer(w.readframes(w.getnframes()), dtype="<i2") / 32768
                    )
                    match = output_onset(out, samples, w.getframerate(), first_queue)
                report(
                    "ready",
                    latencyMs=round((match - end) * 1000)
                    if match is not None
                    else None,
                    endpointMs=round((endpointed - end) * 1000),
                    recognitionMs=round((asr - endpointed) * 1000),
                    submittedMs=round((first_queue - end) * 1000),
                    error=turn.get("error", ""),
                )
            except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
                if speaker.poll() is not None:
                    raise
                report("ready", error=str(exc))
    finally:
        speaker.kill()
        speaker.wait()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        report("error", error=str(exc))
        raise
