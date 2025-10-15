// ======================================================
// panel/uDisplay_rgb_panel.cpp - RGB Panel Implementation
// ======================================================
#ifdef ESP32
#if __has_include("soc/soc_caps.h")
# include "soc/soc_caps.h"
#else
# error "No ESP capability header found"
#endif
#endif

#if SOC_LCD_RGB_SUPPORTED

#include "uDisplay_rgb_panel.h"
#include <cstdint>
#include <algorithm>
#include <rom/cache.h>

extern int Cache_WriteBack_Addr(uint32_t addr, uint32_t size);

RGBPanel::RGBPanel(const esp_lcd_rgb_panel_config_t& config) {
    ESP_ERROR_CHECK(esp_lcd_new_rgb_panel(&config, &panel_handle));
    ESP_ERROR_CHECK(esp_lcd_panel_reset(panel_handle));
    ESP_ERROR_CHECK(esp_lcd_panel_init(panel_handle));
    width = config.timings.h_res;
    height = config.timings.v_res;
    void* buf = NULL;
    esp_lcd_rgb_panel_get_frame_buffer(panel_handle, 1, &buf);
    framebuffer = (uint16_t*)buf;
    uint16_t color = random(0xffff);
    ESP_ERROR_CHECK(esp_lcd_panel_draw_bitmap(panel_handle, 0, 0, 1, 1, &color));
}

RGBPanel::~RGBPanel() {
    // TODO: Cleanup panel_handle if needed
}

void RGBPanel::drawPixel(int16_t x, int16_t y, uint16_t color) {
    int16_t w = width, h = height;
    
    // Apply rotation (copied from uDisplay)
    switch (rotation) {
    case 1: std::swap(w, h); std::swap(x, y); x = w - x - 1; break;
    case 2: x = w - x - 1; y = h - y - 1; break;
    case 3: std::swap(w, h); std::swap(x, y); y = h - y - 1; break;
    }
    
    if ((x < 0) || (x >= w) || (y < 0) || (y >= h)) return;
    
    framebuffer[y * w + x] = color;
    Cache_WriteBack_Addr((uint32_t)&framebuffer[y * w + x], 2);
}

void RGBPanel::fillRect(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t color) {
    for (int16_t yp = y; yp < y + h; yp++) {
        uint16_t* line_start = &framebuffer[yp * width + x];
        for (int16_t i = 0; i < w; i++) {
            line_start[i] = color;
        }
        Cache_WriteBack_Addr((uint32_t)line_start, w * 2);
    }
}

void RGBPanel::setAddrWindow(int16_t x0, int16_t y0, int16_t x1, int16_t y1) {
    window_x1 = x0;
    window_y1 = y0; 
    window_x2 = x1;
    window_y2 = y1;
}

void RGBPanel::pushColors(uint16_t *data, uint16_t len, bool first) {
    esp_lcd_panel_draw_bitmap(panel_handle, window_x1, window_y1, window_x2, window_y2, data);
}

void RGBPanel::drawFastHLine(int16_t x, int16_t y, int16_t w, uint16_t color) {
    // No rotation handling - coordinates are already rotated by setRotation()
    uint16_t* line_start = &framebuffer[y * width + x];
    for (int16_t i = 0; i < w; i++) {
        line_start[i] = color;
    }
    Cache_WriteBack_Addr((uint32_t)line_start, w * 2);
}

void RGBPanel::drawFastVLine(int16_t x, int16_t y, int16_t h, uint16_t color) {
    // No rotation handling - coordinates are already rotated by setRotation()
    for (int16_t j = 0; j < h; j++) {
        framebuffer[(y + j) * width + x] = color;
    }
    Cache_WriteBack_Addr((uint32_t)&framebuffer[y * width + x], h * 2);
}

void RGBPanel::displayOnff(int8_t on) {
    esp_lcd_panel_disp_on_off(panel_handle, on != 0);
}

void RGBPanel::invertDisplay(bool invert) {
    // TODO: Not supported by RGB panels in ESP-IDF API
}

void RGBPanel::setRotation(uint8_t rotation) {
    this->rotation = rotation & 3;  // Store for drawPixel
    esp_lcd_panel_mirror(panel_handle, rotation == 1 || rotation == 2, rotation & 2);
    esp_lcd_panel_swap_xy(panel_handle, rotation & 1);
}

#endif // #if SOC_LCD_RGB_SUPPORTED