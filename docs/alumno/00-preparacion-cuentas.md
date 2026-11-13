# Preparación: cuentas y credenciales

Este procedimiento se completa **antes de la primera sesión**. Todos los servicios son gratuitos, excepto DeepSeek, que es opcional.

| Cuenta | Uso | Prácticas | Costo |
|---|---|---|---|
| n8n (Cloud o local) | Construcción y ejecución de los flujos | P0, P1, P2 | Gratuito (Cloud: prueba de 14 días) |
| Groq | Modelos de lenguaje gratuitos | P1, P2 (modalidad gratuita) | Gratuito, con límites de uso |
| DeepSeek | Modelos de lenguaje de pago | P1, P2 (modalidad de pago, opcional) | Pago por uso |
| GitHub y Render | Publicación del servicio de ML de la P2 | Solo P2, si se despliega un servicio propio | Gratuito |
| VS Code con PlatformIO IDE | Firmware del StickS3 | Solo P3, si se usa el dispositivo físico | Gratuito |

**Nota:** la P0 no utiliza inteligencia artificial; para ella solo se requiere n8n.

---

## 1. n8n

Se elige **una** de las dos opciones siguientes.

### Opción A: n8n Cloud (recomendada, sin instalación)

1. Ingresar a **https://n8n.io/cloud/** y seleccionar **Get started for free**.
2. Registrarse con un correo electrónico o con una cuenta de Google o GitHub, y verificar el correo.
3. n8n asigna una URL propia con el formato `https://<espacio>.app.n8n.cloud`.
4. Para crear un flujo: **Workflows → + Add workflow** (o **Create workflow**). Para importar un flujo del repositorio: menú **⋯** (esquina superior derecha) → **Import from File**.

**Nota:** la prueba gratuita dura 14 días. Al vencer, es posible crear una cuenta nueva o pasar a la opción B.

### Opción B: n8n local con Docker

Con Docker Desktop instalado, ejecutar:

```bash
docker volume create n8n_data
docker run -d --name n8n -p 5678:5678 -v n8n_data:/home/node/.n8n \
  -e GENERIC_TIMEZONE=America/Bogota -e TZ=America/Bogota \
  --restart unless-stopped docker.n8n.io/n8nio/n8n
```

A continuación, abrir **http://localhost:5678** y crear el usuario administrador. Sin Docker, pero con Node.js instalado, la alternativa es `npx n8n`.

---

## 2. Groq (modalidad gratuita, P1 y P2)

1. Ingresar a **https://console.groq.com** y seleccionar **Sign in** (con Google o GitHub).
2. Aceptar los términos de uso.
3. Abrir **API Keys → Create API Key**, asignar un nombre (por ejemplo, `n8n-practicas`) y **copiar la clave** (comienza por `gsk_`). La clave solo se muestra una vez.
4. En n8n: menú lateral **Credentials → + Add credential** → buscar **Groq** → pegar la clave → nombre **`Groq account`** → **Save**.

**Importante:** la credencial debe llamarse exactamente `Groq account`. Las plantillas buscan ese nombre y la asignan de forma automática al importarse.

Los límites del plan gratuito se describen en [modalidades-y-restricciones.md](modalidades-y-restricciones.md).

---

## 3. DeepSeek (modalidad de pago, opcional)

1. Ingresar a **https://platform.deepseek.com** y crear una cuenta.
2. En **Top up**, recargar el saldo mínimo. Unos pocos dólares cubren el curso completo.
3. Abrir **API Keys → Create new API key** y copiar la clave (comienza por `sk-`).
4. En n8n: **Credentials → + Add credential** → **DeepSeek** → pegar la clave → nombre **`DeepSeek account`** → **Save**.

---

## 4. GitHub y Render (solo P2, opcional)

El servicio de ML que utiliza la P2 ya está publicado por el profesor. Estas cuentas solo son necesarias para **desplegar una copia propia**:

1. Crear una cuenta en **https://github.com/signup**.
2. Ingresar a **https://dashboard.render.com** con **Sign in with GitHub** y crear un *workspace* (plan Free, sin tarjeta).

El procedimiento de despliegue se encuentra en el [apéndice de la Práctica 2](03-practica-2-agentes-avanzado.md#apéndice-despliegue-de-un-servicio-propio-en-render).

---

## 5. PlatformIO (solo P3 con dispositivo, opcional)

La P3 puede realizarse con el simulador, sin hardware. Para cargar el firmware en un StickS3:

1. Instalar **Visual Studio Code** desde **https://code.visualstudio.com**.
2. En VS Code, abrir **Extensions** (barra lateral), buscar **PlatformIO IDE** e instalarla.
3. Esperar a que la extensión termine de instalar su núcleo (aviso en la esquina inferior derecha) y reiniciar VS Code.
4. Instalar **uv** (ejecuta el puente USB de la P3 e instala `pyserial`): en macOS, `brew install uv`, o seguir **https://docs.astral.sh/uv/getting-started/installation/**.
5. Conseguir un cable USB-C **de datos**: el StickS3 se comunica con el computador por ese cable, sin WiFi.

---

## Lista de verificación previa a la primera sesión

- [ ] n8n (Cloud o local) abre el editor correctamente.
- [ ] La credencial `Groq account` está creada (necesaria para P1 y P2).
- [ ] (Opcional) La credencial `DeepSeek account` está creada.
- [ ] El repositorio está descargado (**Code → Download ZIP** en GitHub, o `git clone`).
