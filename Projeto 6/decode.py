#Importe todas as bibliotecas
from suaBibSignal import *
import numpy as np
import sounddevice as sd
import matplotlib.pyplot as plt
from scipy.signal import find_peaks
from scipy.io import wavfile
import time
import sys

FS = 44100
DURACAO = 3            # segundos de gravação
NUM_PICOS = 6          # o enunciado pede no mínimo 5
DIST_MIN_HZ = 5        # picos mais próximos que isso são considerados o mesmo
TOLERANCIA_HZ = 20     # distância máxima entre um pico e a frequência da tabela


#funcao para transformas intensidade acustica em dB, caso queira usar
def todB(s):
    sdB = 10*np.log10(s)
    return(sdB)


def gravar():
    sd.default.samplerate = FS
    sd.default.channels = 1
    numAmostras = DURACAO * FS

    print("A captação começará em 2 segundos")
    time.sleep(2)
    print("Gravação inicializada")
    audio = sd.rec(int(numAmostras), FS, channels=1)
    sd.wait()
    print("...     FIM")
    return audio[:, 0]


def ler_wav(caminho):
    fs, dados = wavfile.read(caminho)
    if dados.ndim > 1:
        dados = dados[:, 0]
    if dados.dtype == np.int16:
        dados = dados / 32768.0
    return fs, dados.astype(float)


def encontrar_picos(xf, yf):
    df = xf[1] - xf[0]
    # só a faixa de interesse do DTMF
    faixa = (xf > 500) & (xf < 2000)
    idx_faixa = np.where(faixa)[0]
    picos, _ = find_peaks(yf[faixa], distance=max(1, int(DIST_MIN_HZ / df)))
    picos = idx_faixa[picos]
    # mantém os NUM_PICOS mais altos, ordenados por frequência
    picos = picos[np.argsort(yf[picos])[::-1][:NUM_PICOS]]
    return np.sort(picos)


def identificar_tecla(xf, yf, picos):
    def melhor(freqs_tabela):
        # para cada frequência da tabela, a amplitude do maior pico dentro da tolerância
        scores = []
        for f in freqs_tabela:
            perto = [p for p in picos if abs(xf[p] - f) <= TOLERANCIA_HZ]
            scores.append(max((yf[p] for p in perto), default=0))
        i = int(np.argmax(scores))
        return i, scores[i]

    i, s_linha = melhor(LINHAS)
    j, s_coluna = melhor(COLUNAS)
    if s_linha == 0 or s_coluna == 0:
        return None, None, None
    return TECLAS[i][j], LINHAS[i], COLUNAS[j]


def main():
    signal = signalMeu()

    if len(sys.argv) > 1:
        fs, dados = ler_wav(sys.argv[1])
        print("Lendo arquivo {}".format(sys.argv[1]))
    else:
        fs, dados = FS, gravar()

    t = np.linspace(0, len(dados) / fs, len(dados), endpoint=False)

    # plot do sinal recebido no tempo (apenas 20 ms para enxergar as ondas)
    n = int(0.02 * fs)
    meio = len(dados) // 2
    plt.figure()
    plt.plot(t[meio:meio + n], dados[meio:meio + n])
    plt.title("Sinal recebido (trecho de 20 ms)")
    plt.xlabel("Tempo (s)")
    plt.ylabel("Amplitude")
    plt.grid(True)

    xf, yf = signal.calcFFT(dados, fs)
    picos = encontrar_picos(xf, yf)

    for p in picos:
        print("freq de pico sao {:.2f} Hz".format(xf[p]))

    tecla, f_linha, f_coluna = identificar_tecla(xf, yf, picos)
    if tecla is None:
        print("Nenhuma tecla DTMF identificada")
    else:
        print("Frequências identificadas: {} Hz + {} Hz".format(f_linha, f_coluna))
        print("TECLA: {}".format(tecla))

    plt.figure()
    plt.plot(xf, yf)
    plt.plot(xf[picos], yf[picos], "rx")
    plt.title("Fourier do sinal recebido" + ("" if tecla is None else " - tecla {}".format(tecla)))
    plt.xlabel("Frequência (Hz)")
    plt.ylabel("|X(f)|")
    plt.xlim(0, 2500)
    plt.grid(True)

    ## Exiba gráficos do fourier do som gravados
    plt.show()


if __name__ == "__main__":
    main()
