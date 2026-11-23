#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <cstdio>
#include <map>
#include <string>
#include <algorithm>

#define USE_MULTI_DISPLAY
#define USE_UFILESYS
#define USE_UNIVERSAL_DISPLAY
#define MAX_MULTI_DISPLAYS 3
#define MAX_INDEXCOLORS 32
#define PREDEF_INDEXCOLORS 16
#define RENDERER_UPDATE_RUNNING 1
#define DISPLAY_BUFFER_COLS 128
#define DISPLAY_INIT_PARTIAL 1
#define DISPLAY_INIT_FULL 2
#define TXT_MAX_SFAC 7
#define COLOR_BW 0
#define COLOR_COLOR 1
#define LOG_LEVEL_INFO 1
#define FS_FILE_READ "r"
#define PSTR(value) value
#define snprintf_P snprintf
#define D_HOUR_MINUTE_SEPARATOR ":"
#define D_MINUTE_SECOND_SEPARATOR ":"
#define D_MONTH_DAY_SEPARATOR "/"
#define D_YEAR_MONTH_SEPARATOR "/"
#define FUNC_DISPLAY_SEVENSEG_TEXT 1

struct Renderer {
  bool running = false;
  bool async_refresh = false;
  int lines = 0;
  int refreshes = 0;
  int GetUpdateFrameAsyncStatus() { return running ? RENDERER_UPDATE_RUNNING : 0; }
  void Updateframe() { refreshes++; if (async_refresh) running = true; }
  void setDrawMode(int) {}
  void DisplayInit(int, int, int, int) {}
  void setTextColor(int, int) {}
  void writeFastHLine(int, int, int, int) { lines++; }
  void writeFastVLine(int, int, int, int) { lines++; }
  void writeLine(int, int, int, int, int) { lines++; }
  void drawCircle(int, int, int, int) {}
  void fillCircle(int, int, int, int) {}
  void ep_update_mode(int) {}
  void ep_update_area(int, int, int, int, int) {}
  void drawRect(int, int, int, int, int) {}
  void fillRect(int, int, int, int, int) {}
  void drawRoundRect(int, int, int, int, int, int) {}
  void fillRoundRect(int, int, int, int, int, int) {}
  void setTextSize(int) {}
  void setTextFont(int) {}
  void setRotation(int) {}
};

struct String : std::string {
  using std::string::operator=;
};

struct File {
  const std::string *data = nullptr;
  size_t offset = 0;
  bool operator>(int) const { return data != nullptr; }
  size_t size() const { return data->size(); }
  size_t position() const { return offset; }
  bool seek(size_t target) { if (target > size()) return false; offset = target; return true; }
  bool available() const { return data && offset < size(); }
  size_t read(uint8_t *buffer, size_t count) {
    count = std::min(count, size() - offset);
    memcpy(buffer, data->data() + offset, count);
    offset += count;
    return count;
  }
  void close() {}
};

struct FS {
  std::map<std::string, std::string> files;
  File open(const char *path, const char *) {
    auto entry = files.find(path);
    return entry == files.end() ? File{} : File{&entry->second, 0};
  }
};

struct SettingsData { int display_model = 17; int display_rotate = 0; int display_size = 1; int display_font = 1; int display_mode = 0; } settings;
SettingsData *Settings = &settings;
struct Mailbox { char *data = nullptr; uint32_t data_len = 0; } XdrvMailbox;
struct Clock { int hour = 0; int minute = 0; int second = 0; int day_of_month = 1; int month = 1; int year = 2026; } RtcTime;
Renderer *renderer = nullptr;
uint16_t fg_color = 1, bg_color = 0;
uint8_t color_type = COLOR_BW, auto_draw = 1, display_batch_depth = 0;
uint32_t display_batch_refresh_pending = 0;
int16_t disp_xpos = 0, disp_ypos = 0;
bool udisp_init_busy = false;
bool force_init_busy = false;
FS filesystem;
FS *ufsp = &filesystem;
FS *ffsp = &filesystem;
int bitmap_calls = 0;
uint16_t index_colors[MAX_INDEXCOLORS - PREDEF_INDEXCOLORS];
int disp_device = 1;
std::string response;
std::string drawn_text;
Renderer *text_renderer = nullptr;

void AddLog(int, const char *, ...) {}
void Response_P(const char *) {}
void ResponseCmndChar(const char *text) { response = text; }
void ResponseCmndChar_P(const char *text) { response = text; }
void ResponseCmndDone() { response = "Done"; }
void XdspCall(int) {}
void DisplayClear() {}
void DisplayOnOff(int) {}
void DisplayDrawStringAt(int, int, char *text, int, int) { drawn_text = text; text_renderer = renderer; }
void Draw_RGB_Bitmap(const char *, int, int, int, bool, int, int, bool, bool) { bitmap_calls++; }
uint16_t GetColorFromIndex(uint32_t value) { return value; }
uint32_t decode_te(char *) { return 0; }
void alignright(char *) {}
uint8_t atoiv(char *text, int16_t *value) {
  *value = atoi(text);
  uint8_t count = 0;
  while ((text[count] >= '0' && text[count] <= '9') || text[count] == '-') count++;
  return count;
}
uint8_t fatoiv(char *text, float *value) {
  *value = atof(text);
  uint8_t count = 0;
  while ((text[count] >= '0' && text[count] <= '9') || text[count] == '-' || text[count] == '.') count++;
  return count;
}

