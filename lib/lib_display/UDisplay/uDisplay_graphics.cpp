#include "uDisplay.h"
#include "uDisplay_config.h"

// ===== Basic Drawing Primitives =====

static constexpr uint16_t RGB16_TO_MONO      = 0x8410;
static constexpr uint16_t RGB16_SWAP_TO_MONO = 0x1084;

void uDisplay::drawPixel(int16_t x, int16_t y, uint16_t color) {
    if (universal_panel && universal_panel->drawPixel(x, y, color)) {
        return; // Handled by universal panel
    }

    if (ep_mode) {
        drawPixel_EPD(x, y, color);
        return;
    }

    if (framebuffer) {
        Renderer::drawPixel(x, y, color);
        return;
    }

    if ((x < 0) || (x >= _width) || (y < 0) || (y >= _height)) return;

    spiController->beginTransaction();
    spiController->csLow();
    setAddrWindow_int(x, y, 1, 1);
    WriteColor(color);
    spiController->csHigh();
    spiController->endTransaction();
}

void uDisplay::drawFastHLine(int16_t x, int16_t y, int16_t w, uint16_t color) {
    if (ep_mode) {
        drawFastHLine_EPD(x, y, w, color);
        return;
    }

    if (framebuffer) {
        Renderer::drawFastHLine(x, y, w, color);
        return;
    }

    // Rudimentary clipping
    if((x >= _width) || (y >= _height)) return;
    if((x + w - 1) >= _width)  w = _width - x;

    if (universal_panel && universal_panel->drawFastHLine(x, y, w, color)) {
        return;
    }

    spiController->beginTransaction();
    spiController->csLow();
    setAddrWindow_int(x, y, w, 1);

    if (col_mode == 18) {
        uint8_t r = (color & 0xF800) >> 11;
        uint8_t g = (color & 0x07E0) >> 5;
        uint8_t b = color & 0x001F;
        r = (r * 255) / 31;
        g = (g * 255) / 63;
        b = (b * 255) / 31;

        while (w--) {
            ulcd_data8(r);
            ulcd_data8(g);
            ulcd_data8(b);
        }
    } else {
        while (w--) {
            WriteColor(color);
        }
    }

    spiController->csHigh();
    spiController->endTransaction();
}

void uDisplay::drawFastVLine(int16_t x, int16_t y, int16_t h, uint16_t color) {
    if (ep_mode) {
        drawFastVLine_EPD(x, y, h, color);
        return;
    }

    if (framebuffer) {
        Renderer::drawFastVLine(x, y, h, color);
        return;
    }

    // Rudimentary clipping
    if ((x >= _width) || (y >= _height)) return;
    if ((y + h - 1) >= _height) h = _height - y;

    if (universal_panel && universal_panel->drawFastVLine(x, y, h, color)) {
        return;
    }

    spiController->beginTransaction();
    spiController->csLow();
    setAddrWindow_int(x, y, 1, h);

    if (col_mode == 18) {
        uint8_t r = (color & 0xF800) >> 11;
        uint8_t g = (color & 0x07E0) >> 5;
        uint8_t b = color & 0x001F;
        r = (r * 255) / 31;
        g = (g * 255) / 63;
        b = (b * 255) / 31;

        while (h--) {
            ulcd_data8(r);
            ulcd_data8(g);
            ulcd_data8(b);
        }
    } else {
        while (h--) {
            WriteColor(color);
        }
    }

    spiController->csHigh();
    spiController->endTransaction();
}

void uDisplay::fillRect(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t color) {
    if (universal_panel && universal_panel->fillRect(x, y, w, h, color)) {
        return;
    }

    if (ep_mode) {
        fillRect_EPD(x, y, w, h, color);
        return;
    }

    if (framebuffer) {
        Renderer::fillRect(x, y, w, h, color);
        return;
    }

    if((x >= _width) || (y >= _height)) return;
    if((x + w - 1) >= _width)  w = _width - x;
    if((y + h - 1) >= _height) h = _height - y;

    spiController->beginTransaction();
    spiController->csLow();
    setAddrWindow_int(x, y, w, h);

    if (col_mode == 18) {
        uint8_t r = (color & 0xF800) >> 11;
        uint8_t g = (color & 0x07E0) >> 5;
        uint8_t b = color & 0x001F;
        r = (r * 255) / 31;
        g = (g * 255) / 63;
        b = (b * 255) / 31;

        for (y = h; y > 0; y--) {
            for (x = w; x > 0; x--) {
                ulcd_data8(r);
                ulcd_data8(g);
                ulcd_data8(b);
            }
        }
    } else {
        for (y = h; y > 0; y--) {
            for (x = w; x > 0; x--) {
                WriteColor(color);
            }
        }
    }
    
    spiController->csHigh();
    spiController->endTransaction();
}

void uDisplay::fillScreen(uint16_t color) {
    fillRect(0, 0, width(), height(), color);
}

