// ======================================================
// uDisplay_rgb_panel.h - RGB Panel Implementation  
// ======================================================

#pragma once

#if SOC_LCD_RGB_SUPPORTED

#include "uDisplay_panel.h"
#include "esp_lcd_panel_interface.h"
#include "esp_lcd_panel_rgb.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_ops.h"

class RGBPanel : public UniversalPanel {
public:
    // Takes only the ESP-IDF config
    RGBPanel(const esp_lcd_rgb_panel_config_t& config);
    ~RGBPanel();
    
    void drawPixel(int16_t x, int16_t y, uint16_t color) override;
    void fillRect(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t color) override;
    void pushColors(uint16_t *data, uint16_t len, bool first = false) override;
    void setAddrWindow(int16_t x0, int16_t y0, int16_t x1, int16_t y1) override;
    void drawFastHLine(int16_t x, int16_t y, int16_t w, uint16_t color) override;
    void drawFastVLine(int16_t x, int16_t y, int16_t h, uint16_t color) override;

    void displayOnff(int8_t on) override;
    void invertDisplay(bool invert) override;
    void setRotation(uint8_t rotation) override;
    uint16_t* framebuffer = nullptr;

private:
    esp_lcd_panel_handle_t panel_handle = nullptr;
    uint8_t rotation = 0;
    uint16_t width = 0;
    uint16_t height = 0;
    int16_t window_x1 = 0;
    int16_t window_y1 = 0; 
    int16_t window_x2 = 1;
    int16_t window_y2 = 1;

};

#endif //SOC_LCD_RGB_SUPPORTED