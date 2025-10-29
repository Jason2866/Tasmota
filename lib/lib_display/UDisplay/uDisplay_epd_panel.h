// ======================================================
// uDisplay_epd_panel.h - E-Paper Display Panel Implementation
// ======================================================

#pragma once

#include "uDisplay_panel.h"
#include "uDisplay_SPI_controller.h"

/**
 * Configuration for E-Paper displays
 */
struct EPDPanelConfig {
    uint16_t width;
    uint16_t height;
    uint8_t bpp;  // Always 1 for EPD
    uint8_t ep_mode; // 1=2-LUT, 2=5-LUT, 3=command-based
    
    // Timing
    int16_t lut_full_time;
    uint16_t lut_partial_time;
    uint16_t update_time;
    
    // Pins
    int8_t reset_pin;
    int8_t busy_pin;
    
    // EPD-specific flags
    bool invert_colors;        // If true, invert color logic
    bool invert_framebuffer;   // If true, invert when sending to display
    bool busy_invert;          // If true, busy pin is active low
    
    // Busy timeout
    uint16_t busy_timeout = 3000; // UDSP_BUSY_TIMEOUT
    
    // Command bytes for ep_mode 2 (4.2" displays)
    uint8_t saw_1 = 0;  // First command for frame update
    uint8_t saw_2 = 0;  // Second command for frame update
    uint8_t saw_3 = 0;  // Third command for frame update
    
    // LUT data (for ep_mode 1 - 2-LUT mode)
    const uint8_t* lut_full = nullptr;
    uint16_t lut_full_len = 0;
    const uint8_t* lut_partial = nullptr;
    uint16_t lut_partial_len = 0;
    
    // LUT data (for ep_mode 2 - 5-LUT mode)
    const uint8_t** lut_array = nullptr;  // Array of 5 LUTs
    const uint8_t* lut_cnt = nullptr;     // Size of each LUT
    uint8_t lut_cmd[5] = {0};             // Commands for each LUT
};

class EPDPanel : public UniversalPanel {
public:
    EPDPanel(const EPDPanelConfig& config,
             SPIController* spi_ctrl,
             uint8_t* framebuffer);  // REQUIRED for EPD

    ~EPDPanel();

    // UniversalPanel interface
    bool drawPixel(int16_t x, int16_t y, uint16_t color) override;
    bool fillRect(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t color) override;
    bool pushColors(uint16_t *data, uint16_t len, bool first = false) override;
    bool setAddrWindow(int16_t x0, int16_t y0, int16_t x1, int16_t y1) override;
    bool drawFastHLine(int16_t x, int16_t y, int16_t w, uint16_t color) override;
    bool drawFastVLine(int16_t x, int16_t y, int16_t h, uint16_t color) override;
    
    bool displayOnff(int8_t on) override;
    bool invertDisplay(bool invert) override;
    bool setRotation(uint8_t rotation) override;
    bool updateFrame() override;

    // EPD-specific public methods (for uDisplay wrapper compatibility)
    void setLut(const uint8_t* lut, uint16_t len);
    void setLuts();  // For ep_mode 2 (5-LUT mode)
    void setMemoryArea(int x_start, int y_start, int x_end, int y_end);
    void setMemoryPointer(int x, int y);
    void clearFrameMemory(uint8_t color);
    void displayFrame();
    void delay_sync(int32_t ms);
    
    // ep_mode 2 specific (4.2" displays)
    void clearFrame_42();
    void displayFrame_42();
    
    // Frame memory management
    void setFrameMemory(const uint8_t* image_buffer);
    void setFrameMemory(const uint8_t* image_buffer, uint16_t x, uint16_t y, uint16_t w, uint16_t h);
    void sendEPData();

    EPDPanelConfig cfg;

private:
    SPIController* spi;
    uint8_t* fb_buffer;  // Framebuffer (always used)
    uint8_t update_mode; // 0=full, 1=partial

    // Private helpers
    void resetDisplay();
    void waitBusy();
    void drawAbsolutePixel(int x, int y, uint16_t color);
};