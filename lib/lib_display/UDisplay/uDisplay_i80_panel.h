#pragma once

#ifdef ESP32
#if __has_include("soc/soc_caps.h")
# include "soc/soc_caps.h"
#else
# error "No ESP capability header found"
#endif

#if (SOC_LCD_I80_SUPPORTED && SOC_LCDCAM_I80_NUM_BUSES)

#include "uDisplay_panel.h"

#include "esp_private/gdma.h"
#include <hal/gpio_ll.h>
#include <hal/lcd_hal.h>
#include <soc/lcd_cam_reg.h>
#include <soc/lcd_cam_struct.h>
#include "esp_rom_lldesc.h"
#include "esp_lcd_io_i80.h"
#include "esp_private/gdma.h"
#include <hal/gpio_ll.h>
#include <hal/lcd_hal.h>
#include <soc/lcd_cam_reg.h>
#include <soc/lcd_cam_struct.h>
#include "esp_pm.h"
#include <hal/dma_types.h>
#include <rom/cache.h>
#include "esp_rom_lldesc.h"
#include <rom/gpio.h>

class I80Panel : public UniversalPanel {
public:
    I80Panel(int16_t width, int16_t height, 
            int8_t cs_pin, int8_t dc_pin, int8_t wr_pin, int8_t rd_pin,
            int8_t* data_pins_low, int8_t* data_pins_high, uint8_t bus_width,
            uint32_t clock_speed_hz,
            uint8_t col_cmd, uint8_t row_cmd, uint8_t write_cmd,
            uint8_t color_mode = 16,
            uint16_t* x_offsets = nullptr, uint16_t* y_offsets = nullptr,
            uint8_t* init_commands = nullptr, uint16_t init_commands_count = 0);
    virtual ~I80Panel();

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
    
    // Simple resistive touch hack
    uint32_t getSimpleResistiveTouch(uint32_t threshold);

    // DMA functionality
    bool initDMA();
    void deInitDMA();
    bool dmaBusy();
    void dmaWait();

private:
    // I80 configuration
    int8_t _cs_pin, _dc_pin, _wr_pin, _rd_pin;
    int8_t _data_pins_low[8];
    int8_t _data_pins_high[8];
    uint8_t _bus_width;
    uint32_t _clock_speed;
    int16_t _orig_width, _orig_height;
    int16_t _width, _height;
    uint8_t _rotation;
    uint8_t _color_mode;
    
    // Display commands
    uint8_t _col_cmd, _row_cmd, _write_cmd;
    
    // Rotation offsets
    uint16_t _x_offsets[4];
    uint16_t _y_offsets[4];
    
    // I80 hardware handles
    esp_lcd_i80_bus_handle_t _i80_bus;
    volatile lcd_cam_dev_t* _dev;
    uint32_t _clock_reg_value;

    // DMA resources
    bool _DMA_Enabled;
    gdma_channel_handle_t _dma_chan;
    lldesc_t *_dmadesc;
    uint32_t _dmadesc_size;

    // Current address window
    int16_t _addr_x0, _addr_y0, _addr_x1, _addr_y1;

    // Low-level I80 functions
    void calcClockDiv(uint32_t* div_a, uint32_t* div_b, uint32_t* div_n, uint32_t* clkcnt, uint32_t baseClock, uint32_t targetFreq);
    void _alloc_dmadesc(size_t len);
    void _setup_dma_desc_links(const uint8_t *data, int32_t len);
    void pb_beginTransaction(void);
    void pb_endTransaction(void);
    void pb_wait(void);
    bool pb_busy(void);
    void _pb_init_pin(bool read);
    bool pb_writeCommand(uint32_t data, uint_fast8_t bit_length);
    void pb_writeData(uint32_t data, uint_fast8_t bit_length);
    void pb_writeBytes(const uint8_t* data, uint32_t length, bool use_dma);
    void pb_pushPixels(uint16_t* data, uint32_t length, bool swap_bytes, bool use_dma);
    void cs_control(bool level);
    
    // Color mode helpers
    void writeColor(uint16_t color);
    void setAddrWindow_int(uint16_t x, uint16_t y, uint16_t w, uint16_t h);
};
#endif // SOC_LCD_I80_SUPPORTED && SOC_LCDCAM_I80_NUM_BUSES
#endif // ESP32