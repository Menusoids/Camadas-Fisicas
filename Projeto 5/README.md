# Projeto 5 - UART por software entre dois Arduinos

Frame: `idle(1) | start(0) | 8 dados LSB primeiro | paridade PAR | stop(1)` a 9600 baud, sem `delay()`.

```
tx/tx.ino     transmissor: manda "Camadas Fisicas " em loop, 1 caractere a cada 250 ms
rx/rx.ino     receptor: maquina de estados, amostra no meio de cada bit, acusa erro de paridade/frame
teste/        simulacao no PC: os dois sketches ligados por um fio virtual (nao precisa de Arduino)
```

## Montagem
- `pino 8` do TX -> `pino 8` do RX
- `GND` com `GND`
- reset **livre** nos dois (agora o processador roda)
- Analog Discovery: canal digital no pino 8 do TX + GND

## Rodar
```powershell
arduino-cli compile tx ; arduino-cli upload tx          # porta em tx/sketch.yaml (COM5)
arduino-cli compile rx ; arduino-cli upload rx          # porta em rx/sketch.yaml (COM8)
arduino-cli monitor -p COM8 -c baudrate=115200         # monitor do RX
```
Saida esperada no RX: `<- 'C' 0x43 paridade=1  OK   [ok 12 | paridade 0 | frame 0]`

## Roteiro da apresentacao
| Nota | O que mostrar | Onde |
|---|---|---|
| C+ | 9600 baud | `BAUD` nos dois sketches; RX imprime os caracteres certos |
| B+ | erro de paridade | em `tx.ino` ponha `ERRO_A_CADA = 5`, regrave: a cada 5 frames o RX imprime `ERRO DE PARIDADE` e o contador sobe |
| A  | sem delay/sleep | tudo agendado por `micros()`; `grep delay` nao acha nada |
| A+ | Analog Discovery | WaveForms > Logic Analyzer > Add > UART: pino do canal, 9600 baud, 8 bits, parity **Even**, 1 stop, idle **high**. Base de tempo ~200 us/div mostra o frame; o decoder exibe o caractere |

## Teste no PC (sem Arduino)
```powershell
g++ -std=c++17 -I teste teste/teste.cpp -o teste/teste.exe ; teste/teste.exe
```
Cobre: frames limpos, paridade invertida detectada, RX com cristal +-3% fora, glitch ignorado, break -> erro de frame e recuperacao.
