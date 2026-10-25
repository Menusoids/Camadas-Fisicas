# Projeto 7 - Exercícios 1 a 6 (filtros digitais)
import numpy as np
import sounddevice as sd
import matplotlib.pyplot as plt
from scipy.signal import butter, iirpeak, iirnotch, freqz

FS = 44100  # frequência de amostragem pedida no enunciado (Hz)


def fft(sinal, fs):
    """Calcula o espectro (módulo da FFT) de um sinal real."""
    # rfft devolve só as frequências positivas (o sinal é real, o resto é espelho)
    # dividimos por len(sinal) para a altura dos picos não depender da duração
    X = np.abs(np.fft.rfft(sinal)) / len(sinal)
    # eixo de frequências correspondente a cada ponto da FFT, de 0 até fs/2
    f = np.fft.rfftfreq(len(sinal), 1 / fs)
    return f, X


def filtro_ordem2(x, b, a):
    """Equação de diferenças: y[k] = -a1 y[k-1] - a2 y[k-2] + b0 x[k] + b1 x[k-1] + b2 x[k-2]."""
    # G(Z) = (b0 Z² + b1 Z + b2) / (Z² + a1 Z + a2)
    # Passando o denominador para o outro lado, cada saída y[k] é uma combinação
    # das 2 saídas anteriores e das 3 entradas mais recentes. Os coeficientes a1 e a2
    # entram com sinal negativo porque estavam do lado de Y na equação.
    y = [0.0] * len(x)
    # começa em k = 2 porque precisa de x[k-2] e y[k-2]; y[0] e y[1] ficam 0
    for k in range(2, len(x)):
        y[k] = (-a[1] * y[k-1] - a[2] * y[k-2]
                + b[0] * x[k] + b[1] * x[k-1] + b[2] * x[k-2])
    return np.array(y)


def exercicio1():
    """Ex1: sinal com componentes acima de 500 Hz -> FFT -> passa-baixa -> FFT -> tocar."""
    # Gera 3 s de sinal: 200 Hz (abaixo do corte) + 1500 Hz e 3000 Hz (acima de 500 Hz)
    t = np.arange(0, 3, 1 / FS)
    x = (np.sin(2*np.pi*200*t) + np.sin(2*np.pi*1500*t)
         + np.sin(2*np.pi*3000*t)) / 3      # /3 deixa a amplitude entre -1 e 1

    # Coeficientes do passa-baixa Butterworth de 2ª ordem, corte em 500 Hz.
    # Wn é a frequência de corte normalizada pela de Nyquist (fs/2).
    # Saem os mesmos números do enunciado: b = [0.0012, 0.0024, 0.0012], a = [1, -1.8993, 0.9042]
    b, a = butter(N=2, Wn=500 / (FS / 2), btype="low")
    print("Ex1 - b =", b, " a =", a)
    # Aplica o filtro implementado na mão (equação de diferenças acima)
    y = filtro_ordem2(x, b, a)

    # Plota a FFT do original (3 picos) e do filtrado (1500 e 3000 Hz quase somem)
    plt.figure("Exercício 1", figsize=(9, 5))
    for i, (s, nome) in enumerate([(x, "original"), (y, "filtrado (passa-baixa 500 Hz)")]):
        f, X = fft(s, FS)
        plt.subplot(2, 1, i + 1)
        plt.plot(f, X)
        plt.xlim(0, 4000)                   # só a região que interessa
        plt.title(f"FFT do sinal {nome}")
        plt.ylabel("|X(f)|")
    plt.xlabel("Frequência [Hz]")
    plt.tight_layout()
    plt.show()                              # o áudio toca depois de fechar a janela

    # Toca os dois para comparar: o filtrado soa mais grave/abafado
    print("Tocando original..."); sd.play(x, FS); sd.wait()
    print("Tocando filtrado..."); sd.play(y, FS); sd.wait()


