from enlace import *
import datagrama as dg
import os
import time

serialName = "COM5"

PASTA        = "arquivos"
TIMEOUT_ACK  = 2.0
TIMEOUT_LOG  = 5
MSG_START    = "entendido. Vou iniciar a transmissao simultanea dos arquivos escolhidos"

# --- SIMULACAO DE ERROS PARA A APRESENTACAO (mude aqui antes de rodar) -----
# Ligue so uma flag por vez pra mostrar cada cenario pedido no enunciado.
SIMULA_ERRO_ORDEM = False   # troca a ordem dos 2 primeiros pacotes do 1o arquivo
SIMULA_ERRO_CRC   = False   # corrompe de proposito o 1o pacote de dados enviado
_jaCorrompeuCRC    = [False]   # lista pra poder alterar de dentro de uma funcao sem 'global'



class Abortado(Exception):
    pass


def listaArquivos():
    nomes = sorted(f for f in os.listdir(PASTA) if os.path.isfile(os.path.join(PASTA, f)))
    if len(nomes) < 2:
        raise RuntimeError("coloque pelo menos 2 arquivos na pasta {}/".format(PASTA))
    return nomes


def corta(texto):
    """As mensagens de terminal tambem viajam no payload, que tem teto de 100 B."""
    return texto.encode("utf-8")[:dg.PAYLOAD_MAX]


def handshake(canal):
    """Responde ao HELLO, oferece a lista e vai registrando as escolhas.
    Devolve a lista de nomes escolhidos, na ordem em que foram pedidos.
    """
    nomes = listaArquivos()
    print("Arquivos disponiveis: {}".format(", ".join(nomes)))
    print("\nAguardando o client...\n")

    while True:
        p = canal.recebe()
        if p.tipo == dg.HELLO:
            break
        print("<- ignorando {} antes do handshake".format(dg.descreve(p)))

    print("<- HELLO do client. Estou vivo, enviando a lista de arquivos.")
    enviaLista(canal, nomes)

    escolhidos = []
    while True:
        p = canal.recebe()

        if not p.ok:
            print("<- {} com checksum invalido, ignorando".format(dg.descreve(p)))
            continue

        if p.tipo == dg.HELLO:
            print("<- client quer ver a lista de novo")
            enviaLista(canal, nomes)

        elif p.tipo == dg.PEDIDO:
            nome = p.payload.decode("utf-8", errors="ignore")
            print("<- PEDIDO: {}".format(nome))
            if nome not in nomes:
                msg = "arquivo {} nao existe aqui, escolha da lista".format(nome)
            elif nome in escolhidos:
                msg = "arquivo {} ja estava escolhido, deseja adicionar outro arquivo?".format(nome)
            else:
                escolhidos.append(nome)
                if len(escolhidos) == 1:
                    msg = "arquivo {} escolhido, deseja adicionar outro arquivo?".format(escolhidos[0])
                else:
                    msg = "arquivos {} e {} escolhidos, deseja adicionar outro arquivo?".format(
                        ", ".join(escolhidos[:-1]), escolhidos[-1])
            print("-> {}".format(msg))
            canal.envia(dg.RESPOSTA, payload=corta(msg))

        elif p.tipo == dg.START:
            escolha = finaliza(canal, escolhidos)
            if escolha is not None:
                return escolha

        elif p.tipo == dg.ABORT:
            raise Abortado()

        else:
            print("<- ignorando {}".format(dg.descreve(p)))


def finaliza(canal, escolhidos):
    if len(escolhidos) < 2:
        msg = "escolha pelo menos 2 arquivos antes de comecar"
        print("-> {}".format(msg))
        canal.envia(dg.RESPOSTA, flag=1, payload=corta(msg))
        return None
    print("<- START")
    print("-> {}".format(MSG_START))
    canal.envia(dg.RESPOSTA, payload=corta(MSG_START))
    return escolhidos


def enviaLista(canal, nomes):
    """Um nome por pacote: o payload tem teto de 100 B e a lista inteira nao caberia."""
    for i, nome in enumerate(nomes):
        canal.envia(dg.LISTA, num=i, total=len(nomes), payload=corta(nome))
        print("-> LISTA {}/{}: {}".format(i + 1, len(nomes), nome))
        time.sleep(0.05)


def esperaResume(canal, estado):
    print("\n||| PAUSADO pelo client. Aguardando a tecla de continuar...\n")
    while True:
        p = canal.recebe(timeout=1)
        if p is None:
            continue
        if p.tipo == dg.RESUME:
            estado["pausado"] = False
            print("\n>>> RESUME recebido, retomando a transmissao\n")
            return
        if p.tipo == dg.ABORT:
            raise Abortado()
        print("   (pausado, ignorando {})".format(dg.descreve(p)))


