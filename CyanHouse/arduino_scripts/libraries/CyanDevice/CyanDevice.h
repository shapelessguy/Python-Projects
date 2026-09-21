#pragma once
#include <WiFi.h>
#include <WebServer.h>
#include <ArduinoOTA.h>
#include "credentials.h"
#include "esp_wifi.h"

// Password required to flash over WiFi. Define OTA_PASSWORD in credentials.h to
// use a separate one; otherwise the WiFi password is reused.
#ifndef OTA_PASSWORD
#define OTA_PASSWORD WIFI_PASSWORD
#endif

extern WebServer server;

// Implement these in your sketch
void deviceSetup();
void deviceLoop();
void registerRoutes();

// WebServer always adds Content-Length and "Connection: close" itself and closes
// the socket after each reply, so don't add those headers by hand.
inline void sendResponse(int code, const String& type, const String& body) {
  server.send(code, type, body);
}

class CyanDevice {
public:
  // lastOctet: fixed address on the local network (192.168.178.<lastOctet>).
  // 0 keeps DHCP. Pick one above the router's DHCP pool.
  CyanDevice(const char* ssid, const char* password, uint8_t lastOctet = 0)
    : _ssid(ssid), _password(password), _lastOctet(lastOctet) {}

  void begin() {
    Serial.begin(115200);
    WiFi.mode(WIFI_STA);
    WiFi.setTxPower(WIFI_POWER_19_5dBm);

    WiFi.onEvent([](WiFiEvent_t event, WiFiEventInfo_t info) {
      uint8_t reason = info.wifi_sta_disconnected.reason;
      Serial.print(F("WiFi lost, reason: "));
      Serial.println(WiFi.disconnectReasonName((wifi_err_reason_t)reason));
    }, ARDUINO_EVENT_WIFI_STA_DISCONNECTED);

    connectWiFi();

    server.on("/ping", []() { server.send(200, "text/plain", "ok"); });

    registerRoutes();
    server.begin();
    Serial.println(F("HTTP server started"));

    deviceSetup();
  }

  void loop() {
    if (WiFi.status() != WL_CONNECTED) {
      WiFi.disconnect();
      connectWiFi();
      return;
    }
    beginOTA();
    ArduinoOTA.handle();
    server.handleClient();
    deviceLoop();
  }

private:
  const char* _ssid;
  const char* _password;
  uint8_t _lastOctet;
  bool _otaStarted = false;

  static constexpr uint8_t NET[3] = {192, 168, 178};  // network prefix
  static constexpr uint8_t GATEWAY = 1;               // router, also used as DNS

  // Flash over WiFi: the first upload must be USB, later ones can target the
  // device's IP (arduino-cli: --port <ip> --protocol network --upload-field password=<pw>).
  // Needs a partition scheme with two app slots (not "Huge APP (no OTA)").
  // Started from loop() once connected, so a failed boot connect doesn't disable OTA.
  void beginOTA() {
    if (_otaStarted) return;
    _otaStarted = true;
    ArduinoOTA.setMdnsEnabled(false);  // uploads go by IP
    ArduinoOTA.setPassword(OTA_PASSWORD);
    ArduinoOTA.onStart([]() { Serial.println(F("OTA update starting")); });
    ArduinoOTA.onEnd([]() { Serial.println(F("\nOTA done, rebooting")); });
    ArduinoOTA.onError([](ota_error_t e) { Serial.printf("OTA error %u\n", e); });
    ArduinoOTA.onProgress([](unsigned int done, unsigned int total) {
      static uint8_t lastPct = 255;
      uint8_t pct = done * 100 / total;
      if (pct / 10 != lastPct / 10) Serial.printf("OTA %u%%\n", pct);
      lastPct = pct;
    });
    ArduinoOTA.begin();
    Serial.println(F("OTA ready"));
  }

  void connectWiFi() {
    if (_lastOctet) {
      const IPAddress gw(NET[0], NET[1], NET[2], GATEWAY);
      WiFi.config(IPAddress(NET[0], NET[1], NET[2], _lastOctet), gw, IPAddress(255, 255, 255, 0), gw);
    }
    WiFi.begin(_ssid, _password);
    Serial.print(F("Connecting to WiFi"));
    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < 10000) {
      delay(500);
      Serial.print('.');
    }
    if (WiFi.status() == WL_CONNECTED) {
      WiFi.setSleep(false);
      esp_wifi_set_ps(WIFI_PS_NONE);
      Serial.println(F("\nWiFi connected! IP: "));
      Serial.println(WiFi.localIP());
    } else {
      Serial.println(F("\nFailed to connect, retrying next loop..."));
    }
  }
};
