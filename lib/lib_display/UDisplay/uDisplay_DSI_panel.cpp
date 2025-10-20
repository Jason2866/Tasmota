// WIP
// ======================================================
// uDisplay_DSI_panel.cpp - MIPI-DSI Display Panel Implementation
// ======================================================


#include "uDisplay_DSI_panel.h"
#if SOC_MIPI_DSI_SUPPORTED
#include "esp_lcd_panel_ops.h"
#include <rom/cache.h>

DSIPanel::DSIPanel(esp_lcd_panel_handle_t panel, uint16_t w, uint16_t h)
    : panel_handle(panel), width(w), height(h)
{
    // Get framebuffer pointer (for DPI mode)
    void* buf = nullptr;
    esp_lcd_dpi_panel_get_frame_buffer(panel_handle, 1, &buf);
    framebuffer = (uint16_t*)buf;
}

// ===== Drawing Primitives =====

bool DSIPanel::drawPixel(int16_t x, int16_t y, uint16_t color) {
    if ((x < 0) || (x >= width) || (y < 0) || (y >= height)) return true;
    
    if (framebuffer) {
        // Direct framebuffer access (DPI mode)
        framebuffer[y * width + x] = color;
        CACHE_WRITEBACK_ADDR((uint32_t)&framebuffer[y * width + x], 2);
        return true;
    } else {
        // DBI mode - draw single pixel via panel API
        esp_err_t ret = esp_lcd_panel_draw_bitmap(panel_handle, x, y, x + 1, y + 1, &color);
        return (ret == ESP_OK);
    }
}

bool DSIPanel::fillRect(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t color) {
    // Clip to screen bounds
    if (x < 0) { w += x; x = 0; }
    if (y < 0) { h += y; y = 0; }
    if (x + w > width) w = width - x;
    if (y + h > height) h = height - y;
    if (w <= 0 || h <= 0) return true;
    
    if (framebuffer) {
        // Direct framebuffer fill (DPI mode)
        for (int16_t yp = y; yp < y + h; yp++) {
            uint16_t* line_start = &framebuffer[yp * width + x];
            for (int16_t i = 0; i < w; i++) {
                line_start[i] = color;
            }
            CACHE_WRITEBACK_ADDR((uint32_t)line_start, w * 2);
        }
        return true;
    } else {
        // DBI mode - create buffer and draw
        uint16_t* buf = (uint16_t*)malloc(w * h * sizeof(uint16_t));
        if (!buf) return false;
        
        for (int i = 0; i < w * h; i++) {
            buf[i] = color;
        }
        esp_err_t ret = esp_lcd_panel_draw_bitmap(panel_handle, x, y, x + w, y + h, buf);
        free(buf);
        return (ret == ESP_OK);
    }
}

bool DSIPanel::drawFastHLine(int16_t x, int16_t y, int16_t w, uint16_t color) {
    if ((y < 0) || (y >= height) || (x >= width)) return true;
    if (x < 0) { w += x; x = 0; }
    if (x + w > width) w = width - x;
    if (w <= 0) return true;
    
    if (framebuffer) {
        // Direct framebuffer access
        uint16_t* line_start = &framebuffer[y * width + x];
        for (int16_t i = 0; i < w; i++) {
            line_start[i] = color;
        }
        CACHE_WRITEBACK_ADDR((uint32_t)line_start, w * 2);
        return true;
    } else {
        // DBI mode
        return fillRect(x, y, w, 1, color);
    }
}

bool DSIPanel::drawFastVLine(int16_t x, int16_t y, int16_t h, uint16_t color) {
    if ((x < 0) || (x >= width) || (y >= height)) return true;
    if (y < 0) { h += y; y = 0; }
    if (y + h > height) h = height - y;
    if (h <= 0) return true;
    
    if (framebuffer) {
        // Direct framebuffer access
        for (int16_t j = 0; j < h; j++) {
            framebuffer[(y + j) * width + x] = color;
        }
        // Cache writeback for the column (might be non-contiguous)
        for (int16_t j = 0; j < h; j++) {
            CACHE_WRITEBACK_ADDR((uint32_t)&framebuffer[(y + j) * width + x], 2);
        }
        return true;
    } else {
        // DBI mode
        return fillRect(x, y, 1, h, color);
    }
}

bool DSIPanel::pushColors(uint16_t *data, uint16_t len, bool not_swapped) {
    // Use previously set address window
    // Note: For DSI panels, typically handle byte swapping in hardware
    // so not_swapped parameter may not be needed
    
    if (framebuffer) {
        // DPI mode - direct framebuffer copy
        // Calculate dimensions from window
        int16_t w = window_x1 - window_x0 + 1;
        int16_t h = window_y1 - window_y0 + 1;
        
        uint16_t idx = 0;
        for (int16_t y = window_y0; y <= window_y1 && idx < len; y++) {
            for (int16_t x = window_x0; x <= window_x1 && idx < len; x++) {
                framebuffer[y * width + x] = data[idx++];
            }
        }
        
        // Writeback the affected region
        for (int16_t y = window_y0; y <= window_y1; y++) {
            CACHE_WRITEBACK_ADDR((uint32_t)&framebuffer[y * width + window_x0], w * 2);
        }
        return true;
    } else {
        // DBI mode
        esp_err_t ret = esp_lcd_panel_draw_bitmap(panel_handle, window_x0, window_y0, 
                                                  window_x1 + 1, window_y1 + 1, data);
        return (ret == ESP_OK);
    }
}

bool DSIPanel::setAddrWindow(int16_t x0, int16_t y0, int16_t x1, int16_t y1) {
    // Store window for pushColors
    window_x0 = x0;
    window_y0 = y0;
    window_x1 = x1;
    window_y1 = y1;
    return true;
}

// ===== Control Methods =====

bool DSIPanel::displayOnff(int8_t on) {
    esp_err_t ret = esp_lcd_panel_disp_on_off(panel_handle, on != 0);
    return (ret == ESP_OK);
}

bool DSIPanel::invertDisplay(bool invert) {
    esp_err_t ret = esp_lcd_panel_invert_color(panel_handle, invert);
    return (ret == ESP_OK);
}

bool DSIPanel::setRotation(uint8_t rot) {
    rotation = rot & 3;
    
    esp_err_t ret;
    // MIPI-DSI panels use mirror/swap for rotation
    switch (rotation) {
    case 0:
        ret = esp_lcd_panel_mirror(panel_handle, false, false);
        if (ret == ESP_OK) ret = esp_lcd_panel_swap_xy(panel_handle, false);
        break;
    case 1:
        ret = esp_lcd_panel_mirror(panel_handle, false, true);
        if (ret == ESP_OK) ret = esp_lcd_panel_swap_xy(panel_handle, true);
        break;
    case 2:
        ret = esp_lcd_panel_mirror(panel_handle, true, true);
        if (ret == ESP_OK) ret = esp_lcd_panel_swap_xy(panel_handle, false);
        break;
    case 3:
        ret = esp_lcd_panel_mirror(panel_handle, true, false);
        if (ret == ESP_OK) ret = esp_lcd_panel_swap_xy(panel_handle, true);
        break;
    }
    return (ret == ESP_OK);
}

bool DSIPanel::updateFrame() {
    // For DPI mode with framebuffer, no explicit update needed
    // The DMA continuously sends framebuffer to display
    
    // For DBI mode, this would flush any pending operations
    if (!framebuffer) {
        // Could implement a dirty region tracking system here if needed
    }
    
    return true;  // Always succeeds for DSI panels
}

#endif // SOC_MIPI_DSI_SUPPORTED