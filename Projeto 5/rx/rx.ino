// ============================================================================
// RX - recebe um frame UART num pino digital generico, sem delay() (Projeto 5)
//
// Maquina de estados:
//   ESPERA_START ---(linha caiu pra 0)---> LENDO ---(stop bit lido)---> ESPERA_START
//                                            \--(stop bit = 0)--> ESPERA_LINHA_LIVRE
//
// O relogio do frame e o instante da borda de descida do start bit (tStart).
// O bit k e amostrado no MEIO dele: tStart + k*T + T/2 - nunca na transicao.
// Como so percebemos a borda na volta seguinte do loop(), ela caiu em algum ponto
// entre a ultima leitura HIGH e a primeira LOW: tStart = meio desse intervalo.
// Isso tira o atraso sistematico e sobra folga pra cristais fora do valor.
// Ligacao: pino 8 do TX -> pino 8 daqui, GND com GND. Monitor serial a 115200.
// ============================================================================
#include <Arduino.h>

const uint8_t  PINO_RX = 8;
const uint32_t BAUD    = 9600;
const uint32_t T_BIT   = 1000000UL / BAUD;   // 104 us a 9600

// ponytail: polling com digitalRead (~4 us) + micros() com passo de 4 us aguenta ate
// ~19200 baud. Acima disso: attachInterrupt no start bit e leitura direta do PINB.

enum Estado { ESPERA_START, LENDO, ESPERA_LINHA_LIVRE };

Estado   estado = ESPERA_START;
uint32_t tStart;
uint32_t tUltimoHigh;   // ultima vez que a linha foi lida em repouso (HIGH)
uint8_t  bitAtual;      // 0 = start, 1..8 = dados, 9 = paridade, 10 = stop
uint8_t  dado;
uint8_t  paridadeRx;

uint16_t recebidosOk = 0, errosParidade = 0, errosFrame = 0;

void voltaAoRepouso(uint32_t agora) {   // sempre chamado logo apos ler a linha em HIGH
  estado      = ESPERA_START;
  tUltimoHigh = agora;
}

uint8_t paridadePar(uint8_t d) {
  uint8_t uns = 0;
  for (uint8_t i = 0; i < 8; i++) uns += (d >> i) & 0x01;
  return uns % 2;
}

void concluiFrame(uint8_t stopBit) {
  const char* status;
  if (stopBit != HIGH)                      { errosFrame++;    status = "ERRO DE FRAME (stop bit = 0)"; }
  else if (paridadeRx != paridadePar(dado)) { errosParidade++; status = "ERRO DE PARIDADE"; }
  else                                      { recebidosOk++;   status = "OK"; }

  Serial.print("<- '"); Serial.print((char)dado); Serial.print("' 0x"); Serial.print(dado, HEX);
  Serial.print(" paridade="); Serial.print(paridadeRx);
  Serial.print("  "); Serial.print(status);
  Serial.print("   [ok "); Serial.print(recebidosOk);
  Serial.print(" | paridade "); Serial.print(errosParidade);
  Serial.print(" | frame "); Serial.print(errosFrame); Serial.println("]");
}

void setup() {
  pinMode(PINO_RX, INPUT_PULLUP);   // fio solto le HIGH (= idle) em vez de lixo
  Serial.begin(115200);
  Serial.print("RX UART por software: "); Serial.print(BAUD); Serial.println(" baud, 8 dados, paridade PAR, 1 stop");
  tUltimoHigh = micros();
}

void loop() {
  uint32_t agora = micros();

  switch (estado) {

    case ESPERA_START:
      if (digitalRead(PINO_RX) == HIGH) {
        tUltimoHigh = agora;
      } else {                               // borda de descida = comeco do start bit
        uint32_t gap = agora - tUltimoHigh;  // marca que o frame mudou entre a ultima e essa iteração
        tStart   = agora - (gap < T_BIT ? gap / 2 : 0); // pega o tempo real de inicio
        bitAtual = 0;
        dado     = 0;
        estado   = LENDO;
      }
      break;

    case LENDO:
      if (agora - tStart >= (uint32_t)bitAtual * T_BIT + T_BIT / 2) {   // meio do bit k
        uint8_t nivel = digitalRead(PINO_RX);

        if (bitAtual == 0) {                       // confirma o start no meio dele: filtra ruido
          if (nivel == HIGH) voltaAoRepouso(agora);
        }
        else if (bitAtual <= 8) {                  // dados, LSB primeiro
          dado |= nivel << (bitAtual - 1);
        }
        else if (bitAtual == 9) {
          paridadeRx = nivel;
        }
        else {                                     // bit 10 = stop, fecha o frame
          concluiFrame(nivel);
          if (nivel == HIGH) voltaAoRepouso(agora); else estado = ESPERA_LINHA_LIVRE;
        }
        bitAtual++;
      }
      break;

    case ESPERA_LINHA_LIVRE:   // stop bit errado: espera a linha voltar a 1 pra nao confundir dado com start
      if (digitalRead(PINO_RX) == HIGH) voltaAoRepouso(agora);
      break;
  }
}
