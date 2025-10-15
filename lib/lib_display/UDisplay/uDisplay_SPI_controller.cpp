#include "uDisplay_SPI_controller.h"

// ===== GPIO Macros =====
#ifdef ESP8266
#define PIN_OUT_SET 0x60000304
#define PIN_OUT_CLEAR 0x60000308
#define GPIO_SET(A) WRITE_PERI_REG(PIN_OUT_SET, 1 << A)
#define GPIO_CLR(A) WRITE_PERI_REG(PIN_OUT_CLEAR, 1 << A)
#define GPIO_SET_SLOW(A) digitalWrite(A, HIGH)
#define GPIO_CLR_SLOW(A) digitalWrite(A, LOW)
#else // ESP32
#if CONFIG_IDF_TARGET_ESP32C2 || CONFIG_IDF_TARGET_ESP32C3 || CONFIG_IDF_TARGET_ESP32C5 || CONFIG_IDF_TARGET_ESP32C6 || CONFIG_IDF_TARGET_ESP32P4
#define GPIO_CLR(A) GPIO.out_w1tc.val = (1 << A)
#define GPIO_SET(A) GPIO.out_w1ts.val = (1 << A)
#else // plain ESP32 or S3
#define GPIO_CLR(A) GPIO.out_w1tc = (1 << A)
#define GPIO_SET(A) GPIO.out_w1ts = (1 << A)
#endif
#define GPIO_SET_SLOW(A) digitalWrite(A, HIGH)
#define GPIO_CLR_SLOW(A) digitalWrite(A, LOW)
#endif

// ===== RA8876 Constants =====
static constexpr uint8_t RA8876_DATA_WRITE  = 0x80;
static constexpr uint8_t RA8876_DATA_READ   = 0xC0;
static constexpr uint8_t RA8876_CMD_WRITE   = 0x00;
static constexpr uint8_t RA8876_STATUS_READ = 0x40;

extern void AddLog(uint32_t loglevel, const char* formatP, ...);

SPIController::SPIController(SPIClass* spi_ptr, uint32_t spi_speed, int8_t cs, int8_t dc, int8_t clk, int8_t mosi, 
                           int8_t miso, uint8_t spi_nr, bool use_dma, bool async_dma, int8_t& busy_pin_ref, 
                           void* spi_host_ptr)  // spi_host is spi_host_device_t in ESP32
    : spi(spi_ptr),
      speed(spi_speed),
      pin_cs(cs), 
      pin_dc(dc), 
      pin_clk(clk), 
      pin_mosi(mosi), 
      pin_miso(miso),
      spi_bus_nr(spi_nr),
      async_dma_enabled(async_dma),
      busy_pin(busy_pin_ref),
      spi_host(*(spi_host_device_t*)spi_host_ptr)
{
    if (pin_dc >= 0) {
      pinMode(pin_dc, OUTPUT);
      digitalWrite(pin_dc, HIGH);
    }
    if (pin_cs >= 0) {
      pinMode(pin_cs, OUTPUT);
      digitalWrite(pin_cs, HIGH);
    }

#ifdef ESP8266
    if (spi_nr <= 1) {
      SPI.begin();
      spi = &SPI;
    } else {
      pinMode(pin_clk, OUTPUT);
      digitalWrite(pin_clk, LOW);
      pinMode(pin_mosi, OUTPUT);
      digitalWrite(pin_mosi, LOW);
      if (pin_miso >= 0) {
        pinMode(pin_miso, INPUT_PULLUP);
        busy_pin_ref = pin_miso;  // Update the reference
      }
    }
#endif // ESP8266

#ifdef ESP32
    if (spi_nr == 1) {
      spi = &SPI;
      spi->begin(pin_clk, pin_miso, pin_mosi, -1);
      if (use_dma) {
        spi_host_device_t* spi_host = (spi_host_device_t*)spi_host_ptr;
        *spi_host = VSPI_HOST;
        // initDMA would need to be called separately or passed as callback
      }
    } else if (spi_nr == 2) {
      spi = new SPIClass(HSPI);
      spi->begin(pin_clk, pin_miso, pin_mosi, -1);
      if (use_dma) {
        spi_host_device_t* spi_host = (spi_host_device_t*)spi_host_ptr;
        *spi_host = HSPI_HOST;
        // initDMA would need to be called separately
      }
    } else {
      pinMode(pin_clk, OUTPUT);
      digitalWrite(pin_clk, LOW);
      pinMode(pin_mosi, OUTPUT);
      digitalWrite(pin_mosi, LOW);
      if (pin_miso >= 0) {
        busy_pin_ref = pin_miso;
        pinMode(pin_miso, INPUT_PULLUP);
      }
    }
#endif // ESP32
    if (use_dma) {
        initDMA(async_dma ? pin_cs : -1);
    }
    
    spi_settings = SPISettings((uint32_t)spi_speed*1000000, MSBFIRST, SPI_MODE3);
}

