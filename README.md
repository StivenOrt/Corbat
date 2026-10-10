# Corbat

Asistente de voz para Windows, **100 % gratuito y local**. Lo llamas con "oye Corbat" y controla tu
computador por voz: abre y cierra aplicaciones, maneja el volumen, busca en internet, controla Spotify
y envía mensajes o hace llamadas por WhatsApp. El reconocimiento de voz, el modelo de lenguaje y la voz
corren en tu equipo; nada de eso depende de servicios de pago.

Funciona como Siri: en reposo solo escucha lo mínimo, y al oír su nombre despierta, muestra un orbe
flotante y carga los modelos pesados. Tras un rato sin hablarle vuelve a reposo y libera la memoria.

## Qué puede hacer

- "Oye Corbat, abre Spotify / cierra Brave / abre el bloc de notas" (cualquier app instalada).
- "Oye Corbat, sube el volumen", "¿qué hora es?", "busca en internet…".
- "Oye Corbat, pon algo de Daddy Yankee", "reproduce mis me gusta", "pausa", "siguiente".
- "Oye Corbat, mándale un WhatsApp a Mario…" o "llama a mamá" (siempre te pide confirmación por voz).
- Apagar el equipo o forzar el cierre de una app, también con confirmación por voz.

## Requisitos

- Windows 10 u 11.
- Un micrófono.
- Unos 8 GB de RAM libres cuando está despierto y ~6 GB de disco (modelos incluidos).
- Python 3.12 o 3.11 (el instalador lo puede instalar con winget).

## Instalación

1. Descarga el proyecto (botón **Code > Download ZIP** en GitHub, o `git clone`) y descomprímelo.
2. Haz doble clic en **`instalar.bat`**. Prepara un entorno virtual, instala las dependencias,
   descarga la voz, el modelo de lenguaje con Ollama, los modelos de Whisper y, si quieres, crea el
   arranque automático. La primera vez tarda por las descargas.
3. Arranca Corbat con **`scripts\iniciar_corbat.bat`** (con consola, para probar) y di
   "oye Corbat".

Si algo falla, el instalador te dice qué quedó pendiente; puedes volver a ejecutarlo sin problema.

## Spotify y contactos (opcional)

Ejecuta **`configurar.bat`**. Te guía paso a paso para:

- **Spotify:** creas tu propia app gratuita en el panel de desarrolladores, pegas el *Client ID* y
  autorizas a Corbat. Hace falta una cuenta de Spotify; el control de reproducción funciona mejor con
  Premium.
- **Contactos de Google:** creas tus credenciales de Google Cloud (gratis) y Corbat guarda una copia
  local de tus contactos.
- **Contactos desde archivo:** copia un `.vcf` o un `contactos*.csv` a la carpeta `datos`.

Cada persona usa sus propias credenciales: no se comparten entre equipos.

## Estructura

```
main.py            arranque
instalar.bat       instalación guiada
configurar.bat     Spotify y contactos
scripts/           iniciar_corbat.bat (con consola) y corbat_oculto.vbs (sin ventana)
datos/             log, tokens y contactos (no se sube a git)
voces/             voz de Piper (no se sube a git)
corbat/
  asistente.py     bucle principal y modo reposo
  atajos.py        órdenes rápidas sin pasar por el modelo de lenguaje
  audio/           activación, Whisper, voz y confirmaciones
  interfaz/        orbe flotante
  acciones/        aplicaciones, volumen, archivos, WhatsApp
  musica/          Spotify
  contactos/       vCard, CSV y Google
  herramientas/    diagnósticos
```

## Comandos útiles

| Para | Comando |
|---|---|
| Reconectar Spotify | `.venv\Scripts\python -m corbat.musica.spotify_api` |
| Diagnóstico de Spotify | `.venv\Scripts\python -m corbat.herramientas.diagnostico_spotify` |
| Ver qué contactos lee Corbat | `.venv\Scripts\python -m corbat.contactos.agenda` |
| Ver qué apps detecta | `.venv\Scripts\python -m corbat.acciones.aplicaciones` |

## Seguridad y privacidad

- Todo se procesa en tu equipo. Solo salen a internet las búsquedas web y las llamadas a Spotify/Google
  que tú configures.
- El modelo de lenguaje solo puede usar una lista cerrada de acciones; no ejecuta comandos libres.
- Apagar, forzar el cierre y enviar mensajes o llamadas piden confirmación por voz; si no se entiende
  o no respondes, se cancela.
- Los textos de los mensajes de WhatsApp no se guardan en el log (`datos/acciones.log`).
- `datos/` contiene tokens y contactos: no lo compartas ni lo subas.

## Solución de problemas

- **Se activa con ruidos:** revisa `datos/acciones.log` y ajusta `UMBRAL_NOMBRE_REPOSO` en
  `corbat/asistente.py`.
- **No oye bien:** cambia `DISPOSITIVO` en `corbat/audio/activacion.py` por el número de tu micrófono.
- **Tarda al despertar:** es normal la primera vez tras el reposo, porque carga los modelos.
- **No arranca sin consola:** ejecuta `scripts\iniciar_corbat.bat` para ver el error.
