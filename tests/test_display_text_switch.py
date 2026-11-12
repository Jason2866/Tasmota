#!/usr/bin/env python3
"""Exercise DisplayText's display switch using its native parsing code."""

from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tasmota/tasmota_xdrv_driver/xdrv_13_display.ino"
HARNESS = r"""
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <string>
#define MAX_MULTI_DISPLAYS 3
#define RENDERER_UPDATE_RUNNING 2
#define LOG_LEVEL_INFO 1
#define PSTR(value) value

struct Renderer {
    bool running = false;
    int GetUpdateFrameAsyncStatus() { return running ? RENDERER_UPDATE_RUNNING : 0; }
};
Renderer active_renderer;
Renderer* renderer = &active_renderer;
struct { bool used = true; } displays[MAX_MULTI_DISPLAYS];
uint8_t cur_display = 0;
int set_calls = 0, get_calls = 0, open_calls = 0, log_calls = 0;
std::string opened_path;
void Set_display(uint8_t) { ++set_calls; }
void Get_display(uint8_t) { ++get_calls; }
void AddLog(int, const char*, ...) { ++log_calls; }
struct File {
    bool operator>(int) const { return false; }
    uint32_t size() { return 0; }
    void read(uint8_t*, uint32_t) {}
    void close() {}
};
struct Filesystem {
    File open(const char* path, const char*) {
        ++open_calls;
        opened_path = path;
        return File();
    }
} filesystem;
Filesystem* ffsp = &filesystem;
struct { int display_model = 0, display_rotate = 0; } settings;
auto* Settings = &settings;
Renderer* Init_uDisplay(char*) { return &active_renderer; }
"""
TEST = r"""
bool parse(char* cp, int16_t& xpos, std::string& text) {
    uint8_t var;
    int16_t temp;
    bool escape = false;
    while (*cp) {
        if (!escape) {
            if (*cp == '[') { escape = true; ++cp; }
            else { text += *cp++; }
        } else if (*cp == ']') {
            escape = false;
            ++cp;
        } else {
            switch (*cp++) {
SWITCH_CASE
            case 'x':
                var = atoiv(cp, &xpos);
                cp += var;
                break;
            default:
                return false;
            }
        }
    }
    return true;
}

void check(const char* input, bool running, int expected_x, const char* expected_text,
           int expected_switches, int expected_opens) {
    char buffer[256];
    assert(strlen(input) < sizeof(buffer));
    strcpy(buffer, input);
    active_renderer.running = running;
    renderer = &active_renderer;
    set_calls = get_calls = open_calls = log_calls = 0;
    opened_path.clear();
    int16_t xpos = 0;
    std::string text;
    assert(parse(buffer, xpos, text));
    assert(xpos == expected_x && text == expected_text);
    assert(set_calls == expected_switches && get_calls == expected_switches);
    assert(open_calls == expected_opens);
    assert(log_calls == (running ? 1 : expected_opens));
}

int main() {
    check("[S2:x23]hello", true, 23, "hello", 0, 0);
    check("[S2r-1:x24]hello[x25]world", true, 25, "helloworld", 0, 0);
    check("[S2r3/path/x98rz.ini:x26]hello", true, 26, "hello", 0, 0);
    check("[S2r3/path/x98rz.ini", true, 0, "", 0, 0);
    check("[S2:x27]hello", false, 27, "hello", 1, 0);
    check("[S2r3/path/x98rz.ini:x28]hello", false, 28, "hello", 0, 1);
    assert(opened_path == "/path/x98rz.ini");
}
"""


class DisplayTextSwitchTest(unittest.TestCase):
    def test_switch_during_refresh(self):
        source = SOURCE.read_text()
        start = source.index("uint8_t atoiv(char *cp, int16_t *res)")
        end = source.index("\n}\n", start) + len("\n}\n")
        atoiv = source[start:end]
        start = source.index("          case 'S':")
        end = source.index("#endif // USE_MULTI_DISPLAY", start)
        switch_case = source[start:end]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            harness = path / "display_text.cpp"
            harness.write_text(HARNESS + atoiv + TEST.replace("SWITCH_CASE", switch_case))
            subprocess.run(["c++", "-std=c++11", "-Wall", "-Wextra", "-Werror",
                            str(harness), "-o", str(path / "display_text")], check=True)
            subprocess.run([str(path / "display_text")], check=True)


if __name__ == "__main__":
    unittest.main()
