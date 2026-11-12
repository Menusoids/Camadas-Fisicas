# Projeto 8 - Parte 2: chat entre 2 computadores com modulação digital PSK pelo áudio
#
# Uso (os dois lados precisam usar a mesma --fc e a mesma --taxa):
#   python psk_chat.py rx                 -> receptor: escuta o microfone e escreve as frases
#   python psk_chat.py tx                 -> emissor: digita a frase, Enter, sai no alto-falante
#   python psk_chat.py fft                -> FFT do emitido.wav / recebido.wav + banda necessária
#   python psk_chat.py analise            -> FFT variando a taxa e a portadora (comparação)
#   python psk_chat.py teste              -> canal simulado (sem microfone): ruído, atraso, desvio
#   opções: --fc 4000 --taxa 100 --plot -v
#
# Modulação: BPSK diferencial (DBPSK). Cada bit dura 1/taxa segundos e é um trecho de
# senoide na frequência da portadora; a informação está na FASE:
#   bit 0 -> a fase continua igual à do bit anterior
#   bit 1 -> a fase inverte (soma 180°)
# Por que diferencial: os dois computadores têm relógios diferentes, então a portadora
# "recriada" no receptor nunca tem exatamente a mesma fase/frequência da do emissor.
# Comparando cada bit com o anterior não precisamos saber a fase absoluta.
import argparse
import collections
import queue
import os
import numpy as np
import matplotlib.pyplot as plt
from scipy.io import wavfile
from scipy.signal import butter, sosfiltfilt

FS = 44100 # amostrar por segundo 
PASTA = os.path.dirname(os.path.abspath(__file__))

# Quadro transmitido:  AQUECIMENTO | SYNC | tamanho (8 bits) | texto (8 bits/byte) | checksum (8 bits)
AQUECIMENTO = [0] * 8           # portadora com fase constante: dá tempo do receptor "acordar"
SYNC = [1, 1, 1, 1, 1, 0, 0, 1, 1, 0, 1, 0, 1,     # código de Barker 13 + 19 bits fixos:
        0, 0, 1, 0, 1, 1, 1, 0, 1, 1, 0, 0, 0,     # palavra de sincronismo que os dois lados
        1, 0, 1, 0, 0, 1]                          # conhecem; o receptor procura por ela
FINAL = [0] * 4                 # alguns bits a mais para o último bit não ser cortado


# ---------------------------------------------------------------- quadro (bytes <-> bits)
def bytes_para_bits(dados):
    """Cada byte vira 8 bits, do mais significativo para o menos (ex.: 'A' = 65 = 01000001)."""
    return [(b >> (7 - i)) & 1 for b in dados for i in range(8)]

# O modulador só trabalha em bits então os dados que estão em bytes precisam ser convertidos para bits. 
# ai ele faz a modulação e depois o receptor pega os bits e transforma em bytes de novo.

def bits_para_bytes(bits): #junta 8 bits em um byte
    return bytes(int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits) - 7, 8))


def monta_quadro(texto):
    dados = texto.encode("utf-8")[:255]          # transforma o texto em bytes
    checksum = sum(dados) % 256                  # calcula o checksum

    #                           isso aqui fala quantos bytes esperar
    return AQUECIMENTO + SYNC + bytes_para_bits([len(dados)]) + bytes_para_bits(dados) \
        + bytes_para_bits([checksum]) + FINAL #junta tudo em uma lista de bits


# ---------------------------------------------------------------- emissor
def amostras_por_bit(taxa): # quantas amostras por bit
    return round(FS / taxa)                      # 100 bit/s a 44100 Hz (frequencia de desenho da onda(pontos que ele desenha por segundo)) -> 441 amostras por bit
  

