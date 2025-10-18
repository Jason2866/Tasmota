#include "uDisplay_i2c_panel.h"

i2c_panel::i2c_panel(uint8_t i2c_addr, TwoWire& wire,
                     uint16_t width, uint16_t height,
                     uint8_t set_x_cmd, uint8_t set_y_cmd, uint8_t write_cmd,
                     uint8_t page_start, uint8_t page_end, uint8_t col_start, uint8_t col_end,
                     uint8_t display_on_cmd, uint8_t display_off_cmd,
                     uint8_t invert_on_cmd, uint8_t invert_off_cmd, uint8_t* init_commands, uint16_t init_commands_count, uint8_t* framebuffer)
    : _i2c_address(i2c_addr), _wire(wire),
      _width(width), _height(height),
      _set_x_cmd(set_x_cmd), _set_y_cmd(set_y_cmd), _write_cmd(write_cmd),
      _page_start(page_start), _page_end(page_end), _col_start(col_start), _col_end(col_end),
      _display_on_cmd(display_on_cmd), _display_off_cmd(display_off_cmd),
      _invert_on_cmd(invert_on_cmd), _invert_off_cmd(invert_off_cmd), framebuffer(framebuffer) {
            
        for (uint16_t i = 0; i < init_commands_count; i++) {
            i2c_command(init_commands[i]);
        }
}

bool i2c_panel::updateFrame() {
    if (!framebuffer) return false;
    
    i2c_command(_set_x_cmd | 0x0);
    i2c_command(_page_start | 0x0);  
    i2c_command(_page_end | 0x0);

    uint8_t ys = _height >> 3;  // Use stored height
    uint8_t xs = _width >> 3;   // Use stored width
    uint8_t m_row = _set_y_cmd;
    uint8_t m_col = _col_start;

    uint16_t p = 0;
    uint8_t i, j, k = 0;

    for (i = 0; i < ys; i++) {
        i2c_command(0xB0 + i + m_row);
        i2c_command(m_col & 0xf);
        i2c_command(0x10 | (m_col >> 4));

        for (j = 0; j < 8; j++) {
            _wire.beginTransmission(_i2c_address);
            _wire.write(0x40);
            for (k = 0; k < xs; k++, p++) {
                _wire.write(framebuffer[p]);
            }
            _wire.endTransmission();
        }
    }
    return true;
}

bool i2c_panel::displayOnff(int8_t on) {
    i2c_command(on ? _display_on_cmd : _display_off_cmd);
    return true;
}

bool i2c_panel::invertDisplay(bool invert) {
    i2c_command(invert ? _invert_on_cmd : _invert_off_cmd);
    return true;
}

void i2c_panel::i2c_command(uint8_t val) {
    _wire.beginTransmission(_i2c_address);
    _wire.write(0);
    _wire.write(val);
    _wire.endTransmission();
}