def exercicios_2_a_4():
    # Ex2: I_dB = 10 log(I / 1e-12), com 1e-12 W/m² sendo o limiar da audição
    #   audição: 10 log(1e-12 / 1e-12) = 0 dB  |  dor: 10 log(1 / 1e-12) = 120 dB
    print("Ex2 - audição:", 10*np.log10(1e-12 / 1e-12), "dB | dor:", 10*np.log10(1 / 1e-12), "dB")

    # Ex3: para tensão/amplitude usa-se 20 log(Vsaída / Ventrada) -> 20 log(10/20) ≈ -6 dB
    print("Ex3 - ganho:", round(20*np.log10(10 / 20), 2), "dB")

    # Ex4a: em vez de ler o Bode no olho, calculamos o ganho do mesmo filtro do Ex1.
    # As entradas são dadas em rad/s (50 sen(1e4 t) e 50 sen(1e3 t)),
    # então convertemos para Hz com f = w / 2π antes de chamar freqz.
    b, a = butter(N=2, Wn=500 / (FS / 2), btype="low")
    for w in [1e4, 1e3]:
        _, h = freqz(b, a, worN=[w / (2*np.pi)], fs=FS)   # h = G(e^jw) nessa frequência
        # amplitude de saída = amplitude de entrada (50) x |G|
        print(f"Ex4a - w = {w:.0f} rad/s: ganho {20*np.log10(abs(h[0])):.1f} dB, "
              f"amplitude de saída = {50*abs(h[0]):.1f}")

    # Ex4b: frequência de corte definida como o ponto de -6 dB.
    # Varremos de 1 a 5000 Hz e pegamos a frequência cujo ganho é mais próximo de -6 dB.
    f = np.linspace(1, 5000, 50000)
    _, h = freqz(b, a, worN=f, fs=FS)
    fc = f[np.argmin(np.abs(20*np.log10(np.abs(h)) + 6))]
    # -6 dB em amplitude: Vs/Ve = 10^(-6/20) ≈ 0,5 (a saída tem metade da amplitude)
    print(f"Ex4b - fc(-6 dB) = {fc:.0f} Hz = {2*np.pi*fc:.0f} rad/s, Vs/Ve = {10**(-6/20):.2f}")


def bode_q(projeta, titulo):
    """Ex5 e Ex6: Bode do filtro em 2 kHz para vários Q, para ver o efeito do fator de qualidade."""
    # projeta é iirpeak (passa-faixa, Ex5) ou iirnotch (rejeita-faixa, Ex6).
    # Q maior = faixa mais estreita em volta de 2 kHz (largura ≈ f0 / Q).
    plt.figure(titulo, figsize=(8, 4))
    for Q in [1, 5, 10, 30]:
        b, a = projeta(2000 / (FS / 2), Q)                # f0 normalizada por Nyquist
        w, h = freqz(b, a, worN=8000, fs=FS)              # resposta em frequência
        # w[1:] pula 0 Hz (log de 0 não existe); +1e-12 evita log(0) no fundo do notch
        plt.semilogx(w[1:], 20*np.log10(np.abs(h[1:]) + 1e-12), label=f"Q = {Q}")
    plt.title(titulo)
    plt.xlabel("Frequência [Hz]")
    plt.ylabel("Ganho [dB]")
    plt.ylim(-60, 5)
    plt.grid(which="both", linestyle="--", linewidth=0.5)
    plt.legend()
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    exercicios_2_a_4()                                    # Ex2, Ex3, Ex4a, Ex4b (só prints)
    exercicio1()                                          # Ex1 (gráfico + áudio)
    # Ex5 - Resposta: Q controla a largura da faixa que passa (largura ≈ f0/Q).
    # Q pequeno (1) deixa passar uma faixa larga em volta de 2 kHz; Q grande (30)
    # só deixa passar uma faixa bem estreita. O ganho em 2 kHz continua 0 dB,
    # o que muda é a seletividade do filtro.
    print("Ex5 - Q controla a largura da faixa: Q maior = faixa mais estreita em volta de f0 "
          "(largura ≈ f0/Q). O ganho em f0 continua 0 dB.")
    bode_q(iirpeak, "Ex5 - passa-faixa em 2 kHz")

    # Ex6 - Resposta: é o inverso do Ex5. Q controla a largura do "buraco":
    # Q alto remove só uma frequência bem estreita, Q baixo remove uma faixa larga.
    # Mudando f0, o buraco se desloca para a nova frequência central.
    # Utilidade: remover um ruído de frequência fixa sem estragar o resto do sinal,
    # por exemplo o zumbido de 60 Hz da rede elétrica em áudio/ECG ou um apito
    # de microfonia num show.
    print("Ex6 - Q controla a largura do 'buraco': Q maior = rejeita uma faixa mais estreita. "
          "Mudar f0 desloca o buraco. Utilidade: remover ruído de frequência fixa, "
          "ex.: zumbido de 60 Hz da rede elétrica ou microfonia.")
    bode_q(iirnotch, "Ex6 - rejeita-faixa em 2 kHz")
