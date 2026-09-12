#pragma once
#include <WiFi.h>
#include <ESPmDNS.h>
#include <WebServer.h>
#include "credentials.h"
#include "esp_wifi.h"

extern WebServer server;

// Implement these in your sketch
void deviceSetup();
void deviceLoop();
void registerRoutes();

// Use this instead of server.send() to enable keep-alive
inline void sendResponse(int code, const String& type, const String& body) {
  server.sendHeader("Content-Length", String(body.length()));
  server.sendHeader("Connection", "keep-alive");
  server.sendHeader("Keep-Alive", "timeout=10, max=100");
  server.send(code, type, body);
}

class CyanDevice {
public:
  CyanDevice(const char* ssid, const char* password, const char* hostname)
    : _ssid(ssid), _password(password), _hostname(hostname) {}

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

    if (MDNS.begin(_hostname)) {
      Serial.print(F("mDNS started: http://"));
      Serial.print(_hostname);
      Serial.println(F(".local"));
    }

    server.on("/ping", []() {
      server.sendHeader("Content-Length", "2");
      server.sendHeader("Connection", "keep-alive");
      server.sendHeader("Keep-Alive", "timeout=10, max=100");
      server.send(200, "text/plain", "ok");
    });

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
    server.handleClient();
    deviceLoop();
  }

private:
  const char* _ssid;
  const char* _password;
  const char* _hostname;

  void connectWiFi() {
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