static inline void lvgl_color_swap(uint16_t *data, uint16_t len) { for (uint32_t i = 0; i < len; i++) (data[i] = data[i] << 8 | data[i] >> 8); }

void uDisplay::pushColors(uint16_t *data, uint16_t len, boolean not_swapped) {

  if (lvgl_param.swap_color) {
    not_swapped = !not_swapped;
  }
#ifdef USE_UNIVERSAL_PANEL
    if (universal_panel && universal_panel->pushColors(data, len, not_swapped)) {
        return;
    }
#endif

  //Serial.printf("push %x - %d - %d - %d\n", (uint32_t)data, len, not_swapped, lvgl_param.data);

  // Isolating _UDSP_RGB to increase code sharing
  //
  // Use ESP-IDF LCD driver to push colors and rely on the following assumptions:
  // * bytes swapping is already handled in the driver configuration (see uDisplay::Init()),
  // * pushColors() is only called with not_swapped equals true,
  // * cache flushing is done by the LCD driver


  if (not_swapped == false) {
    // called from LVGL bytes are swapped
    if (bpp != 16) {
      // lvgl_color_swap(data, len); -- no need to swap anymore, we have inverted the mask
      pushColorsMono(data, len, true);
      return;
    }

    if ( (col_mode != 18) && (spiController->spi_config.dc >= 0) && (spiController->spi_config.bus_nr <= 2) ) {
      // special version 8 bit spi I or II
#ifdef ESP8266
      lvgl_color_swap(data, len);
      while (len--) {
       spiController->getSPI()->write(*data++);
      }
#else
      if (lvgl_param.use_dma) {
        spiController->pushPixelsDMA(data, len );
      } else {
        spiController->getSPI()->writeBytes((uint8_t*)data, len * 2);
      }
#endif
    } else {

#ifdef ESP32
      if ( (col_mode == 18) && (spiController->spi_config.dc >= 0) && (spiController->spi_config.bus_nr <= 2) ) {
        uint8_t *line = (uint8_t*)malloc(len * 3);
        uint8_t *lp = line;
        if (line) {
          uint16_t color;
          for (uint32_t cnt = 0; cnt < len; cnt++) {
            color = *data++;
            color = (color << 8) | (color >> 8);
            uint8_t r = (color & 0xF800) >> 11;
            uint8_t g = (color & 0x07E0) >> 5;
            uint8_t b = color & 0x001F;
            r = (r * 255) / 31;
            g = (g * 255) / 63;
            b = (b * 255) / 31;
            *lp++ = r;
            *lp++ = g;
            *lp++ = b;
          }

          if (lvgl_param.use_dma) {
            spiController->pushPixels3DMA(line, len );
          } else {
            spiController->getSPI()->writeBytes(line, len * 3);
          }
          free(line);
        }

      } else {
          lvgl_color_swap(data, len);
          while (len--) {
            WriteColor(*data++);
          }
      }
#endif // ESP32

#ifdef ESP8266
      lvgl_color_swap(data, len);
      while (len--) {
        WriteColor(*data++);
      }
#endif
    }
  } else {
    // called from displaytext, no byte swap, currently no dma here

    if (bpp != 16) {
      pushColorsMono(data, len);
      return;
    }
    if ( (col_mode != 18) && (spiController->spi_config.dc >= 0) && (spiController->spi_config.bus_nr <= 2) ) {
      // special version 8 bit spi I or II
  #ifdef ESP8266
      while (len--) {
        //uspi->write(*data++);
        WriteColor(*data++);
      }
  #else
      spiController->getSPI()->writePixels(data, len * 2);
  #endif
    } else {
      // 9 bit and others
        while (len--) {
          WriteColor(*data++);
        }
    }
  }
}

// convert to mono, these are framebuffer based
void uDisplay::pushColorsMono(uint16_t *data, uint16_t len, bool rgb16_swap) {
  // pixel is white if at least one of the 3 components is above 50%
  // this is tested with a simple mask, swapped if needed
  uint16_t rgb16_to_mono_mask = rgb16_swap ? RGB16_SWAP_TO_MONO : RGB16_TO_MONO;

  for (uint32_t y = seta_yp1; y < seta_yp2; y++) {
    seta_yp1++;
    if (lvgl_param.invert_bw) {
      for (uint32_t x = seta_xp1; x < seta_xp2; x++) {
        uint16_t color = *data++;
        if (bpp == 1) color = (color & rgb16_to_mono_mask) ? 0 : 1;
        drawPixel(x, y, color);   // todo - inline the method to save speed
        len--;
        if (!len) return;         // failsafe - exist if len (pixel number) is exhausted
      }
    } else {
      for (uint32_t x = seta_xp1; x < seta_xp2; x++) {
        uint16_t color = *data++;
        if (bpp == 1) color = (color & rgb16_to_mono_mask) ? 1 : 0;
        drawPixel(x, y, color);   // todo - inline the method to save speed
        len--;
        if (!len) return;         // failsafe - exist if len (pixel number) is exhausted
      }
    }
  }
}

