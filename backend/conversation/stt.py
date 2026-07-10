# from faster_whisper import WhisperModel
# import io
# import wave
# import numpy as np

# # "base" ou "small" pra testar latência primeiro; "medium" tem mais qualidade mas é mais lento
# model = WhisperModel("tiny", device="cpu", compute_type="int8", cpu_threads=4)

# async def transcribe_audio(audio_bytes):
#     # Assume áudio já vem como WAV 16kHz mono
#     audio_io = io.BytesIO(audio_bytes)
#     segments, info = model.transcribe(audio_io, language="en")
#     text = " ".join([seg.text for seg in segments])
#     return text.strip()

import time
from faster_whisper import WhisperModel

model = WhisperModel("tiny", device="cpu", compute_type="int8")

start = time.time()
segments, info = model.transcribe("teste.wav", language="en")
text = " ".join([seg.text for seg in segments])
print(f"Texto: {text}")
print(f"Tempo: {time.time() - start:.2f}s")