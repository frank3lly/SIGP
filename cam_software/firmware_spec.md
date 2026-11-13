# Especificación Técnica de Software de Cámara (Firmware)

- **Sistema:** Parqueame — Módulo de Captura y Transmisión Remota
- **Hardware:** Seeed Studio XIAO ESP32-S3 Sense + Sensor OV2640 (DVP 2MP)
- **Alimentación:** Escudo de Batería de Litio 18650 V8 (Doble Voltaje 5V/3A y 3V/1A)
- **Protocolo de Enlace:** HTTP/1.1 POST Multipart Form-Data
- **Destino:** Servidor Central FastAPI (`/api/v1/upload/{camera_id}`)

---

## 1. Requerimientos Funcionales y de Arquitectura

El firmware debe operar bajo un modelo **Cliente Activo (Push)**. A diferencia de un servidor web embebido (como el ejemplo `CameraWebServer`), el microcontrolador no escucha conexiones pasivas de navegadores; en su lugar, toma el fotograma y lo despacha de forma autónoma hacia el backend central.

### Requerimientos Clave:
1. **Captura en Color Nativo:** Fotogramas JPEG a resolución VGA ($640 \times 480$), calidad JPEG 12, espacio de color RGB.
2. **Ciclo de Ejecución Dual:**
   - **Modo Desarrollo (`DEV_MODE = true`):** Conexión serie USB CDC permanente, sin Deep Sleep, para permitir reprogramación inmediata desde CLI sin manipulación física de los pulsadores de la placa.
   - **Modo Producción (`DEV_MODE = false`):** Ciclo intermitente de ultrabajo consumo (Captura -> Envío -> Deep Sleep).
3. **Cero Fugas de Memoria:** El framebuffer asignado por `esp_camera_fb_get()` debe retornarse obligatoriamente con `esp_camera_fb_return()` antes de cualquier espera o nuevo ciclo.
4. **Manejo de Red Robusto:** Si la red WiFi se desconecta o el servidor no responde, el microcontrolador no debe congelarse; debe registrar el fallo, reintentar limpiamente o continuar el ciclo programado.

---

## 2. Especificación de Alimentación y Telemetría (Escudo 18650 V8)

### A. Características del Escudo 18650 V8
* **Salidas reguladas:**
  - Puerto USB-A y terminales soldados: **5V / 3A** (convertidor Boost integrado).
  - Pines de cabecera: **3.3V / 1A** (regulador LDO integrado).
* **Alimentación del XIAO ESP32-S3 Sense:** 
  - Se alimenta conectando la salida de **5V** del escudo al puerto USB-C del XIAO, o al pin `5V` (VBUS) y `GND` de la placa.
  - El regulador interno del XIAO acondiciona los 5V hacia los 3.3V que requiere el ESP32-S3 y el sensor OV2640.

### B. Especificación de Lectura de Batería (ADC)
* **El Problema del Regulador Boost:** Dado que el escudo V8 regula su salida a 5.0V constantes hasta que las celdas 18650 se agotan por completo (~3.0V de corte), medir el pin de 5V o de 3.3V del XIAO siempre dará una lectura fija del 100%.
* **Medición Real de la Celda 18650:**
  - Para telemetría real, se debe conectar un cable desde el terminal positivo directo de la batería en el escudo (**pad `B+` / `BAT+`**, voltaje variable de 3.0V a 4.2V) hacia un divisor de tensión formado por dos resistencias de $100\text{ k}\Omega$ conectadas en serie hacia `GND`.
  - El punto medio del divisor se conecta al pin **A0 (GPIO 1)** del XIAO.
  - En el firmware se define la constante multiplicadora:
    $$\text{Ratio} = 2.0$$
    $$\text{Voltaje Real} = \text{Lectura Pin (mV)} \times 2.0$$
* **Comportamiento sin cable de telemetría:**
  - Si el usuario no ha soldado el cable al pad `B+`, el parámetro `HAS_BATTERY_DIVIDER` se configura en `false`, reportando valores estáticos sin alterar el flujo de captura ni saturar el conversor ADC.

---

## 3. Estados del Sistema y Máquina de Estados

### Diagrama de Estados (Tabla Descriptiva)

