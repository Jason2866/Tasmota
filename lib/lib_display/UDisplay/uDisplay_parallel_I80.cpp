#include "uDisplay.h"
#include "uDisplay_config.h"

#if defined(UDISPLAY_I80)

#define WAIT_LCD_NOT_BUSY while (*reg_lcd_user & LCD_CAM_LCD_START) {}

// ===== Parallel Bus Control Functions =====
static inline volatile uint32_t* get_gpio_hi_reg(int_fast8_t pin) { return (pin & 32) ? &GPIO.out1_w1ts.val : &GPIO.out_w1ts; }
static inline volatile uint32_t* get_gpio_lo_reg(int_fast8_t pin) { return (pin & 32) ? &GPIO.out1_w1tc.val : &GPIO.out_w1tc; }
static inline void gpio_hi(int_fast8_t pin) { if (pin >= 0) *get_gpio_hi_reg(pin) = 1 << (pin & 31); } // ESP_LOGI("LGFX", "gpio_hi: %d", pin); }
static inline void gpio_lo(int_fast8_t pin) { if (pin >= 0) *get_gpio_lo_reg(pin) = 1 << (pin & 31); } // ESP_LOGI("LGFX", "gpio_lo: %d", pin); }

// ===== ESP32-S3 Pin Control =====

void uDisplay::cs_control(bool level) {
    auto pin = par_cs;
    if (pin < 0) return;
    if (level) {
      gpio_hi(pin);
    }
    else {
      gpio_lo(pin);
    }
}

// ===== ESP32-S3 Clock Calculation =====

void uDisplay::calcClockDiv(uint32_t* div_a, uint32_t* div_b, uint32_t* div_n, uint32_t* clkcnt, uint32_t baseClock, uint32_t targetFreq) {
    uint32_t diff = INT32_MAX;
    *div_n = 256;
    *div_a = 63;
    *div_b = 62;
    *clkcnt = 64;
    uint32_t start_cnt = std::min<uint32_t>(64u, (baseClock / (targetFreq * 2) + 1));
    uint32_t end_cnt = std::max<uint32_t>(2u, baseClock / 256u / targetFreq);
    if (start_cnt <= 2) { end_cnt = 1; }
    for (uint32_t cnt = start_cnt; diff && cnt >= end_cnt; --cnt)
    {
      float fdiv = (float)baseClock / cnt / targetFreq;
      uint32_t n = std::max<uint32_t>(2u, (uint32_t)fdiv);
      fdiv -= n;

      for (uint32_t a = 63; diff && a > 0; --a)
      {
        uint32_t b = roundf(fdiv * a);
        if (a == b && n == 256) {
          break;
        }
        uint32_t freq = baseClock / ((n * cnt) + (float)(b * cnt) / (float)a);
        uint32_t d = abs((int)targetFreq - (int)freq);
        if (diff <= d) { continue; }
        diff = d;
        *clkcnt = cnt;
        *div_n = n;
        *div_b = b;
        *div_a = a;
        if (b == 0 || a == b) {
          break;
        }
      }
    }
    if (*div_a == *div_b)
    {
        *div_b = 0;
        *div_n += 1;
    }
}

// ===== ESP32-S3 DMA Descriptor Management =====

void uDisplay::_alloc_dmadesc(size_t len) {
    if (_dmadesc) heap_caps_free(_dmadesc);
    _dmadesc_size = len;
    _dmadesc = (lldesc_t*)heap_caps_malloc(sizeof(lldesc_t) * len, MALLOC_CAP_DMA);
}

void uDisplay::_setup_dma_desc_links(const uint8_t *data, int32_t len) {
    static constexpr size_t MAX_DMA_LEN = (4096-4);
}

void uDisplay::_pb_init_pin(bool read) {
    if (read) {
      if (interface == _UDSP_PAR8) {
        for (size_t i = 0; i < 8; ++i) {
          gpio_ll_output_disable(&GPIO, (gpio_num_t)par_dbl[i]);
        }
      } else {
        for (size_t i = 0; i < 8; ++i) {
          gpio_ll_output_disable(&GPIO, (gpio_num_t)par_dbl[i]);
        }
        for (size_t i = 0; i < 8; ++i) {
          gpio_ll_output_disable(&GPIO, (gpio_num_t)par_dbh[i]);
        }
      }
    }
    else {
      auto idx_base = LCD_DATA_OUT0_IDX;
      if (interface == _UDSP_PAR8) {
        for (size_t i = 0; i < 8; ++i) {
          gpio_matrix_out(par_dbl[i], idx_base + i, 0, 0);
        }
      } else {
        for (size_t i = 0; i < 8; ++i) {
          gpio_matrix_out(par_dbl[i], idx_base + i, 0, 0);
        }
        for (size_t i = 0; i < 8; ++i) {
          gpio_matrix_out(par_dbh[i], idx_base + 8 + i, 0, 0);
        }
      }
    }
}

