import os
import numpy as np
import sounddevice as sd
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, Button
from scipy.io import wavfile
from scipy.signal import lfilter, freqz

FS = 44100
ARQUIVO = "audio_teste.wav"
DURACAO_GRAVACAO = 5      # segundos
BANDAS = [20, 32, 64, 125, 250, 500, 1000, 2000, 4000, 8000, 16000, 20000]
Q = 1.4                   # ~1 oitava de largura por banda


def peaking_eq(f0, gain_db, Q, fs):
    """Filtro de pico (código fornecido no filtro_peaking_EQ.ipynb)."""
    A = 10**(gain_db / 40)
    omega = 2 * np.pi * f0 / fs
    alpha = np.sin(omega) / (2 * Q)

    b = np.array([1 + alpha * A, -2 * np.cos(omega), 1 - alpha * A])
    a = np.array([1 + alpha / A, -2 * np.cos(omega), 1 - alpha / A])
    return b / a[0], a / a[0]


def carrega_audio():
    """Usa o áudio salvo; se não existir, grava pelo microfone e salva."""
    if not os.path.exists(ARQUIVO):
        print(f"Gravando {DURACAO_GRAVACAO} s de áudio... fale/toque algo!")
        audio = sd.rec(DURACAO_GRAVACAO * FS, samplerate=FS, channels=1)
        sd.wait()
        wavfile.write(ARQUIVO, FS, (audio[:, 0] * 32767).astype(np.int16))
    fs, audio = wavfile.read(ARQUIVO)
    if audio.ndim > 1:                       # estéreo -> mono
        audio = audio.mean(axis=1)
    audio = audio.astype(float)
    return fs, audio / np.max(np.abs(audio))


def equaliza(audio, ganhos, fs):
    """Aplica os 12 filtros um a um ao sinal e devolve os coeficientes de cada um."""
    filtros = [peaking_eq(f0, g, Q, fs) for f0, g in zip(BANDAS, ganhos)]
    y = audio
    for b, a in filtros:
        y = lfilter(b, a, y)
    return y, filtros


def plota_bode(filtros, fs):
    # Filtros em série: G_total(Z) = G1(Z)·G2(Z)·...·G12(Z).
    # ponytail: multiplica as respostas em frequência em vez de expandir o
    # polinômio de grau 24 (np.polymul), que perde precisão numérica.
    f = np.logspace(np.log10(10), np.log10(fs / 2), 2000)
    H = np.ones(len(f), dtype=complex)
    for b, a in filtros:
        H *= freqz(b, a, worN=f, fs=fs)[1]

    plt.figure("Bode do equalizador", figsize=(9, 4))
    plt.semilogx(f, 20 * np.log10(np.abs(H)))
    for f0 in BANDAS:
        plt.axvline(f0, color="gray", linestyle=":", linewidth=0.7)
    plt.title("Diagrama de Bode - filtro completo (12 bandas em série)")
    plt.xlabel("Frequência [Hz]")
    plt.ylabel("Ganho [dB]")
    plt.ylim(-15, 15)
    plt.grid(which="both", linestyle="--", linewidth=0.5)
    plt.tight_layout()
    plt.show(block=False)


def main():
    fs, audio = carrega_audio()

    # Interface: 12 sliders verticais de -10 a +10 dB
    fig = plt.figure("Equalizador - Projeto 7", figsize=(11, 5))
    sliders = []
    for i, f0 in enumerate(BANDAS):
        ax = fig.add_axes([0.05 + i * 0.075, 0.25, 0.03, 0.6])
        rotulo = f"{f0 // 1000}k" if f0 >= 1000 else str(f0)
        sliders.append(Slider(ax, rotulo, -10, 10, valinit=0, valstep=1,
                              orientation="vertical"))
    botao = Button(fig.add_axes([0.4, 0.05, 0.2, 0.08]), "Aplicar e tocar")

    def aplicar(_):
        ganhos = [s.val for s in sliders]
        print("Ganhos (dB):", dict(zip(BANDAS, ganhos)))
        y, filtros = equaliza(audio, ganhos, fs)
        y = y / max(1, np.max(np.abs(y)))    # evita saturar (clipping)

        print("Tocando original...")
        sd.play(audio, fs); sd.wait()
        print("Tocando equalizado...")
        sd.play(y, fs); sd.wait()
        plota_bode(filtros, fs)

    botao.on_clicked(aplicar)
    plt.show()


if __name__ == "__main__":
    main()
