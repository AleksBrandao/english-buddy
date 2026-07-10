import collections
import sys
import time

import numpy as np
import sounddevice as sd
import webrtcvad
from scipy.io.wavfile import write

# ==== CONFIG ====
SAMPLE_RATE = 16000
FRAME_DURATION_MS = 30        # webrtcvad só aceita 10, 20 ou 30 ms
FRAME_SIZE = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)

VAD_AGGRESSIVENESS = 2        # 0 (permissivo) a 3 (mais agressivo em filtrar ruído)
SILENCIO_PARA_PARAR_MS = 1200  # quanto tempo de silêncio até considerar que parou de falar
SILENCIO_FRAMES = int(SILENCIO_PARA_PARAR_MS / FRAME_DURATION_MS)

TIMEOUT_MAX_S = 15            # segurança: nunca grava mais que isso, mesmo sem silêncio


def gravar_com_vad(caminho_saida="entrada.wav"):
    vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)

    print("🎙️  Fale quando quiser... (grava automaticamente e para quando você silenciar)")

    audio_capturado = []
    frames_silencio_seguidos = 0
    comecou_a_falar = False
    inicio = time.time()

    def callback(indata, frames, time_info, status):
        nonlocal frames_silencio_seguidos, comecou_a_falar

        audio_int16 = (indata[:, 0] * 32767).astype(np.int16)
        audio_capturado.append(audio_int16.copy())

        is_speech = vad.is_speech(audio_int16.tobytes(), SAMPLE_RATE)

        if is_speech:
            if not comecou_a_falar:
                print("🗣️  Detectei fala, gravando...")
            comecou_a_falar = True
            frames_silencio_seguidos = 0
        elif comecou_a_falar:
            frames_silencio_seguidos += 1

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype='float32',
        blocksize=FRAME_SIZE,
        callback=callback,
    ):
        while True:
            time.sleep(FRAME_DURATION_MS / 1000)

            if comecou_a_falar and frames_silencio_seguidos >= SILENCIO_FRAMES:
                print("🤫 Silêncio detectado, parando gravação.")
                break

            if time.time() - inicio > TIMEOUT_MAX_S:
                print("⏱️  Tempo máximo atingido, parando gravação.")
                break

    if not audio_capturado or not comecou_a_falar:
        print("⚠️  Nenhuma fala detectada.")
        return None

    audio_final = np.concatenate(audio_capturado)
    write(caminho_saida, SAMPLE_RATE, audio_final)
    return caminho_saida


if __name__ == "__main__":
    caminho = gravar_com_vad()
    if caminho:
        print(f"✅ Áudio salvo em: {caminho}")
    else:
        sys.exit(1)