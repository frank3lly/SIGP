<div align="center">
  <img src="app/public/logo.svg" alt="SGIP Logo" width="280" />

  # SGIP - Sistema de Gestion Inteligente de Parqueos

  Monitoreo y navegacion de estacionamientos en tiempo real mediante vision artificial ligera y planos vectoriales interactivos.

  ---
</div>

## Proposito del Sistema

El Sistema de Gestion Inteligente de Parqueos (SGIP) optimiza la gestion y utilizacion de plazas de estacionamiento en campus educativos, establecimientos comerciales y edificios corporativos.

A traves de dispositivos de captura estrategicamente ubicados y algoritmos de vision artificial, el sistema determina de forma continua la disponibilidad de cada plaza y transmite su estado a un plano interactivo accesible desde cualquier dispositivo movil o de escritorio.

Los conductores visualizan con precision los espacios disponibles antes de entrar a un sector, reduciendo los tiempos de busqueda, la congestion vehicular y las emisiones generadas por recorridos innecesarios. Al mismo tiempo, los administradores obtienen metricas de ocupacion, telemetria de dispositivos y herramientas de configuracion dinamica.

<div align="center">
  <img src="app/public/mapa_parqueo_uce.svg" alt="Plano Vectorial del Estacionamiento" width="650" />
  <p><em>Plano esquematico en tiempo real con codificacion cromatica de plazas (verde: libre, rojo: ocupado).</em></p>
</div>

## Caracteristicas Principales

- Monitoreo en Tiempo Real: Deteccion constante del estado de cada estacionamiento con transmision de baja latencia hacia la plataforma web.
- Plano Vectorial Interactivo: Visualizacion esquematica basada en SVG escalable, sin texturas pesadas y optimizada para lectura rapida.
- Inferencia Optimizada: Motor de vision artificial ejecutado sobre CPU con consumo de memoria contenido (menos de 160 MB de RAM).
- Soporte Multi-Camara y Multi-Establecimiento: Capacidad de integrar multiples zonas de estacionamiento y dispositivos bajo un mismo panel centralizado.
- Panel de Administracion: Modulo web para calibracion de zonas de interes (ROI), inspeccion de camaras y gestion operativa.

## Estados de Disponibilidad

La interfaz utiliza una convencion visual directa y sin ambiguedades:

| Estado | Color | Descripcion |
| :--- | :--- | :--- |
| Libre | Verde (#16a34a) | Plaza disponible para estacionar inmediatamente. |
| Ocupado | Rojo (#dc2626) | Plaza ocupada por un vehiculo detectado. |
| En Revision | Ambar (#d97706) | Nivel de confianza optico bajo o verificacion requerida. |

## Arquitectura General

1. Dispositivos de Captura: Camaras IP o microcontroladores (ESP32-CAM) que capturan y transmiten imagenes periodicas al servidor central.
2. Servidor Central y API: Servicio desarrollado en FastAPI con motor de inferencia ONNX Runtime y base de datos relacional PostgreSQL serverless para persistencia de eventos y telemetria.
3. Cliente Web: Aplicacion web desarrollada con Vite y JavaScript estandar, dise&ntilde;ada con un sistema de dise&ntilde;o minimalista y lectura inmediata.

## Ejecucion y Despliegue

### Requisitos

- Docker o Python 3.12+
- Node.js 18+ (para el cliente web)

### Servidor API con Docker

```bash
# Construir la imagen
docker build -t parqueame-api .

# Iniciar el servicio con variables de entorno
docker run -d -p 8000:8000 --env-file .env parqueame-api
```

### Servidor API en Entorno Local

```bash
# Instalar dependencias
pip install -r requirements.txt

# Iniciar servidor
uvicorn server.main:app --host 0.0.0.0 --port 8000
```

### Cliente Web

```bash
cd app
npm install
npm run dev
```

## Despliegue en Produccion

El backend esta configurado para ejecutarse en contenedores Docker dentro de la capa gratuita de Render, cumpliendo holgadamente los limites de recursos (512 MB de RAM y 0.1 vCPU) y enlazado con Neon PostgreSQL Serverless.