def confirmaPacote(canal, pacote, idArq, num, estado,corromperPrimeiroEnvio=False):
    """Stop and wait: reenvia o mesmo pacote ate o client confirmar aquele numero."""

    envio = pacote
    if corromperPrimeiroEnvio:
        malformado = bytearray(pacote)
        malformado[dg.HEAD_LEN] ^= 0xFF   # inverte o 1o byte do payload de proposito
        envio = bytes(malformado)
        print("   >>> (SIMULACAO) corrompendo de proposito o pacote {} do arquivo {}".format(num + 1, idArq))
    canal.enviaBytes(envio)
    tentativas = 0
    while True:
        p = canal.recebe(timeout=TIMEOUT_ACK)

        if p is None:
            tentativas += 1
            estado["retransmissoes"] += 1
            if tentativas % TIMEOUT_LOG == 0:
                print("   !!! {} tentativas sem resposta - o fio entre os Arduinos esta conectado?"
                      .format(tentativas))
            else:
                print("   ... time out esperando ACK do arquivo {} pacote {}, retransmitindo"
                      .format(idArq, num + 1))
            canal.enviaBytes(pacote)
            continue

        if p.tipo == dg.ACK and p.id == idArq and p.num == num:
            print("<- ACK   arq {} pacote {}".format(idArq, num + 1))
            return

        if p.tipo == dg.NACK:
            estado["retransmissoes"] += 1
            print("<- NACK  arq {} pacote {} chegou corrompido, retransmitindo".format(idArq, num + 1))
            canal.enviaBytes(pacote)
            continue

        if p.tipo == dg.PAUSE:
            estado["pausado"] = True
            print("<- PAUSE do client")
            esperaResume(canal, estado)
            canal.enviaBytes(pacote)
            continue

        if p.tipo == dg.ABORT:
            raise Abortado()

        if p.tipo == dg.START:
            print("<- START repetido (a RESPOSTA se perdeu), reenviando a confirmacao")
            canal.envia(dg.RESPOSTA, payload=corta(MSG_START))
            continue

        if p.tipo == dg.ACK:
            print("   (ACK repetido de arq {} pacote {}, ignorando)".format(p.id, p.num + 1))
            continue

        print("   (ignorando {})".format(dg.descreve(p)))


def transmite(canal, escolhidos, estado):
    arquivos = []
    for i, nome in enumerate(escolhidos, start=1):
        with open(os.path.join(PASTA, nome), "rb") as f:
            dados = f.read()
        partes = dg.fragmenta(dados)
        ordem = list(range(len(partes)))
        if SIMULA_ERRO_ORDEM and i == 1 and len(ordem) >= 2:
            ordem[0], ordem[1] = ordem[1], ordem[0]   # manda o pacote 2 antes do 1
            print("   >>> (SIMULACAO) invertendo a ordem dos 2 primeiros pacotes do arquivo {}".format(i))
        arquivos.append({"id": i, "nome": nome, "tam": len(dados), "partes": partes, "ordem": ordem, "prox": 0})
        print("  arquivo {}: {:<20} {:>7} bytes -> {} pacotes".format(i, nome, len(dados), len(partes)))

    print("\n=== INICIANDO TRANSMISSAO SIMULTANEA ===\n")
    t0 = time.time()
    ativos = list(arquivos)

    while ativos:
        for arq in list(ativos):
            if estado["pausado"]:
                esperaResume(canal, estado)

            total = len(arq["partes"])
            num   = arq["ordem"][arq["prox"]] 
            dados = arq["partes"][num]
            pacote = dg.monta(dg.DADOS, idArq=arq["id"], num=num, total=total, payload=dados)
            print("-> DADOS arq {} ({}) pacote {}/{} - {} B de payload"
                  .format(arq["id"], arq["nome"], num + 1, total, len(dados)))

            corromper = SIMULA_ERRO_CRC and not _jaCorrompeuCRC[0]
            if corromper:
                _jaCorrompeuCRC[0] = True
            confirmaPacote(canal, pacote, arq["id"], num, estado, corromperPrimeiroEnvio=corromper)
            arq["prox"] += 1


            if arq["prox"] == total:
                print("=== arquivo {} ({}) enviado por completo, {} pacotes ==="
                      .format(arq["id"], arq["nome"], total))
                confirmaPacote(canal, dg.monta(dg.FIM, idArq=arq["id"], num=total, total=total),
                               arq["id"], total, estado)
                ativos.remove(arq)
                if ativos:
                    print("    ainda em transmissao: {}\n".format(
                        ", ".join(a["nome"] for a in ativos)))

    return arquivos, time.time() - t0


def resumo(arquivos, dt, estado, canal):
    print("\n================ RESUMO DA TRANSMISSAO (SERVER) ================")
    for arq in arquivos:
        print("  {:<20} {:>7} bytes   {:>4} pacotes".format(arq["nome"], arq["tam"], len(arq["partes"])))
    totalBytes = sum(a["tam"] for a in arquivos)
    totalPct   = sum(len(a["partes"]) for a in arquivos)
    overhead   = (totalPct * dg.PACOTE_MAX) / totalBytes if totalBytes else 0
    print("  " + "-" * 58)
    print("  {:<20} {:>7} bytes   {:>4} pacotes".format("TOTAL", totalBytes, totalPct))
    print("  tempo: {:.1f} s   ({:.0f} bytes/s de dado util)".format(dt, totalBytes / dt if dt else 0))
    print("  pacotes enviados: {}   retransmissoes: {}".format(canal.enviados, estado["retransmissoes"]))
    print("  overhead maximo do protocolo: {:.2f}x ({} B de head+eop por pacote)"
          .format(overhead, dg.HEAD_LEN + len(dg.EOP)))
    print("================================================================")


def main():
    com1 = None
    estado = {"pausado": False, "retransmissoes": 0}
    try:
        com1 = enlace(serialName)
        com1.enable()
        com1.fisica.flush()
        print("Server aberto em {}".format(serialName))

        canal = dg.Canal(com1, "server")

        escolhidos = handshake(canal)
        arquivos, dt = transmite(canal, escolhidos, estado)
        resumo(arquivos, dt, estado, canal)

    except Abortado:
        print("\n!!! ABORT recebido do client. Transmissao cancelada.")
    except Exception as erro:
        print("ops! :-\\")
        print(erro)
    finally:
        if com1 is not None:
            com1.disable()
        print("-------------------------")
        print("Comunicacao encerrada")


if __name__ == "__main__":
    main()
