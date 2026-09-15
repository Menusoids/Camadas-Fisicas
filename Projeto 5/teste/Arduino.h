// Mock minimo do Arduino para rodar tx.ino e rx.ino no PC, ligados por um fio virtual.
// So existe o que os dois sketches usam.
#pragma once
#include <stdint.h>
#include <string>
#include <cstdio>

#define HIGH 1
#define LOW  0
#define INPUT        0
#define OUTPUT       1
#define INPUT_PULLUP 2
#define HEX 16

extern uint32_t g_micros;   // relogio simulado, em us
extern double   g_escala;   // 1.03 = o lado que esta rodando acha que o tempo passa 3% mais rapido (cristal fora)
extern int      g_fio;      // nivel logico do fio TX -> RX

inline uint32_t micros() { return ((uint32_t)(g_micros * g_escala)) & ~3u; }   // passo de 4 us, como no Uno
inline void pinMode(uint8_t, uint8_t) {}
inline void digitalWrite(uint8_t, uint8_t v) { g_fio = v; }
inline int  digitalRead(uint8_t) { return g_fio; }

struct SerialMock {
  std::string saida;
  void begin(long) {}
  void print(const char* s) { saida += s; }
  void print(char c) { saida += c; }
  template <class T> void print(T v, int base = 10) {
    char b[24];
    snprintf(b, sizeof b, base == 16 ? "%llX" : "%lld", (long long)v);
    saida += b;
  }
  void println() { saida += '\n'; }
  template <class T> void println(T v) { print(v); println(); }
};
extern SerialMock Serial;
