#!/usr/bin/env python3
"""Exercise the checked universal-panel refresh with native panel stubs."""

from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "lib/lib_display/UDisplay/src/uDisplay_graphics.cpp"
HEADER = r"""
#include <cassert>
#include <cstdint>
#define _UDSP_I2C 1
#define _UDSP_SPI 2
#define _UDSP_RGB 5
#define _UDSP_DSI 6
#define _UDSP_QSPI 7
struct UniversalPanel {
    bool result = false;
    int calls = 0;
    bool updateFrame() { ++calls; return result; }
};
struct uDisplay {
    UniversalPanel* universal_panel = nullptr;
    uint8_t interface = 0;
    uint8_t ep_mode = 0;
    uint8_t bpp = 0;
    uint8_t* frame_buffer = nullptr;
    bool UpdateframeChecked();
};
"""
TEST = r"""
int main() {
    uDisplay display;
    UniversalPanel panel;
    uint8_t framebuffer = 0;

    display.interface = _UDSP_QSPI;
    assert(!display.UpdateframeChecked());
    display.universal_panel = &panel;
    assert(display.UpdateframeChecked());
    assert(panel.calls == 0);

    display.interface = _UDSP_SPI;
    display.bpp = 16;
    assert(display.UpdateframeChecked());
    assert(panel.calls == 0);
    display.bpp = 18;
    assert(display.UpdateframeChecked());

    display.frame_buffer = &framebuffer;
    assert(!display.UpdateframeChecked());
    panel.result = true;
    assert(display.UpdateframeChecked());
    panel.result = false;
    display.frame_buffer = nullptr;
    display.bpp = 1;
    assert(!display.UpdateframeChecked());
    display.frame_buffer = &framebuffer;
    assert(!display.UpdateframeChecked());
    display.bpp = 8;
    assert(!display.UpdateframeChecked());
    display.ep_mode = 4;
    display.bpp = 16;
    display.frame_buffer = nullptr;
    assert(!display.UpdateframeChecked());

    display.ep_mode = 0;
    for (uint8_t interface : {_UDSP_I2C, _UDSP_RGB, _UDSP_DSI}) {
        display.interface = interface;
        assert(!display.UpdateframeChecked());
        panel.result = true;
        assert(display.UpdateframeChecked());
        panel.result = false;
    }
    assert(panel.calls == 12);
}
"""


class UniversalPanelRefreshTest(unittest.TestCase):
    def test_checked_refresh(self):
        source = SOURCE.read_text()
        start = source.index("bool uDisplay::UpdateframeChecked(void) {")
        end = source.index("\n}\n", start) + len("\n}\n")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            harness = path / "refresh.cpp"
            harness.write_text("#include <initializer_list>\n" + HEADER + source[start:end] + TEST)
            subprocess.run(["c++", "-std=c++11", "-Wall", "-Wextra", "-Werror",
                            str(harness), "-o", str(path / "refresh")], check=True)
            subprocess.run([str(path / "refresh")], check=True)


if __name__ == "__main__":
    unittest.main()
