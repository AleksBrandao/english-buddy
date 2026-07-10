import time
from faster_whisper import WhisperModel

# ==== TROQUE AQUI PELO CAMINHO REAL DO SEU ARQUIVO ====
CAMINHO_AUDIO = r"C:\Users\89721\Downloads\Day 24 Speak English in 30 Days 99 Sentences Shadowing Practice English Podcast.wav"

# model = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=4)
model = WhisperModel("base", device="cpu", compute_type="int8", cpu_threads=4)


print(f"Transcrevendo: {CAMINHO_AUDIO}")
print("Isso pode levar alguns minutos...")
start = time.time()

segments, info = model.transcribe(
    CAMINHO_AUDIO,
    language="en",
    vad_filter=True,
    beam_size=5,
)

with open("transcricao.txt", "w", encoding="utf-8") as f:
    for seg in segments:
        linha = f"[{seg.start:.1f}s -> {seg.end:.1f}s] {seg.text.strip()}"
        print(linha)
        f.write(linha + "\n")

print(f"\nConcluído em {time.time() - start:.1f}s")
print(f"Idioma detectado: {info.language} (confiança: {info.language_probability:.2f})")