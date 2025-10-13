// ======================================================
// uDisplay_panel.h - Base Panel Interface
// ======================================================

#pragma once

#include <Arduino.h>

class UniversalPanel {
public:
    virtual ~UniversalPanel() {}
    
    // Core graphics API
    virtual void drawPixel(int16_t x, int16_t y, uint16_t color) = 0;
    virtual void fillRect(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t color) = 0;
    virtual void pushColors(uint16_t *data, uint16_t len, bool first = false) = 0;
    
    // Control API
    virtual void displayOnff(int8_t on) = 0;
    virtual void setBrightness(uint8_t level) = 0;
    virtual void invertDisplay(bool invert) = 0;
    virtual void setRotation(uint8_t rotation) = 0;
};