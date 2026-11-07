/**
 * Sistema: Parqueame — Módulo de Captura y Transmisión Remota (Alta Calidad SXGA)
 * Hardware: Seeed Studio XIAO ESP32-S3 Sense (OV2640) + Escudo 18650 V8
 * Protocolo: HTTP/1.1 POST Multipart Form-Data -> FastAPI (/api/v1/upload/{camera_id})
 */

// Version definitiva
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include "esp_camera.h"
#include "esp_sleep.h"

// ============================================================================
// 1. PARÁMETROS DE CONFIGURACIÓN GENERAL Y MODO DE OPERACIÓN
// ============================================================================

const bool DEV_MODE = true;
const bool HAS_BATTERY_DIVIDER = false;

// Credenciales de Red Wi-Fi (Banda de 2.4 GHz)
const char* WIFI_SSID     = "Ezequiel";
const char* WIFI_PASSWORD = "Ezequiel23101609";

// Configuración del Servidor Central FastAPI
// Modo 1: Cloud Deployment (Hugging Face Spaces): "thegxnster-parqueame-server.hf.space", puerto 443, USE_HTTPS=true
// Modo 2: Local Network Discovery via mDNS / LAN: "parqueame.local" o IP "192.168.1.29", puerto 8000, USE_HTTPS=false
const char* SERVER_HOST   = "192.168.1.29";
const uint16_t SERVER_PORT = 8000;
const bool USE_HTTPS      = false;
const char* CAMERA_ID     = "cam_01";

// Tiempos de ciclo y variables dinámicas de Hot-Configuration
const uint32_t DEFAULT_INTERVAL_SECONDS = 30;
uint32_t currentIntervalSeconds         = DEFAULT_INTERVAL_SECONDS;
bool     cameraIsActive                 = true;
uint8_t  currentQuality                 = 12;

const uint32_t WIFI_TIMEOUT_MS      = 10000;
const uint32_t HTTP_TIMEOUT_MS      = 10000;
const char*    MULTIPART_BOUNDARY   = "----ParqueameBoundary7MA4YWxkTrZu0gW";

// Fotogramas de calentamiento para que el sensor estabilice luz y elimine el tono verde
const int      WARMUP_FRAMES        = 8;
const int      WARMUP_DELAY_MS      = 120;

// ============================================================================
// 2. DEFINICIÓN DE PINES HARDWARE (XIAO ESP32-S3 SENSE - OV2640)
// ============================================================================
#define PWDN_GPIO_NUM     -1
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM     10
#define SIOD_GPIO_NUM     40
#define SIOC_GPIO_NUM     39

#define Y9_GPIO_NUM       48
#define Y8_GPIO_NUM       11
#define Y7_GPIO_NUM       12
#define Y6_GPIO_NUM       14
#define Y5_GPIO_NUM       16
#define Y4_GPIO_NUM       18
#define Y3_GPIO_NUM       17
#define Y2_GPIO_NUM       15
#define VSYNC_GPIO_NUM    38
#define HREF_GPIO_NUM     47
#define PCLK_GPIO_NUM     13

#define BATTERY_ADC_PIN   1
#define VOLTAGE_RATIO     2.0f
#define BAT_MIN_VOLTS     3.00f
#define BAT_MAX_VOLTS     4.20f

// ============================================================================
// 3. VARIABLES DE ESTADO Y MEMORIA RTC
// ============================================================================
RTC_DATA_ATTR uint32_t bootCount = 0;
unsigned long lastCaptureTime = 0;
bool cameraReady = false;

struct BatteryTelemetry {
  float voltage;
  float percentage;
};

// ============================================================================
// 4. FUNCIONES AUXILIARES DE HARDWARE, ÓPTICA Y TELEMETRÍA
// ============================================================================

