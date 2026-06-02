# 🎥 YouTube Live Manager

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.3-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![OBS](https://img.shields.io/badge/OBS%20Studio-29%2B-purple.svg)](https://obsproject.com/)

**Sistema de automatización profesional para transmisiones en vivo de YouTube** usando Flask, OBS Studio WebSockets y la YouTube Data API v3. Programa, gestiona y controla tus streams directamente desde un panel web intuitivo.

---

## ✨ Características principales

### 📅 Programación Inteligente
- **Programación Recurrente**: Agenda transmisiones por días de la semana con horas específicas de inicio y fin.
- **Persistencia Automática**: Las programaciones se guardan en `schedules.json` y sobreviven a reinicios del servidor.
- **Manejo de Zonas Horarias**: Soporte completo para zonas horarias (configurable, por defecto `America/Buenos_Aires`).

### 🎬 Control Total de OBS
- **Control Remoto**: Cambio automático de escenas, configuración de Stream Keys y control de inicio/parada del encoder.
- **Multi-Programa**: Gestiona múltiples programas, cada uno con su propia Stream Key permanente y escena asociada.
- **Transiciones Inteligentes**: Polling automático del estado del stream antes de transicionar a `live` (evita errores de transición inválida).

### 🌐 Panel Web Profesional
- **Interfaz Responsive**: Dashboard moderno construido con Flask y Jinja2 para gestión visual completa.
- **Gestión Visual**: Configura programas, horarios y monitorea el estado de tus transmisiones en tiempo real.

### 🔒 Cumplimiento y Seguridad
- **COPPA Compliance**: Declaración automática de "Contenido para niños" para evitar bloqueos de YouTube.
- **OAuth 2.0**: Autenticación segura mediante Google Cloud.

---

## 📋 Requisitos previos

- **Python 3.10 o superior**
- **OBS Studio 29+** con el plugin `obs-websocket` v5 habilitado (incluido por defecto en versiones recientes)
- Cuenta de Google Cloud con la **YouTube Data API v3** habilitada
- Credenciales OAuth 2.0 (`client_secrets.json`)

---

## 🚀 Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/tu-usuario/youtube-live-manager.git
cd youtube-live-manager
```

### 2. Crear entorno virtual e instalar dependencias

```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configurar credenciales de Google Cloud

1. Ve a [Google Cloud Console](https://console.cloud.google.com/)
2. Crea un nuevo proyecto o selecciona uno existente
3. Habilita la **YouTube Data API v3**
4. Crea credenciales OAuth 2.0 (tipo "Aplicación de escritorio")
5. Descarga el archivo JSON y guárdalo como `client_secrets.json` en la raíz del proyecto

### 4. Configurar OBS Studio

1. Abre OBS Studio
2. Ve a **Herramientas → Configuración de WebSocket**
3. Activa el servidor WebSocket
4. Establece una contraseña (opcional pero recomendado)
5. Anota el puerto (por defecto: 4455)

---

## ⚙️ Configuración

Crea un archivo `.env` o configura las siguientes variables de entorno:

```bash
# Configuración de OBS
OBS_HOST=localhost
OBS_PORT=4455
OBS_PASSWORD=tu_contraseña  # Opcional

# Configuración de zona horaria
TIMEZONE=America/Buenos_Aires

# Puerto del servidor Flask
FLASK_PORT=5000
```

---

## 🎯 Uso

### Iniciar el servidor

```bash
python app.py
```

El servidor se iniciará en `http://localhost:5000`

### Primer acceso

1. Abre tu navegador y ve a `http://localhost:5000`
2. Serás redirigido a la autenticación de Google
3. Autoriza la aplicación para acceder a tu canal de YouTube
4. ¡Listo! Ya puedes comenzar a configurar tus programas

### Estructura del proyecto

```
youtube-live-manager/
├── app.py              # Aplicación Flask principal
├── scheduler.py        # Lógica de programación y automatización
├── youtube_api.py      # Integración con YouTube Data API
├── requirements.txt    # Dependencias de Python
├── templates/
│   └── dashboard.html  # Interfaz web del panel de control
├── schedules.json      # Almacenamiento persistente de programaciones
└── client_secrets.json # Credenciales OAuth (no versionar)
```

---

## 🧪 Pruebas

Ejecuta las pruebas unitarias del scheduler:

```bash
python test_scheduler.py
```

---

## 🛠️ Tecnologías utilizadas

| Tecnología | Versión | Propósito |
|------------|---------|-----------|
| **Python** | 3.10+ | Lenguaje base |
| **Flask** | 2.3.0 | Framework web |
| **APScheduler** | 3.10.4 | Programación de tareas |
| **google-api-python-client** | 2.108.0 | YouTube Data API |
| **requests** | 2.31.0 | Cliente HTTP para OBS WebSocket |
| **Jinja2** | - | Templates HTML |

---

## 🔧 Funcionalidades avanzadas

### Programas múltiples
Cada programa puede tener:
- Su propia Stream Key de YouTube
- Escena específica de OBS
- Horarios independientes
- Días de la semana configurables

### Transiciones automáticas
El sistema:
1. Verifica el estado actual del stream en YouTube
2. Espera hasta que sea válido realizar la transición
3. Cambia la escena en OBS
4. Inicia la transmisión automáticamente

### Persistencia de datos
- Todas las programaciones se guardan en `schedules.json`
- Los datos sobreviven a reinicios del servidor
- No se pierde ninguna configuración programada

---

## 📝 Notas importantes

- **Stream Keys**: Cada programa requiere una Stream Key única obtenida desde YouTube Studio
- **OBS WebSocket**: Asegúrate de que OBS esté ejecutándose antes de iniciar el servidor
- **Límites de API**: YouTube tiene límites de cuota para la API (10,000 unidades/día por defecto)
- **Zona horaria**: Todas las horas se interpretan según la zona horaria configurada

---

## 🤝 Contribuciones

Las contribuciones son bienvenidas. Por favor:

1. Haz un fork del repositorio
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

---

## 📄 Licencia

Este proyecto está bajo la Licencia MIT. Ver el archivo [LICENSE](LICENSE) para más detalles.

---

## 🆘 Soporte y Troubleshooting

### Problemas comunes

**Error: Invalid transition**
- El sistema ya incluye polling automático para evitar este error
- Verifica que OBS esté transmitiendo correctamente

**Error: Authentication failed**
- Verifica que `client_secrets.json` esté en la raíz del proyecto
- Asegúrate de haber habilitado la YouTube Data API v3

**OBS no conecta**
- Verifica que obs-websocket esté habilitado en OBS
- Confirma que el puerto y la contraseña sean correctos

---

## 📞 Contacto

Para soporte o preguntas, abre un issue en el repositorio.

---

<div align="center">

**¿Te gusta este proyecto? ¡Dale una estrella! ⭐**

Hecho con ❤️ para creadores de contenido

</div>