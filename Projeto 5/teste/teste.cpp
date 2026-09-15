// Roda tx.ino e rx.ino no PC, ligados por um fio virtual, e confere:
//   1. frames limpos chegam com o byte certo e sem erro
//   2. paridade invertida de proposito e detectada, e o byte continua certo
//   3. RX com cristal 3% fora ainda decodifica (folga do UART e ~4-5%)
//   4. glitch curto no fio nao vira frame; linha presa em 0 vira ERRO DE FRAME e o RX se recupera
//
//   g++ -std=c++17 -I teste teste/teste.cpp -o teste/teste.exe && teste/teste.exe
#include "Arduino.h"
#include <cassert>
#include <random>
#include <vector>
#include <iostream>

uint32_t   g_micros = 0;
double     g_escala = 1.0;
int        g_fio    = HIGH;
SerialMock Serial;

namespace TX {
#include "../tx/tx.ino"
}
namespace RX {
#include "../rx/rx.ino"
}

static std::mt19937 rng(1);
static std::vector<uint8_t> recebidos;   // byte de cada frame que o RX fechou, na ordem

// dois processadores independentes: cada um roda seu loop() a cada 4..8 us (micros + digitalRead/Write)
static uint32_t tProxTX = 0, tProxRX = 0;
static void passo(double escalaRx) {
  g_micros++;
  if (g_micros >= tProxTX) { g_escala = 1.0;      TX::loop(); tProxTX = g_micros + 4 + rng() % 5; }
  if (g_micros >= tProxRX) { g_escala = escalaRx; RX::loop(); tProxRX = g_micros + 4 + rng() % 5; }
}

// avanca o mundo ate o TX ter enviado `nFrames` frames e o ultimo deles ter aterrissado no RX
static void roda(int nFrames, double escalaRx = 1.0) {
  uint32_t framesRx = RX::recebidosOk + RX::errosParidade + RX::errosFrame;
  uint16_t alvo     = TX::enviados + nFrames;
  uint32_t tFim     = 0;
  while (true) {
    passo(escalaRx);
    uint32_t agoraRx = RX::recebidosOk + RX::errosParidade + RX::errosFrame;
    if (agoraRx != framesRx) { recebidos.push_back(RX::dado); framesRx = agoraRx; }
    if (TX::enviados == alvo && !tFim) tFim = g_micros + 20 * TX::T_BIT;   // folga pro ultimo frame chegar
    if (tFim && g_micros > tFim) break;
  }
  g_escala = 1.0;
}

int main() {
  TX::setup(); RX::setup();
  const char* msg = TX::MENSAGEM;
  const int   n   = 20;

  // 1) transmissao limpa
  roda(n);
  assert(RX::recebidosOk == n && RX::errosParidade == 0 && RX::errosFrame == 0);
  assert(recebidos.size() == n);
  for (int i = 0; i < n; i++) assert(recebidos[i] == (uint8_t)msg[i % 16]);
  std::cout << "ok: " << n << " frames limpos, bytes identicos\n";

  // 2) paridade invertida a cada 5 frames -> 4 erros em 20, dados continuam certos
  recebidos.clear();
  TX::ERRO_A_CADA = 5;
  roda(n);
  TX::ERRO_A_CADA = 0;
  assert(RX::errosParidade == 4 && RX::recebidosOk == 2 * n - 4 && RX::errosFrame == 0);
  for (int i = 0; i < n; i++) assert(recebidos[i] == (uint8_t)msg[(n + i) % 16]);
  std::cout << "ok: 4 erros de paridade detectados, bytes ainda identicos\n";

  // 3) RX com relogio 3% mais rapido e depois 3% mais lento
  for (double esc : {1.03, 0.97}) {
    recebidos.clear();
    uint16_t antes = RX::recebidosOk;
    roda(n, esc);
    assert(RX::recebidosOk == antes + n && RX::errosParidade == 4 && RX::errosFrame == 0);
    for (int i = 0; i < n; i++) assert(recebidos[i] == (uint8_t)msg[(TX::enviados - n + i) % 16]);
  }
  std::cout << "ok: RX com cristal +-3% ainda decodifica tudo\n";

  // 4a) glitch de 20 us durante o idle: nao pode virar frame
  uint32_t framesAntes = RX::recebidosOk + RX::errosParidade + RX::errosFrame;
  g_fio = LOW;  for (int i = 0; i < 4; i++) { RX::loop(); g_micros += 5; }
  g_fio = HIGH; for (int i = 0; i < 40; i++) { RX::loop(); g_micros += 5; }
  assert(RX::estado == RX::ESPERA_START);
  assert(RX::recebidosOk + RX::errosParidade + RX::errosFrame == framesAntes);
  std::cout << "ok: glitch curto ignorado\n";

  // 4b) linha presa em 0 por 15 bits (break) -> 1 ERRO DE FRAME, depois recupera e recebe normal
  g_fio = LOW;   // o TX esta no intervalo entre frames e nao escreve no fio; o harness segura a linha
  for (uint32_t t0 = g_micros; g_micros - t0 < 15 * TX::T_BIT; ) { RX::loop(); g_micros += 5; }
  assert(RX::errosFrame == 1 && RX::estado == RX::ESPERA_LINHA_LIVRE);
  g_fio = HIGH; RX::loop();
  assert(RX::estado == RX::ESPERA_START);
  uint16_t okAntes = RX::recebidosOk;
  recebidos.clear();
  roda(3);
  assert(RX::recebidosOk == okAntes + 3 && recebidos.size() == 3);
  std::cout << "ok: break gerou ERRO DE FRAME e o RX voltou a receber\n";

  std::cout << "\nultimas linhas do monitor serial (TX e RX misturados):\n";
  auto& s = Serial.saida;
  size_t pos = s.size();
  for (int i = 0; i < 4 && pos != std::string::npos; i++) pos = s.rfind('\n', pos - 1);
  std::cout << s.substr(pos + 1);
  std::cout << "\n=== todos os cenarios passaram ===\n";
  return 0;
}