void uDisplay::pb_beginTransaction(void) {
    auto dev = _dev;
    dev->lcd_clock.val = _clock_reg_value;
    dev->lcd_misc.val = LCD_CAM_LCD_CD_IDLE_EDGE;
    dev->lcd_user.val = LCD_CAM_LCD_CMD | LCD_CAM_LCD_UPDATE_REG;
    _cache_flip = _cache[0];
}

void uDisplay::pb_endTransaction(void) {
    auto dev = _dev;
    while (dev->lcd_user.val & LCD_CAM_LCD_START) {}
}

void uDisplay::pb_wait(void) {
    auto dev = _dev;
    while (dev->lcd_user.val & LCD_CAM_LCD_START) {}
}

bool uDisplay::pb_busy(void) {
    auto dev = _dev;
    return (dev->lcd_user.val & LCD_CAM_LCD_START);
}

// ===== Parallel Bus Write Functions =====

bool uDisplay::pb_writeCommand(uint32_t data, uint_fast8_t bit_length) {
    auto dev = _dev;
    auto reg_lcd_user = &(dev->lcd_user.val);
    dev->lcd_misc.val = LCD_CAM_LCD_CD_IDLE_EDGE | LCD_CAM_LCD_CD_CMD_SET;

    if (interface == _UDSP_PAR8) {
        auto bytes = bit_length >> 3;
        do {
            dev->lcd_cmd_val.lcd_cmd_value = data;
            data >>= 8;
            WAIT_LCD_NOT_BUSY
            *reg_lcd_user = LCD_CAM_LCD_CMD | LCD_CAM_LCD_UPDATE_REG | LCD_CAM_LCD_START;
        } while (--bytes);
        return true;
    } else {
        dev->lcd_cmd_val.val = data;
        WAIT_LCD_NOT_BUSY
        *reg_lcd_user = LCD_CAM_LCD_2BYTE_EN | LCD_CAM_LCD_CMD | LCD_CAM_LCD_UPDATE_REG | LCD_CAM_LCD_START;
        return true;
    }
}

void uDisplay::pb_writeData(uint32_t data, uint_fast8_t bit_length) {
    auto dev = _dev;
    auto reg_lcd_user = &(dev->lcd_user.val);
    dev->lcd_misc.val = LCD_CAM_LCD_CD_IDLE_EDGE;
    auto bytes = bit_length >> 3;

    if (interface == _UDSP_PAR8) {
        uint8_t shift = (bytes - 1) * 8;
        for (uint32_t cnt = 0; cnt < bytes; cnt++) {
            dev->lcd_cmd_val.lcd_cmd_value = (data >> shift) & 0xff;
            shift -= 8;
            WAIT_LCD_NOT_BUSY
            *reg_lcd_user = LCD_CAM_LCD_CMD | LCD_CAM_LCD_UPDATE_REG | LCD_CAM_LCD_START;
        }
        return;
    } else {
        if (bytes == 1 || bytes == 4) {
            uint8_t shift = (bytes - 1) * 8;
            for (uint32_t cnt = 0; cnt < bytes; cnt++) {
                dev->lcd_cmd_val.lcd_cmd_value = (data >> shift) & 0xff;
                shift -= 8;
                WAIT_LCD_NOT_BUSY
                *reg_lcd_user = LCD_CAM_LCD_2BYTE_EN | LCD_CAM_LCD_CMD | LCD_CAM_LCD_UPDATE_REG | LCD_CAM_LCD_START;
            }
            return;
        }

        dev->lcd_cmd_val.val = data;
        WAIT_LCD_NOT_BUSY
        *reg_lcd_user = LCD_CAM_LCD_2BYTE_EN | LCD_CAM_LCD_CMD | LCD_CAM_LCD_UPDATE_REG | LCD_CAM_LCD_START;
        return;
    }
}