void uDisplay::setAddrWindow(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1) {
    if (universal_panel && universal_panel->setAddrWindow(x0, y0, x1, y1)) {
        return;
    }

    if (!x0 && !y0 && !x1 && !y1) {
        spiController->csHigh();
        spiController->endTransaction();
    } else {
        spiController->beginTransaction();
        spiController->csLow();
        setAddrWindow_int(x0, y0, x1 - x0, y1 - y0);
    }
}

void uDisplay::setAddrWindow_int(uint16_t x, uint16_t y, uint16_t w, uint16_t h) {
    if (interface == _UDSP_RGB) {
        return;
    }

    x += x_addr_offs[cur_rot];
    y += y_addr_offs[cur_rot];

    if (sa_mode != 8) {
        uint32_t xa = ((uint32_t)x << 16) | (x + w - 1);
        uint32_t ya = ((uint32_t)y << 16) | (y + h - 1);

        ulcd_command(saw_1);
        ulcd_data32(xa);

        ulcd_command(saw_2);
        ulcd_data32(ya);

        if (saw_3 != 0xff) {
            ulcd_command(saw_3); // write to RAM
        }
    } else {
        uint16_t x2 = x + w - 1,
                 y2 = y + h - 1;

        if (cur_rot & 1) { // Vertical address increment mode
            std::swap(x,y);
            std::swap(x2,y2);
        }
        ulcd_command(saw_1);
        if (allcmd_mode) {
            ulcd_data8(x);
            ulcd_data8(x2);
        } else {
            ulcd_command(x);
            ulcd_command(x2);
        }
        ulcd_command(saw_2);
        if (allcmd_mode) {
            ulcd_data8(y);
            ulcd_data8(y2);
        } else {
            ulcd_command(y);
            ulcd_command(y2);
        }
        if (saw_3 != 0xff) {
            ulcd_command(saw_3); // write to RAM
        }
    }
}

void uDisplay::setRotation(uint8_t rotation) {
    cur_rot = rotation;
    if (universal_panel && universal_panel->setRotation(rotation)) {
        return;
    }

    if (framebuffer) {
        Renderer::setRotation(cur_rot);
        return;
    }

    if (interface == _UDSP_SPI || interface == _UDSP_PAR8 || interface == _UDSP_PAR16) {

        if (ep_mode) {
            Renderer::setRotation(cur_rot);
            return;
        }
        spiController->beginTransaction();
        spiController->csLow();
        ulcd_command(madctrl);

        if (!allcmd_mode) {
            ulcd_data8(rot[cur_rot]);
        } else {
            ulcd_command(rot[cur_rot]);
        }

        if ((sa_mode == 8) && !allcmd_mode) {
            ulcd_command(startline);
            ulcd_data8((cur_rot < 2) ? height() : 0);
        }

        spiController->csHigh();
        spiController->endTransaction();
    }
    
    switch (rotation) {
        case 0:
            _width  = gxs;
            _height = gys;
            break;
        case 1:
            _width  = gys;
            _height = gxs;
            break;
        case 2:
            _width  = gxs;
            _height = gys;
            break;
        case 3:
            _width  = gys;
            _height = gxs;
            break;
    }
}

void uDisplay::Updateframe(void) {

  if (universal_panel && universal_panel->updateFrame()) {
      return;
  }

  if (ep_mode) {
    Updateframe_EPD();
    return;
  }

  if (interface == _UDSP_SPI) {
    if (framebuffer == nullptr) { return; }

    spiController->beginTransaction();
    spiController->csLow();
    // below commands are not needed for SH1107
    // ulcd_command(saw_1 | 0x0);  // set low col = 0, 0x00
    // ulcd_command(i2c_page_start | 0x0);  // set hi col = 0, 0x10
    // ulcd_command(i2c_page_end | 0x0); // set startline line #0, 0x40

	  uint8_t ys = gys >> 3;
	  uint8_t xs = gxs >> 3;
    //uint8_t xs = 132 >> 3;
	  uint8_t m_row = saw_2;
	  uint8_t m_col = i2c_col_start; // reuse global var i2c_col_start for spi
    // AddLog(LOG_LEVEL_DEBUG, "m_row=%d m_col=%d xs=%d ys=%d\n", m_row, m_col, xs, ys);

	  uint16_t p = 0;

	  uint8_t i, j, k = 0;
	  for ( i = 0; i < ys; i++) {   // i = line from 0 to ys
		    // send a bunch of data in one xmission
        ulcd_command(0xB0 + i + m_row); //set page address
        ulcd_command(m_col & 0xf); //set lower column address
        ulcd_command(0x10 | (m_col >> 4)); //set higher column address

        for ( j = 0; j < 8; j++) {
            for ( k = 0; k < xs; k++, p++) {
		            ulcd_data8(framebuffer[p]);
            }
	      }
    }
    spiController->csLow();
    spiController->beginTransaction();
  }
}
