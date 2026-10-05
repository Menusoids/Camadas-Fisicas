// ============================================================================
// TX - UART por software num pino digital generico (Projeto 5)
//
// Frame:  idle(1) | start(0) | d0 d1 d2 d3 d4 d5 d6 d7 (LSB primeiro) | paridade PAR | stop(1)
//
// Sem delay(): cada bit e agendado por micros() a partir do INICIO do frame
// (tInicio + i*T), entao o erro de tempo de um bit nao acumula no seguinte.
// Ligacao: pino 8 daqui -> pino 8 do RX, e GND com GND. Reset LIVRE.
// ============================================================================
#include <Arduino.h>

const uint8_t  PINO_TX     = 8;
const uint32_t BAUD        = 9600;
const uint32_t T_BIT       = 1000000UL / BAUD;   // 104 us a 9600
const uint32_t INTERVALO   = 250000UL;           // us de silencio entre frames, so pra dar tempo de ler o monitor
                                                 // (minimo ~10 ms: o print do RX leva ~6 ms a 115200 e engoliria o proximo start)
const char     MENSAGEM[]  = "Camadas Fisicas ";
uint8_t        ERRO_A_CADA = 0;   // DEMO do erro de paridade: inverte o bit de paridade a cada N frames (0 = desligado)

const uint8_t  BITS_FRAME  = 11;  // 1 start + 8 dados + 1 paridade + 1 stop

// ponytail: micros() tem passo de 4 us e digitalWrite leva ~4 us, entao isso vale
// ate ~19200 baud. Acima disso: timer1 em modo CTC + escrita direta no PORTB.

uint8_t paridadePar(uint8_t dado) {
  uint8_t uns = 0;
  for (uint8_t i = 0; i < 8; i++) uns += (dado >> i) & 0x01;
  return uns % 2;   // paridade PAR: bit = 1 se o numero de 1s for impar, pra ficar par no total
}

uint16_t montaFrame(uint8_t dado, bool inverteParidade) { // guarda o frame em forma de um inteiro, é uma fila de bits afinal
  uint8_t p = paridadePar(dado) ^ (inverteParidade ? 1 : 0); // Inverte o de paridade pra simular o erro 
  // bit 0 = start (0)  |  bits 1..8 = dado  |  bit 9 = paridade  |  bit 10 = stop (1)
  return (1u << 10) | ((uint16_t)p << 9) | ((uint16_t)dado << 1);
  // ele desloca os bits de dado para suas posições corretas. ai ele usa o XOR pra juntar com o bit de paridade
}

uint16_t frame;
uint8_t  bitAtual = BITS_FRAME;   // faz isso pra ja começar na situaçao 2
uint32_t tInicio;
uint16_t enviados = 0;
uint8_t  idx = 0;

void setup() {
  pinMode(PINO_TX, OUTPUT);
  digitalWrite(PINO_TX, HIGH);   // linha em repouso
  Serial.begin(115200);          // USB: so pra monitorar, nao participa da transmissao
  Serial.print("TX UART por software: "); Serial.print(BAUD); Serial.println(" baud, 8 dados, paridade PAR, 1 stop");
  tInicio = micros();
}

void loop() {
  uint32_t agora = micros();

  if (bitAtual < BITS_FRAME) { // esta no meio de um fram tem que enviar o próximo bit
    // a subtracao unsigned continua certa quando micros() da a volta (a cada ~70 min)
    if (agora - tInicio >= (uint32_t)bitAtual * T_BIT) { 
//  se o tempo desde que começou >=  tempo de envio do bit de analise no momento
      digitalWrite(PINO_TX, (frame >> bitAtual) & 0x01);
      bitAtual++;
    }
    return;
  }

  if (agora - tInicio >= (uint32_t)BITS_FRAME * T_BIT + INTERVALO) { // está na hora de começar outr frame
    uint8_t dado = MENSAGEM[idx];          // 1. pega a próxima letra
    idx = (idx + 1) % (sizeof(MENSAGEM) - 1);     // 2. avança o índice (e volta ao início no fim)
    enviados++;
    bool erro = ERRO_A_CADA && (enviados % ERRO_A_CADA == 0);     // 3. é a vez de errar de propósito?
    frame    = montaFrame(dado, erro);                             // 4. monta os 11 bits

    Serial.print("-> '"); Serial.print((char)dado); Serial.print("' 0x"); Serial.print(dado, HEX);
    Serial.print(" paridade="); Serial.print((frame >> 9) & 0x01);          
    if (erro) Serial.print("  (INVERTIDA de proposito)");
    Serial.println();                   // 5. mostra no monitor o que vai sair

    bitAtual = 0;
    tInicio  = micros();   // depois do print, pra ele nao roubar tempo do start bit
  }
}
