# 🎥 YouTube Live Manager

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![OBS](https://img.shields.io/badge/OBS%20Studio-29%2B-purple.svg)](https://obsproject.com/)

**Sistema de automatización profesional para transmisiones en vivo de YouTube** usando Flask, OBS Studio WebSockets y la YouTube Data API v3. Programa, gestiona y controla tus streams directamente desde un panel web.

---

## ✨ Características principales

- 📅 **Programación Recurrente**: Agenda transmisiones por días de la semana con horas específicas de inicio y fin.
- 🔄 **Persistencia Automática**: Las programaciones se guardan en `schedules.json` y sobreviven a reinicios del servidor.
- 🎬 **Control Remoto de OBS**: Cambio automático de escenas, configuración de Stream Keys y control de inicio/parada del encoder.
- 📺 **Multi-Programa**: Gestiona múltiples "Programas", cada uno con su propia Stream Key permanente y escena asociada.
- 👶 **Cumplimiento COPPA**: Declaración automática de "Contenido para niños" para evitar bloqueos de YouTube.
- 🌐 **Panel Web Profesional**: Interfaz responsive construida con Flask y Jinja2 para gestión visual.
- ⏰ **Manejo de Zonas Horarias**: Soporte completo para `pytz` (configurado por defecto para `America/Buenos_Aires`).
- 🎯 **Transiciones Inteligentes**: Polling automático del estado del stream antes de transicionar a `live` (evita el error `Invalid transition`).

---

## 📋 Requisitos previos

- **Python 3.10 o superior**
- **OBS Studio 29+** con el plugin `obs-websocket` v5 habilitado (incluido por defecto en versiones recientes).
- Una cuenta de Google Cloud con la **YouTube Data API v3** habilitada.
- Credenciales OAuth 2.0 (`client_secrets.json`).

---

## 🚀 Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/tu-usuario/youtube-live-manager.git
cd youtube-live-manager