# ============================================================================
# CLIENT - quem PEDE os arquivos. Roteiro do arquivo:
#   1) constantes e leitura de teclado     2) handshake HELLO/LISTA
#   3) pacotes de controle (PEDIDO/START)  4) menu de escolha dos arquivos
#   5) pausa/retomada pelo teclado         6) loop de recepcao (DADOS/ACK/FIM)
#   7) grava o arquivo                     8) resumo final e main()
# ============================================================================
from enlace import *
import datagrama as dg
import os
import sys
import time

# --- 1) CONFIGURACAO -------------------------------------------------------
serialName = "COM8"   # porta do Arduino do client

PASTA         = "recebidos"   # onde os arquivos recebidos sao gravados
TIMEOUT_CTRL  = 2.0           # espera por resposta de controle
TIMEOUT_DADOS = 3.0           # silencio ate avisar "cade o server?"
TENTATIVAS    = 8             # retransmissoes antes de desistir

TECLA_PAUSA   = "p"
TECLA_SEGUE   = "c"
TECLA_ABORTA  = "a"

try:
    import msvcrt
except ImportError:
    msvcrt = None
    import select


# le o teclado SEM travar o loop de recepcao (msvcrt no Windows, select no resto)
def tecla():
    """Tecla apertada desde a ultima chamada, ou None. Nao bloqueia."""
    if msvcrt is not None:
        if msvcrt.kbhit():
            return msvcrt.getch().decode("utf-8", errors="ignore").lower()
        return None
    pronto, _, _ = select.select([sys.stdin], [], [], 0)
    if pronto:
        linha = sys.stdin.readline().strip().lower()
        return linha[0] if linha else None
    return None


# excecao usada para sair de tudo quando o usuario aperta "a"
class Abortado(Exception):
    pass


# --- 2) HANDSHAKE ----------------------------------------------------------
# manda HELLO e monta a lista de nomes a partir dos varios pacotes LISTA.
# so retorna quando TODOS os pedacos da lista chegaram; senao reenvia o HELLO.
def pedeLista(canal):
    """HELLO -> o server responde com um pacote LISTA por arquivo disponivel."""
    for t in range(TENTATIVAS):
        print("-> HELLO: server, voce esta vivo? quais arquivos voce tem?")
        canal.envia(dg.HELLO)
        nomes = None
        while True:
            p = canal.recebe(timeout=TIMEOUT_CTRL)
            if p is None:
                break
            if p.tipo != dg.LISTA or not p.ok:
                continue
            if nomes is None:
                nomes = [None] * p.total
            if p.num < len(nomes):
                nomes[p.num] = p.payload.decode("utf-8", errors="ignore")
            if nomes and all(n is not None for n in nomes):
                return nomes
        print("... server calado, tentativa {}/{}".format(t + 2, TENTATIVAS))
    raise RuntimeError("o server nao respondeu ao handshake")


# --- 3) CONTROLE COM RETRANSMISSAO -----------------------------------------
# padrao "envia e espera RESPOSTA": se nao vier nada no prazo, reenvia.
# e isso que garante o protocolo mesmo com pacote perdido no fio.
def controle(canal, tipo, payload=b""):
    """Manda um pacote de controle e espera a RESPOSTA de texto do server."""
    for t in range(TENTATIVAS):
        canal.envia(tipo, payload=payload)
        prazo = time.time() + TIMEOUT_CTRL
        while time.time() < prazo:
            p = canal.recebe(timeout=TIMEOUT_CTRL)
            if p is None:
                break
            if p.tipo == dg.RESPOSTA and p.ok:
                return p
        print("... sem resposta, reenviando ({}/{})".format(t + 2, TENTATIVAS))
    raise RuntimeError("o server nao respondeu ao pacote de controle")