def modula(bits, fc, taxa):
    """PSK: s(t) = sen(2π·fc·t + fase), com fase ∈ {0, π} trocando a cada bit 1."""
    sps = amostras_por_bit(taxa)
    fases = np.concatenate([[0], np.cumsum(bits) % 2]) * np.pi   # faz a soma acumulada dos bits, quando aparece um 1 ele soma pi na fase, 0 fica igual
    fase_t = np.repeat(fases, sps)                               # faz o bit durar 441 amostras
    t = np.arange(len(fase_t)) / FS                              # monta uma lista de instante de tempo pra cada amostra
    s = np.sin(2 * np.pi * fc * t + fase_t)                      # monta a onda, fazendo 2pi * fc * t + fase (faz a senoide legal)
    rampa = np.linspace(0, 1, int(0.005 * FS))                   # cria uma rampa que vai de 0 a 1 em 5 ms
    s[:len(rampa)] *= rampa
    s[-len(rampa):] *= rampa[::-1]
    # faz um fade in e fade out no final pra evitar estalos no início e no fim do sinal. cai no aquicimento e no final.
    return s


# ---------------------------------------------------------------- receptor
def passa_baixa(x, fc, ordem=5):  # faz o filtro
    sos = butter(ordem, fc, btype="low", fs=FS, output="sos")
    return sosfiltfilt(sos, x.real) + 1j * sosfiltfilt(sos, x.imag)


def banda_base(x, fc, taxa):
    """Demodulação: traz a portadora para 0 Hz e integra cada bit.

    Multiplicar por cos e por sen da portadora (= por e^{-j2πfc·t}) é igual à demodulação AM
    da parte 1: aparece a informação em 0 Hz e um termo em 2·fc, que o passa-baixa remove.
    Usamos cos (I) e sen (Q) juntos porque a fase da portadora do receptor é desconhecida:
    o resultado é um número complexo cujo ÂNGULO é a fase do bit.
    Depois somamos as amostras de um bit inteiro (integrador): y[n] = soma de z nos últimos sps
    pontos. Isso reduz o ruído; no fim de cada bit y[n] "aponta" para a fase daquele bit.
    """
    t = np.arange(len(x)) / FS
    z = passa_baixa(x * np.exp(-2j * np.pi * fc * t), 2 * taxa)  #multiplica por fc e passa o filtro pra tirar a parte inutil
    sps = amostras_por_bit(taxa)
    return np.convolve(z, np.ones(sps))[:len(z)]


def acha_sync(y, sps):  # procura o sync no sinal recebido,
    """Procura a palavra SYNC. Retorna (posição do fim do 1º bit do SYNC, qualidade 0..1).

    d[n] = y[n]·conj(y[n-sps]) compara a fase do bit que termina em n com a do bit anterior:
    parte real > 0 -> mesma fase (bit 0); < 0 -> fase invertida (bit 1).
    Correlacionamos isso com o SYNC esperado em todas as posições e ficamos com o máximo.
    """
    d = np.real(y[sps:] * np.conj(y[:-sps]))
    a = np.abs(y[sps:] * np.conj(y[:-sps]))
    esperado = 1 - 2 * np.array(SYNC)                 # bit 0 -> +1, bit 1 -> -1
    n = len(d) - (len(SYNC) - 1) * sps
    if n <= 0:
        return None, 0.0
    corr, norma = np.zeros(n), np.zeros(n)
    for k, e in enumerate(esperado):
        corr += e * d[k * sps:k * sps + n]
        norma += a[k * sps:k * sps + n]
    i = int(np.argmax(corr))
    return i + sps, corr[i] / (norma[i] + 1e-20) # retorna a posição do fim do primeiro bit de Sync


