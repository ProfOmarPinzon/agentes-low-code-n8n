// Práctica 3: agente de ambiente con M5Stack StickS3 + sensor ENV III, conectado por USB-C.
//
// El dispositivo NO usa WiFi ni Bluetooth: no se incluye <WiFi.h> y el radio nunca se enciende.
// Toda la comunicación pasa por el cable USB-C (puerto serie USB del ESP32-S3):
//
//   StickS3 --USB serial--> puente_serial.py (Mac) --HTTP POST--> webhook local de n8n
//   StickS3 <--USB serial-- puente_serial.py (Mac) <--respuesta--
//
// Protocolo (una línea de texto por mensaje, terminada en '\n'):
// - Dispositivo -> Mac: una línea JSON por lectura, por ejemplo
//     {"dispositivo":"sticks3","ciudad":"Bogota","temperatura_c":26.4,"humedad_pct":55.0,"presion_hpa":752.1}
// - Dispositivo -> Mac: los mensajes de diagnóstico empiezan con "# " (el puente los muestra, no los envía).
// - Mac -> dispositivo: la respuesta del agente {"pantalla":...,"nivel":...,"detalle":...}
//   o un error del puente {"error":"..."}.
//
// Uso:
// - En reposo muestra la lectura interior cada 2 s.
// - Botón A: envía la lectura por USB y muestra la recomendación del agente.
// - Botón B: muestra el detalle de la recomendación (por páginas) y vuelve a la lectura.
// - Cualquier falla (sensor, puente, n8n) se muestra en pantalla con su causa.

#include <M5Unified.h>
#include <ArduinoJson.h>
#include <M5UnitENV.h>
#include <math.h>
#include <vector>

// config.h es opcional: permite cambiar los valores por defecto sin tocar este archivo.
#if __has_include("config.h")
#include "config.h"
#endif
#ifndef DISPOSITIVO
#define DISPOSITIVO "sticks3"  // nombre con el que el dispositivo aparece en n8n
#endif
#ifndef CIUDAD
#define CIUDAD "Bogota"  // ciudad para el clima exterior (servicio /clima de la P0)
#endif
#ifndef ENVIO_AUTOMATICO_S
#define ENVIO_AUTOMATICO_S 0  // 0 = solo con el botón A; por ejemplo 600 = cada 10 minutos
#endif
#ifndef LECTURA_DE_EJEMPLO
#define LECTURA_DE_EJEMPLO 0  // 1 = sin sensor: envía {"temperatura_c":26.4} para probar el enlace USB
#endif
#ifndef ESPERA_RESPUESTA_MS
#define ESPERA_RESPUESTA_MS 90000  // el agente y la herramienta de clima tardan varios segundos
#endif

// Texto tamaño 2 (12 x 16 px) en 240 x 135 px: 20 columnas y 8 filas (1 título + 7 de contenido).
static const int COLUMNAS = 20;
static const int FILAS = 7;

static SHT3X sht3x;      // temperatura y humedad (I2C 0x44)
static QMP6988 qmp;      // presión (I2C 0x70)
static bool sensorListo = false;

struct Lectura {
  float temperatura_c;
  float humedad_pct;  // NAN si el sensor no la mide
  float presion_hpa;  // NAN si el sensor no la mide
  bool valida;
};
static Lectura ultima = {0, NAN, NAN, false};

enum class Vista { Lectura, Esperando, Respuesta, Detalle, Error };
static Vista vista = Vista::Lectura;
static String pantalla, nivel;
static std::vector<String> lineasDetalle;
static int paginaDetalle = 0;
static uint32_t inicioEspera = 0;
static String entrada;  // línea que se está recibiendo por USB

// ---------------------------------------------------------------- utilidades de texto