BatteryTelemetry readBatteryTelemetry() {
  BatteryTelemetry data;

  if (!HAS_BATTERY_DIVIDER) {
    data.voltage = 4.20f;
    data.percentage = 100.0f;
    return data;
  }

  uint32_t mvSum = 0;
  for (int i = 0; i < 16; i++) {
    mvSum += analogReadMilliVolts(BATTERY_ADC_PIN);
    delay(2);
  }
  float pinMilliVolts = (float)mvSum / 16.0f;

  data.voltage = (pinMilliVolts * VOLTAGE_RATIO) / 1000.0f;

  float pct = ((data.voltage - BAT_MIN_VOLTS) / (BAT_MAX_VOLTS - BAT_MIN_VOLTS)) * 100.0f;
  if (pct > 100.0f) pct = 100.0f;
  if (pct < 0.0f)   pct = 0.0f;
  data.percentage = pct;

  return data;
}

/**
 * Descarta fotogramas previos para obligar al DSP del OV2640 a converger
 * en exposición (AEC) y balance de blancos (AWB), eliminando el tinte verde.
 */
void stabilizeSensorAWB(int framesToFlush, int delayMs) {
  for (int i = 0; i < framesToFlush; i++) {
    camera_fb_t* fb = esp_camera_fb_get();
    if (fb != NULL) {
      esp_camera_fb_return(fb);
    }
    delay(delayMs);
  }
}

/**
 * Estado 2 (INIT_CAM): Inicializa el OV2640 a 10 MHz en alta resolución SXGA (1280x1024)
 * usando el área completa 4:3 del sensor (máxima amplitud) y calibración ISP completa.
 */
bool initCamera() {
  camera_config_t config = {};

  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;

  // 10 MHz reduce a la mitad el estrés del chip y duplica el tiempo de exposición por píxel
  config.xclk_freq_hz = 10000000;
  config.pixel_format = PIXFORMAT_JPEG;

  // Pre-reserva de buffer UXGA (1600x1200) en PSRAM con calidad alta (8)
  if (psramFound()) {
    config.frame_size   = FRAMESIZE_UXGA;
    config.jpeg_quality = 8;
    config.fb_location  = CAMERA_FB_IN_PSRAM;
    config.fb_count     = 2;
    config.grab_mode    = CAMERA_GRAB_LATEST;
  } else {
    config.frame_size   = FRAMESIZE_SVGA;
    config.jpeg_quality = 10;
    config.fb_location  = CAMERA_FB_IN_DRAM;
    config.fb_count     = 1;
    config.grab_mode    = CAMERA_GRAB_WHEN_EMPTY;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[ERROR] Fallo esp_camera_init con codigo: 0x%x\n", err);
    return false;
  }

  // Configuración avanzada del ISP del sensor OV2640 para eliminar imagen negra/verde
  sensor_t* s = esp_camera_sensor_get();
  if (s != NULL) {
    s->set_framesize(s, FRAMESIZE_SXGA); // 1280x1024 (Amplitud completa 4:3 en HD)
    s->set_quality(s, 8);

    // Balance de blancos automático (elimina el tinte verde)
    s->set_whitebal(s, 1);
    s->set_awb_gain(s, 1);
    s->set_wb_mode(s, 0);        // 0 = Auto White Balance

    // Exposición automática extendida para interiores/tarde/noche
    s->set_exposure_ctrl(s, 1);  // AEC activo
    s->set_aec2(s, 1);           // DSP de exposición nocturna activo
    s->set_ae_level(s, 1);       // Compensación de exposición (+1 evita subexposición oscura)

    // Ganancia automática (ISO) ampliada hasta 32x para condiciones de poca luz
    s->set_gain_ctrl(s, 1);
    s->set_gainceiling(s, GAINCEILING_32X);

    // Correcciones ópticas de curva Gamma y lente
    s->set_brightness(s, 1);     // Ligero refuerzo de brillo (+1)
    s->set_contrast(s, 0);
    s->set_saturation(s, 0);
    s->set_special_effect(s, 0); // 0 = Color natural RGB
    s->set_bpc(s, 1);            // Corrección de píxeles negros defectuosos
    s->set_wpc(s, 1);            // Corrección de píxeles blancos calientes
    s->set_raw_gma(s, 1);        // Curva Gamma activa (crítico para levantar tonos medios)
    s->set_lenc(s, 1);           // Corrección de sombreado de lente (ilumina las esquinas)
  }

  Serial.println("[CAMARA] Calibrando sensor (AWB/AEC inicial)...");
  delay(500);
  stabilizeSensorAWB(10, 120);

  Serial.println("[CAMARA] OV2640 lista en alta definicion SXGA (1280x1024), Calidad 8.");
  return true;
}