def demodula(x, fc, taxa, verbose=False): # transforma o audio em bits, sintoniza, desmodula e retorna o texto
    """Áudio recebido -> texto. Levanta ValueError se não achar mensagem válida."""
    sps = amostras_por_bit(taxa)
    y = banda_base(x, fc, taxa) # lista de valores a ser desmodulada
    inicio, qualidade = acha_sync(y, sps)
    if verbose:
        print(f"  SYNC encontrado na amostra {inicio} ({inicio / FS:.3f} s), "
              f"qualidade {qualidade:.2f} (1 = perfeito)")
    if inicio is None or qualidade < 0.5:
        raise ValueError(f"palavra de sincronismo não encontrada (qualidade {qualidade:.2f})")

    def bit(k):                       # o que transforma audio em bit, comparando a fase do bit atual com a do anterior (não faz em bytes, vai bit por bit)
        n = inicio + k * sps
        if n >= len(y):
            raise ValueError("áudio terminou antes da mensagem")
        return int(np.real(y[n] * np.conj(y[n - sps])) < 0)   # Linha que pega a fase do bit atual e compara com o antigo, quando da perto de 1 ele coloca o bit como 1. o resto da zero

    k = len(SYNC)  # começa depois do SYNC
    tamanho = bits_para_bytes([bit(k + i) for i in range(8)])[0] # lê o tamanho do texto (em bytes) que está nos 8 bits seguintes ao SYNC
    k += 8 # pula os 8 bits do tamanho
    dados = bits_para_bytes([bit(k + i) for i in range(8 * tamanho)]) # lê todos os bits do texto em uma tacada só e transforma em bytes
    k += 8 * tamanho #pula os bits do texto
    checksum = bits_para_bytes([bit(k + i) for i in range(8)])[0] # lê os 8 bits do checksum
    if verbose:
        print(f"  tamanho = {tamanho} bytes, checksum recebido = {checksum}, "
              f"calculado = {sum(dados) % 256}")
        print(f"  bytes = {list(dados)}")
    if checksum != sum(dados) % 256:
        raise ValueError(f"checksum não confere, chegou: {dados.decode('utf-8', 'replace')!r}") #fala se deu errado
    return dados.decode("utf-8", "replace") # retorna o texto decodificado


# ---------------------------------------------------------------- FFT e banda
def fft(x):
    X = np.abs(np.fft.rfft(x)) / len(x)
    return np.fft.rfftfreq(len(x), 1 / FS), X


def banda_ocupada(x, fc, fracao=0.9):
    """Menor faixa simétrica fc ± B que contém `fracao` da energia do sinal (medido pela FFT)."""
    f, X = fft(x)
    energia = X ** 2
    total = energia.sum()
    for B in np.arange(1, FS / 2, 1.0):
        if energia[(f >= fc - B) & (f <= fc + B)].sum() >= fracao * total:
            return 2 * B
    return FS / 2


def descreve_banda(x, fc, taxa):
    # Bits retangulares: o espectro de cada bit é um sinc centrado em fc, com zeros em
    # fc ± taxa, fc ± 2·taxa... -> o lóbulo principal (onde está quase toda a energia) vai de
    # fc - taxa a fc + taxa: banda necessária ≈ 2 x taxa.
    print(f"  fc = {fc} Hz, taxa = {taxa} bit/s")
    print(f"  banda teórica (lóbulo principal): {fc - taxa} a {fc + taxa} Hz = {2 * taxa} Hz")
    print(f"  banda medida com 90% da energia: {banda_ocupada(x, fc, 0.9):.0f} Hz, "
          f"com 99%: {banda_ocupada(x, fc, 0.99):.0f} Hz")


def plota(ax, x, fc, taxa, titulo, zoom=True):
    f, X = fft(x)
    ax.axvspan(fc - taxa, fc + taxa, color="C1", alpha=0.2, label=f"fc ± taxa ({2 * taxa} Hz)")
    ax.plot(f, X, linewidth=0.7)
    if zoom:
        ax.set_xlim(max(0, fc - 6 * taxa), fc + 6 * taxa)
    ax.set_title(titulo)
    ax.set_ylabel("|X(f)|")
    ax.legend(loc="upper right")


# ---------------------------------------------------------------- modos
def salva(nome, x):
    wavfile.write(os.path.join(PASTA, nome), FS, (x / np.max(np.abs(x)) * 32767).astype(np.int16))


def le(nome):
    fs, x = wavfile.read(os.path.join(PASTA, nome))
    if x.ndim > 1:
        x = x[:, 0]
    return x.astype(float) / 32768


