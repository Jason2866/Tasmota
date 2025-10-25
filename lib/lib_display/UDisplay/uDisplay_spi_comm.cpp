#include "uDisplay.h"
#include "uDisplay_config.h"

// ===== High-Level SPI Communication Functions =====
void uDisplay::ulcd_command(uint8_t val) {
    if (interface == _UDSP_SPI) {
        spiController->writeCommand(val);
        return;
    }
}

void uDisplay::ulcd_data8(uint8_t val) {
    if (interface == _UDSP_SPI) {
        spiController->writeData8(val);
        return;
    }
}

// ulcd_data16, ulcd_data32 - removed as dead code

void uDisplay::ulcd_command_one(uint8_t val) {
    if (interface == _UDSP_SPI) {
        spiController->beginTransaction();
        spiController->csLow();
        ulcd_command(val);
        spiController->csHigh();
        spiController->endTransaction();
    }
}

// WriteColor - removed as dead code (I80Panel has its own implementation)