/**
 * Estado 3 (CONNECT_WIFI): Conecta a la red Wi-Fi con timeout de 10 segundos
 */
bool connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    return true;
  }

  Serial.printf("[WIFI] Conectando a %s", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long startAttempt = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - startAttempt) < WIFI_TIMEOUT_MS) {
    delay(250);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("[WIFI] Conectado. IP local: %s (RSSI: %d dBm)\n",
                  WiFi.localIP().toString().c_str(), WiFi.RSSI());
    return true;
  } else {
    Serial.println("[WIFI] ERROR: Tiempo de espera agotado (10 s).");
    return false;
  }
}

/**
 * Estado 5 (DISPATCH): Construye y despacha el paquete HTTP/1.1 POST Multipart Form-Data
 */
bool dispatchFrame(camera_fb_t* fb, const BatteryTelemetry& telemetry) {
  WiFiClient plainClient;
  WiFiClientSecure secureClient;
  WiFiClient* clientPtr = nullptr;

  if (USE_HTTPS) {
    secureClient.setInsecure();
    clientPtr = &secureClient;
  } else {
    clientPtr = &plainClient;
  }
  WiFiClient& client = *clientPtr;
  client.setTimeout(HTTP_TIMEOUT_MS / 1000);

  Serial.printf("[HTTP] Conectando a %s:%u (HTTPS=%s)...\n", SERVER_HOST, SERVER_PORT, USE_HTTPS ? "SI" : "NO");
  if (!client.connect(SERVER_HOST, SERVER_PORT, HTTP_TIMEOUT_MS)) {
    Serial.println("[HTTP] ERROR: connect failed hacia el servidor central.");
    return false;
  }

  char urlPath[128];
  snprintf(urlPath, sizeof(urlPath),
           "/api/v1/upload/%s?battery=%.1f&voltage=%.2f",
           CAMERA_ID, telemetry.percentage, telemetry.voltage);

  String bodyHead = "--" + String(MULTIPART_BOUNDARY) + "\r\n";
  bodyHead += "Content-Disposition: form-data; name=\"file\"; filename=\"" + String(CAMERA_ID) + ".jpg\"\r\n";
  bodyHead += "Content-Type: image/jpeg\r\n\r\n";

  String bodyTail = "\r\n--" + String(MULTIPART_BOUNDARY) + "--\r\n";

  size_t totalContentLength = bodyHead.length() + fb->len + bodyTail.length();

  client.printf("POST %s HTTP/1.1\r\n", urlPath);
  client.printf("Host: %s:%u\r\n", SERVER_HOST, SERVER_PORT);
  client.printf("Content-Type: multipart/form-data; boundary=%s\r\n", MULTIPART_BOUNDARY);
  client.printf("Content-Length: %u\r\n", (unsigned int)totalContentLength);
  client.print("Connection: close\r\n\r\n");

  client.print(bodyHead);

  const size_t chunkSize = 1024;
  uint8_t* bufPtr = fb->buf;
  size_t remaining = fb->len;

  while (remaining > 0) {
    size_t toWrite = (remaining > chunkSize) ? chunkSize : remaining;
    size_t written = client.write(bufPtr, toWrite);
    if (written == 0) {
      Serial.println("[HTTP] ERROR: Corte en escritura del socket TCP.");
      client.stop();
      return false;
    }
    bufPtr    += written;
    remaining -= written;
  }

  client.print(bodyTail);

  unsigned long waitStart = millis();
  while (client.connected() && !client.available()) {
    if (millis() - waitStart > HTTP_TIMEOUT_MS) {
      Serial.println("[HTTP] ERROR: Timeout esperando respuesta del servidor.");
      client.stop();
      return false;
    }
    delay(10);
  }

  String statusLine = client.readStringUntil('\n');
  statusLine.trim();
  Serial.printf("[HTTP] Respuesta del servidor: %s\n", statusLine.c_str());

  // Leer encabezados HTTP hasta línea vacía
  while (client.connected() && client.available()) {
    String headerLine = client.readStringUntil('\n');
    headerLine.trim();
    if (headerLine.length() == 0) {
      break;
    }
  }

  // Leer cuerpo JSON para extraer Hot-Configuration
  String responseBody = "";
  while (client.connected() && client.available()) {
    char c = client.read();
    responseBody += c;
  }
  client.stop();

  if (responseBody.length() > 0) {
    Serial.printf("[HOT-CONFIG] Payload recibido: %s\n", responseBody.c_str());

    // 1. Extraer interval_seconds
    int idxInterval = responseBody.indexOf("\"interval_seconds\":");
    if (idxInterval >= 0) {
      int start = idxInterval + 19;
      int end = responseBody.indexOf(",", start);
      if (end < 0) end = responseBody.indexOf("}", start);
      if (end > start) {
        uint32_t newInterval = responseBody.substring(start, end).toInt();
        if (newInterval >= 5 && newInterval <= 3600) {
          if (newInterval != currentIntervalSeconds) {
            Serial.printf("[HOT-CONFIG] Intervalo actualizado dinamicamente de %u s a %u s\n",
                          currentIntervalSeconds, newInterval);
            currentIntervalSeconds = newInterval;
          }
        }
      }
    }

    // 2. Extraer active
    int idxActive = responseBody.indexOf("\"active\":");
    if (idxActive >= 0) {
      int start = idxActive + 9;
      while (start < responseBody.length() && responseBody.charAt(start) == ' ') start++;
      if (responseBody.substring(start).startsWith("false")) {
        if (cameraIsActive) {
          Serial.println("[HOT-CONFIG] Estado de camara actualizado a INACTIVA (pause).");
          cameraIsActive = false;
        }
      } else if (responseBody.substring(start).startsWith("true")) {
        if (!cameraIsActive) {
          Serial.println("[HOT-CONFIG] Estado de camara actualizado a ACTIVA.");
          cameraIsActive = true;
        }
      }
    }

    // 3. Extraer quality
    int idxQuality = responseBody.indexOf("\"quality\":");
    if (idxQuality >= 0) {
      int start = idxQuality + 10;
      int end = responseBody.indexOf(",", start);
      if (end < 0) end = responseBody.indexOf("}", start);
      if (end > start) {
        int newQuality = responseBody.substring(start, end).toInt();
        if (newQuality >= 1 && newQuality <= 63) {
          currentQuality = (uint8_t)newQuality;
        }
      }
    }
  }

  return statusLine.startsWith("HTTP/1.1 200") || statusLine.startsWith("HTTP/1.1 201");
}

