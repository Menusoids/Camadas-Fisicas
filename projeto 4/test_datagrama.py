"""Confere o empacotamento e a ressincronizacao. Sem serial, roda solto:
       python test_datagrama.py
"""
import datagrama as dg

pacote = dg.monta(dg.DADOS, idArq=2, num=513, total=1000, payload=b"abc")
assert len(pacote) == dg.HEAD_LEN + 3 + len(dg.EOP), "tamanho do pacote errado"
p, resto, lixo = dg.extrai(pacote)
assert (p.tipo, p.id, p.num, p.total, p.payload, p.ok) == (dg.DADOS, 2, 513, 1000, b"abc", True)
assert resto == b"" and lixo == 0

for carga in (b"", bytes(range(dg.PAYLOAD_MAX))):
    p, _, _ = dg.extrai(dg.monta(dg.ACK, idArq=1, payload=carga))
    assert p.payload == carga and p.ok

try:
    dg.monta(dg.DADOS, payload=b"x" * (dg.PAYLOAD_MAX + 1))
    raise AssertionError("aceitou payload acima de 100 bytes")
except ValueError:
    pass

sujo = b"\x00\xff\xAA\xBB\x12" + dg.monta(dg.FIM, idArq=1, num=7)
p, resto, lixo = dg.extrai(sujo)
assert p.tipo == dg.FIM and p.num == 7, "nao ressincronizou depois do lixo"
assert lixo == 5, "contou {} bytes de lixo, esperava 5".format(lixo)

carga = b"x" + dg.EOP + b"y" * 10
p, _, _ = dg.extrai(dg.monta(dg.DADOS, idArq=1, payload=carga))
assert p.payload == carga, "o EOP dentro do payload cortou o pacote"

ruim = bytearray(dg.monta(dg.DADOS, idArq=1, payload=b"dados"))
ruim[dg.HEAD_LEN] ^= 0xFF
p, _, _ = dg.extrai(bytes(ruim))
assert p is not None and not p.ok, "checksum nao pegou o byte trocado"

p, resto, _ = dg.extrai(dg.monta(dg.ACK, idArq=1, num=1) + dg.monta(dg.ACK, idArq=2, num=2))
assert p.num == 1
p2, resto, _ = dg.extrai(resto)
assert p2.num == 2 and resto == b""

metade = dg.monta(dg.DADOS, idArq=1, payload=b"abc")[:-2]
p, resto, _ = dg.extrai(metade)
assert p is None and resto == metade

dados = bytes(range(256)) * 3
partes = dg.fragmenta(dados)
assert max(len(x) for x in partes) <= dg.PAYLOAD_MAX
assert b"".join(partes) == dados, "remontagem perdeu bytes"
assert dg.fragmenta(b"") == [b""], "arquivo vazio precisa de 1 pacote"

print("ok: {} pacotes para {} bytes, overhead {:.2f}x".format(
    len(partes), len(dados), len(partes) * dg.PACOTE_MAX / len(dados)))
