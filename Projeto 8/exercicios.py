# Projeto 8 - Exercícios 1 a 7 (modulação AM e modulação digital)
import numpy as np
import matplotlib.pyplot as plt
from projeto8_am import FS, passa_baixa, carrega_audio, toca, energia_fora, plota_fft


def exercicio1():
    """Ex1: somar informação (2 kHz) e portadora (15 kHz) NÃO é modulação."""
    t = np.arange(0, 1, 1 / FS)
    m = np.sin(2 * np.pi * 2000 * t)                    # informação
    c = np.sin(2 * np.pi * 15000 * t)                   # portadora
    # A FFT da soma tem um pico em 2 kHz e outro em 15 kHz: o de 2 kHz está fora
    # da banda permitida (12-18 kHz), então esse sinal não pode ser transmitido.
    plota_fft([m + c], ["m(t) + C(t): o pico de 2 kHz fica fora da banda 12-18 kHz"],
              "Exercício 1", faixas=[(12000, 18000)])
    plt.show()


def exercicio3():
    """Ex3: multiplicar informação (2 kHz) pela portadora (15 kHz) = AM."""
    t = np.arange(0, 2, 1 / FS)                         # 2 s, como pede o enunciado
    s = np.sin(2 * np.pi * 2000 * t) * np.sin(2 * np.pi * 15000 * t)   # ponto a ponto
    # sen(a)·sen(b) = [cos(a-b) - cos(a+b)] / 2 -> picos só em 13 kHz e 17 kHz
    plota_fft([s], ["m(t) · C(t): picos em 15 ± 2 kHz, dentro da banda mínima 13-17 kHz"],
              "Exercício 3", faixas=[(13000, 17000)])
    plt.show()


def exercicio5():
    """Ex5: modula um áudio em 16 kHz dentro de 14-18 kHz e demodula de volta."""
    audio = carrega_audio(1)                            # mesmo áudio 1 do projeto
    t = np.arange(len(audio)) / FS
    c = np.cos(2 * np.pi * 16000 * t)                   # 2) portadora com o mesmo nº de pontos

    # 3) a faixa 14-18 kHz tem 2 kHz para cada lado da portadora, mas a voz vai bem além
    # disso (ver FFT do original). Então tratamos o sinal antes: passa-baixa em 1,8 kHz
    # (2 kHz menos uma margem para a queda do filtro) e só depois multiplicamos.
    m = passa_baixa(audio, 1800)
    s = m * c
    print(f"Ex5 - energia do modulado fora de 14-18 kHz: "
          f"{10 * np.log10(energia_fora(s, 14000, 18000)):.1f} dB")

    # 6) demodulação síncrona: multiplica pela mesma portadora e passa-baixa
    d = 2 * passa_baixa(s * c, 1800)

    plota_fft([audio, s, d],                            # 1), 4) e 7)
              ["Áudio original", "Modulado em AM (portadora 16 kHz)", "Demodulado"],
              "Exercício 5", faixas=[(14000, 18000)])
    plt.show()
    toca(audio, "original")                             # 1)
    toca(s, "modulado")                                 # 5) agudo/chiado: só tem 14-18 kHz
    toca(d, "demodulado")                               # 8)


def respostas():
    # Ex2: o produto só tem fc - fm e fc + fm -> banda mínima de 13 kHz a 17 kHz (largura 2·fm = 4 kHz)
    fc, fm = 15000, 2000
    print(f"Ex2 - banda mínima: {fc - fm} a {fc + fm} Hz (largura {2 * fm} Hz)")

    # Ex4: com portadora de 15 kHz e banda 14-16 kHz, a informação só pode ter até 1 kHz
    # (fc ± fm tem que caber). Solução: passar m(t) num passa-baixa de 1 kHz antes de modular,
    # aceitando perder o conteúdo de 1 a 2 kHz (o áudio fica mais "abafado", mas inteligível).
    print("Ex4 - filtrar m(t) com passa-baixa de 1 kHz antes de modular: 15 kHz ± 1 kHz = 14-16 kHz")

    # Ex6: 64-QAM -> log2(64) = 6 bits por símbolo; 1 símbolo a cada 2 períodos de 2,4 GHz
    simbolos = 2.4e9 / 2
    print(f"Ex6 - {simbolos:.1e} símbolos/s x 6 bits = {6 * simbolos / 1e9:.1f} Gbit/s")

    # Ex7: 256-QAM -> 8 bits por símbolo; 1 símbolo a cada 10 períodos
    taxa = 8 * 2.4e9 / 10                               # bit/s
    print(f"Ex7 - taxa = {taxa / 1e9:.2f} Gbit/s -> 480 MB = {480e6 * 8 / 1e9:.2f} Gbit "
          f"-> {480e6 * 8 / taxa:.1f} s  (com MB = 2^20 bytes: {480 * 2**20 * 8 / taxa:.2f} s)")


if __name__ == "__main__":
    respostas()                                         # Ex2, Ex4, Ex6, Ex7 (só prints)
    exercicio1()
    exercicio3()
    exercicio5()