// La fuente del dispositivo solo tiene ASCII: se quitan tildes, eñes y símbolos.
static String aAscii(const String& s) {
  String out;
  out.reserve(s.length());
  for (size_t i = 0; i < s.length();) {
    uint8_t c = s[i];
    if (c < 0x80) {
      out += (c == '\n' || c == '\r') ? ' ' : (char)c;
      i++;
      continue;
    }
    if (c == 0xC3 && i + 1 < s.length()) {
      const char* desde = "\xA1\xA9\xAD\xB3\xBA\xBC\xB1\x81\x89\x8D\x93\x9A\x9C\x91";
      const char* hacia = "aeiouunAEIOUUN";
      const char* p = strchr(desde, s[i + 1]);
      if (p) out += hacia[p - desde];
      i += 2;
      continue;
    }
    i += (c >= 0xF0) ? 4 : (c >= 0xE0) ? 3 : 2;  // otros caracteres (°, ¿, emojis): se omiten
  }
  return out;
}

// Parte el texto en líneas de máximo `columnas` caracteres, sin cortar palabras cortas.
static std::vector<String> envolver(const String& texto, int columnas) {
  std::vector<String> lineas;
  String linea;
  int i = 0;
  const int n = texto.length();
  while (i < n) {
    int j = texto.indexOf(' ', i);
    if (j < 0) j = n;
    String palabra = texto.substring(i, j);
    i = j + 1;
    if (palabra.isEmpty()) continue;
    while ((int)palabra.length() > columnas) {
      if (!linea.isEmpty()) { lineas.push_back(linea); linea = ""; }
      lineas.push_back(palabra.substring(0, columnas));
      palabra = palabra.substring(columnas);
    }
    if (linea.isEmpty()) linea = palabra;
    else if ((int)(linea.length() + 1 + palabra.length()) <= columnas) linea += " " + palabra;
    else { lineas.push_back(linea); linea = palabra; }
  }
  if (!linea.isEmpty()) lineas.push_back(linea);
  return lineas;
}

// Mensaje de diagnóstico: empieza con "# " para que el puente no lo confunda con una lectura.
static void diagnostico(const String& texto) {
  Serial.print("# ");
  Serial.println(texto);
}

// ---------------------------------------------------------------- pantalla

static void dibujar(uint16_t fondo, uint16_t tinta, const String& titulo,
                    const std::vector<String>& lineas, int desde = 0) {
  auto& d = M5.Display;
  d.fillScreen(fondo);
  d.setFont(&fonts::Font0);
  d.setTextColor(tinta, fondo);
  d.setTextSize(2);
  d.setCursor(0, 0);
  d.println(titulo);
  for (int k = desde; k < desde + FILAS && k < (int)lineas.size(); ++k) d.println(lineas[k]);
}

// Pantalla de reposo: la temperatura medida en grande (fuente de 7 segmentos, 48 px de alto)
// y debajo la humedad, la presión y el estado del USB.
static void mostrarLectura() {
  vista = Vista::Lectura;
  const String usb = HWCDC::isConnected() ? "USB: conectado" : "USB: sin computador";
  if (!ultima.valida) {
    dibujar(TFT_BLACK, TFT_WHITE, "A: consultar",
            {String("Sensor ENV III"), String("no detectado."), String("Revisar cable Grove"), String(""), usb});
    return;
  }

  auto& d = M5.Display;
  d.fillScreen(TFT_BLACK);
  d.setTextColor(TFT_WHITE, TFT_BLACK);
  d.setTextSize(2);
  d.setCursor(0, 0);
  d.print(LECTURA_DE_EJEMPLO ? "A: consultar (ej.)" : "A: consultar");

  // Temperatura: color según el rango de confort del prompt (20 a 26 C verde; 18 a 28 C amarillo; fuera, rojo).
  const float t = ultima.temperatura_c;
  const uint16_t color = (t >= 20 && t <= 26) ? TFT_GREEN : (t >= 18 && t <= 28) ? TFT_YELLOW : TFT_RED;
  d.setFont(&fonts::Font7);
  d.setTextSize(1);
  d.setTextColor(color, TFT_BLACK);
  const String valor = String(t, 1);
  d.drawString(valor, 0, 22);
  const int x = d.textWidth(valor) + 6;
  d.drawCircle(x + 4, 26, 4, color);  // símbolo de grados (la fuente no tiene °)
  d.drawCircle(x + 4, 26, 3, color);
  d.setFont(&fonts::Font0);
  d.setTextSize(3);
  d.drawString("C", x + 12, 22);

  d.setTextSize(2);
  d.setTextColor(TFT_WHITE, TFT_BLACK);
  d.setCursor(0, 78);
  if (!isnan(ultima.humedad_pct)) d.print("Hum " + String(ultima.humedad_pct, 0) + "%");
  if (!isnan(ultima.presion_hpa)) d.print("  " + String(ultima.presion_hpa, 0) + "hPa");
  d.setCursor(0, 98);
  d.print(CIUDAD);
  d.setCursor(0, 118);
  d.setTextColor(HWCDC::isConnected() ? TFT_CYAN : TFT_ORANGE, TFT_BLACK);
  d.print(usb);
}

