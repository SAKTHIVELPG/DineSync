/**
 * ==============================================================================
 *  DINESYNC ESP32 Smart Restaurant Occupancy Sensor Node Firmware
 * ==============================================================================
 *  Target Hardware : ESP32 Dev Module / ESP32-WROOM-32 / ESP32-C3
 *  Sensors Supported: HC-SR04 / US-100 Ultrasonic Proximity Sensor,
 *                     VL53L0X Time-of-Flight Laser Sensor, or Pressure Mat.
 *  Communication   : Wi-Fi HTTP / REST + JSON Telemetry
 * ==============================================================================
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h> // ArduinoJson library (v6 or v7)

// ---------------- CONFIGURATION PARAMETERS ----------------
// Set these locally before flashing; never commit real Wi-Fi credentials.
const char* WIFI_SSID     = "YOUR_RESTAURANT_IOT_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// DINESYNC Central Server Endpoint
const char* SERVER_URL    = "http://192.168.1.100:8000/api/v1/sensors/telemetry";

// Hardware Identification
const char* SENSOR_ID     = "ESP32-NODE-04"; // Unique identifier for this table node
const int   TABLE_NUMBER  = 4;               // Associated table number
const char* FIRMWARE_VER  = "v2.1.0-esp32";

// Pin Definitions (HC-SR04 Ultrasonic Proximity)
const int PIN_TRIG        = 5;
const int PIN_ECHO        = 18;
const int PIN_BATTERY_ADC = 34;              // Voltage divider on ADC1
const int PIN_STATUS_LED  = 2;               // Onboard Blue/Green LED

// Sensor Calibration Thresholds
const float OCCUPANCY_THRESHOLD_CM = 45.0;   // Distance < 45cm indicates customer seated
const float VACANT_THRESHOLD_CM    = 75.0;   // Distance > 75cm indicates empty seat
const int   DEBOUNCE_SAMPLES       = 3;      // Consecutive samples required for state flip
const unsigned long PING_INTERVAL_MS = 3000; // Telemetry transmit interval (3 seconds)

// ---------------- GLOBAL VARIABLES ----------------
bool currentOccupiedState = false;
int consecutiveOccupiedCount = 0;
int consecutiveVacantCount = 0;
unsigned long lastPingTime = 0;

// Function Prototypes
float readUltrasonicDistanceCM();
int readBatteryLevelPercent();
void transmitTelemetry(float distanceCm, bool isOccupied, int batteryPercent, int rssi);
void connectToWiFi();

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n[DINESYNC] Initializing ESP32 Smart Table Node...");

  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  pinMode(PIN_STATUS_LED, OUTPUT);
  digitalWrite(PIN_TRIG, LOW);

  connectToWiFi();
}

void loop() {
  // Ensure Wi-Fi stays connected
  if (WiFi.status() != WL_CONNECTED) {
    digitalWrite(PIN_STATUS_LED, LOW);
    connectToWiFi();
  }

  // Periodic Telemetry Measurement
  unsigned long now = millis();
  if (now - lastPingTime >= PING_INTERVAL_MS) {
    lastPingTime = now;

    float distance = readUltrasonicDistanceCM();
    int battery = readBatteryLevelPercent();
    int rssi = WiFi.RSSI();

    // Debounce Filter
    if (distance > 0 && distance < OCCUPANCY_THRESHOLD_CM) {
      consecutiveOccupiedCount++;
      consecutiveVacantCount = 0;
      if (consecutiveOccupiedCount >= DEBOUNCE_SAMPLES) {
        currentOccupiedState = true;
      }
    } else if (distance >= VACANT_THRESHOLD_CM) {
      consecutiveVacantCount++;
      consecutiveOccupiedCount = 0;
      if (consecutiveVacantCount >= DEBOUNCE_SAMPLES) {
        currentOccupiedState = false;
      }
    }

    // LED visual status
    digitalWrite(PIN_STATUS_LED, currentOccupiedState ? HIGH : LOW);

    Serial.printf("[DINESYNC] Distance: %.1f cm | State: %s | Battery: %d%% | RSSI: %d dBm\n",
                  distance, currentOccupiedState ? "OCCUPIED" : "VACANT", battery, rssi);

    transmitTelemetry(distance, currentOccupiedState, battery, rssi);
  }

  delay(100);
}

/**
 * Measure ultrasonic echo time and calculate distance in centimeters
 */
float readUltrasonicDistanceCM() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);

  long duration = pulseIn(PIN_ECHO, HIGH, 30000); // 30ms timeout (max ~5 meters)
  if (duration == 0) {
    return 120.0; // Default clear reading on timeout
  }
  // Speed of sound = 343 m/s = 0.0343 cm/us
  float distance = (duration * 0.0343) / 2.0;
  return distance;
}

/**
 * Estimate battery percentage from LiPo battery ADC voltage divider
 */
int readBatteryLevelPercent() {
  int rawAdc = analogRead(PIN_BATTERY_ADC);
  // Assume 3.3V reference and 2:1 resistor divider (Max 4.2V LiPo)
  float voltage = (rawAdc / 4095.0) * 3.3 * 2.0;
  int percent = (int)((voltage - 3.2) / (4.2 - 3.2) * 100.0);
  return constrain(percent, 0, 100);
}

/**
 * Connect to Wi-Fi access point with automatic retry
 */
void connectToWiFi() {
  Serial.printf("[WiFi] Connecting to %s", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 20) {
    delay(500);
    Serial.print(".");
    retries++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WiFi] Connected! IP: " + WiFi.localIP().toString());
  } else {
    Serial.println("\n[WiFi] Connection failed. Will retry in main loop.");
  }
}

/**
 * Transmit JSON telemetry payload to DINESYNC server
 */
void transmitTelemetry(float distanceCm, bool isOccupied, int batteryPercent, int rssi) {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");

  // Format JSON payload (ArduinoJson v6 & v7 compatible)
  #if defined(ARDUINOJSON_VERSION_MAJOR) && ARDUINOJSON_VERSION_MAJOR >= 7
  JsonDocument doc;
  #else
  StaticJsonDocument<256> doc;
  #endif
  doc["sensor_id"]        = SENSOR_ID;
  doc["table_id"]         = TABLE_NUMBER;
  doc["distance_cm"]      = distanceCm;
  doc["occupied"]         = isOccupied;
  doc["battery_level"]    = batteryPercent;
  doc["signal_rssi"]      = rssi;
  doc["firmware_version"] = FIRMWARE_VER;

  String jsonPayload;
  serializeJson(doc, jsonPayload);

  int httpResponseCode = http.POST(jsonPayload);
  if (httpResponseCode > 0) {
    Serial.printf("[HTTP] Telemetry POST Success (Code: %d)\n", httpResponseCode);
  } else {
    Serial.printf("[HTTP] Error sending POST: %s\n", http.errorToString(httpResponseCode).c_str());
  }
  http.end();
}
