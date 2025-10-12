#include "uDisplay.h"
#include "uDisplay_config.h"

#if SOC_LCD_RGB_SUPPORTED

void uDisplay::drawPixel_RGB(int16_t x, int16_t y, uint16_t color) {
    int16_t w = _width, h = _height;

    if ((x < 0) || (x >= w) || (y < 0) || (y >= h)) {
        return;
    }

    // check rotation, move pixel around if necessary
    switch (cur_rot) {
    case 1:
        std::swap(w, h);
        std::swap(x, y);
        x = w - x - 1;
        break;
    case 2:
        x = w - x - 1;
        y = h - y - 1;
        break;
    case 3:
        std::swap(w, h);
        std::swap(x, y);
        y = h - y - 1;
        break;
    }

    uint16_t *fb = rgb_fb;
    fb += (int32_t)y * w;
    fb += x;
    *fb = color;
    Cache_WriteBack_Addr((uint32_t)fb, 2);
}

#endif // SOC_LCD_RGB_SUPPORTED