| Estado | Evento de Entrada | Operación en DEV_MODE | Operación en PROD_MODE |
| :--- | :--- | :--- | :--- |
| **1. BOOT** | Encendido o Reset | Inicializa Serial a 115200 baudios, verifica memoria PSRAM OPI. | Lee contador `bootCount` desde RTC RAM, inicializa Serial mínimo. |
| **2. INIT_CAM** | Hardware OK | Configura registros DVP del OV2640 a VGA con doble buffer en PSRAM. | Configura registros DVP del OV2640 con un único buffer para ahorrar DRAM. |
| **3. CONNECT_WIFI** | Cámara lista | Conecta a WiFi STA una sola vez en el `setup()`. Mantiene radio activa. | Conecta a WiFi con límite de espera de 10 s. |
| **4. CAPTURE** | Temporizador expirado | Descarta fotogramas residuales, captura nuevo JPEG. | Captura JPEG limpio inmediatamente. |
| **5. DISPATCH** | Fotograma en RAM | POST HTTP Multipart al servidor. Imprime código HTTP de respuesta. | POST HTTP Multipart al servidor. Cierra socket TCP. |
| **6. CLEANUP** | Respuesta recibida | Libera buffer con `esp_camera_fb_return()`. | Libera buffer con `esp_camera_fb_return()`. |
| **7. WAIT / SLEEP** | Memoria liberada | **NO duerme:** Espera `INTERVAL_SECONDS` usando `millis()`. USB CDC activo. | Apaga WiFi (`WIFI_OFF`) y entra en `esp_deep_sleep_start()`. |

---

## 4. Requerimientos de Compilación y Flasheo (Arduino CLI)

Para que el firmware compile y reconozca la memoria PSRAM y el puerto serie nativo, se deben satisfacer los siguientes parámetros obligatorios:

### Parámetros FQBN (Fully Qualified Board Name)
```text
esp32:esp32:XIAO_ESP32S3:PSRAM=opi,CDCOnBoot=default,FlashSize=8M,CPUFreq=240,DebugLevel=info
```

### Justificación Técnica de Parámetros:
* **`PSRAM=opi`:** Imprescindible. La memoria externa del módulo Seeed Sense es de 8 MB tipo Octal SPI. Si se compila como QSPI o Desactivada, la cámara devuelve error fatal `0x103` (`ESP_ERR_NO_MEM`) al intentar reservar el buffer VGA.
* **`CDCOnBoot=default`:** Fuerza a que el canal serie USB nativo se active desde el primer ciclo de reloj, permitiendo capturar los mensajes de arranque sin perder el descriptor USB.
* **`FlashSize=8M`:** Asigna correctamente las tablas de particiones para los 8 MB de memoria flash física del chip.

### Flujo de Compilación y Subida desde WSL vía PowerShell:

```bash
# 1. Identificar el puerto asignado por Windows (ej. COM3, COM5)
powershell.exe -NoProfile -Command "[System.IO.Ports.SerialPort]::GetPortNames()"

# 2. Compilar el sketch
powershell.exe -NoProfile -Command "Set-Location 'C:\Users\frank'; & 'C:\Program Files\Arduino CLI\arduino-cli.exe' compile --fqbn esp32:esp32:XIAO_ESP32S3:PSRAM=opi,CDCOnBoot=default,FlashSize=8M,CPUFreq=240 'C:\Users\frank\parqueame_sketch\xiao_camera'"

# 3. Flashear la placa sin tocar botones (gracias a DEV_MODE = true)
powershell.exe -NoProfile -Command "Set-Location 'C:\Users\frank'; & 'C:\Program Files\Arduino CLI\arduino-cli.exe' upload -p COMx --fqbn esp32:esp32:XIAO_ESP32S3:PSRAM=opi,CDCOnBoot=default,FlashSize=8M,CPUFreq=240 'C:\Users\frank\parqueame_sketch\xiao_camera'"

# 4. Monitorear telemetría en tiempo real
powershell.exe -NoProfile -Command "& 'C:\Program Files\Arduino CLI\arduino-cli.exe' monitor -p COMx -c baudrate=115200"
```

---

## 5. Contrato de Comunicación de Red (Endpoint de Ingestión)

El microcontrolador debe estructurar su petición HTTP coincidiendo con el modelo definido en `server/routers/upload.py`:

* **Método:** `POST`
* **URL:** `http://<SERVER_HOST>:<SERVER_PORT>/api/v1/upload/<CAMERA_ID>?battery=<PCT>&voltage=<VOLTS>`
* **Cabecera `Content-Type`:** `multipart/form-data; boundary=----ParqueameBoundary7MA4YWxkTrZu0gW`
* **Campo de Formulario:** `file` con nombre de archivo `cam_XX.jpg` y tipo MIME `image/jpeg`.

### Ejemplo de Carga Útil Transmitida:
```http
POST /api/v1/upload/cam_01?battery=92.5&voltage=4.12 HTTP/1.1
Host: 192.168.1.50:8000
Content-Type: multipart/form-data; boundary=----ParqueameBoundary7MA4YWxkTrZu0gW
Content-Length: 48321
Connection: close

------ParqueameBoundary7MA4YWxkTrZu0gW
Content-Disposition: form-data; name="file"; filename="cam_01.jpg"
Content-Type: image/jpeg

[BYTES BINARIOS DEL JPEG]
------ParqueameBoundary7MA4YWxkTrZu0gW--
```

