// ======================================================
// uDisplay_rgb_panel.h - RGB Panel Implementation  
// ======================================================

#pragma once

#ifdef USE_UNIVERSAL_PANEL

#include "uDisplay_panel.h"
#include "../uDisplay.h"

class uDisplay; // Forward declaration

class RGBPanel : public UniversalPanel {
public:
    RGBPanel(uDisplay* display) : disp(display) {}
    
    void drawPixel(int16_t x, int16_t y, uint16_t color) override;
    void fillRect(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t color) override;
    void pushColors(uint16_t *data, uint16_t len, bool first = false) override;
    
    void displayOnff(int8_t on) override;
    void setBrightness(uint8_t level) override;
    void invertDisplay(bool invert) override;
    void setRotation(uint8_t rotation) override;

private:
    uDisplay* disp;
};

#endif // USE_UNIVERSAL_PANEL