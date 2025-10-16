#include "uDisplay.h"
#include "uDisplay_config.h"

// ===== High-Level SPI Communication Functions =====

void uDisplay::ulcd_command(uint8_t val) {
    if (interface == _UDSP_SPI) {
        if (spi_dc < 0) {
            if (spi_nr > 2) {
                if (spi_nr == 3) {
                    spiController->write9(val, 0);
                } else {
                    spiController->write9_slow(val, 0);
                }
            } else {
                spiController->hw_write9(val, 0);
            }
        } else {
            spiController->dcLow();
            if (spi_nr > 2) {
                if (spi_nr == 3) {
                    spiController->write8(val);
                } else {
                    spiController->write8_slow(val);
                }
            } else {
                spiController->getSPI()->write(val);
            }
            spiController->dcHigh();
        }
        return;
    }

#ifdef UDISPLAY_I80
    if (interface == _UDSP_PAR8 || interface == _UDSP_PAR16) {
        pb_writeCommand(val, 8);
    }
#endif //UDISPLAY_I80
}

void uDisplay::ulcd_data8(uint8_t val) {
    if (interface == _UDSP_SPI) {
        if (spi_dc < 0) {
            if (spi_nr > 2) {
                if (spi_nr == 3) {
                    spiController->write9(val, 1);
                } else {
                    spiController->write9_slow(val, 1);
                }
            } else {
                spiController->hw_write9(val, 1);
            }
        } else {
            if (spi_nr > 2) {
                if (spi_nr == 3) {
                    spiController->write8(val);
                } else {
                    spiController->write8_slow(val);
                }
            } else {
                spiController->getSPI()->write(val);
            }
        }
        return;
    }

#ifdef UDISPLAY_I80
    if (interface == _UDSP_PAR8 || interface == _UDSP_PAR16) {
        pb_writeData(val, 8);
    }
#endif // UDISPLAY_I80
}

void uDisplay::ulcd_data16(uint16_t val) {
    if (interface == _UDSP_SPI) {
        if (spi_dc < 0) {
            if (spi_nr > 2) {
                spiController->write9(val >> 8, 1);
                spiController->write9(val, 1);
            } else {
                spiController->hw_write9(val >> 8, 1);
                spiController->hw_write9(val, 1);
            }
        } else {
            if (spi_nr > 2) {
                spiController->write16(val);
            } else {
                spiController->getSPI()->write16(val);
            }
        }
        return;
    }

#ifdef UDISPLAY_I80
    if (interface == _UDSP_PAR8 || interface == _UDSP_PAR16) {
        pb_writeData(val, 16);
    }
#endif // UDISPLAY_I80
}

void uDisplay::ulcd_data32(uint32_t val) {
    if (interface == _UDSP_SPI) {
        if (spi_dc < 0) {
            if (spi_nr > 2) {
                spiController->write9(val >> 24, 1);
                spiController->write9(val >> 16, 1);
                spiController->write9(val >> 8, 1);
                spiController->write9(val, 1);
            } else {
                spiController->hw_write9(val >> 24, 1);
                spiController->hw_write9(val >> 16, 1);
                spiController->hw_write9(val >> 8, 1);
                spiController->hw_write9(val, 1);
            }
        } else {
            if (spi_nr > 2) {
                spiController->write32(val);
            } else {
                spiController->getSPI()->write32(val);
            }
        }
        return;
    }

#ifdef UDISPLAY_I80
    if (interface == _UDSP_PAR8 || interface == _UDSP_PAR16) {
        pb_writeData(val, 32);
    }
#endif //UDISPLAY_I80
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