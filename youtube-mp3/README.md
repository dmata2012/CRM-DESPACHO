# Convertidor YouTube → MP3

Aplicación web interna, con un flujo parecido al de y2mate: pegas un enlace, ves el video, eliges la calidad, se convierte y descargas el MP3.

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

| Paso | Endpoint | Descripción |
|------|----------|-------------|
| 1 | `POST /api/info` | Valida el enlace y devuelve título, canal, duración y miniatura |
| 2 | `POST /api/convert` | Crea un trabajo de conversión en segundo plano (128/192/256/320 kbps) |
| 3 | `GET /api/status/<id>` | Devuelve el progreso; la interfaz lo consulta cada segundo |
| 4 | `GET /api/download/<id>` | Entrega el MP3 con el título del video como nombre de archivo |

Los archivos generados se borran solos cuando pasan los 30 minutos.

## Configuración (variables de entorno)

| Variable | Default | Uso |
|----------|---------|-----|
| `HOST` | `127.0.0.1` | Usa `0.0.0.0` para abrirla a la red local |
| `PORT` | `5000` | Puerto |
| `MAX_DURATION_SECONDS` | `3600` | Duración máxima permitida por video |
| `FILE_TTL_SECONDS` | `1800` | Tiempo que se conservan los MP3 |
| `DOWNLOAD_DIR` | `./downloads` | Carpeta temporal |

## Mantenimiento

YouTube cambia su plataforma con frecuencia. `iniciar.bat` actualiza yt-dlp en cada arranque. Si usas el modo manual y las descargas empiezan a fallar, actualiza yt-dlp:

```bash
pip install -U yt-dlp
```

## Aviso legal

Úsala solo con contenido propio, con licencia libre (por ejemplo, Creative Commons) o sobre el que tengas derechos. Los Términos de Servicio de YouTube restringen la descarga de contenido de terceros.
