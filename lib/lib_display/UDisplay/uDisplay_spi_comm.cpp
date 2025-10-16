#include "uDisplay.h"
#include "uDisplay_config.h"

// ===== High-Level SPI Communication Functions =====
void uDisplay::ulcd_command(uint8_t val) {
    if (interface == _UDSP_SPI) {
        spiController->writeCommand(val);
        return;
    }
#ifdef UDISPLAY_I80
    if (interface == _UDSP_PAR8 || interface == _UDSP_PAR16) {
        pb_writeCommand(val, 8);
    }
#endif
}

void uDisplay::ulcd_data8(uint8_t val) {
    if (interface == _UDSP_SPI) {
        spiController->writeData8(val);
        return;
    }
#ifdef UDISPLAY_I80
    if (interface == _UDSP_PAR8 || interface == _UDSP_PAR16) {
        pb_writeData(val, 8);
    }
#endif
}

void uDisplay::ulcd_data16(uint16_t val) {
    if (interface == _UDSP_SPI) {
        spiController->writeData16(val);
        return;
    }
#ifdef UDISPLAY_I80
    if (interface == _UDSP_PAR8 || interface == _UDSP_PAR16) {
        pb_writeData(val, 16);
    }
#endif
}

void uDisplay::ulcd_data32(uint32_t val) {
    if (interface == _UDSP_SPI) {
        spiController->writeData32(val);
        return;
    }
#ifdef UDISPLAY_I80
    if (interface == _UDSP_PAR8 || interface == _UDSP_PAR16) {
        pb_writeData(val, 32);
    }
#endif
}

void uDisplay::ulcd_command_one(uint8_t val) {
    if (interface == _UDSP_SPI) {
        spiController->beginTransaction();
        spiController->csLow();
        ulcd_command(val);
        spiController->csHigh();
        spiController->endTransaction();
    }
}

void uDisplay::WriteColor(uint16_t color) {
    if (col_mode == 18) {
        uint8_t r = (color & 0xF800) >> 11;
        uint8_t g = (color & 0x07E0) >> 5;
        uint8_t b = color & 0x001F;
        r = (r * 255) / 31;
        g = (g * 255) / 63;
        b = (b * 255) / 31;

        ulcd_data8(r);
        ulcd_data8(g);
        ulcd_data8(b);
    } else {
        ulcd_data16(color);
    }
}