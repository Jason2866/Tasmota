// ======================================================
// uDisplay_epd_panel.cpp - E-Paper Display Panel Implementation
// ======================================================

#include "uDisplay_epd_panel.h"
#include <Arduino.h>

// EPD Command Definitions
static constexpr uint8_t DRIVER_OUTPUT_CONTROL                = 0x01;
static constexpr uint8_t BOOSTER_SOFT_START_CONTROL           = 0x0C;
static constexpr uint8_t GATE_SCAN_START_POSITION             = 0x0F;
static constexpr uint8_t DEEP_SLEEP_MODE                      = 0x10;
static constexpr uint8_t DATA_ENTRY_MODE_SETTING              = 0x11;
static constexpr uint8_t SW_RESET                             = 0x12;
static constexpr uint8_t TEMPERATURE_SENSOR_CONTROL           = 0x1A;
static constexpr uint8_t MASTER_ACTIVATION                    = 0x20;
static constexpr uint8_t DISPLAY_UPDATE_CONTROL_1             = 0x21;
static constexpr uint8_t DISPLAY_UPDATE_CONTROL_2             = 0x22;
static constexpr uint8_t WRITE_RAM                            = 0x24;
static constexpr uint8_t WRITE_VCOM_REGISTER                  = 0x2C;
static constexpr uint8_t WRITE_LUT_REGISTER                   = 0x32;
static constexpr uint8_t SET_DUMMY_LINE_PERIOD                = 0x3A;
static constexpr uint8_t SET_GATE_TIME                        = 0x3B;
static constexpr uint8_t BORDER_WAVEFORM_CONTROL              = 0x3C;
static constexpr uint8_t SET_RAM_X_ADDRESS_START_END_POSITION = 0x44;
static constexpr uint8_t SET_RAM_Y_ADDRESS_START_END_POSITION = 0x45;
static constexpr uint8_t SET_RAM_X_ADDRESS_COUNTER            = 0x4E;
static constexpr uint8_t SET_RAM_Y_ADDRESS_COUNTER            = 0x4F;
static constexpr uint8_t TERMINATE_FRAME_READ_WRITE           = 0xFF;

EPDPanel::EPDPanel(const EPDPanelConfig& config,
                   SPIController* spi_ctrl,
                   uint8_t* framebuffer,
                   const uint8_t* lut_full,
                   uint16_t lut_full_len,
                   const uint8_t* lut_partial,
                   uint16_t lut_partial_len,
                   const uint8_t** lut_array,
                   const uint8_t* lut_cnt)
    : spi(spi_ctrl), cfg(config), fb_buffer(framebuffer), update_mode(0),
      lut_full(lut_full), lut_partial(lut_partial),
      lut_full_len(lut_full_len), lut_partial_len(lut_partial_len),
      lut_array(lut_array), lut_cnt(lut_cnt)
{
    // Set EPD-specific defaults
    if (!cfg.invert_framebuffer) {
        cfg.invert_framebuffer = true; // Most EPDs need inversion
    }
    
    // Reset display
    resetDisplay();
    
    // Set initial LUT
    if (lut_full && lut_full_len > 0) {
        setLut(lut_full, lut_full_len);
    }
    
    // Clear display
    clearFrameMemory(0xFF);
    displayFrame();
}

EPDPanel::~EPDPanel() {
    // Panel doesn't own framebuffer or SPI controller
}

void EPDPanel::delay_sync(int32_t ms) {
    uint8_t busy_level = cfg.busy_invert ? LOW : HIGH;
    uint32_t time = millis();
    if (cfg.busy_pin >= 0) {
        while (digitalRead(cfg.busy_pin) == busy_level) {
            delay(1);
            if ((millis() - time) > cfg.busy_timeout) {
                break;
            }
        }
    } else {
        delay(ms);
    }
}

void EPDPanel::resetDisplay() {
    if (cfg.reset_pin < 0) return;
    
    pinMode(cfg.reset_pin, OUTPUT);
    digitalWrite(cfg.reset_pin, HIGH);
    delay(10);
    digitalWrite(cfg.reset_pin, LOW);
    delay(10);
    digitalWrite(cfg.reset_pin, HIGH);
    delay(10);
    delay_sync(100); // Use delay_sync instead of waitBusy
}

