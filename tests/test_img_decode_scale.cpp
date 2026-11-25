#include <cassert>

#include "../lib/libesp32/berry_tasmota/src/be_img_resize.h"

int main() {
  assert(be_img_decode_scale(1600, 1000, 3, 3300000, 2000000, 1000, 600) == 2);
  assert(be_img_decode_scale(1600, 1000, 3, 3200000, 2000000, 1000, 600) == 4);
  assert(be_img_decode_scale(800, 800, 3, 500000, 250000, 800, 800) == -1);
  assert(be_img_decode_scale(800, 800, 3, 500000, 250000, 800, 800, 0, true, false) == 4);
  assert(be_img_decode_scale(800, 800, 3, 500000, 250000, 800, 800, 0, false, false) == 8);
  assert(be_img_decode_scale(800, 800, 3, 1000000, 1000000, 0, 0) == 2);
  assert(be_img_decode_scale(800, 800, 3, 0, 0, 800, 800, 1920000) == 0);
}
