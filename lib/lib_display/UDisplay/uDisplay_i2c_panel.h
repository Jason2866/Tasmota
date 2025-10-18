#ifndef _UDISPLAY_I2C_PANEL_H_
#define _UDISPLAY_I2C_PANEL_H_

#include <Arduino.h>
#include <Wire.h>
#include "uDisplay_panel.h"

class i2c_panel : public UniversalPanel {

public:
    i2c_panel(uint8_t i2c_addr, TwoWire& wire,
              uint16_t width, uint16_t height,  // Add dimensions
              uint8_t set_x_cmd, uint8_t set_y_cmd, uint8_t write_cmd,
              uint8_t page_start, uint8_t page_end, uint8_t col_start, uint8_t col_end,
              uint8_t display_on_cmd, uint8_t display_off_cmd,
              uint8_t invert_on_cmd, uint8_t invert_off_cmd,
              uint8_t* init_commands, uint16_t init_commands_count,
              uint8_t* framebuffer);
    
    bool updateFrame() override;
    bool displayOnff(int8_t on) override;
    bool invertDisplay(bool invert) override;
    bool setRotation(uint8_t rotation) override { return true; }
    
    bool drawPixel(int16_t x, int16_t y, uint16_t color) override { return false; }
    bool fillRect(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t color) override { return false; }
    bool pushColors(uint16_t *data, uint16_t len, bool first = false) override { return false; }
    bool setAddrWindow(int16_t x0, int16_t y0, int16_t x1, int16_t y1) override { return false; }
    bool drawFastHLine(int16_t x, int16_t y, int16_t w, uint16_t color) override { return false; }
    bool drawFastVLine(int16_t x, int16_t y, int16_t h, uint16_t color) override { return false; }

    uint8_t* framebuffer = nullptr;

private:
    void i2c_command(uint8_t val);

    uint8_t _i2c_address;
    TwoWire& _wire;
    
    uint16_t _width, _height;
    uint8_t _set_x_cmd, _set_y_cmd, _write_cmd;
    uint8_t _page_start, _page_end, _col_start, _col_end;
    uint8_t _display_on_cmd, _display_off_cmd;
    uint8_t _invert_on_cmd, _invert_off_cmd;
};

#endif // _UDISPLAY_I2C_PANEL_H_