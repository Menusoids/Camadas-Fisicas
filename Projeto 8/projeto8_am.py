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
AUDIOS = ["audio_1.wav", "audio_2.wav", "Audio_3.wav"]  # na raiz do repo, um por estação
FAIXAS = [(9000, 12000), (12000, 15000), (15000, 18000)]  # Hz, uma faixa por estação
# Cada faixa tem 3 kHz e a portadora fica no centro, então a mensagem pode ter no máximo
# 1,5 kHz (o AM ocupa fc ± fm). Cortamos em 1,2 kHz para sobrar margem para a queda do filtro.
F_MSG = 1200
ORDEM = 10


def fft(sinal, fs): # Monta o gráfico da transformada de fourrier
    """Módulo da FFT (só frequências positivas), igual ao do projeto 7."""
    X = np.abs(np.fft.rfft(sinal)) / len(sinal)
    f = np.fft.rfftfreq(len(sinal), 1 / fs)
    return f, X


# Butterworth em formato "sos" = cascata de filtros de 2ª ordem (como os 12 do equalizador).
# Em ordem alta o polinômio único (b, a) tem coeficientes enormes e fica sensível a arredondamento;
# a cascata não (é a forma recomendada pelo scipy).
# sosfiltfilt aplica o filtro para frente e para trás: fase zero (sem atraso) e atenuação dobrada em dB.
def passa_baixa(x, fc, fs=FS): # Filtro
    return sosfiltfilt(butter(ORDEM, fc, btype="low", fs=fs, output="sos"), x)


def passa_faixa(x, f1, f2, fs=FS): # Filtro
    return sosfiltfilt(butter(ORDEM, [f1, f2], btype="band", fs=fs, output="sos"), x)


def carrega_audio(nome):
    """Lê um dos áudios da raiz do repositório (um por canal)."""
    arquivo = os.path.join(PASTA, "..", nome)
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


def transmite(audios): #modula
    """Emissor: limita a banda de cada áudio, modula na sua faixa e soma as 3 estações."""
    n = max(len(a) for a in audios)
    t = np.arange(n) / FS
    modulados = []
    for audio, (f1, f2) in zip(audios, FAIXAS):
        m = passa_baixa(np.pad(audio, (0, n - len(audio))), F_MSG)  # trata o sinal pra modular
        fc = (f1 + f2) / 2                                         # calcula a portadora, pegando a freq do centro da faixa
        modulados.append(m * np.cos(2 * np.pi * fc * t))           # Modula
    return modulados, sum(modulados)                               # soma as três estações pra pegar o sinal do "ar"


def recebe(canal): #Desmodula
    """Receptor: separa cada estação com passa-faixa e demodula (síncrona)."""
    t = np.arange(len(canal)) / FS
    extraidos, demodulados = [], []
    for f1, f2 in FAIXAS: # pra cada estação
        s = passa_faixa(canal, f1, f2)     # Pega só o que ta dentro dela
        fc = (f1 + f2) / 2                 # calcula a portadora
        extraidos.append(s)
        demodulados.append(4 * passa_baixa(s * np.cos(2 * np.pi * fc * t), F_MSG))
         # Desmodula multiplicando por fc, usa o passa baixa pra pegar só a f que presta e multiplica por 2 pra acertar o volume
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
    audios = [carrega_audio(a) for a in AUDIOS] # um áudio diferente por canal
    for i, a in enumerate(audios, 1):
        toca(a, f"áudio original {i}") # toca eles

    modulados, canal = transmite(audios) # pega os modulados
    for i, (s, (f1, f2)) in enumerate(zip(modulados, FAIXAS), 1):
        print(f"Estação {i} ({f1 // 1000}-{f2 // 1000} kHz): energia fora da faixa = "
              f"{10 * np.log10(energia_fora(s, f1, f2)):.1f} dB") # fala se a modulação escapou da banda alvo

    extraidos, demodulados = recebe(canal) #desmodula
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