static void mostrarError(const String& causa) {
  vista = Vista::Error;
  diagnostico("ERROR: " + causa);
  dibujar(TFT_MAROON, TFT_WHITE, "ERROR (B: volver)", envolver(aAscii(causa), COLUMNAS));
}

static void mostrarRespuesta() {
  vista = Vista::Respuesta;
  uint16_t fondo = TFT_DARKGREEN, tinta = TFT_WHITE;
  if (nivel == "atencion") { fondo = TFT_YELLOW; tinta = TFT_BLACK; }
  else if (nivel == "alerta") { fondo = TFT_RED; tinta = TFT_WHITE; }
  dibujar(fondo, tinta, "B: detalle", envolver(pantalla, COLUMNAS));
}

static void mostrarDetalle() {
  vista = Vista::Detalle;
  int paginas = max(1, (int)((lineasDetalle.size() + FILAS - 1) / FILAS));
  String titulo = "Detalle " + String(paginaDetalle + 1) + "/" + String(paginas);
  dibujar(TFT_NAVY, TFT_WHITE, titulo, lineasDetalle, paginaDetalle * FILAS);
}

// ---------------------------------------------------------------- sensor

static void iniciarSensor() {
  const int sda = M5.getPin(m5::pin_name_t::port_a_sda);  // G9 en el StickS3
  const int scl = M5.getPin(m5::pin_name_t::port_a_scl);  // G10 en el StickS3
  sensorListo = sht3x.begin(&Wire, SHT3X_I2C_ADDR, sda, scl, 400000U) &&
                qmp.begin(&Wire, QMP6988_SLAVE_ADDRESS_L, sda, scl, 400000U);
  diagnostico(String("ENV III en SDA=") + sda + " SCL=" + scl + ": " + (sensorListo ? "OK" : "no detectado"));
}

static void leerSensor() {
  if (LECTURA_DE_EJEMPLO) {
    ultima = {26.4f, NAN, NAN, true};
    return;
  }
  if (!sensorListo) iniciarSensor();
  if (sensorListo && sht3x.update() && qmp.update()) {
    ultima = {sht3x.cTemp, sht3x.humidity, qmp.pressure / 100.0f, true};  // Pa -> hPa
  } else {
    ultima.valida = false;
    sensorListo = false;  // se reintenta en la siguiente lectura (por si se reconecta el cable)
  }
}

// ---------------------------------------------------------------- comunicación USB

// Escribe la lectura como UNA línea JSON en el puerto serie USB.
static void enviarLectura() {
  if (!ultima.valida) { mostrarError("Sin lectura del sensor. Revisar el cable Grove del ENV III."); return; }
  if (!HWCDC::isConnected()) { mostrarError("USB sin computador. Usar un cable USB-C de datos."); return; }

  JsonDocument cuerpo;
  cuerpo["dispositivo"] = DISPOSITIVO;
  cuerpo["ciudad"] = CIUDAD;
  cuerpo["temperatura_c"] = serialized(String(ultima.temperatura_c, 1));
  if (!isnan(ultima.humedad_pct)) cuerpo["humedad_pct"] = serialized(String(ultima.humedad_pct, 1));
  if (!isnan(ultima.presion_hpa)) cuerpo["presion_hpa"] = serialized(String(ultima.presion_hpa, 1));
  serializeJson(cuerpo, Serial);
  Serial.println();

  vista = Vista::Esperando;
  inicioEspera = millis();
  dibujar(TFT_NAVY, TFT_WHITE, "Consultando...", envolver("El agente compara el interior con el exterior", COLUMNAS));
}