// ===== Pin Control =====

void SPIController::csLow() {
    if (pin_cs >= 0) GPIO_CLR_SLOW(pin_cs);
}

void SPIController::csHigh() {
    if (pin_cs >= 0) GPIO_SET_SLOW(pin_cs);
}

void SPIController::dcLow() {
    if (pin_dc >= 0) GPIO_CLR_SLOW(pin_dc);
}

void SPIController::dcHigh() {
    if (pin_dc >= 0) GPIO_SET_SLOW(pin_dc);
}

// ===== Transaction Control =====

void SPIController::beginTransaction() {
    if (spi) {
        AddLog(3, "SPICtrl: beginTransaction, spi=%p set=%p", spi, spi_settings);
        spi->beginTransaction(spi_settings);
    } else {
        AddLog(3, "SPICtrl: SPI is NULL!");
    }
}

void SPIController::endTransaction() {
    if (spi) spi->endTransaction();
}

// ===== Low-Level Write Functions =====

void SPIController::write8(uint8_t val) {
    for (uint8_t bit = 0x80; bit; bit >>= 1) {
        GPIO_CLR(pin_clk);
        if (val & bit) GPIO_SET(pin_mosi);
        else GPIO_CLR(pin_mosi);
        GPIO_SET(pin_clk);
    }
}

void SPIController::write8_slow(uint8_t val) {
    for (uint8_t bit = 0x80; bit; bit >>= 1) {
        GPIO_CLR_SLOW(pin_clk);
        if (val & bit) GPIO_SET_SLOW(pin_mosi);
        else GPIO_CLR_SLOW(pin_mosi);
        GPIO_SET_SLOW(pin_clk);
    }
}

void SPIController::write9(uint8_t val, uint8_t dc) {
    GPIO_CLR(pin_clk);
    if (dc) GPIO_SET(pin_mosi);
    else GPIO_CLR(pin_mosi);
    GPIO_SET(pin_clk);

    for (uint8_t bit = 0x80; bit; bit >>= 1) {
        GPIO_CLR(pin_clk);
        if (val & bit) GPIO_SET(pin_mosi);
        else GPIO_CLR(pin_mosi);
        GPIO_SET(pin_clk);
    }
}

void SPIController::write9_slow(uint8_t val, uint8_t dc) {
    GPIO_CLR_SLOW(pin_clk);
    if (dc) GPIO_SET_SLOW(pin_mosi);
    else GPIO_CLR_SLOW(pin_mosi);
    GPIO_SET_SLOW(pin_clk);

    for (uint8_t bit = 0x80; bit; bit >>= 1) {
        GPIO_CLR_SLOW(pin_clk);
        if (val & bit) GPIO_SET_SLOW(pin_mosi);
        else GPIO_CLR_SLOW(pin_mosi);
        GPIO_SET_SLOW(pin_clk);
    }
}

void SPIController::write16(uint16_t val) {
    for (uint16_t bit = 0x8000; bit; bit >>= 1) {
        GPIO_CLR(pin_clk);
        if (val & bit) GPIO_SET(pin_mosi);
        else GPIO_CLR(pin_mosi);
        GPIO_SET(pin_clk);
    }
}

void SPIController::write32(uint32_t val) {
    for (uint32_t bit = 0x80000000; bit; bit >>= 1) {
        GPIO_CLR(pin_clk);
        if (val & bit) GPIO_SET(pin_mosi);
        else GPIO_CLR(pin_mosi);
        GPIO_SET(pin_clk);
    }
}