#include "display_batch_under_test.inc"

Renderer replacement;
Renderer *Init_uDisplay(const char *) {
  if (force_init_busy) {
    udisp_init_busy = true;
    return nullptr;
  }
  udisp_init_busy = false;
  displays[cur_display].display = &replacement;
  displays[cur_display].used = 1;
  return &replacement;
}

void reset(Renderer &first, Renderer &second) {
  first = Renderer{};
  second = Renderer{};
  replacement = Renderer{};
  for (auto &display : displays) display = MULTI_DISP{};
  displays[0].display = &first;
  displays[0].used = 1;
  displays[0].auto_draw = 1;
  displays[1].display = &second;
  displays[1].used = 1;
  displays[1].auto_draw = 1;
  renderer = &first;
  cur_display = 0;
  disp_xpos = disp_ypos = 0;
  auto_draw = 1;
  display_batch_depth = 0;
  display_batch_refresh_pending = 0;
  display_batch_continuation = DisplayBatchContinuation{};
  free(display_text_continuation.request);
  free(display_text_continuation.text);
  display_text_continuation = DisplayTextContinuation{};
  filesystem.files.clear();
  bitmap_calls = 0;
  force_init_busy = false;
  udisp_init_busy = false;
  response.clear();
  drawn_text.clear();
  text_renderer = nullptr;
}