void EPDPanel::waitBusy() {
    // Deprecated - use delay_sync instead
    delay_sync(cfg.update_time);
}

void EPDPanel::setLut(const uint8_t* lut, uint16_t len) {
    if (!lut || len == 0) return;
    
    spi->beginTransaction();
    spi->csLow();
    spi->writeCommand(WRITE_LUT_REGISTER);
    for (uint16_t i = 0; i < len; i++) {
        spi->writeData8(lut[i]);
    }
    spi->csHigh();
    spi->endTransaction();
}

void EPDPanel::setMemoryArea(int x_start, int y_start, int x_end, int y_end) {
    int x_start1 = (x_start >> 3) & 0xFF;
    int x_end1 = (x_end >> 3) & 0xFF;
    int y_start1 = y_start & 0xFF;
    int y_start2 = (y_start >> 8) & 0xFF;
    int y_end1 = y_end & 0xFF;
    int y_end2 = (y_end >> 8) & 0xFF;

    spi->beginTransaction();
    spi->csLow();
    spi->writeCommand(SET_RAM_X_ADDRESS_START_END_POSITION);
    spi->writeData8(x_start1);
    spi->writeData8(x_end1);
    
    spi->writeCommand(SET_RAM_Y_ADDRESS_START_END_POSITION);
    if (cfg.ep_mode == 3) {
        // ep_mode 3: reversed Y order
        spi->writeData8(y_end1);
        spi->writeData8(y_end2);
        spi->writeData8(y_start1);
        spi->writeData8(y_start2);
    } else {
        spi->writeData8(y_start1);
        spi->writeData8(y_start2);
        spi->writeData8(y_end1);
        spi->writeData8(y_end2);
    }
    spi->csHigh();
    spi->endTransaction();
}

void EPDPanel::setMemoryPointer(int x, int y) {
    int x1, y1, y2;
    
    if (cfg.ep_mode == 3) {
        x1 = (x >> 3) & 0xFF;
        y--;
        y1 = y & 0xFF;
        y2 = (y >> 8) & 0xFF;
    } else {
        x1 = (x >> 3) & 0xFF;
        y1 = y & 0xFF;
        y2 = (y >> 8) & 0xFF;
    }

    spi->beginTransaction();
    spi->csLow();
    spi->writeCommand(SET_RAM_X_ADDRESS_COUNTER);
    spi->writeData8(x1);
    spi->writeCommand(SET_RAM_Y_ADDRESS_COUNTER);
    spi->writeData8(y1);
    spi->writeData8(y2);
    spi->csHigh();
    spi->endTransaction();
}

void EPDPanel::clearFrameMemory(uint8_t color) {
    setMemoryArea(0, 0, cfg.width - 1, cfg.height - 1);
    setMemoryPointer(0, 0);
    
    spi->beginTransaction();
    spi->csLow();
    spi->writeCommand(WRITE_RAM);
    
    uint32_t pixel_count = (cfg.width * cfg.height) / 8;
    for (uint32_t i = 0; i < pixel_count; i++) {
        spi->writeData8(color);
    }
    
    spi->csHigh();
    spi->endTransaction();
}

void EPDPanel::displayFrame() {
    spi->beginTransaction();
    spi->csLow();
    spi->writeCommand(DISPLAY_UPDATE_CONTROL_2);
    spi->writeData8(0xC4);
    spi->writeCommand(MASTER_ACTIVATION);
    spi->writeData8(TERMINATE_FRAME_READ_WRITE);
    spi->csHigh();
    spi->endTransaction();
    
    delay_sync(cfg.update_time); // Use delay_sync with proper timing
}

