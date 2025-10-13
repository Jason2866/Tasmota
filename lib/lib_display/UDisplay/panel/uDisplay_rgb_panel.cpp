// ======================================================
// panel/uDisplay_rgb_panel.cpp - RGB Panel Implementation
// ======================================================

#ifdef USE_UNIVERSAL_PANEL

#include "uDisplay_rgb_panel.h"
#include "../uDisplay.h"

void RGBPanel::drawPixel(int16_t x, int16_t y, uint16_t color) {
    disp->drawPixel_RGB(x, y, color);
}

void RGBPanel::fillRect(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t color) {
    for (int16_t j = y; j < y + h; j++) {
        for (int16_t i = x; i < x + w; i++) {
            disp->drawPixel_RGB(i, j, color);
        }
    }
}

void RGBPanel::pushColors(uint16_t *data, uint16_t len, bool first) {
    disp->pushColors(data, len, first);
}

void RGBPanel::displayOnff(int8_t on) {
    disp->DisplayOnff(on);
}

void RGBPanel::setBrightness(uint8_t level) {
    disp->dim10(level, level);
}

void RGBPanel::invertDisplay(bool invert) {
    disp->invertDisplay(invert);
}

void RGBPanel::setRotation(uint8_t rotation) {
    disp->setRotation(rotation);
}

#endif // USE_UNIVERSAL_PANEL