# --- 4) MENU: escolhe os arquivos, um PEDIDO por vez, e fecha com START ----
def escolheArquivos(canal):
    nomes = pedeLista(canal)
    escolhidos = []

    while True:
        print("\nArquivos disponiveis no server:")
        for i, nome in enumerate(nomes, start=1):
            marca = "  (ja escolhido)" if nome in escolhidos else ""
            print("   [{}] {}{}".format(i, nome, marca))

        escolha = input("Numero (ou nome) do arquivo que voce quer: ").strip()
        if escolha.isdigit() and 1 <= int(escolha) <= len(nomes):
            escolha = nomes[int(escolha) - 1]
        if escolha not in nomes:
            print("   nao entendi, escolha um da lista.")
            continue

        print("-> PEDIDO: {}".format(escolha))
        resp = controle(canal, dg.PEDIDO, payload=escolha.encode("utf-8"))
        print("<- server: \"{}\"".format(resp.payload.decode("utf-8", errors="ignore")))
        if escolha not in escolhidos:
            escolhidos.append(escolha)

        # o enunciado exige pelo menos 2 arquivos na mesma transmissao
        if len(escolhidos) < 2:
            print("   (o enunciado pede pelo menos 2 arquivos simultaneos)")
            outro = "s"
        else:
            outro = input("Deseja adicionar outro arquivo? (s/n): ").strip().lower()

        if outro.startswith("s"):
            print("-> pedindo a lista de novo")
            nomes = pedeLista(canal)
            continue

        # START = "acabei de pedir"; flag=1 na resposta significa recusa -> volta ao menu
        print("-> START: nao quero mais nenhum, pode comecar")
        resp = controle(canal, dg.START)
        print("<- server: \"{}\"".format(resp.payload.decode("utf-8", errors="ignore")))
        if resp.flag == 1:
            continue
        return escolhidos


# --- 5) PAUSA / RETOMADA / ABORTO durante a transmissao --------------------
def checaTeclado(canal, estado):
    t = tecla()
    if t is None:
        return
    if t == TECLA_PAUSA and not estado["pausado"]:
        estado["pausado"] = True
        canal.envia(dg.PAUSE)
        print("\n||| PAUSE enviado. Aperte '{}' para continuar ou '{}' para abortar.\n"
              .format(TECLA_SEGUE, TECLA_ABORTA))
    elif t == TECLA_SEGUE and estado["pausado"]:
        estado["pausado"] = False
        canal.envia(dg.RESUME)
        print("\n>>> RESUME enviado, retomando.\n")
    elif t == TECLA_ABORTA:
        canal.envia(dg.ABORT)
        raise Abortado()


# --- 6) LOOP PRINCIPAL DE RECEPCAO -----------------------------------------
# recebe os dois arquivos INTERCALADOS: cada pacote traz o id do arquivo,
# entao guardo os pedacos em dicionarios separados ate cada um ficar completo.
def recebeArquivos(canal, escolhidos, estado):

    # um "slot" por arquivo pedido; partes = {numero do pacote: bytes}
    arquivos = {i: {"nome": nome, "partes": {}, "total": None, "pronto": False}
                for i, nome in enumerate(escolhidos, start=1)}

    print("\n=== AGUARDANDO A TRANSMISSAO ({}) ===".format(", ".join(escolhidos)))
    print("    teclas:  {} = pausa   {} = continua   {} = aborta\n"
          .format(TECLA_PAUSA.upper(), TECLA_SEGUE.upper(), TECLA_ABORTA.upper()))
    t0 = time.time()
    calado = 0

    while not all(a["pronto"] for a in arquivos.values()):   # so sai quando todos terminarem
        checaTeclado(canal, estado)

        p = canal.recebe(timeout=0.4)
        if p is None:
            calado += 0.4
            if calado >= TIMEOUT_DADOS:
                print("   ... {:.0f} s sem receber nada{}".format(
                    calado, " (pausado)" if estado["pausado"] else
                            " - o fio entre os Arduinos caiu? continuo esperando"))
                calado = 0
            continue
        calado = 0

        if p.tipo == dg.DADOS:
            arq = arquivos.get(p.id)
            if arq is None:
                print("<- DADOS de arquivo desconhecido (id {}), ignorando".format(p.id))
                continue
            # checksum errado -> NACK, o server reenvia so esse pacote
            if not p.ok:
                print("<- DADOS arq {} pacote {} com CHECKSUM INVALIDO -> NACK".format(p.id, p.num + 1))
                canal.envia(dg.NACK, idArq=p.id, num=p.num)
                continue
            arq["total"] = p.total
            # pacote repetido = meu ACK anterior se perdeu; guardo nada e reconfirmo
            if p.num in arq["partes"]:
                print("<- DADOS arq {} pacote {}/{} DUPLICADO (o ACK anterior se perdeu) -> ACK de novo"
                      .format(p.id, p.num + 1, p.total))
            else:
                arq["partes"][p.num] = p.payload
                print("<- DADOS arq {} ({}) pacote {}/{} - {} B   [{}/{} recebidos]"
                      .format(p.id, arq["nome"], p.num + 1, p.total, len(p.payload),
                              len(arq["partes"]), p.total))
            canal.envia(dg.ACK, idArq=p.id, num=p.num)
            print("-> ACK   arq {} pacote {}".format(p.id, p.num + 1))

        # FIM: server diz que acabou. So aceito se nao faltar nenhum pacote.
        elif p.tipo == dg.FIM:
            arq = arquivos.get(p.id)
            canal.envia(dg.ACK, idArq=p.id, num=p.num)
            if arq is None or arq["pronto"]:
                continue
            faltando = [n for n in range(p.total) if n not in arq["partes"]]
            if faltando:
                print("<- FIM do arquivo {} mas faltam os pacotes {}".format(p.id, faltando[:5]))
                continue
            arq["pronto"] = True
            salva(arq)

        elif p.tipo == dg.RESPOSTA:
            print("<- server: \"{}\"".format(p.payload.decode("utf-8", errors="ignore")))

        else:
            print("   (ignorando {})".format(dg.descreve(p)))

    return arquivos, time.time() - t0


