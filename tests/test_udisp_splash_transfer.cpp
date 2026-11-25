#include <cassert>
#include <cstdint>

using boolean = bool;
constexpr int DISPLAY_INIT_MODE = 0;
constexpr int DISPLAY_INIT_PARTIAL = 1;
constexpr int DISPLAY_INIT_FULL = 2;
constexpr int LOG_LEVEL_DEBUG = 0;
#define PSTR(value) value

void AddLog(int, const char *, ...) {}

struct Panel {
  bool handled = false;
  bool swapped = false;
  bool pushColors(uint16_t *, uint32_t, bool order) { swapped = order; return handled; }
};

struct EPDPanel : Panel {
  struct {
    int lutpsize = 0, lutfsize = 0, lut_partial_data = 0, lut_full_data = 0;
    int lut_partial_time = 0, lut_full_time = 0;
  } cfg;
  void setUpdateMode(int) {}
  void setLut(int, int) {}
  void updateFrame() {}
  void delay_sync(int) {}
  void clearFrame_42() {}
  void displayFrame_42() {}
};

struct uDisplay {
  int ep_mode = 0, splash_font = 1, splash_size = 1, splash_xp = 0, splash_yp = 0;
  int fg_col = 0, bg_col = 0, bpp = 1, updates = 0, mono = 0, draws = 0;
  char *dname = nullptr;
  uint8_t *frame_buffer = nullptr;
  Panel *universal_panel = nullptr;
  struct { bool swap_color = false; } lvgl_param;
  struct { struct { int update_time = 0; } epd; } config;
  decltype(config) *panel_config = &config;
  void DisplayInit(int8_t, int8_t, int8_t, int8_t);
  void Splash();
  void pushColors(uint16_t *, uint32_t, boolean);
  bool pushColorsChecked(uint16_t *, uint32_t, boolean);
  void Updateframe() { updates++; }
  void setRotation(int) {}
  void invertDisplay(bool) {}
  void setTextWrap(bool) {}
  void cp437(bool) {}
  void setTextFont(int) {}
  void setTextSize(int) {}
  void setTextColor(int, int) {}
  void setCursor(int, int) {}
  void fillScreen(int) {}
  void DrawStringAt(int, int, char *, int, int) { draws++; }
  void pushColorsMono(uint16_t *, uint32_t, bool) { mono++; }
};

#include "udisp_under_test.inc"

int main() {
  EPDPanel panel;
  uDisplay display;
  display.universal_panel = &panel;
  display.ep_mode = 4;
  display.DisplayInit(DISPLAY_INIT_MODE, 1, 0, 1);
  assert(display.updates == 0);
  display.Splash();
  assert(display.draws == 1 && display.updates == 1);

  display.ep_mode = 1;
  display.updates = 0;
  display.DisplayInit(DISPLAY_INIT_MODE, 1, 0, 1);
  display.Splash();
  assert(display.updates == 3);

  uint8_t framebuffer = 0;
  uint16_t pixel = 0;
  display.frame_buffer = &framebuffer;
  display.ep_mode = 4;
  display.pushColors(&pixel, 1, true);
  assert(display.mono == 0);
  display.ep_mode = 0;
  display.bpp = 16;
  display.pushColors(&pixel, 1, true);
  assert(display.mono == 0);
  display.bpp = 1;
  display.frame_buffer = nullptr;
  display.pushColors(&pixel, 1, true);
  assert(display.mono == 0);
  display.frame_buffer = &framebuffer;
  display.lvgl_param.swap_color = true;
  display.pushColors(&pixel, 1, true);
  assert(display.mono == 1 && !panel.swapped);
  assert(display.pushColorsChecked(&pixel, 1, true) && display.mono == 2);
  panel.handled = true;
  display.pushColors(&pixel, 1, true);
  assert(display.mono == 2);
}
