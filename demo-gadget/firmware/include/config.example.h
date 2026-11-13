// Configuración opcional. El firmware compila sin este archivo, con los valores por defecto.
// Para cambiarlos: copiar este archivo como config.h (en la misma carpeta) y editarlo.
// No hay claves ni direcciones de red: el StickS3 se comunica solo por USB-C, con la WiFi apagada.
#pragma once

// Nombre con el que el dispositivo aparece en las ejecuciones de n8n (campo "dispositivo").
#define DISPOSITIVO "sticks3"

// Ciudad con la que el agente consulta el clima exterior (servicio /clima de la P0).
#define CIUDAD "Bogota"

// Envío automático cada N segundos, además del botón A. 0 = solo con el botón A.
// Con Groq gratis, no bajar de 60 s (límite de tokens por minuto).
#define ENVIO_AUTOMATICO_S 0

// 1 = no leer el sensor y enviar siempre {"temperatura_c":26.4}.
// Sirve para probar el enlace USB -> puente -> n8n sin el sensor conectado.
#define LECTURA_DE_EJEMPLO 0