def emissor(args):
    import sounddevice as sd
    print(f"EMISSOR PSK - portadora {args.fc} Hz, {args.taxa} bit/s. Digite e tecle Enter (Ctrl+C sai).")
    while True:
        try:
            texto = input("> ")
        except (EOFError, KeyboardInterrupt):
            break
        if not texto:
            continue
        bits = monta_quadro(texto)
        s = modula(bits, args.fc, args.taxa)
        print(f"  {len(bits)} bits -> {len(s) / FS:.2f} s de áudio")
        if args.verbose:
            print(f"  bits do quadro: {''.join(map(str, bits))}")
            descreve_banda(s, args.fc, args.taxa)
        salva("emitido.wav", s)
        sd.play(0.8 * s, FS)
        sd.wait()
        if args.plot:
            _, ax = plt.subplots(2, 1, figsize=(9, 6))
            plota(ax[0], s, args.fc, args.taxa, "FFT do sinal emitido", zoom=False)
            plota(ax[1], s, args.fc, args.taxa, "FFT do sinal emitido (zoom na portadora)")
            ax[1].set_xlabel("Frequência [Hz]")
            plt.tight_layout()
            plt.show()


def potencia_na_banda(bloco, fc, taxa): # faz a fft do silencio em um bloco para pegar a energia do ruido
    f, X = fft(bloco)
    return np.sum(X[(f > fc - 2 * taxa) & (f < fc + 2 * taxa)] ** 2)


def receptor(args):
    """Escuta o microfone sem parar. Quando a energia perto da portadora sobe, começa a gravar;
    quando volta ao nível do ruído, demodula o trecho gravado e escreve a frase."""
    import sounddevice as sd
    bloco_n = int(0.05 * FS)                               # blocos de 50 ms
    fila = queue.Queue()
    stream = sd.InputStream(samplerate=FS, channels=1, blocksize=bloco_n,
                            callback=lambda dados, *_: fila.put(dados[:, 0].copy()))
    with stream:
        print("Calibrando o ruído (fique em silêncio 1 s)...")
        ruido = np.median([potencia_na_banda(fila.get(), args.fc, args.taxa) for _ in range(20)])
        limiar = 10 * ruido + 1e-12                       # calcula o limiar de quando começar a gravar
        print(f"RECEPTOR PSK - portadora {args.fc} Hz, {args.taxa} bit/s. Escutando... (Ctrl+C sai)")
        if args.verbose:
            print(f"  ruído na banda = {ruido:.2e}, limiar = {limiar:.2e}")
        antes = collections.deque(maxlen=6)                # 300 ms antes do disparo
        gravando, trecho, silencio = False, [], 0
        try:
            while True:
                bloco = fila.get()
                alto = potencia_na_banda(bloco, args.fc, args.taxa) > limiar # ativa agravação
                if not gravando:
                    antes.append(bloco)
                    if alto:
                        gravando, trecho, silencio = True, list(antes), 0
                        print("  (recebendo...)")
                    continue
                trecho.append(bloco)
                silencio = 0 if alto else silencio + 1
                if silencio >= 6:                          # 300 ms sem sinal: acabou a mensagem
                    gravando = False
                    x = np.concatenate(trecho)
                    salva("recebido.wav", x)
                    try:
                        print(f"[recebido] {demodula(x, args.fc, args.taxa, args.verbose)}")
                    except ValueError as erro:
                        print(f"[erro] {erro}")
                    if args.plot:
                        _, ax = plt.subplots(2, 1, figsize=(9, 6))
                        plota(ax[0], x, args.fc, args.taxa, "FFT do sinal recebido", zoom=False)
                        plota(ax[1], x, args.fc, args.taxa, "FFT do sinal recebido (zoom na portadora)")
                        ax[1].set_xlabel("Frequência [Hz]")
                        plt.tight_layout()
                        plt.show()
                        while not fila.empty():            # descarta o que chegou com o gráfico aberto
                            fila.get()
                    antes.clear()
        except KeyboardInterrupt:
            pass


