# Convertidor YouTube → Audio

Aplicación web interna, con un flujo parecido al de y2mate: pegas un enlace, ves el video, eliges formato y calidad, y lo agregas a una **cola de descargas**. Puedes seguir agregando videos mientras los anteriores se convierten.

**Formatos:** MP3, M4A (AAC) y OPUS con calidad de 128 a 320 kbps; WAV y FLAC sin pérdida.

- **Backend:** Python + Flask
- **Descarga:** [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- **Conversión:** ffmpeg
- **Frontend:** HTML, CSS y JS sin dependencias, adaptado a celular y con modo oscuro

## Requisitos

- Python 3.10 o superior
- ffmpeg instalado y disponible en el PATH (`ffmpeg -version`)
  - Windows: `winget install ffmpeg`
  - macOS: `brew install ffmpeg`
  - Ubuntu/Debian: `sudo apt install ffmpeg`

## Instalación y uso

### Windows (recomendado)

Doble clic en **`iniciar.bat`**. La primera vez instala todo; después solo actualiza yt-dlp y abre el navegador en http://127.0.0.1:5000. Para cerrar la app, cierra la ventana negra.

### Manual (cualquier sistema)

```bash
cd youtube-mp3
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Abre http://127.0.0.1:5000

## Cómo funciona

1. Pega el enlace y pulsa **Buscar**.
2. Elige el **formato** y la **calidad**. La app recuerda la última elección.
3. Pulsa **Agregar a la cola**. El campo queda libre para el siguiente enlace.
4. Cada video muestra su estado: en espera (con su posición), descargando, convirtiendo o listo.
5. Al terminar, el archivo se descarga solo. Si desmarcas *Descargar al terminar*, usa el botón **Descargar** de cada video.
6. **Cancelar** saca de la cola un video en espera; **Quitar terminados** limpia la lista.

| Endpoint | Descripción |
|----------|-------------|
| `POST /api/info` | Valida el enlace y devuelve título, canal, duración, miniatura y formatos |
| `POST /api/convert` | Agrega un video a la cola (`url`, `format`, `bitrate`) |
| `GET /api/jobs` | Estado de toda la cola |
| `DELETE /api/jobs/<id>` | Cancela un trabajo en espera o quita uno terminado |
| `GET /api/download/<id>` | Entrega el archivo con el título del video como nombre |

Los archivos terminados se borran solos a los 30 minutos.

## Configuración (variables de entorno)

| Variable | Default | Uso |
|----------|---------|-----|
| `HOST` | `127.0.0.1` | Usa `0.0.0.0` para abrirla a la red local |
| `PORT` | `5000` | Puerto |
| `MAX_DURATION_SECONDS` | `3600` | Duración máxima permitida por video |
| `FILE_TTL_SECONDS` | `1800` | Tiempo que se conservan los MP3 |
| `WORKERS` | `2` | Videos que se convierten al mismo tiempo; el resto espera en la cola |
| `DOWNLOAD_DIR` | `./downloads` | Carpeta temporal |

## Mantenimiento

YouTube cambia su plataforma con frecuencia. `iniciar.bat` actualiza yt-dlp en cada arranque. Si usas el modo manual y las descargas empiezan a fallar, actualiza yt-dlp:

```bash
pip install -U yt-dlp
```

## Aviso legal

Úsala solo con contenido propio, con licencia libre (por ejemplo, Creative Commons) o sobre el que tengas derechos. Los Términos de Servicio de YouTube restringen la descarga de contenido de terceros.
