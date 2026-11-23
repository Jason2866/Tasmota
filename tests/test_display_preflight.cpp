#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>

#define USE_GRAPH
#define USE_DT_VARS
#define USE_TOUCH_BUTTONS
#define USE_RAMFONT
#define USE_AWATCH
#define MAX_MULTI_DISPLAYS 3
#define RENDERER_UPDATE_RUNNING 1
#define COLOR_COLOR 1

struct Renderer {
  bool running = false;
  int GetUpdateFrameAsyncStatus() { return running ? RENDERER_UPDATE_RUNNING : 0; }
};

struct DisplaySlot { Renderer *display = nullptr; bool used = false; uint8_t color_type = 0; };
DisplaySlot displays[MAX_MULTI_DISPLAYS];
Renderer *renderer = nullptr;
uint8_t color_type = 0;

#include "display_preflight_under_test.inc"

int main() {
  Renderer first, second;
  renderer = &first;
  displays[0] = {&first, true, 0};
  displays[1] = {&second, true, 0};
  second.running = true;

  assert(DisplayTextPreflight("[P/images/S2.png:][h2]", false));
  assert(DisplayTextPreflight("[F/fonts/S2.fnt:][h2]", false));
  assert(DisplayTextPreflight("[Gs1:/path/S2:][h2]", false));
  assert(DisplayTextPreflight("[dv1,2,3,4,5,6,7,8,9,10:labelS2:unit:][h2]", false));
  assert(DisplayTextPreflight("[b1,1,2,3,4,5,6,7,8:labelS2:][h2]", false));
  assert(!DisplayTextPreflight("[Gs1:/path/S2:S2:]", false));
  assert(!DisplayTextPreflight("[dv1,2,3,4,5,6,7,8,9,10:labelS2:unit:S2:]", false));
  assert(!DisplayTextPreflight("[b1,1,2,3,4,5,6,7,8:labelS2:S2:]", false));
  color_type = COLOR_COLOR;
  assert(!DisplayTextPreflight("[G1,2,3,4,5,6,7,8,9S2:]", false));
}