def mostra_fft(args):
    """FFT do último sinal emitido e do último recebido (os .wav salvos por tx e rx)."""
    arquivos = [a for a in ("emitido.wav", "recebido.wav") if os.path.exists(os.path.join(PASTA, a))]
    if not arquivos:
        print("Nenhum emitido.wav / recebido.wav nesta pasta: rode tx ou rx antes.")
        return
    _, ax = plt.subplots(len(arquivos), 1, figsize=(9, 3 * len(arquivos)), squeeze=False)
    for a, eixo in zip(arquivos, ax[:, 0]):
        x = le(a)
        print(a)
        descreve_banda(x, args.fc, args.taxa)
        plota(eixo, x, args.fc, args.taxa, f"FFT de {a}")
    ax[-1, 0].set_xlabel("Frequência [Hz]")
    plt.tight_layout()
    plt.show()


def analise(args):
    """Mesma frase com várias taxas (portadora fixa) e várias portadoras (taxa fixa)."""
    texto = "Camada Fisica"
    taxas = [50, 100, 200, 400]
    portadoras = [2000, 4000, 6000]
    _, ax = plt.subplots(len(taxas), 1, figsize=(9, 2.2 * len(taxas)), sharex=True)
    print(f"Variando a taxa (portadora {args.fc} Hz):")
    for taxa, eixo in zip(taxas, ax):
        s = modula(monta_quadro(texto), args.fc, taxa)
        descreve_banda(s, args.fc, taxa)
        plota(eixo, s, args.fc, taxa, f"taxa = {taxa} bit/s")
        eixo.set_xlim(args.fc - 1500, args.fc + 1500)
    ax[-1].set_xlabel("Frequência [Hz]")
    plt.tight_layout()

    _, ax = plt.subplots(len(portadoras), 1, figsize=(9, 2.2 * len(portadoras)), sharex=True)
    print(f"Variando a portadora (taxa {args.taxa} bit/s):")
    for fc, eixo in zip(portadoras, ax):
        s = modula(monta_quadro(texto), fc, args.taxa)
        descreve_banda(s, fc, args.taxa)
        plota(eixo, s, fc, args.taxa, f"portadora = {fc} Hz", zoom=False)
        eixo.set_xlim(0, 8000)
    ax[-1].set_xlabel("Frequência [Hz]")
    plt.tight_layout()
    plt.show()


def teste(args):
    """Canal simulado: o que o microfone faria com o sinal (sem precisar de 2 computadores)."""
    rng = np.random.default_rng(0)
    frases = ["oi", "Olá, tudo bem? Camada Física 2026!", "x" * 255]
    for frase in frases:
        s = modula(monta_quadro(frase), args.fc, args.taxa)
        n = np.arange(len(s))
        # relógios diferentes (200 ppm): a portadora chega com frequência um pouco diferente
        # e cada bit fica um pouco mais curto -> testa se o DBPSK aguenta sem sincronizar fase
        s = np.interp(n * (1 + 200e-6), n, s)
        s = 0.05 * np.concatenate([np.zeros(rng.integers(1000, 20000)), s, np.zeros(5000)])
        s += 0.02 * rng.standard_normal(len(s))                # ruído (SNR ≈ 6 dB no total)
        recebido = demodula(s, args.fc, args.taxa, args.verbose)
        assert recebido == frase[:255], (recebido, frase)
        print(f"ok: {recebido[:40]!r}{'...' if len(recebido) > 40 else ''}")
    print("teste ok")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Chat por áudio com modulação PSK")
    p.add_argument("modo", choices=["tx", "rx", "fft", "analise", "teste"])
    p.add_argument("--fc", type=float, default=4000, help="portadora em Hz (2000 a 6000)")
    p.add_argument("--taxa", type=int, default=100, help="taxa em bit/s")
    p.add_argument("--plot", action="store_true", help="mostra a FFT a cada mensagem")
    p.add_argument("-v", "--verbose", action="store_true", help="imprime bits, sync, banda...")
    args = p.parse_args()
    {"tx": emissor, "rx": receptor, "fft": mostra_fft, "analise": analise, "teste": teste}[args.modo](args)
