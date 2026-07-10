import time
from faster_whisper import WhisperModel

print("Carregando modelo...")
load_start = time.time()
model = WhisperModel("tiny", device="cpu", compute_type="int8")
print(f"Modelo carregado em {time.time() - load_start:.2f}s")

print("Transcrevendo...")
start = time.time()
segments, info = model.transcribe("teste.wav", language="en")
text = " ".join([seg.text for seg in segments])
latency = time.time() - start

print(f"\nTexto: {text}")
print(f"Tempo de transcrição: {latency:.2f}s")
print(f"Idioma detectado: {info.language} (confiança: {info.language_probability:.2f})")