---

## 6. Procedimientos de Depuración y Resolución de Problemas

### Matriz de Diagnóstico de Fallos

| Síntoma Observado | Causa Frecuente | Procedimiento de Resolución |
| :--- | :--- | :--- |
| **Error `0x103` en `esp_camera_init`** | Falta de memoria PSRAM. | Comprobar que en la compilación se especificó `PSRAM=opi`. Verificar que `psramFound()` retorne `true`. |
| **Error `0x20002` en `esp_camera_init`** | Falla de bus I2C (SCCB) con el sensor. | 1. La cinta flex de la cámara está ligeramente ladeada o mal insertada.<br>2. La placa Seeed Sense (superior) no está insertada firmemente a presión contra el módulo XIAO (inferior). |
| **`esp_camera_fb_get()` retorna `NULL`** | Desbordamiento de buffer o caída de tensión. | 1. Asegurar que el escudo 18650 tenga la celda con carga superior a 3.5V.<br>2. Verificar que se llame a `esp_camera_fb_return()` después de cada foto. |
| **El microcontrolador no se conecta a Wi-Fi** | Banda de frecuencia incompatible. | El ESP32-S3 **únicamente admite redes de 2.4 GHz**. Si el router emite en 5 GHz con el mismo nombre (band steering), se debe conectar a una red dedicada de 2.4 GHz o compartir internet desde el móvil en 2.4 GHz. |
| **`connect failed` hacia el servidor** | Aislamiento de red o firewall de Windows. | 1. Verificar que el servidor FastAPI esté iniciado (`uvicorn server.main:app --host 0.0.0.0 --port 8000`).<br>2. Comprobar que el firewall de Windows permita tráfico entrante en el puerto 8000.<br>3. Verificar con `ipconfig` en Windows la IP real de la máquina en la red local. |
| **Pérdida del Puerto COM (Modo Recuperación)** | Bloqueo o código anterior en bucle cerrado. | 1. Mantener pulsado el botón **`B` (Boot)** en la placa.<br>2. Pulsar una vez el botón **`R` (Reset)**.<br>3. Soltar el botón **`B`**. La placa entrará en modo cargador de arranque (*ROM Bootloader*) forzado y el puerto COM reaparecerá en Windows. |

---

## 7. Ajuste Óptico y Calibración en Campo

El lente del sensor OV2640 de la placa XIAO viene de fábrica con el foco preajustado a corta distancia (0.5 m a 1 m):
1. **Enfoque a Distancia (Aparcamiento a 15–20 metros):** Es necesario girar suavemente en sentido horario o antihorario el anillo exterior de la lente de la cámara hasta que las líneas del asfalto y los vehículos lejanos se vean completamente nítidos.
2. **Fijación de Posición:** Una vez calibrado el foco, asegurar el lente con una pequeña gota de silicona o cinta para evitar descalibraciones por vibración o viento en la estructura de montaje.

---

## 8. Protocolo de Hot-Configuration Bidireccional y Resolución Dinámica

### A. Respuesta del Servidor con Configuración Dinámica
Cada respuesta HTTP 200/201 a `POST /api/v1/upload/{camera_id}` retorna un objeto `config` JSON con parámetros operativos:

```json
{
  "status": "success",
  "camera_id": "cam_01",
  "processed_at": 1730935560.12,
  "inference_time_ms": 15.2,
  "total_spots": 28,
  "occupied_spots": 12,
  "free_spots": 16,
  "config": {
    "interval_seconds": 45,
    "active": true,
    "quality": 12,
    "firmware_version": "1.0.1"
  }
}
```

### B. Campos de Hot-Configuration
| Campo | Tipo | Rango / Formato | Efecto en Firmware |
| :--- | :--- | :--- | :--- |
| `interval_seconds` | Entero | `5` a `3600` s | Actualiza la frecuencia de captura sin reiniciar el microcontrolador. |
| `active` | Booleano | `true` / `false` | Si es `false`, la cámara suspende captura de fotogramas y mantiene latido mínimo. |
| `quality` | Entero | `1` a `63` | Ajusta la compresión JPEG del sensor OV2640. |
| `firmware_version` | Cadena | Semantic Versioning | Identificador de versión esperada de la flota. |

### C. Resolución Dinámica de Host (Sin IPs Fijas)
1. **Modo Nube (Render Web Service):**
   - Host: `parqueame-api.onrender.com`
   - Puerto: `443`
   - Protocolo: HTTPS mediante `WiFiClientSecure` con `client.setInsecure()`.
2. **Modo Local (mDNS / Zeroconf):**
   - Host: `parqueame.local`
   - Puerto: `8000`
   - Protocolo: HTTP mediante `WiFiClient`.
