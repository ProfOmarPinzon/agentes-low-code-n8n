# /// script
# requires-python = ">=3.10"
# dependencies = ["pyserial>=3.5"]
# ///
"""Puente USB serial -> n8n para la Práctica 3 (StickS3 sin WiFi).

Lee del puerto serie USB del StickS3 una línea JSON por lectura, la valida y la
envía por POST (Content-Type: application/json) al webhook local de n8n. La
respuesta del agente vuelve al dispositivo por el mismo cable, también como una
línea JSON. Todo ocurre en el Mac: no se usa la red corporativa ni internet
(salvo lo que el propio flujo de n8n necesite, como el modelo y Open-Meteo).

Cada mensaje del registro lleva una etiqueta que indica dónde falló la comunicación:

    [SERIAL]       el cable o el puerto (no existe, ocupado, desconectado)
    [DISPOSITIVO]  mensajes de diagnóstico del firmware (líneas "# ...")
    [LECTURA]      la línea llegó, pero no es una lectura válida
    [N8N]          el POST al webhook (n8n apagado, flujo sin publicar, error del flujo)
    [RESPUESTA]    n8n respondió, pero la respuesta no se puede entregar al dispositivo

Uso (desde la raíz del repositorio; uv instala pyserial la primera vez):
    uv run demo-gadget/puente/puente_serial.py --listar
    uv run demo-gadget/puente/puente_serial.py --puerto /dev/cu.usbmodem101
    uv run demo-gadget/puente/puente_serial.py --puerto /dev/cu.usbmodem101 \\
        --url http://localhost:5678/webhook-test/ambiente
    uv run demo-gadget/puente/puente_serial.py --puerto /dev/cu.usbmodem101 --sin-envio
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import math
import os
import sys
import time
import urllib.error
import urllib.request

try:
    import serial  # pyserial
except ImportError:  # pragma: no cover - mensaje para quien no use uv
    sys.exit("Falta pyserial. Ejecutar con:  uv run demo-gadget/puente/puente_serial.py ...")

URL_POR_DEFECTO = os.environ.get("N8N_WEBHOOK_URL", "http://localhost:5678/webhook/ambiente")
CAMPOS_OPCIONALES = ("humedad_pct", "presion_hpa")

log = logging.getLogger("puente")


class LecturaInvalida(ValueError):
    """La línea recibida no es una lectura que se pueda enviar a n8n."""


class ErrorN8n(RuntimeError):
    """El POST al webhook falló. `para_dispositivo` es el texto corto que se muestra en la pantalla."""

    def __init__(self, detalle: str, para_dispositivo: str):
        super().__init__(detalle)
        self.para_dispositivo = para_dispositivo


# ---------------------------------------------------------------- puertos


def puertos_usb() -> list[str]:
    """Puertos serie USB de macOS. Se usa /dev/cu.* (no /dev/tty.*) porque no espera la señal DCD."""
    return sorted(glob.glob("/dev/cu.usbmodem*") + glob.glob("/dev/cu.usbserial*"))


def elegir_puerto(indicado: str | None) -> str:
    if indicado:
        return indicado
    candidatos = puertos_usb()
    if len(candidatos) == 1:
        log.info("[SERIAL] puerto detectado automáticamente: %s", candidatos[0])
        return candidatos[0]
    if not candidatos:
        sys.exit("[SERIAL] no hay ningún /dev/cu.usbmodem*: conectar el StickS3 con un cable USB-C de DATOS "
                 "y revisar con  ls /dev/cu.*")
    sys.exit("[SERIAL] hay varios puertos USB; indicar uno con --puerto:\n  " + "\n  ".join(candidatos))


def abrir_puerto(puerto: str, baudios: int) -> serial.Serial:
    s = serial.Serial()
    s.port = puerto
    s.baudrate = baudios
    s.timeout = 0.5
    # DTR y RTS en bajo: en el USB nativo del ESP32-S3 ciertas combinaciones reinician el chip.
    s.dtr = False
    s.rts = False
    s.exclusive = True
    s.open()
    s.reset_input_buffer()  # descarta una línea a medias que hubiera quedado de antes
    return s


# ---------------------------------------------------------------- lectura


def validar_lectura(linea: str) -> dict:
    """Convierte la línea en el cuerpo del POST. Lanza LecturaInvalida con la causa."""
    try:
        datos = json.loads(linea)
    except json.JSONDecodeError as e:
        raise LecturaInvalida(f"no es JSON válido ({e.msg}, columna {e.colno})") from None
    if not isinstance(datos, dict):
        raise LecturaInvalida("el JSON no es un objeto {...}")

    # Se acepta "device" (formato de referencia) como sinónimo de "dispositivo", que es el que usa el flujo.
    if "dispositivo" not in datos and "device" in datos:
        datos["dispositivo"] = datos.pop("device")

    def numero(campo: str) -> float:
        valor = datos[campo]
        if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor):
            raise LecturaInvalida(f"{campo} debe ser un número, llegó {valor!r}")
        return float(valor)

    if "temperatura_c" not in datos:
        raise LecturaInvalida("falta el campo temperatura_c")
    datos["temperatura_c"] = numero("temperatura_c")
    for campo in CAMPOS_OPCIONALES:
        if datos.get(campo) is None:
            datos.pop(campo, None)
        else:
            datos[campo] = numero(campo)
    # Los rangos físicos (por ejemplo, humedad entre 0 y 100 %) los valida el flujo de n8n
    # con el nodo "¿Lectura válida?", que responde 400 sin invocar al modelo.
    return datos


# ---------------------------------------------------------------- n8n


def enviar_a_n8n(url: str, cuerpo: dict, timeout: float) -> dict:
    """POST JSON al webhook. Devuelve la respuesta del agente o lanza ErrorN8n con la causa."""
    pedido = urllib.request.Request(
        url,
        data=json.dumps(cuerpo).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(pedido, timeout=timeout) as r:
            codigo, texto = r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        codigo, texto = e.code, e.read().decode("utf-8", "replace")
    except urllib.error.URLError as e:
        raise ErrorN8n(f"n8n no responde en {url}: {e.reason}. ¿Está encendido? (docker ps)",
                       "n8n no responde en el Mac") from None
    except TimeoutError:
        raise ErrorN8n(f"n8n no respondió en {timeout:.0f} s (el modelo o la herramienta tardan demasiado)",
                       "n8n tardo demasiado") from None

    if codigo == 404:
        if "/webhook-test/" in url:
            causa = ("la URL de prueba solo atiende una petición después de pulsar 'Execute workflow' "
                     "en el editor; pulsarlo de nuevo o usar la URL de producción")
        else:
            causa = "el flujo P3 no está publicado (Publish) o la ruta no es /webhook/ambiente"
        raise ErrorN8n(f"HTTP 404: {causa}. Respuesta: {texto[:200]}", "HTTP 404: flujo sin publicar")
    if codigo == 400:
        raise ErrorN8n(f"HTTP 400: el flujo rechazó la lectura (fuera de rango). Respuesta: {texto[:200]}",
                       "Lectura fuera de rango (400)")
    if codigo != 200:
        raise ErrorN8n(f"HTTP {codigo}: error dentro del flujo; revisar Executions en n8n. Respuesta: {texto[:200]}",
                       f"HTTP {codigo}: ver Executions")
    try:
        respuesta = json.loads(texto)
    except json.JSONDecodeError:
        raise ErrorN8n(f"HTTP 200 pero la respuesta no es JSON: {texto[:200]}", "Respuesta de n8n no es JSON") from None
    if not isinstance(respuesta, dict) or not respuesta.get("pantalla"):
        raise ErrorN8n(f"HTTP 200 sin el campo 'pantalla': {texto[:200]}", "Respuesta sin pantalla")
    return respuesta


# ---------------------------------------------------------------- dispositivo


def responder(s: serial.Serial, mensaje: dict) -> None:
    """Envía al dispositivo UNA línea JSON (la respuesta del agente o {"error": ...})."""
    try:
        s.write((json.dumps(mensaje, ensure_ascii=False) + "\n").encode("utf-8"))
        s.flush()
    except serial.SerialException as e:
        log.error("[RESPUESTA] no se pudo escribir en el puerto: %s", e)
        raise


def atender_linea(s: serial.Serial, linea: str, args: argparse.Namespace) -> None:
    if not linea:
        return
    if not linea.startswith("{"):
        log.info("[DISPOSITIVO] %s", linea.removeprefix("# "))
        return
    try:
        cuerpo = validar_lectura(linea)
    except LecturaInvalida as e:
        log.warning("[LECTURA] descartada: %s. Línea: %s", e, linea[:200])
        responder(s, {"error": f"Lectura invalida: {e}"[:120]})
        return

    log.info("[LECTURA] %s", json.dumps(cuerpo, ensure_ascii=False))
    if args.sin_envio:
        log.info("[N8N] --sin-envio: no se envía a n8n")
        responder(s, {"pantalla": "Puente OK (sin envio a n8n)", "nivel": "ok",
                      "detalle": "La lectura llego al Mac por USB. Quitar --sin-envio para consultar al agente."})
        return

    inicio = time.monotonic()
    try:
        respuesta = enviar_a_n8n(args.url, cuerpo, args.timeout)
    except ErrorN8n as e:
        log.error("[N8N] %s", e)
        responder(s, {"error": e.para_dispositivo})
        return
    log.info("[N8N] HTTP 200 en %.1f s: nivel=%s pantalla=%r",
             time.monotonic() - inicio, respuesta.get("nivel"), respuesta.get("pantalla"))
    responder(s, {k: respuesta.get(k, "") for k in ("pantalla", "nivel", "detalle")})


def bucle(puerto: str, args: argparse.Namespace) -> None:
    """Lee líneas del puerto para siempre; si el cable se desconecta, espera y reabre."""
    aviso_espera = False
    while True:
        try:
            s = abrir_puerto(puerto, args.baudios)
        except serial.SerialException as e:
            texto = str(e)
            if "Resource busy" in texto or "Could not exclusively lock" in texto:
                sys.exit(f"[SERIAL] {puerto} está ocupado: cerrar el Serial Monitor de PlatformIO "
                         "u otro programa que lo use, y volver a ejecutar el puente.")
            if not aviso_espera:
                log.error("[SERIAL] no se pudo abrir %s: %s. Puertos disponibles: %s. Reintentando cada 2 s...",
                          puerto, e, ", ".join(puertos_usb()) or "ninguno")
                aviso_espera = True
            time.sleep(2)
            continue

        aviso_espera = False
        log.info("[SERIAL] conectado a %s. Esperando lecturas (botón A del StickS3). Ctrl+C para salir.", puerto)
        log.info("[N8N] webhook: %s", args.url)
        pendiente = b""
        try:
            while True:
                pendiente += s.read(s.in_waiting or 1)
                while b"\n" in pendiente:
                    crudo, pendiente = pendiente.split(b"\n", 1)
                    try:
                        linea = crudo.decode("utf-8").strip()
                    except UnicodeDecodeError:
                        log.warning("[SERIAL] bytes no UTF-8 descartados (¿ruido o velocidad distinta?): %r", crudo[:60])
                        continue
                    atender_linea(s, linea, args)
                if len(pendiente) > 8192:
                    log.warning("[SERIAL] 8 KB sin salto de línea: se descartan")
                    pendiente = b""
        except (serial.SerialException, OSError) as e:
            log.error("[SERIAL] se perdió la conexión con %s (%s). ¿Se desconectó o reinició el StickS3? "
                      "Reintentando...", puerto, e)
            try:
                s.close()
            except Exception:
                pass
            time.sleep(2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--puerto", help="puerto serie, p. ej. /dev/cu.usbmodem101 (si se omite y hay uno solo, se detecta)")
    parser.add_argument("--url", default=URL_POR_DEFECTO,
                        help="URL del webhook de n8n (por defecto %(default)s; también variable N8N_WEBHOOK_URL)")
    parser.add_argument("--baudios", type=int, default=115200, help="velocidad del puerto (por defecto %(default)s)")
    parser.add_argument("--timeout", type=float, default=60, help="segundos de espera por la respuesta de n8n")
    parser.add_argument("--sin-envio", action="store_true", help="solo leer y validar; no llamar a n8n")
    parser.add_argument("--listar", action="store_true", help="mostrar los puertos USB disponibles y salir")
    parser.add_argument("--depurar", action="store_true", help="registro más detallado")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.depurar else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    if args.listar:
        print("\n".join(puertos_usb()) or "No hay puertos /dev/cu.usbmodem* ni /dev/cu.usbserial*")
        return
    try:
        bucle(elegir_puerto(args.puerto), args)
    except KeyboardInterrupt:
        log.info("Puente detenido.")


if __name__ == "__main__":
    main()
