import struct
import time
import datetime
from collections import namedtuple
import crcmod.predefined


HEAD_LEN    = 12
PAYLOAD_MAX = 100
EOP         = b"\xAA\xBB\xCC\xDD"
PACOTE_MAX  = HEAD_LEN + PAYLOAD_MAX + len(EOP)

# tipos de pacote (byte 0 do head). client -> server e server -> client:
HELLO    = 1    # client: "voce esta vivo? quais arquivos voce tem?"
LISTA    = 2    # server: um pacote por nome de arquivo disponivel
PEDIDO   = 3    # client: quero este arquivo (nome no payload)
RESPOSTA = 4    # server: texto de confirmacao/recusa (flag=1 = recusa)
START    = 5    # client: acabei de pedir, pode comecar a mandar
DADOS    = 6    # server: um pedaco do arquivo (id + num/total)
ACK      = 7    # client: recebi o pacote num do arquivo id
NACK     = 8    # client: checksum invalido, reenvia so esse pacote
FIM      = 9    # server: acabou o arquivo id
PAUSE    = 10   # client: pausa a transmissao (tecla P)
RESUME   = 11   # client: pode continuar (tecla C)
ABORT    = 12   # client: cancela tudo (tecla A)

NOME_TIPO = {HELLO: "HELLO", LISTA: "LISTA", PEDIDO: "PEDIDO", RESPOSTA: "RESPOSTA",
             START: "START", DADOS: "DADOS", ACK: "ACK", NACK: "NACK", FIM: "FIM",
             PAUSE: "PAUSE", RESUME: "RESUME", ABORT: "ABORT"}

Pacote = namedtuple("Pacote", "tipo id num total payload flag ok")

_crc16 = crcmod.predefined.mkCrcFun("crc-ccitt-false")


def checksum(payload):
    """CRC-16 (2 bytes) do payload, exigido pelo Projeto 4."""
    return _crc16(payload)


def monta(tipo, idArq=0, num=0, total=0, payload=b"", flag=0):
    """Monta o pacote pronto para ir para a serial."""
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    if len(payload) > PAYLOAD_MAX:
        raise ValueError("payload de {} bytes estoura o maximo de {}".format(len(payload), PAYLOAD_MAX))
    head = (bytes([tipo, idArq])
            + struct.pack(">HH", num, total)
            + bytes([len(payload), flag])
            + struct.pack(">H", checksum(payload))
            + bytes([0, 0]))    
    return head + payload + EOP


def extrai(buf):
    """Procura o primeiro pacote dentro de buf.
    Varre todas as posicoes possiveis de inicio: um pacote so e aceito quando o
    tamanho anunciado no head coloca o EOP exatamente onde ele esta. E isso que
    permite reencontrar o sincronismo depois de um fio desconectado (lixo no
    meio do buffer) e tambem tolera o EOP aparecer por acaso dentro do payload.
    Devolve (pacote ou None, resto do buffer, bytes de lixo descartados).
    """
    limite = len(buf) - HEAD_LEN - len(EOP)
    for s in range(0, limite + 1):
        head = buf[s:s + HEAD_LEN]
        n = head[6]
        if n > PAYLOAD_MAX:
            continue
        fim = s + HEAD_LEN + n
        if buf[fim:fim + len(EOP)] != EOP:
            continue
        payload = buf[s + HEAD_LEN:fim]
        crcRecebido = struct.unpack(">H", head[8:10])[0]
        p = Pacote(tipo=head[0], id=head[1],
                   num=struct.unpack(">H", head[2:4])[0],
                   total=struct.unpack(">H", head[4:6])[0],
                   payload=payload, flag=head[7],
                   ok=(checksum(payload) == crcRecebido))
        return p, buf[fim + len(EOP):], s
    return None, buf, 0


def descreve(p):
    """Uma linha resumindo o pacote, para os prints."""
    nome = NOME_TIPO.get(p.tipo, "TIPO?{}".format(p.tipo))
    txt = "{:<8}".format(nome)
    if p.id:
        txt += " arq {} pacote {}/{}".format(p.id, p.num, p.total)
    if p.payload:
        txt += " payload {} B".format(len(p.payload))
    if not p.ok:
        txt += " [CHECKSUM INVALIDO]"
    return txt


class Canal(object):
    """Envia e recebe pacotes por cima da camada de enlace.
    Guarda o que sobrou do buffer entre uma leitura e outra, porque um pacote
    pode chegar picado em varias leituras da serial.
    """

    def __init__(self, com, rotulo=""):
        self.com    = com
        self.rotulo = rotulo
        self.buf    = b""
        self.enviados  = 0
        self.recebidos = 0
        self.arquivoLog = open("log_{}.txt".format(rotulo or "canal"), "a", encoding="utf-8")

    def _linhaLog(self, direcao, tipo, tamanhoTotal, num=None, total=None, crc=None):
        agora = datetime.datetime.now()
        carimbo = agora.strftime("%d/%m/%Y %H:%M:%S.") + "{:03d}".format(agora.microsecond // 1000)
        campos = [carimbo, direcao, str(tipo), str(tamanhoTotal)]
        if tipo == DADOS and num is not None:
            campos += [str(num + 1), str(total), "{:04X}".format(crc)]
        self.arquivoLog.write(" / ".join(campos) + "\n")
        self.arquivoLog.flush()

    def envia(self, tipo, idArq=0, num=0, total=0, payload=b"", flag=0):
        pacote = monta(tipo, idArq, num, total, payload, flag)
        self.enviaBytes(pacote)
        return pacote

    def enviaBytes(self, pacote):
        """Reenvio de um pacote ja montado (retransmissao)."""
        self.com.sendData(pacote)
        self.com.tx.getStatus()
        self.enviados += 1
        tipo  = pacote[0]
        num   = struct.unpack(">H", pacote[2:4])[0]
        total = struct.unpack(">H", pacote[4:6])[0]
        crc   = struct.unpack(">H", pacote[8:10])[0]
        self._linhaLog("envio", tipo, len(pacote), num=num, total=total, crc=crc)

    def recebe(self, timeout=None, silencioso=False):
        """Espera um pacote. Devolve None se estourar o timeout."""
        prazo = None if timeout is None else time.time() + timeout
        while True:
            n = self.com.rx.getBufferLen()
            if n:
                self.buf += self.com.rx.getBuffer(n)
            p, self.buf, lixo = extrai(self.buf)
            if lixo and not silencioso:
                print("   [{}] {} bytes de lixo descartados (ressincronizando)".format(self.rotulo, lixo))
            if p is not None:
                self.recebidos += 1
                tamanhoTotal = HEAD_LEN + len(p.payload) + len(EOP)
                self._linhaLog("receb", p.tipo, tamanhoTotal, num=p.num, total=p.total, crc=checksum(p.payload))
                return p
            if prazo is not None and time.time() > prazo:
                return None

            if len(self.buf) > 4 * PACOTE_MAX:
                self.buf = self.buf[-2 * PACOTE_MAX:]
            time.sleep(0.02)


def fragmenta(dados, tamanho=PAYLOAD_MAX):
    """Corta o arquivo em pedacos de no maximo 100 bytes."""
    return [dados[i:i + tamanho] for i in range(0, len(dados), tamanho)] or [b""]
