#ifndef UDISPLAY_CONFIG_H
#define UDISPLAY_CONFIG_H

// Logging system interface
enum LoggingLevels {
    LOG_LEVEL_NONE, 
    LOG_LEVEL_ERROR, 
    LOG_LEVEL_INFO, 
    LOG_LEVEL_DEBUG, 
    LOG_LEVEL_DEBUG_MORE
};

extern void AddLog(uint32_t loglevel, const char* formatP, ...);

extern int32_t ESP_ResetInfoReason();


enum uColorType { uCOLOR_BW, uCOLOR_COLOR };

// Color definitions
#define UDISP_BLACK       0x0000      /*   0,   0,   0 */
#define UDISP_NAVY        0x000F      /*   0,   0, 128 */
#define UDISP_DARKGREEN   0x03E0      /*   0, 128,   0 */
#define UDISP_DARKCYAN    0x03EF      /*   0, 128, 128 */
#define UDISP_MAROON      0x7800      /* 128,   0,   0 */
#define UDISP_PURPLE      0x780F      /* 128,   0, 128 */
#define UDISP_OLIVE       0x7BE0      /* 128, 128,   0 */
#define UDISP_LIGHTGREY   0xC618      /* 192, 192, 192 */
#define UDISP_DARKGREY    0x7BEF      /* 128, 128, 128 */
#define UDISP_BLUE        0x001F      /*   0,   0, 255 */
#define UDISP_GREEN       0x07E0      /*   0, 255,   0 */
#define UDISP_CYAN        0x07FF      /*   0, 255, 255 */
#define UDISP_RED         0xF800      /* 255,   0,   0 */
#define UDISP_MAGENTA     0xF81F      /* 255,   0, 255 */
#define UDISP_YELLOW      0xFFE0      /* 255, 255,   0 */
#define UDISP_WHITE       0xFFFF      /* 255, 255, 255 */
#define UDISP_ORANGE      0xFD20      /* 255, 165,   0 */
#define UDISP_GREENYELLOW 0xAFE5      /* 173, 255,  47 */
#define UDISP_PINK        0xFc18      /* 255, 128, 192 */


// epaper pseudo opcodes
#define EP_RESET 0x60
#define EP_LUT_FULL 0x61
#define EP_LUT_PARTIAL 0x62
#define EP_WAITIDLE 0x63
#define EP_SET_MEM_AREA 0x64
#define EP_SET_MEM_PTR 0x65
#define EP_SEND_DATA 0x66
#define EP_CLR_FRAME 0x67
#define EP_SEND_FRAME 0x68
#define EP_BREAK_RR_EQU 0x69
#define EP_BREAK_RR_NEQ 0x6a

#endif