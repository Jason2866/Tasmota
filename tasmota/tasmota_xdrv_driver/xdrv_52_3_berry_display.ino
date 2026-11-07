/*
  xdrv_52_3_berry_display.ino - Berry scripting language, native fucnctions

  Copyright (C) 2021 Stephan Hadinger, Berry language by Guan Wenliang https://github.com/Skiars/berry

  This program is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.

  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.

  You should have received a copy of the GNU General Public License
  along with this program.  If not, see <http://www.gnu.org/licenses/>.
*/


#ifdef USE_BERRY
#ifdef USE_DISPLAY

#include <berry.h>

#ifdef USE_UNIVERSAL_DISPLAY
Renderer *Init_uDisplay(const char *desc);
extern Renderer *renderer;
#endif //  USE_UNIVERSAL_DISPLAY

#if defined(USE_UNIVERSAL_DISPLAY) && defined(USE_UFILESYS) && defined(JPEG_PICTS)
extern bool Draw_RGB_Bitmap(char *file, uint16_t xp, uint16_t yp, uint8_t scale, bool inverted, uint16_t xs, uint16_t ys, bool allow_url);
#endif
#if defined(USE_UNIVERSAL_DISPLAY)
extern void BrTimeoutReset(void);
extern void BrTimeoutStart(void);
#endif