/**
 * Ejecuta el ciclo de Estabilización + Captura (Estado 4), Despacho (Estado 5) y Limpieza (Estado 6)
 */
void executeCaptureAndDispatchCycle() {
  if (!cameraReady) {
    Serial.println("[ERROR] La camara no esta inicializada.");
    return;
  }

  if (!cameraIsActive) {
    Serial.printf("[HOT-CONFIG] Camara en pausa remota (active=false). Omitiendo captura. Espera heartbeat: %u s.\n",
                  currentIntervalSeconds);
    return;
  }

  if (!connectWiFi()) {
    Serial.println("[CICLO] Omitiendo captura por falta de red Wi-Fi.");
    return;
  }

  BatteryTelemetry telemetry = readBatteryTelemetry();
  Serial.printf("[TELEMETRIA] Bateria: %.1f%% (%.2f V) | PSRAM libre: %u bytes\n",
                telemetry.percentage, telemetry.voltage, (unsigned int)ESP.getFreePsram());

  // ESTADO 4: CAPTURE (Con estabilización previa de exposición y balance de blancos)
  stabilizeSensorAWB(WARMUP_FRAMES, WARMUP_DELAY_MS);

  camera_fb_t* fb = esp_camera_fb_get();
  if (fb == NULL) {
    Serial.println("[CAMARA] ERROR: esp_camera_fb_get() retorno NULL.");
    return;
  }

  Serial.printf("[CAMARA] Fotograma HD SXGA capturado (%u bytes - %ux%u).\n",
                (unsigned int)fb->len, (unsigned int)fb->width, (unsigned int)fb->height);

  // ESTADO 5: DISPATCH
  bool sent = dispatchFrame(fb, telemetry);
  if (!sent) {
    Serial.println("[CICLO] ADVERTENCIA: El fotograma no pudo ser entregado.");
  }

  // ESTADO 6: CLEANUP
  esp_camera_fb_return(fb);
  fb = NULL;
  Serial.println("[MEMORIA] Framebuffer liberado correctamente.\n");
}

