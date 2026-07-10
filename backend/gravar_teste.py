import sounddevice as sd
from scipy.io.wavfile import write

DURACAO = 5  # segundos
SAMPLE_RATE = 16000  # Whisper espera 16kHz

print("Gravando em 3 segundos... prepare-se para falar em inglês.")
sd.sleep(3000)

print("🎙️ Gravando agora! Fale por", DURACAO, "segundos...")
audio = sd.rec(int(DURACAO * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype='int16')
sd.wait()  # espera terminar a gravação

write("teste.wav", SAMPLE_RATE, audio)
print("✅ Gravação salva como teste.wav")