void uDisplay::pb_pushPixels(uint16_t* data, uint32_t length, bool swap_bytes, bool use_dma) {
    auto dev = _dev;
    auto reg_lcd_user = &(dev->lcd_user.val);
    dev->lcd_misc.val = LCD_CAM_LCD_CD_IDLE_EDGE;

    if (interface == _UDSP_PAR8) {
        if (swap_bytes) {
            for (uint32_t cnt = 0; cnt < length; cnt++) {
                dev->lcd_cmd_val.lcd_cmd_value = *data;
                while (*reg_lcd_user & LCD_CAM_LCD_START) {}
                *reg_lcd_user = LCD_CAM_LCD_CMD | LCD_CAM_LCD_UPDATE_REG | LCD_CAM_LCD_START;
                dev->lcd_cmd_val.lcd_cmd_value = *data >> 8;
                WAIT_LCD_NOT_BUSY
                *reg_lcd_user = LCD_CAM_LCD_CMD | LCD_CAM_LCD_UPDATE_REG | LCD_CAM_LCD_START;
                data++;
            }
        } else {
            for (uint32_t cnt = 0; cnt < length; cnt++) {
                dev->lcd_cmd_val.lcd_cmd_value = *data >> 8;
                while (*reg_lcd_user & LCD_CAM_LCD_START) {}
                *reg_lcd_user = LCD_CAM_LCD_CMD | LCD_CAM_LCD_UPDATE_REG | LCD_CAM_LCD_START;
                dev->lcd_cmd_val.lcd_cmd_value = *data;
                WAIT_LCD_NOT_BUSY
                *reg_lcd_user = LCD_CAM_LCD_CMD | LCD_CAM_LCD_UPDATE_REG | LCD_CAM_LCD_START;
                data++;
            }
        }
    } else {
        if (swap_bytes) {
            uint16_t iob;
            for (uint32_t cnt = 0; cnt < length; cnt++) {
                iob = *data++;
                iob = (iob << 8) | (iob >> 8);
                dev->lcd_cmd_val.lcd_cmd_value = iob;
                WAIT_LCD_NOT_BUSY
                *reg_lcd_user = LCD_CAM_LCD_2BYTE_EN | LCD_CAM_LCD_CMD | LCD_CAM_LCD_UPDATE_REG | LCD_CAM_LCD_START;
            }
        } else {
            for (uint32_t cnt = 0; cnt < length; cnt++) {
                dev->lcd_cmd_val.lcd_cmd_value = *data++;
                WAIT_LCD_NOT_BUSY
                *reg_lcd_user = LCD_CAM_LCD_2BYTE_EN | LCD_CAM_LCD_CMD | LCD_CAM_LCD_UPDATE_REG | LCD_CAM_LCD_START;
            }
        }
    }
}

// reconfigures parallel bus pins as GPIOs for analog touch sensing and digital I/O
uint32_t uDisplay::get_sr_touch(uint32_t _xp, uint32_t _xm, uint32_t _yp, uint32_t _ym) {
  uint32_t aval = 0;
  uint16_t xp,yp;
  if (pb_busy()) return 0;

  _pb_init_pin(true);
  gpio_matrix_out(par_rs, 0x100, 0, 0);

  pinMode(_ym, INPUT_PULLUP); // d0
  pinMode(_yp, INPUT_PULLUP); // rs

  pinMode(_xm, OUTPUT); // cs
  pinMode(_xp, OUTPUT); // d1
  digitalWrite(_xm, HIGH); // cs
  digitalWrite(_xp, LOW); // d1

  xp = 4096 - analogRead(_ym); // d0

  pinMode(_xm, INPUT_PULLUP); // cs
  pinMode(_xp, INPUT_PULLUP); // d1

  pinMode(_ym, OUTPUT); // d0
  pinMode(_yp, OUTPUT); // rs
  digitalWrite(_ym, HIGH); // d0
  digitalWrite(_yp, LOW); // rs

  yp = 4096 - analogRead(_xp); // d1

  aval = (xp << 16) | yp;

  pinMode(_yp, OUTPUT); // rs
  pinMode(_xm, OUTPUT); // cs
  pinMode(_ym, OUTPUT); // d0
  pinMode(_xp, OUTPUT); // d1
  digitalWrite(_yp, HIGH); // rs
  digitalWrite(_xm, HIGH); // cs

  _pb_init_pin(false);
  gpio_matrix_out(par_rs, LCD_DC_IDX, 0, 0);

  return aval;
}

#endif // SOC_LCD_I80_SUPPORTED