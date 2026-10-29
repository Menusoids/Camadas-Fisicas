# Projeto 8 - Rádio AM: 3 estações moduladas, somadas no "ar", separadas por filtros e demoduladas
import os
import sys
import numpy as np
import sounddevice as sd
import matplotlib.pyplot as plt
from scipy.io import wavfile
from scipy.signal import butter, sosfiltfilt

FS = 44100
PASTA = os.path.dirname(os.path.abspath(__file__))
DURACAO_GRAVACAO = 4                                    # segundos por áudio
FAIXAS = [(9000, 12000), (12000, 15000), (15000, 18000)]  # Hz, uma faixa por estação
# Cada faixa tem 3 kHz e a portadora fica no centro, então a mensagem pode ter no máximo
# 1,5 kHz (o AM ocupa fc ± fm). Cortamos em 1,2 kHz para sobrar margem para a queda do filtro.
F_MSG = 1200
ORDEM = 10


def fft(sinal, fs):
    """Módulo da FFT (só frequências positivas), igual ao do projeto 7."""
    X = np.abs(np.fft.rfft(sinal)) / len(sinal)
    f = np.fft.rfftfreq(len(sinal), 1 / fs)
    return f, X


# Butterworth em formato "sos" = cascata de filtros de 2ª ordem (como os 12 do equalizador).
# Em ordem alta o polinômio único (b, a) tem coeficientes enormes e fica sensível a arredondamento;
# a cascata não (é a forma recomendada pelo scipy).
# sosfiltfilt aplica o filtro para frente e para trás: fase zero (sem atraso) e atenuação dobrada em dB.
def passa_baixa(x, fc, fs=FS):
    return sosfiltfilt(butter(ORDEM, fc, btype="low", fs=fs, output="sos"), x)


def passa_faixa(x, f1, f2, fs=FS):
    return sosfiltfilt(butter(ORDEM, [f1, f2], btype="band", fs=fs, output="sos"), x)


def carrega_audio(i):
    """Lê audio{i}.wav; se não existir, grava pelo microfone e salva."""
    arquivo = os.path.join(PASTA, f"audio{i}.wav")
    if not os.path.exists(arquivo):
        input(f"Aperte Enter e fale por {DURACAO_GRAVACAO} s (áudio {i})...")
        audio = sd.rec(DURACAO_GRAVACAO * FS, samplerate=FS, channels=1)
        sd.wait()
        wavfile.write(arquivo, FS, (audio[:, 0] * 32767).astype(np.int16))
    fs, audio = wavfile.read(arquivo)
    assert fs == FS, f"{arquivo} está a {fs} Hz, precisa ser {FS} Hz"
    if audio.ndim > 1:                                  # estéreo -> mono
        audio = audio.mean(axis=1)
    audio = audio.astype(float)
    return audio / np.max(np.abs(audio))


def toca(x, nome):
    print(f"Tocando {nome}...")
    sd.play(x / np.max(np.abs(x)), FS)
    sd.wait()


def salva(x, nome):
    wavfile.write(os.path.join(PASTA, nome), FS, (x / np.max(np.abs(x)) * 32767).astype(np.int16))


def energia_fora(s, f1, f2):
    """Fração da energia do sinal que está fora da faixa [f1, f2] (pela FFT)."""
    f, X = fft(s, FS)
    fora = (f < f1) | (f > f2)
    return np.sum(X[fora]**2) / np.sum(X**2)


def transmite(audios):
    """Emissor: limita a banda de cada áudio, modula na sua faixa e soma as 3 estações."""
    n = max(len(a) for a in audios)
    t = np.arange(n) / FS
    modulados = []
    for audio, (f1, f2) in zip(audios, FAIXAS):
        m = passa_baixa(np.pad(audio, (0, n - len(audio))), F_MSG)  # completa com zeros até o maior
        fc = (f1 + f2) / 2                                         # portadora no centro da faixa
        modulados.append(m * np.cos(2 * np.pi * fc * t))           # AM = multiplicação
    return modulados, sum(modulados)                               # soma = sinal no meio físico