extern "C" {
  /*********************************************************************************************\
   * Native functions mapped to Berry functions
   *
   * import display
   * display.start(string) -> comptr or nil if failed
   *
  \*********************************************************************************************/
  int be_ntv_display_start(struct bvm *vm) {
  #ifdef USE_UNIVERSAL_DISPLAY
    int32_t argc = be_top(vm); // Get the number of arguments
    if (argc >= 1 && be_isstring(vm, 1)) {
      const char * desc = be_tostring(vm, 1);
      // remove all objects on stack to avoid warnings in subsequent calls to Berry
      be_pop(vm, argc);
      Renderer * renderer = Init_uDisplay(desc);
      if (renderer) {
        be_pushcomptr(vm, renderer);
      } else {
        be_pushnil(vm);
      }
      be_return(vm);
    }
    be_raise(vm, kTypeError, nullptr);
  #else // USE_UNIVERSAL_DISPLAY
    be_raise(vm, "internal_error", "universal display driver not present");
  #endif // USE_UNIVERSAL_DISPLAY
  }

  int32_t be_ntv_display_width(void) {
  #ifdef USE_UNIVERSAL_DISPLAY
    if (renderer) {
      return renderer->width();
    }
  #endif
    return 0;
  }

  int32_t be_ntv_display_height(void) {
  #ifdef USE_UNIVERSAL_DISPLAY
    if (renderer) {
      return renderer->height();
    }
  #endif
    return 0;
  }

  // `display.draw_jpg(path:string) -> bool` draws a filesystem JPEG at (0, 0)
  // and refreshes the active universal display.
  int be_ntv_display_draw_jpg(struct bvm *vm) {
#if defined(USE_UNIVERSAL_DISPLAY) && defined(USE_UFILESYS) && defined(JPEG_PICTS)
    int32_t argc = be_top(vm);
    if (argc != 1 || !be_isstring(vm, 1)) {
      be_raise(vm, kTypeError, nullptr);
    }
    if (!renderer) {
      be_raise(vm, "display_error", "universal display is not initialized");
    }

    char *file = const_cast<char *>(be_tostring(vm, 1));
    // Inky refresh can take about 32 seconds, longer than Berry's execution
    // timeout. This native call services the display synchronously.
    BrTimeoutReset();
    if (!Draw_RGB_Bitmap(file, 0, 0, 0, false, 0, 0, false)) {
      BrTimeoutStart();
      be_raise(vm, "display_error", "could not decode the dithered JPEG");
    }
    if (!renderer->UpdateframeChecked()) {
      BrTimeoutStart();
      be_raise(vm, "display_error", "display refresh failed");
    }
    be_pop(vm, argc);
    BrTimeoutStart();
    be_pushbool(vm, true);
    be_return(vm);
#else
    be_raise(vm, "feature_error", "JPEG display requires universal display, filesystem, JPEG_PICTS support");
#endif
  }

#if defined(USE_UNIVERSAL_DISPLAY)
  static void be_ntv_display_validate_rgb888(struct bvm *vm, int32_t argc,
                                              const uint8_t **pixels, int32_t *width, int32_t *height) {
    if (argc != 3 || !be_isbytes(vm, 1) || !be_isint(vm, 2) || !be_isint(vm, 3)) {
      be_raise(vm, kTypeError, nullptr);
    }
    if (!renderer) {
      be_raise(vm, "display_error", "universal display is not initialized");
    }

    *width = be_toint(vm, 2);
    *height = be_toint(vm, 3);
    if (*width <= 0 || *height <= 0 || *width > UINT16_MAX || *height > UINT16_MAX ||
        *width != renderer->width() || *height != renderer->height() ||
        (size_t)*width > SIZE_MAX / 3 / (size_t)*height) {
      be_raise(vm, "value_error", "RGB888 dimensions must match the display");
    }
    size_t pixel_size = 0;
    *pixels = (const uint8_t *)be_tobytes(vm, 1, &pixel_size);
    const size_t expected_size = (size_t)*width * (size_t)*height * 3;
    if (!*pixels || pixel_size != expected_size) {
      be_raise(vm, "value_error", "RGB888 buffer size does not match its dimensions");
    }
  }

  static void be_ntv_display_push_rgb888(struct bvm *vm, const uint8_t *pixels, int32_t width, int32_t height) {
    uint16_t *row = (uint16_t *)special_malloc((uint32_t)width * sizeof(uint16_t));
    if (!row) {
      be_raise(vm, "memory_error", "could not allocate RGB565 display row");
    }

    BrTimeoutReset();
    for (int32_t y = 0; y < height; y++) {
      const uint8_t *source = pixels + (size_t)y * width * 3;
      for (int32_t x = 0; x < width; x++) {
        const uint8_t red = source[x * 3];
        const uint8_t green = source[x * 3 + 1];
        const uint8_t blue = source[x * 3 + 2];
        row[x] = ((uint16_t)(red & 0xF8) << 8) |
                 ((uint16_t)(green & 0xFC) << 3) | (blue >> 3);
      }
      renderer->setAddrWindow(0, y, width, y + 1);
      renderer->pushColors(row, width, true);
      OsWatchLoop();
    }
    renderer->setAddrWindow(0, 0, 0, 0);
    free(row);
  }
#endif

  // `display.draw_rgb888(pixels:bytes, width:int, height:int) -> bool`
  // draws a full logical RGB888 frame and refreshes the active display.
  int be_ntv_display_draw_rgb888(struct bvm *vm) {
#if defined(USE_UNIVERSAL_DISPLAY)
    int32_t argc = be_top(vm);
    const uint8_t *pixels;
    int32_t width, height;
    be_ntv_display_validate_rgb888(vm, argc, &pixels, &width, &height);

    be_ntv_display_push_rgb888(vm, pixels, width, height);
    const bool refreshed = renderer->UpdateframeChecked();
    BrTimeoutStart();
    if (!refreshed) {
      be_raise(vm, "display_error", "display refresh failed");
    }

    be_pop(vm, argc);
    be_pushbool(vm, true);
    be_return(vm);
#else
    be_raise(vm, "feature_error", "RGB888 display requires universal display support");
#endif
  }

  // `display.draw_rgb888_async(pixels:bytes, width:int, height:int) -> bool`
  // draws a full logical RGB888 frame and starts a cooperative display refresh.
  int be_ntv_display_draw_rgb888_async(struct bvm *vm) {
#if defined(USE_UNIVERSAL_DISPLAY)
    int32_t argc = be_top(vm);
    const uint8_t *pixels;
    int32_t width, height;
    be_ntv_display_validate_rgb888(vm, argc, &pixels, &width, &height);
    if (!renderer->CanStartUpdateFrameAsync()) {
      be_pop(vm, argc);
      be_pushbool(vm, false);
      be_return(vm);
    }

    be_ntv_display_push_rgb888(vm, pixels, width, height);
    BrTimeoutStart();
    const bool started = renderer->StartUpdateFrameAsync();
    if (!started) {
      be_pop(vm, argc);
      be_pushbool(vm, false);
      be_return(vm);
    }

    be_pop(vm, argc);
    be_pushbool(vm, true);
    be_return(vm);
#else
    be_raise(vm, "feature_error", "asynchronous RGB888 display requires universal display support");
#endif
  }

  // `display.refresh_status() -> string` reports the asynchronous refresh state.
  int be_ntv_display_refresh_status(struct bvm *vm) {
#if defined(USE_UNIVERSAL_DISPLAY)
    if (be_top(vm) != 0) {
      be_raise(vm, kTypeError, nullptr);
    }
    if (!renderer) {
      be_raise(vm, "display_error", "universal display is not initialized");
    }
    const char *status = "unsupported";
    switch (renderer->GetUpdateFrameAsyncStatus()) {
      case RENDERER_UPDATE_IDLE: status = "idle"; break;
      case RENDERER_UPDATE_RUNNING: status = "running"; break;
      case RENDERER_UPDATE_COMPLETE: status = "complete"; break;
      case RENDERER_UPDATE_FAILED: status = "failed"; break;
    }
    be_pushstring(vm, status);
    be_return(vm);
#else
    be_raise(vm, "feature_error", "asynchronous display status requires universal display");
#endif
  }

  // `display.dimmer([dim:int]) -> int` sets the dimmer of display, value 0..100. If `0` then turn off display. If no arg, read the current value.
  int be_ntv_display_dimmer(struct bvm *vm) {
    int32_t argc = be_top(vm); // Get the number of arguments
    int32_t dimmer;
    bool no_settings = false;   // by default change settings
    if (argc >= 1) {
      if (!be_isint(vm, 1)) { be_raise(vm, "type_error", "arg must be int"); }
      dimmer = be_toint(vm, 1);
      if (argc >= 2) {
        if (!be_isbool(vm, 2)) { be_raise(vm, "type_error", "arg2 must be bool"); }
        no_settings = be_tobool(vm, 2);
      }
      if ((dimmer < 0) || (dimmer > 100)) { be_raise(vm, "value_error", "value must be in range 0..100"); }
      be_pop(vm, argc);   // clear stack to avoid ripple errors in code called later
      if (!no_settings) {  // change settings
        SetDisplayDimmer(dimmer);
      }
      ApplyDisplayDimmer(dimmer);
    }
    be_pushint(vm, GetDisplayDimmer());
    be_return(vm);
  }

  void be_ntv_display_touch_update(int32_t touches, int32_t raw_x, int32_t raw_y, int32_t gesture) {
  #if defined(USE_UNIVERSAL_TOUCH) || defined(USE_FT5206) || defined(USE_XPT2046) || defined(USE_GT911) || defined(USE_LILYGO47) || defined(USE_TOUCH_BUTTONS)
    Touch_SetStatus(touches, raw_x, raw_y, gesture,true /*don't convert*/);
  #endif
  }

  const char* be_ntv_display_driver_name(void) {
  #ifdef USE_UNIVERSAL_DISPLAY
    if (renderer) {
      char* devname = renderer->devname();
      if (devname) {
        return devname;
      }
    }
  #endif
    return "";
  }

  bbool be_ntv_display_started(void) {
  #ifdef USE_UNIVERSAL_DISPLAY
    if (renderer) {
      return true;
    }
  #endif
    return false;
  }
}

#endif // USE_DISPLAY
#endif  // USE_BERRY
