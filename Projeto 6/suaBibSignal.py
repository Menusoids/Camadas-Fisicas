import numpy as np
import matplotlib.pyplot as plt
from scipy.fftpack import fft
from scipy import signal as window


# Tabela DTMF (frequências padrão ITU)
LINHAS = [697, 770, 852, 941]
COLUNAS = [1209, 1336, 1477, 1633]
TECLAS = [
    ["1", "2", "3", "A"],
    ["4", "5", "6", "B"],
    ["7", "8", "9", "C"],
    ["X", "0", "#", "D"],
]

DTMF = {}
for i, f_linha in enumerate(LINHAS):
    for j, f_coluna in enumerate(COLUNAS):
        DTMF[TECLAS[i][j]] = (f_linha, f_coluna)


class signalMeu:

    def __init__(self):
        self.init = 0

    def generateSin(self, freq, amplitude, time, fs):
        n = int(time * fs)
        x = np.linspace(0.0, time, n, endpoint=False)
        s = amplitude * np.sin(2 * np.pi * freq * x)
        return (x, s)

    def calcFFT(self, signal, fs):
        # https://docs.scipy.org/doc/scipy/reference/tutorial/fftpack.html
        N = len(signal)
        W = window.windows.hann(N)
        T = 1 / fs
        xf = np.linspace(0.0, 1.0 / (2.0 * T), N // 2)
        yf = fft(signal * W)
        return (xf, np.abs(yf[0:N // 2]))

    def plotFFT(self, signal, fs, titulo="Fourier"):
        x, y = self.calcFFT(signal, fs)
        plt.figure()
        plt.plot(x, np.abs(y))
        plt.title(titulo)
        plt.xlabel("Frequência (Hz)")
        plt.ylabel("|X(f)|")
        plt.grid(True)