int main() {
  Renderer first, second;
  reset(first, second);
  second.running = true;
  char busy[] = "[h10S2:]";
  XdrvMailbox.data = busy;
  DisplayTextState busy_state;
  assert(!DisplayText_Run(&busy_state));
  assert(first.lines == 0 && disp_xpos == 0 && !busy_state.changed);
  char wrapped_index[] = "[h10S65538:]";
  XdrvMailbox.data = wrapped_index;
  DisplayTextState wrapped_state;
  assert(!DisplayText_Run(&wrapped_state));
  assert(first.lines == 0 && disp_xpos == 0);
  char prefixed[] = "hello[h10S2:]";
  XdrvMailbox.data = prefixed;
  DisplayTextState prefixed_state;
  assert(!DisplayText_Run(&prefixed_state));
  assert(first.lines == 0 && drawn_text.empty() && disp_xpos == 0);

  char path[] = "[P/pathS2file:][h3]";
  XdrvMailbox.data = path;
  DisplayTextState path_state;
  assert(DisplayText_Run(&path_state));
  assert(bitmap_calls == 1 && first.lines == 1 && disp_xpos == 3);

  char clock[] = "[tSh2]";
  XdrvMailbox.data = clock;
  DisplayTextState clock_state;
  assert(DisplayText_Run(&clock_state));
  assert(first.lines == 2 && disp_xpos == 5);

  reset(first, second);
  first.async_refresh = true;
  char partial[] = "[h10dS2:h5]";
  XdrvMailbox.data = partial;
  DisplayTextState partial_state;
  assert(!DisplayText_Run(&partial_state));
  assert(partial_state.active && partial_state.changed && first.lines == 1 && disp_xpos == 10);
  first.running = false;
  first.async_refresh = false;
  assert(DisplayText_Run(&partial_state));
  assert(first.lines == 1 && second.lines == 1 && disp_xpos == 5);

  reset(first, second);
  first.async_refresh = true;
  char buffered[] = "[tdS2:]";
  XdrvMailbox.data = buffered;
  DisplayTextState buffered_state;
  assert(!DisplayText_Run(&buffered_state));
  assert(drawn_text.empty() && buffered_state.changed);
  first.running = false;
  first.async_refresh = false;
  assert(DisplayText_Run(&buffered_state));
  assert(drawn_text == "00:00" && text_renderer == &second);

  reset(first, second);
  first.async_refresh = true;
  char direct[] = "[h10dS2:h5]";
  XdrvMailbox.data = direct;
  XdrvMailbox.data_len = strlen(direct);
  CmndDisplayText();
  assert(response == "Partial" && first.lines == 1);
  first.running = false;
  first.async_refresh = false;
  CmndDisplayText();
  assert(response == direct && first.lines == 1 && second.lines == 1);

  reset(first, second);
  first.async_refresh = true;
  XdrvMailbox.data = direct;
  XdrvMailbox.data_len = strlen(direct);
  CmndDisplayText();
  assert(response == "Partial" && first.lines == 1);
  first.running = false;
  first.async_refresh = false;
  char replacement_text[] = "[h3]";
  XdrvMailbox.data = replacement_text;
  XdrvMailbox.data_len = strlen(replacement_text);
  CmndDisplayText();
  assert(response == replacement_text && first.lines == 2 && second.lines == 0);
  assert(!display_text_continuation.request && !display_text_continuation.text);

  reset(first, second);
  first.async_refresh = true;
  XdrvMailbox.data = direct;
  XdrvMailbox.data_len = strlen(direct);
  CmndDisplayText();
  assert(response == "Partial");
  char busy_replacement[] = "[h3S2:]";
  XdrvMailbox.data = busy_replacement;
  XdrvMailbox.data_len = strlen(busy_replacement);
  CmndDisplayText();
  assert(response == "Busy" && first.lines == 1 && second.lines == 0);
  assert(!display_text_continuation.request && !display_text_continuation.text);
  first.running = false;
  first.async_refresh = false;
  CmndDisplayText();
  assert(response == busy_replacement && first.lines == 2 && second.lines == 0);

  reset(first, second);
  first.async_refresh = true;
  XdrvMailbox.data = direct;
  XdrvMailbox.data_len = strlen(direct);
  CmndDisplayText();
  assert(response == "Partial");
  Settings->display_model = 15;
  XdrvMailbox.data = replacement_text;
  XdrvMailbox.data_len = strlen(replacement_text);
  CmndDisplayText();
  assert(response == replacement_text && !display_text_continuation.request && !display_text_continuation.text);
  Settings->display_model = 17;

  reset(first, second);
  first.async_refresh = true;
  XdrvMailbox.data = direct;
  XdrvMailbox.data_len = strlen(direct);
  CmndDisplayText();
  assert(response == "Partial");
  XdrvMailbox.data_len = 0;
  CmndDisplayText();
  assert(response == "Done" && !display_text_continuation.request);

  reset(first, second);
  first.async_refresh = true;
  filesystem.files["/batch"] = "[h5]\n[h10dS2:h3]\n[h4]\n";
  char filename[] = "/batch";
  XdrvMailbox.data = filename;
  XdrvMailbox.data_len = strlen(filename);
  assert(Display_Text_From_File(filename) == DISPLAY_BATCH_PARTIAL);
  assert(first.lines == 2 && second.lines == 0);
  assert(Display_Text_From_File(filename) == DISPLAY_BATCH_PARTIAL);
  assert(first.lines == 2 && second.lines == 0);
  first.running = false;
  first.async_refresh = false;
  assert(Display_Text_From_File(filename) == DISPLAY_BATCH_OK);
  assert(first.lines == 2 && second.lines == 2);

  reset(first, second);
  first.async_refresh = true;
  filesystem.files["/batch"] = "[P/path:][h3dS2:h1]\n";
  XdrvMailbox.data = filename;
  XdrvMailbox.data_len = strlen(filename);
  assert(Display_Text_From_File(filename) == DISPLAY_BATCH_PARTIAL);
  assert(bitmap_calls == 1 && first.lines == 1);
  first.running = false;
  first.async_refresh = false;
  assert(Display_Text_From_File(filename) == DISPLAY_BATCH_OK);
  assert(bitmap_calls == 1 && first.lines == 1 && second.lines == 1);

  reset(first, second);
  first.async_refresh = true;
  filesystem.files["/batch"] = "[h5]\n[h10dS2:h3]\n";
  XdrvMailbox.data = filename;
  XdrvMailbox.data_len = strlen(filename);
  CmndDisplayBatch();
  assert(response == "Partial" && display_batch_continuation.active);
  XdrvMailbox.data_len = 0;
  CmndDisplayBatch();
  assert(response == "Done" && !display_batch_continuation.active);

  reset(first, second);
  second.running = true;
  filesystem.files["/busy"] = "[h10S2:]\n";
  char busy_file[] = "/busy";
  XdrvMailbox.data = busy_file;
  XdrvMailbox.data_len = strlen(busy_file);
  assert(Display_Text_From_File(busy_file) == DISPLAY_BATCH_BUSY);
  assert(first.lines == 0 && !display_batch_continuation.active);

  reset(first, second);
  filesystem.files["/descriptor"] = "display";
  second.async_refresh = true;
  display_batch_depth = 1;
  display_batch_refresh_pending = 1UL << 1;
  char rebind[] = "[h10S2/descriptor:h2]";
  XdrvMailbox.data = rebind;
  DisplayTextState rebind_state;
  assert(!DisplayText_Run(&rebind_state));
  assert(rebind_state.changed && first.lines == 1 && displays[1].display == &second);
  second.running = false;
  second.async_refresh = false;
  assert(DisplayText_Run(&rebind_state));
  assert(first.lines == 1 && replacement.lines == 1 && displays[1].display == &replacement);

  reset(first, second);
  filesystem.files["/descriptor"] = "display";
  force_init_busy = true;
  char refused[] = "[h10S2/descriptor:h2]";
  XdrvMailbox.data = refused;
  DisplayTextState refused_state;
  assert(!DisplayText_Run(&refused_state));
  assert(refused_state.changed && first.lines == 1 && renderer == &first && cur_display == 0);
  assert(displays[1].display == &second);
  force_init_busy = false;
  assert(DisplayText_Run(&refused_state));
  assert(first.lines == 1 && replacement.lines == 1);
}
