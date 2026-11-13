"""Simula el StickS3 de la Práctica 3: envía lecturas de ejemplo al webhook /ambiente.

Sirve para hacer la práctica sin el dispositivo físico. Cada perfil se envía
como lo haría el puente USB serial (POST JSON) y se muestra la respuesta tal
como aparecería en la pantalla.

Uso (desde la raíz del repo):
    uv run scripts/simular_gadget.py
    uv run scripts/simular_gadget.py --url http://localhost:5678/webhook-test/ambiente
    uv run scripts/simular_gadget.py --ciudad Medellin --pausa 0
"""
import argparse
import json
import time
import urllib.error
import urllib.request

PERFILES = [
    ("confortable", {"temperatura_c": 22.5, "humedad_pct": 50.0, "presion_hpa": 752.0}),
    ("caluroso y húmedo", {"temperatura_c": 30.8, "humedad_pct": 76.0, "presion_hpa": 752.0}),
    ("frío", {"temperatura_c": 16.0, "humedad_pct": 45.0, "presion_hpa": 752.0}),
    ("solo temperatura (sensor sin humedad)", {"temperatura_c": 26.4}),
    ("inválido (humedad 150 %)", {"temperatura_c": 22.0, "humedad_pct": 150.0, "presion_hpa": 752.0}),
]
COLORES = {"ok": "verde", "atencion": "amarillo", "alerta": "rojo"}


def enviar(url: str, cuerpo: dict) -> tuple[int, dict | str, float]:
    datos = json.dumps(cuerpo).encode("utf-8")
    pedido = urllib.request.Request(url, data=datos, headers={"Content-Type": "application/json"})
    inicio = time.monotonic()
    try:
        with urllib.request.urlopen(pedido, timeout=60) as r:
            codigo, texto = r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        codigo, texto = e.code, e.read().decode("utf-8")
    segundos = time.monotonic() - inicio
    try:
        return codigo, json.loads(texto), segundos
    except json.JSONDecodeError:
        return codigo, texto, segundos


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://localhost:5678/webhook/ambiente")
    parser.add_argument("--ciudad", default="Bogota")
    parser.add_argument("--pausa", type=float, default=20, help="segundos entre perfiles (límite por minuto de Groq)")
    args = parser.parse_args()

    for i, (nombre, lectura) in enumerate(PERFILES):
        if i and args.pausa:
            time.sleep(args.pausa)
        cuerpo = {"dispositivo": "simulador", "ciudad": args.ciudad, **lectura}
        print(f"\n=== {nombre}: {json.dumps(lectura)}")
        try:
            codigo, resp, seg = enviar(args.url, cuerpo)
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"  sin conexión: {e}")
            continue
        print(f"  HTTP {codigo} en {seg:.1f} s")
        if codigo == 200 and isinstance(resp, dict):
            pantalla = resp.get("pantalla", "")
            print(f"  pantalla ({len(pantalla)} car., fondo {COLORES.get(resp.get('nivel'), '?')}): {pantalla}")
            print(f"  detalle: {resp.get('detalle', '')}")
        else:
            print(f"  respuesta: {resp}")


if __name__ == "__main__":
    main()