// Procesa una línea JSON recibida del puente: la respuesta del agente o un error.
static void procesarRespuesta(const String& linea) {
  JsonDocument r;
  if (deserializeJson(r, linea)) { diagnostico("linea ignorada (no es JSON): " + linea.substring(0, 60)); return; }
  if (!r["error"].isNull()) { mostrarError(String("Puente: ") + (r["error"] | "")); return; }
  pantalla = aAscii(r["pantalla"] | "");
  nivel = String(r["nivel"] | "");
  lineasDetalle = envolver(aAscii(r["detalle"] | ""), COLUMNAS);
  if (pantalla.isEmpty()) { mostrarError("La respuesta no trae el campo pantalla."); return; }
  diagnostico("respuesta recibida: nivel=" + nivel);
  mostrarRespuesta();
}

// Lee sin bloquear lo que llega por USB y procesa cada línea completa.
static void atenderUsb() {
  while (Serial.available()) {
    const char c = (char)Serial.read();
    if (c == '\n') {
      entrada.trim();
      if (entrada.startsWith("{")) procesarRespuesta(entrada);
      entrada = "";
    } else if (entrada.length() < 4096) {
      entrada += c;
    }
  }
}

// ---------------------------------------------------------------- programa principal

void setup() {
  Serial.setRxBufferSize(4096);  // la respuesta del agente puede superar el búfer por defecto (256 B)
  auto cfg = M5.config();
  cfg.serial_baudrate = 115200;  // en USB nativo la velocidad es simbólica, pero el puente usa la misma
  M5.begin(cfg);
  M5.Power.setExtOutput(true);  // en el StickS3 los 5 V del puerto Grove vienen apagados
  M5.Display.setRotation(1);
  M5.Display.setBrightness(128);

  dibujar(TFT_BLACK, TFT_WHITE, "Iniciando", {String("Sensor ENV III...")});
  delay(200);
  if (!LECTURA_DE_EJEMPLO) iniciarSensor();
  leerSensor();
  diagnostico(String("StickS3 listo. WiFi apagada. Dispositivo=") + DISPOSITIVO + " ciudad=" + CIUDAD);
  mostrarLectura();
}

void loop() {
  M5.update();
  atenderUsb();

  static uint32_t ultimaLectura = 0;
  if (millis() - ultimaLectura >= 2000) {
    ultimaLectura = millis();
    leerSensor();
    if (vista == Vista::Lectura) mostrarLectura();
  }

  if (ENVIO_AUTOMATICO_S > 0 && vista != Vista::Esperando) {
    static uint32_t ultimoEnvio = 0;
    if (millis() - ultimoEnvio >= (uint32_t)ENVIO_AUTOMATICO_S * 1000UL) {
      ultimoEnvio = millis();
      if (ultima.valida && HWCDC::isConnected()) enviarLectura();
    }
  }

  if (vista == Vista::Esperando && millis() - inicioEspera > ESPERA_RESPUESTA_MS) {
    mostrarError("Sin respuesta del Mac. Revisar que puente_serial.py este corriendo y n8n encendido.");
  }

  if (M5.BtnA.wasClicked() && vista != Vista::Esperando) enviarLectura();

  if (M5.BtnB.wasClicked()) {
    if (vista == Vista::Respuesta) {
      paginaDetalle = 0;
      mostrarDetalle();
    } else if (vista == Vista::Detalle && (paginaDetalle + 1) * FILAS < (int)lineasDetalle.size()) {
      paginaDetalle++;
      mostrarDetalle();
    } else {
      mostrarLectura();
    }
  }
  delay(10);
}
