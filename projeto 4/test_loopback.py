"""Roda o server e o client inteiros sem Arduino, ligados por um fio de mentira que
perde pacotes e corta pacotes no meio (o fio desconectado). Tres cenarios:
    1. transmissao com perda   -> os arquivos chegam identicos aos originais
    2. pausa e retomada        -> P para, C continua, os arquivos chegam do mesmo jeito
    3. abortar                 -> A derruba os dois lados sem salvar nada
       python test_loopback.py
"""
import builtins
import os
import queue
import random
import shutil
import tempfile
import threading
import time

import datagrama as dg
import client
import server

PERDA = 6
LIXO  = []


class FioDeMentira(object):
    """Mesma interface do dg.Canal, mas em cima de duas filas em memoria."""

    def __init__(self, entrada, saida, rotulo, ruido=False):
        self.entrada   = entrada
        self.saida     = saida
        self.rotulo    = rotulo
        self.ruido     = ruido
        self.buf       = b""
        self.enviados  = 0
        self.recebidos = 0
        self.perdidos  = 0

    def envia(self, tipo, idArq=0, num=0, total=0, payload=b"", flag=0):
        pacote = dg.monta(tipo, idArq, num, total, payload, flag)
        self.enviaBytes(pacote)
        return pacote

    def enviaBytes(self, pacote):
        self.enviados += 1
        if self.ruido and random.randrange(PERDA) == 0:
            self.perdidos += 1
            if random.random() < 0.5:
                return
            pacote = pacote[:len(pacote) // 2]
        self.saida.put(pacote)

    def recebe(self, timeout=None, silencioso=True):
        prazo = None if timeout is None else time.time() + timeout
        while True:
            try:
                self.buf += self.entrada.get(timeout=0.01)
            except queue.Empty:
                pass
            p, self.buf, _ = dg.extrai(self.buf)
            if p is not None:
                self.recebidos += 1
                return p
            if prazo is not None and time.time() > prazo:
                return None


def teclado(roteiro):
    """Aperta as teclas do roteiro {numero da chamada: tecla} durante a transmissao."""
    contador = {"n": 0}

    def tecla():
        contador["n"] += 1
        return roteiro.get(contador["n"])
    return tecla


def roda(nome, ruido=True, roteiro=None, seed=3):
    print("\n" + "#" * 70)
    print("# CENARIO: {}".format(nome))
    print("#" * 70 + "\n")
    random.seed(seed)

    server.TIMEOUT_ACK   = 0.2
    client.TIMEOUT_CTRL  = 0.3
    client.TIMEOUT_DADOS = 1.0
    client.tecla = teclado(roteiro or {})

    destino = tempfile.mkdtemp(prefix="proj3_")
    LIXO.append(destino)
    client.PASTA = destino

    aServer, aClient = queue.Queue(), queue.Queue()
    canalServer = FioDeMentira(aServer, aClient, "server", ruido=ruido)
    canalClient = FioDeMentira(aClient, aServer, "client", ruido=ruido)

    escolhas = iter(["1", "2", "n"])
    builtins.input = lambda *a: next(escolhas)

    resultado = {"destino": destino, "canalServer": canalServer, "canalClient": canalClient}

    def ladoServer():
        try:
            estado = {"pausado": False, "retransmissoes": 0}
            escolhidos = server.handshake(canalServer)
            arquivos, dt = server.transmite(canalServer, escolhidos, estado)
            server.resumo(arquivos, dt, estado, canalServer)
            resultado["estado"] = estado
        except server.Abortado:
            resultado["serverAbortou"] = True
            print("\n!!! ABORT recebido do client. Transmissao cancelada.")
        except Exception as e:
            resultado["erro"] = e

    t = threading.Thread(target=ladoServer)
    t.start()
    try:
        escolhidos = client.escolheArquivos(canalClient)
        arquivos, dt = client.recebeArquivos(canalClient, escolhidos, {"pausado": False})
        client.resumo(arquivos, dt, canalClient)
        resultado["arquivos"] = arquivos
    except client.Abortado:
        resultado["clientAbortou"] = True
        print("\n!!! ABORT enviado ao server.")
    t.join(timeout=180)

    assert "erro" not in resultado, "o server explodiu: {}".format(resultado.get("erro"))
    assert not t.is_alive(), "o server travou"
    return resultado


def confereArquivos(r):
    for arq in r["arquivos"].values():
        original = open(os.path.join(server.PASTA, arq["nome"]), "rb").read()
        recebido = open(os.path.join(r["destino"], arq["nome"]), "rb").read()
        assert arq["pronto"], "{} nao terminou".format(arq["nome"])
        assert original == recebido, "{} chegou corrompido ({} B != {} B)".format(
            arq["nome"], len(original), len(recebido))
    return len(r["arquivos"])


def main():

    r = roda("transmissao com perda de pacotes")
    n = confereArquivos(r)
    perdidos = r["canalServer"].perdidos + r["canalClient"].perdidos
    assert perdidos > 0, "o cenario nao chegou a exercitar a retransmissao"
    assert r["estado"]["retransmissoes"] > 0, "nao houve retransmissao"
    print("\nok: {} arquivos identicos com {} pacotes perdidos/cortados e {} retransmissoes"
          .format(n, perdidos, r["estado"]["retransmissoes"]))

    r = roda("pausar e retomar", ruido=False, roteiro={12: "p", 60: "c"})
    n = confereArquivos(r)
    assert r["canalServer"].perdidos == 0, "cenario 2 deveria ter fio limpo"
    print("\nok: {} arquivos completos mesmo com pausa no meio da transmissao".format(n))

    r = roda("abortar", ruido=False, roteiro={20: "a"})
    assert r.get("clientAbortou"), "o client nao abortou"
    assert r.get("serverAbortou"), "o server nao viu o ABORT"
    assert not os.listdir(r["destino"]), "abortou mas salvou arquivo pela metade"
    print("\nok: ABORT parou os dois lados sem deixar arquivo pela metade")

    for pasta in LIXO:
        shutil.rmtree(pasta, ignore_errors=True)
    print("\n=== os 3 cenarios passaram ===")


if __name__ == "__main__":
    main()
