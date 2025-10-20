// WIP
// ======================================================
// uDisplay_DSI_panel.cpp - MIPI-DSI Display Panel Implementation
// ======================================================


#include "uDisplay_DSI_panel.h"
#if SOC_MIPI_DSI_SUPPORTED
#include "esp_lcd_panel_ops.h"
#include <rom/cache.h>

DSIPanel::DSIPanel(const DSIPanelConfig& config)
    : cfg(config), rotation(0)
{
    esp_ldo_channel_handle_t ldo_mipi_phy = nullptr;
    esp_ldo_channel_config_t ldo_config = {
        .chan_id = cfg.ldo_channel,
        .voltage_mv = cfg.ldo_voltage_mv,
        .flags = {
            .adjustable = 0,  // Fixed voltage, don't need to adjust later
            .owned_by_hw = 0, // Software controlled, not hardware/eFuse
        }
    };
    ESP_ERROR_CHECK(esp_ldo_acquire_channel(&ldo_config, &ldo_mipi_phy));

    esp_lcd_dsi_bus_handle_t dsi_bus = nullptr;
    esp_lcd_dsi_bus_config_t bus_config = {
        .bus_id = 0,
        .num_data_lanes = cfg.dsi_lanes,
        .phy_clk_src = MIPI_DSI_PHY_CLK_SRC_DEFAULT,
        .lane_bit_rate_mbps = cfg.lane_speed_mbps
    };

    ESP_ERROR_CHECK(esp_lcd_new_dsi_bus(&bus_config, &dsi_bus));

    esp_lcd_dpi_panel_config_t dpi_config = {
        .virtual_channel = 0,
        .dpi_clk_src = MIPI_DSI_DPI_CLK_SRC_DEFAULT,
        .dpi_clock_freq_mhz = cfg.pixel_clock_hz / 1000000,
        .pixel_format = LCD_COLOR_PIXEL_FORMAT_RGB565,
        .in_color_format = LCD_COLOR_FMT_RGB565,
        .out_color_format = LCD_COLOR_FMT_RGB888, // For 24bpp JD9165 fixed - TODO maybe use descriptor!!
        .num_fbs = 1,
        .video_timing = {
            .h_size = cfg.width,                    // 1024
            .v_size = cfg.height,                   // 600
            .hsync_pulse_width = cfg.timing.h_sync_pulse,      // 12
            .hsync_back_porch = cfg.timing.h_back_porch,       // 160
            .hsync_front_porch = cfg.timing.h_front_porch,     // 160
            .vsync_pulse_width = cfg.timing.v_sync_pulse,      // 10
            .vsync_back_porch = cfg.timing.v_back_porch,       // 23
            .vsync_front_porch = cfg.timing.v_front_porch,     // 40
        },
        .flags = {
            .use_dma2d = 1,
            .disable_lp = 0,
        }
    };

    esp_lcd_dbi_io_config_t io_config = {
        .virtual_channel = 0,
        .lcd_cmd_bits = 8,     // Most displays use 8-bit commands
        .lcd_param_bits = 8,   // Most parameters are 8-bit
    };
    ESP_ERROR_CHECK(esp_lcd_new_panel_io_dbi(dsi_bus, &io_config, &io_handle));

    if (cfg.init_commands && cfg.init_commands_count > 0) {

        sendInitCommandsDBI();
    }
    ESP_ERROR_CHECK(esp_lcd_new_panel_dpi(dsi_bus, &dpi_config, &panel_handle));
    
    // Initialize panel
    ESP_ERROR_CHECK(esp_lcd_panel_init(panel_handle));
    
    // Display on
    ESP_ERROR_CHECK(esp_lcd_panel_disp_on_off(panel_handle, true));

    void* buf = nullptr;
    esp_lcd_dpi_panel_get_frame_buffer(panel_handle, 1, &buf);
    framebuffer = (uint16_t*)buf;
}

void DSIPanel::sendInitCommandsDBI() {
    uint16_t index = 0;
    while (index < cfg.init_commands_count) {
        // DSI Format: cmd, data_size, data..., delay_ms
        uint8_t cmd = cfg.init_commands[index++];
        uint8_t data_size = cfg.init_commands[index++];
        
        // Send command with data
        if (data_size > 0) {
            ESP_ERROR_CHECK(esp_lcd_panel_io_tx_param(io_handle, cmd, 
                                                     &cfg.init_commands[index], 
                                                     data_size));
            index += data_size;
        } else {
            ESP_ERROR_CHECK(esp_lcd_panel_io_tx_param(io_handle, cmd, NULL, 0));
        }
        
        // Get delay (1 byte)
        uint8_t delay_ms = cfg.init_commands[index++];
        
        // Handle delay
        if (delay_ms > 0) {
            vTaskDelay(pdMS_TO_TICKS(delay_ms));
        }
    }
}

// ===== Drawing Primitives =====

bool DSIPanel::drawPixel(int16_t x, int16_t y, uint16_t color) {
    if ((x < 0) || (x >= cfg.width) || (y < 0) || (y >= cfg.height)) return true;
    
    if (framebuffer) {
        // Direct framebuffer access (DPI mode)
        framebuffer[y * cfg.width + x] = color;
        CACHE_WRITEBACK_ADDR((uint32_t)&framebuffer[y * cfg.width + x], 2);
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
    if (x + w > cfg.width) w = cfg.width - x;
    if (y + h > cfg.height) h = cfg.height - y;
    if (w <= 0 || h <= 0) return true;
    
    if (framebuffer) {
        // Direct framebuffer fill (DPI mode)
        for (int16_t yp = y; yp < y + h; yp++) {
            uint16_t* line_start = &framebuffer[yp * cfg.width + x];
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
    if ((y < 0) || (y >= cfg.height) || (x >= cfg.width)) return true;
    if (x < 0) { w += x; x = 0; }
    if (x + w > cfg.width) w = cfg.width - x;
    if (w <= 0) return true;
    
    if (framebuffer) {
        // Direct framebuffer access
        uint16_t* line_start = &framebuffer[y * cfg.width + x];
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
    if ((x < 0) || (x >= cfg.width) || (y >= cfg.height)) return true;
    if (y < 0) { h += y; y = 0; }
    if (y + h > cfg.height) h = cfg.height - y;
    if (h <= 0) return true;
    
    if (framebuffer) {
        // Direct framebuffer access
        for (int16_t j = 0; j < h; j++) {
            framebuffer[(y + j) * cfg.width + x] = color;
        }
        // Cache writeback for the column (might be non-contiguous)
        for (int16_t j = 0; j < h; j++) {
            CACHE_WRITEBACK_ADDR((uint32_t)&framebuffer[(y + j) * cfg.width + x], 2);
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
                framebuffer[y * cfg.width + x] = data[idx++];
            }
        }
        
        // Writeback the affected region
        for (int16_t y = window_y0; y <= window_y1; y++) {
            CACHE_WRITEBACK_ADDR((uint32_t)&framebuffer[y * cfg.width + window_x0], w * 2);
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