# --- 7) GRAVACAO: junta os pedacos na ordem do numero de pacote ------------
def salva(arq):
    dados = b"".join(arq["partes"][n] for n in sorted(arq["partes"]))
    caminho = os.path.join(PASTA, arq["nome"])
    with open(caminho, "wb") as f:
        f.write(dados)
    arq["tam"] = len(dados)
    print("=== arquivo {} completo: {} bytes em {} pacotes, salvo em {} ===\n"
          .format(arq["nome"], len(dados), len(arq["partes"]), caminho))


# --- 8) RESUMO pedido no enunciado: bytes, pacotes, tempo e taxa -----------
def resumo(arquivos, dt, canal):
    print("\n================ RESUMO DA TRANSMISSAO (CLIENT) ================")
    totalBytes = 0
    totalPct   = 0
    for arq in arquivos.values():
        tam = arq.get("tam", 0)
        totalBytes += tam
        totalPct   += len(arq["partes"])
        print("  {:<20} {:>7} bytes   {:>4} pacotes   {}".format(
            arq["nome"], tam, len(arq["partes"]),
            "OK" if arq["pronto"] else "INCOMPLETO"))
    print("  " + "-" * 58)
    print("  {:<20} {:>7} bytes   {:>4} pacotes".format("TOTAL", totalBytes, totalPct))
    print("  tempo: {:.1f} s   ({:.0f} bytes/s de dado util)".format(dt, totalBytes / dt if dt else 0))
    print("  pacotes recebidos: {}   confirmacoes enviadas: {}".format(canal.recebidos, canal.enviados))
    print("  arquivos salvos em {}/".format(os.path.abspath(PASTA)))
    print("================================================================")


# --- MAIN: abre a serial, roda menu -> recepcao -> resumo, e sempre fecha --
def main():
    com1 = None
    estado = {"pausado": False}
    try:
        if not os.path.isdir(PASTA):
            os.makedirs(PASTA)

        com1 = enlace(serialName)
        com1.enable()
        com1.fisica.flush()          # limpa lixo antigo do buffer antes de comecar
        print("Client aberto em {}".format(serialName))

        canal = dg.Canal(com1, "client")

        escolhidos = escolheArquivos(canal)
        arquivos, dt = recebeArquivos(canal, escolhidos, estado)
        resumo(arquivos, dt, canal)

    except Abortado:
        print("\n!!! ABORT enviado ao server. Transmissao cancelada, nada foi salvo.")
    except KeyboardInterrupt:
        print("\n!!! interrompido no teclado")
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