def recebe(canal):
    """Receptor: separa cada estação com passa-faixa e demodula (síncrona)."""
    t = np.arange(len(canal)) / FS
    extraidos, demodulados = [], []
    for f1, f2 in FAIXAS:
        s = passa_faixa(canal, f1, f2)                  # "sintoniza" a estação
        fc = (f1 + f2) / 2
        # m·cos·cos = m/2 + (m/2)·cos(2·2π·fc·t): o passa-baixa tira o termo em 2fc
        # e o fator 2 devolve a amplitude original
        extraidos.append(s)
        demodulados.append(2 * passa_baixa(s * np.cos(2 * np.pi * fc * t), F_MSG))
    return extraidos, demodulados


def plota_fft(sinais, nomes, titulo, faixas=FAIXAS):
    """Um subplot com a FFT de cada sinal; as faixas permitidas ficam sombreadas."""
    plt.figure(titulo, figsize=(9, 1.2 + 2 * len(sinais)))
    for i, (s, nome) in enumerate(zip(sinais, nomes)):
        plt.subplot(len(sinais), 1, i + 1)
        for k, (f1, f2) in enumerate(faixas):
            plt.axvspan(f1, f2, color=f"C{k + 1}", alpha=0.15)
        f, X = fft(s, FS)
        plt.plot(f, X, linewidth=0.6)
        plt.xlim(0, FS / 2)
        plt.title(nome)
        plt.ylabel("|X(f)|")
    plt.xlabel("Frequência [Hz]")
    plt.tight_layout()


def main():
    audios = [carrega_audio(i) for i in (1, 2, 3)]
    for i, a in enumerate(audios, 1):
        toca(a, f"áudio original {i}")

    modulados, canal = transmite(audios)
    for i, (s, (f1, f2)) in enumerate(zip(modulados, FAIXAS), 1):
        print(f"Estação {i} ({f1 // 1000}-{f2 // 1000} kHz): energia fora da faixa = "
              f"{10 * np.log10(energia_fora(s, f1, f2)):.1f} dB")

    extraidos, demodulados = recebe(canal)
    for i, d in enumerate(demodulados, 1):
        salva(d, f"demodulado{i}.wav")

    nomes = [f"Estação {i}: {f1 // 1000}-{f2 // 1000} kHz" for i, (f1, f2) in enumerate(FAIXAS, 1)]
    plota_fft(modulados, nomes, "FFT dos 3 sinais modulados (emissor)")
    plota_fft([canal], ["Soma das 3 estações (sinal no meio físico)"], "FFT do sinal resultante")
    plota_fft(extraidos, nomes, "FFT dos 3 sinais extraídos (receptor)")
    plt.show()                                          # os áudios tocam depois de fechar as janelas

    for i, d in enumerate(demodulados, 1):
        toca(d, f"áudio demodulado {i}")


def autoteste():
    """Sem microfone: 3 tons passam pela cadeia inteira e têm que voltar iguais."""
    # tons diferentes em cada estação: se uma vazar na outra, o erro aparece.
    # ponytail: tons abaixo de ~800 Hz; perto do corte (1,2 kHz) o Butterworth já atenua alguns %
    t = np.arange(2 * FS) / FS
    tons = [np.sin(2 * np.pi * f * t) for f in (300, 500, 800)]
    modulados, canal = transmite(tons)
    _, demodulados = recebe(canal)
    for tom, s, d, (f1, f2) in zip(tons, modulados, demodulados, FAIXAS):
        assert energia_fora(s, f1, f2) < 1e-4, "estação invadiu outra faixa"
        assert np.max(np.abs(tom - d)[FS // 2:-FS // 2]) < 0.01, "demodulação não recuperou o tom"
    print("autoteste ok")


if __name__ == "__main__":
    autoteste() if sys.argv[1:] == ["teste"] else main()