void EPDPanel::drawAbsolutePixel(int x, int y, uint16_t color) {
    if (x < 0 || x >= cfg.width || y < 0 || y >= cfg.height) {
        return;
    }
    
    uint16_t byte_pos = (x + y * cfg.width) / 8;
    uint8_t bit_pos = 7 - (x % 8);
    
    if (color) {
        fb_buffer[byte_pos] |= (1 << bit_pos);
    } else {
        fb_buffer[byte_pos] &= ~(1 << bit_pos);
    }
}

// ===== UniversalPanel Interface Implementation =====

bool EPDPanel::drawPixel(int16_t x, int16_t y, uint16_t color) {
    if (!fb_buffer) return false;
    
    // Convert color to monochrome with inversion support
    uint16_t mono_color = (color != 0) ? 1 : 0;
    if (cfg.invert_colors) {
        mono_color = !mono_color;
    }
    drawAbsolutePixel(x, y, mono_color);
    return true;
}

bool EPDPanel::fillRect(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t color) {
    if (!fb_buffer) return false;
    
    uint16_t mono_color = (color != 0) ? 1 : 0;
    if (cfg.invert_colors) {
        mono_color = !mono_color;
    }
    
    for (int16_t yy = y; yy < y + h; yy++) {
        for (int16_t xx = x; xx < x + w; xx++) {
            drawAbsolutePixel(xx, yy, mono_color);
        }
    }
    return true;
}

bool EPDPanel::pushColors(uint16_t *data, uint16_t len, bool first) {
    // EPD doesn't support direct color pushing, only framebuffer
    return false;
}

bool EPDPanel::setAddrWindow(int16_t x0, int16_t y0, int16_t x1, int16_t y1) {
    // EPD uses full framebuffer, address window not applicable
    return true;
}

bool EPDPanel::drawFastHLine(int16_t x, int16_t y, int16_t w, uint16_t color) {
    return fillRect(x, y, w, 1, color);
}

bool EPDPanel::drawFastVLine(int16_t x, int16_t y, int16_t h, uint16_t color) {
    return fillRect(x, y, 1, h, color);
}

bool EPDPanel::displayOnff(int8_t on) {
    // EPD doesn't have on/off in traditional sense
    return true;
}

bool EPDPanel::invertDisplay(bool invert) {
    // Toggle color inversion logic
    cfg.invert_colors = invert;
    
    // For EPD, we need to redraw the entire display when inversion changes
    if (fb_buffer) {
        // Invert the entire framebuffer
        uint32_t byte_count = (cfg.width * cfg.height) / 8;
        for (uint32_t i = 0; i < byte_count; i++) {
            fb_buffer[i] = ~fb_buffer[i];
        }
        updateFrame();
    }
    return true;
}

bool EPDPanel::setRotation(uint8_t rotation) {
    // EPD rotation handled in uDisplay framebuffer
    return true;
}

bool EPDPanel::updateFrame() {
    if (!fb_buffer) return false;
    
    // Set memory area to full screen
    setMemoryArea(0, 0, cfg.width - 1, cfg.height - 1);
    setMemoryPointer(0, 0);
    
    // Send framebuffer data with optional inversion
    spi->beginTransaction();
    spi->csLow();
    spi->writeCommand(WRITE_RAM);
    
    uint32_t byte_count = (cfg.width * cfg.height) / 8;
    for (uint32_t i = 0; i < byte_count; i++) {
        uint8_t data = fb_buffer[i];
        if (cfg.invert_framebuffer) {
            data ^= 0xFF; // Invert for EPD display characteristics
        }
        spi->writeData8(data);
    }
    
    spi->csHigh();
    spi->endTransaction();
    
    // Update display
    displayFrame();
    
    // Wait appropriate time based on update mode using delay_sync
    if (update_mode == 0) {
        delay_sync(cfg.lut_full_time);
    } else {
        delay_sync(cfg.lut_partial_time);
    }
    
    return true;
}

// ===== ep_mode 2 Support (5-LUT mode) =====