// ===== Hardware 9-bit Mode =====

#ifdef ESP32
void SPIController::hw_write9(uint8_t val, uint8_t dc) {
    if (pin_dc < -1) {
        // RA8876 mode
        if (!dc) {
            spi->write(RA8876_CMD_WRITE);
            spi->write(val);
        } else {
            spi->write(RA8876_DATA_WRITE);
            spi->write(val);
        }
    } else {
        uint32_t regvalue = val >> 1;
        if (dc) regvalue |= 0x80;
        else regvalue &= 0x7f;
        if (val & 1) regvalue |= 0x8000;

        REG_SET_BIT(SPI_USER_REG(3), SPI_USR_MOSI);
        REG_WRITE(SPI_MOSI_DLEN_REG(3), 9 - 1);
        uint32_t *dp = (uint32_t*)SPI_W0_REG(3);
        *dp = regvalue;
        REG_SET_BIT(SPI_CMD_REG(3), SPI_USR);
        while (REG_GET_FIELD(SPI_CMD_REG(3), SPI_USR));
    }
}
#else
void SPIController::hw_write9(uint8_t val, uint8_t dc) {
    if (pin_dc < -1) {
        // RA8876 mode
        if (!dc) {
            spi->write(RA8876_CMD_WRITE);
            spi->write(val);
        } else {
            spi->write(RA8876_DATA_WRITE);
            spi->write(val);
        }
    } else {
        uint32_t regvalue;
        uint8_t bytetemp;
        if (!dc) {
            bytetemp = (val >> 1) & 0x7f;
        } else {
            bytetemp = (val >> 1) | 0x80;
        }
        regvalue = ((8 & SPI_USR_COMMAND_BITLEN) << SPI_USR_COMMAND_BITLEN_S) | ((uint32)bytetemp);
        if (val & 0x01) regvalue |= BIT15;
        while (READ_PERI_REG(SPI_CMD(1)) & SPI_USR);
        WRITE_PERI_REG(SPI_USER2(1), regvalue);
        SET_PERI_REG_MASK(SPI_CMD(1), SPI_USR);
    }
}
#endif

bool SPIController::initDMA(int32_t ctrl_cs) {
#ifdef ESP32
    if (!spi) return false;
    
    esp_err_t ret;
    spi_bus_config_t buscfg = {
        .mosi_io_num = pin_mosi,
        .miso_io_num = -1,
        .sclk_io_num = pin_clk,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = 320 * 240 * 2 + 8,
        .flags = 0,
        .intr_flags = 0
    };

    spi_device_interface_config_t devcfg = {
        .command_bits = 0,
        .address_bits = 0,
        .dummy_bits = 0,
        .mode = SPI_MODE3,
        .duty_cycle_pos = 0,
        .cs_ena_pretrans = 0,
        .cs_ena_posttrans = 0,
        .clock_speed_hz = speed,
        .input_delay_ns = 0,
        .spics_io_num = ctrl_cs,
        .flags = SPI_DEVICE_NO_DUMMY,
        .queue_size = 1,
        .pre_cb = 0,
        .post_cb = 0
    };
    
    spi_host_device_t spi_host = (spi_bus_nr == 1) ? VSPI_HOST : HSPI_HOST;
    ret = spi_bus_initialize(spi_host, &buscfg, 1);
    if (ret != ESP_OK) return false;
    
    ret = spi_bus_add_device(spi_host, &devcfg, &dmaHAL);
    return (ret == ESP_OK);
#else
    return false;
#endif
}

// ===== RA8876 Specific =====

uint8_t SPIController::writeReg16(uint8_t reg, uint16_t wval) {
    hw_write9(reg, 0);
    hw_write9(wval, 1);
    hw_write9(reg + 1, 0);
    hw_write9(wval >> 8, 1);
    return 0;
}

uint8_t SPIController::readData(void) {
    if (!spi) return 0;
    spi->write(RA8876_DATA_READ);
    return spi->transfer(0);
}

uint8_t SPIController::readStatus(void) {
    if (!spi) return 0;
    spi->write(RA8876_STATUS_READ);
    return spi->transfer(0);
}