void enterProductionDeepSleep() {
  Serial.printf("[SLEEP] Apagando Wi-Fi y entrando en Deep Sleep por %u s...\n", currentIntervalSeconds);
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  Serial.flush();

  esp_sleep_enable_timer_wakeup((uint64_t)currentIntervalSeconds * 1000000ULL);
  esp_deep_sleep_start();
}

// ============================================================================
// 5. CICLO DE VIDA ARDUINO (SETUP & LOOP)
// ============================================================================

void setup() {
  bootCount++;
  Serial.begin(115200);

  if (DEV_MODE) {
    unsigned long serialWait = millis();
    while (!Serial && (millis() - serialWait) < 4000) {
      delay(10);
    }
  }

  Serial.println("\n=======================================================");
  Serial.printf(" PARQUEAME FIRMWARE - Camara: %s | Boot #%u\n", CAMERA_ID, bootCount);
  Serial.printf(" Modo: %s | Intervalo: %u s | PSRAM OPI: %s (%u bytes)\n",
                DEV_MODE ? "DEV_MODE (Continuo)" : "PROD_MODE (Deep Sleep)",
                currentIntervalSeconds,
                psramFound() ? "OK" : "NO DETECTADA",
                (unsigned int)ESP.getPsramSize());
  Serial.println("=======================================================");

  if (HAS_BATTERY_DIVIDER) {
    pinMode(BATTERY_ADC_PIN, INPUT);
    analogReadResolution(12);
    analogSetPinAttenuation(BATTERY_ADC_PIN, ADC_11db);
  }

  // ESTADO 2: INIT_CAM
  cameraReady = initCamera();
  if (!cameraReady) {
    Serial.println("[FATAL] Fallo al inicializar la camara OV2640.");
    if (!DEV_MODE) {
      enterProductionDeepSleep();
    }
    return;
  }

  // ESTADO 3: CONNECT_WIFI
  connectWiFi();

  if (DEV_MODE) {
    executeCaptureAndDispatchCycle();
    lastCaptureTime = millis();
  } else {
    executeCaptureAndDispatchCycle();
    enterProductionDeepSleep();
  }
}

void loop() {
  if (DEV_MODE) {
    if (millis() - lastCaptureTime >= (currentIntervalSeconds * 1000UL)) {
      lastCaptureTime = millis();
      executeCaptureAndDispatchCycle();
    }
    delay(50);
  }
}