void EPDPanel::setLuts() {
    if (!lut_array || !lut_cnt) return;
    
    for (uint8_t index = 0; index < 5; index++) {
        if (cfg.lut_cmd[index] == 0 || !lut_array[index]) continue;
        
        spi->beginTransaction();
        spi->csLow();
        spi->writeCommand(cfg.lut_cmd[index]);
        for (uint8_t count = 0; count < lut_cnt[index]; count++) {
            spi->writeData8(lut_array[index][count]);
        }
        spi->csHigh();
        spi->endTransaction();
    }
}

void EPDPanel::clearFrame_42() {
    spi->beginTransaction();
    spi->csLow();
    
    spi->writeCommand(cfg.saw_1);
    for (uint16_t j = 0; j < cfg.height; j++) {
        for (uint16_t i = 0; i < cfg.width; i++) {
            spi->writeData8(0xFF);
        }
    }

    spi->writeCommand(cfg.saw_2);
    for (uint16_t j = 0; j < cfg.height; j++) {
        for (uint16_t i = 0; i < cfg.width; i++) {
            spi->writeData8(0xFF);
        }
    }

    spi->writeCommand(cfg.saw_3);
    spi->csHigh();
    spi->endTransaction();
    
    delay_sync(100);
}

void EPDPanel::displayFrame_42() {
    spi->beginTransaction();
    spi->csLow();
    
    spi->writeCommand(cfg.saw_1);
    for(int i = 0; i < cfg.width / 8 * cfg.height; i++) {
        spi->writeData8(0xFF);
    }
    
    spi->csHigh();
    spi->endTransaction();
    delay(2);

    spi->beginTransaction();
    spi->csLow();
    spi->writeCommand(cfg.saw_2);
    for(int i = 0; i < cfg.width / 8 * cfg.height; i++) {
        spi->writeData8(fb_buffer[i] ^ 0xff);
    }
    spi->csHigh();
    spi->endTransaction();
    delay(2);

    setLuts();

    spi->beginTransaction();
    spi->csLow();
    spi->writeCommand(cfg.saw_3);
    spi->csHigh();
    spi->endTransaction();
    
    delay_sync(100);
}

// ===== Frame Memory Management =====

void EPDPanel::setFrameMemory(const uint8_t* image_buffer) {
    setMemoryArea(0, 0, cfg.width - 1, cfg.height - 1);
    setMemoryPointer(0, 0);
    
    spi->beginTransaction();
    spi->csLow();
    spi->writeCommand(WRITE_RAM);
    for (int i = 0; i < cfg.width / 8 * cfg.height; i++) {
        spi->writeData8(image_buffer[i] ^ 0xff);
    }
    spi->csHigh();
    spi->endTransaction();
}

void EPDPanel::setFrameMemory(const uint8_t* image_buffer, uint16_t x, uint16_t y, uint16_t image_width, uint16_t image_height) {
    if (!image_buffer) return;
    
    // Align to 8-pixel boundary
    x &= 0xFFF8;
    image_width &= 0xFFF8;
    
    uint16_t x_end = (x + image_width >= cfg.width) ? cfg.width - 1 : x + image_width - 1;
    uint16_t y_end = (y + image_height >= cfg.height) ? cfg.height - 1 : y + image_height - 1;

    // Full screen optimization
    if (!x && !y && image_width == cfg.width && image_height == cfg.height) {
        setFrameMemory(image_buffer);
        return;
    }

    setMemoryArea(x, y, x_end, y_end);
    setMemoryPointer(x, y);
    
    spi->beginTransaction();
    spi->csLow();
    spi->writeCommand(WRITE_RAM);
    for (uint16_t j = 0; j < y_end - y + 1; j++) {
        for (uint16_t i = 0; i < (x_end - x + 1) / 8; i++) {
            spi->writeData8(image_buffer[i + j * (image_width / 8)] ^ 0xff);
        }
    }
    spi->csHigh();
    spi->endTransaction();
}

void EPDPanel::sendEPData() {
    uint16_t image_width = cfg.width & 0xFFF8;
    
    for (uint16_t j = 0; j < cfg.height; j++) {
        for (uint16_t i = 0; i < cfg.width / 8; i++) {
            spi->writeData8(fb_buffer[i + j * (image_width / 8)] ^ 0xff);
        }
    }
}
