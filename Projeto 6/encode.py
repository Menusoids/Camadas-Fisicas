#importe as bibliotecas
from suaBibSignal import *
import numpy as np
import sounddevice as sd
import matplotlib.pyplot as plt
from scipy.io import wavfile
import signal as sig
import sys

FS = 44100        # taxa de amostragem
DURACAO = 5       # segundos de som emitido
AMPLITUDE = 1


#funções caso queriram usar para sair...
def signal_handler(signal, frame):
        print('You pressed Ctrl+C!')
        sys.exit(0)

#converte intensidade em Db, caso queiram ...
def todB(s):
    sdB = 10*np.log10(s)
    return(sdB)


def main():
    sig.signal(sig.SIGINT, signal_handler)
    signal = signalMeu()

    print("Inicializando encoder")
    print("Aguardando usuário")
    NUM = input("Digite uma tecla (0-9, A-D, X ou #): ").strip().upper()
    while NUM not in DTMF:
        NUM = input("Tecla inválida. Digite novamente: ").strip().upper()

    f_linha, f_coluna = DTMF[NUM]

    print("Gerando Tons base")
    t, s1 = signal.generateSin(f_linha, AMPLITUDE, DURACAO, FS)
    _, s2 = signal.generateSin(f_coluna, AMPLITUDE, DURACAO, FS)
    tone = s1 + s2

    # a soma pode chegar a 2; normaliza para [-1, 1] para não saturar a placa de som
    tone_play = tone / np.max(np.abs(tone))

    # opcional: salva o sinal gerado em arquivo
    wavfile.write("tecla_{}.wav".format(NUM if NUM != "#" else "hash"), FS,
                  (tone_play * 32767).astype(np.int16))

    print("Gerando Tom referente ao símbolo : {}".format(NUM))
    print("Frequências : {} + {}".format(f_linha, f_coluna))
    print("Executando as senoides (emitindo o som)")
    sd.play(tone_play, FS)
    # aguarda fim do audio
    sd.wait()

    print("Plotando")
    # sinal no tempo: apenas os primeiros 10 ms (alguns períodos)
    n = int(0.01 * FS)
    plt.figure()
    plt.plot(t[:n] * 1000, tone[:n])
    plt.title("Sinal emitido - tecla {} ({} Hz + {} Hz)".format(NUM, f_linha, f_coluna))
    plt.xlabel("Tempo (ms)")
    plt.ylabel("Amplitude")
    plt.grid(True)

    signal.plotFFT(tone, FS, "Fourier do sinal emitido - tecla {}".format(NUM))
    plt.xlim(0, 2500)
    # Exibe gráficos
    plt.show()


if __name__ == "__main__":
    main()
