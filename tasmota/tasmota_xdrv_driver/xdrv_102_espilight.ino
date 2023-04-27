/*
  xdrv_101_rcswitch.ino - CC1101 Library for Tasmota based on LSatans SmartRC

  Copyright (C) 2021  Theo Arends

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
#ifdef USE_ESPILIGHT
/*********************************************************************************************\
 * Library https://github.com/puuu/ESPiLight
\*********************************************************************************************/

#define XDRV_102  102

#include <ESPiLight.h>
/*
Pin() will return -1 when not used, TX disabled
*/
ESPiLight ESPiLight(Pin(GPIO_ESPILIGHT_TX));

/*********************************************************************************************\
 * Commands
\*********************************************************************************************/

const char espilightCommands[] PROGMEM = "esplilight|"  // esplilight Prefix
  "send|";

void (* const espilightCommand[])(void) PROGMEM = {
  &Cmndesplilightsend,};

/*
Check the Test
*/
void Cmndesplilightsend(void) {
  if(PinUsed(GPIO_ESPILIGHT_TX)){
    String protocol = "";
    String data = "";
    uint16_t repeats = 0;

    JsonParser parser(XdrvMailbox.data);
    AddLog(LOG_LEVEL_DEBUG_MORE, PSTR("ESPiLight: %s"), XdrvMailbox.data);
    JsonParserObject root = parser.getRootObject();

    if (root) {
      // esplilightsend {"protocol": "heitech","data": {"systemcode": 5,"unitcode": 1,"state": "off"},"repeats": 5}
      // rf.send("elro_800_switch", "{\"systemcode\":17,\"unitcode\":1,\"on\":1}");
      protocol = root[PSTR("protocol")].getStr();
      AddLog(LOG_LEVEL_DEBUG, PSTR("ESPiLight.protocol: %s"), protocol.c_str());

      JsonGeneratorObject dataGenerator;
      JsonParserObject dataObj = root[PSTR("data")];
      for(auto key : dataObj){
        dataGenerator.add(key, 123);
      }
      data = dataGenerator.toString();
      AddLog(LOG_LEVEL_DEBUG, PSTR("ESPiLight.data: %s"), data.c_str());

      repeats = root[PSTR("repeats")].getUInt();
      AddLog(LOG_LEVEL_DEBUG, PSTR("ESPiLight.repeats: %d"), repeats);

#ifdef USE_SMARTRC
      ELECHOUSE_cc1101.setCCMode(0);
      ELECHOUSE_cc1101.SetTx();
#endif    
      ESPiLight.send(protocol, data, repeats);
      ResponseCmndDone();
#ifdef USE_SMARTRC
      smartRCreconfigure();
#endif     
    }
  }
}

/*********************************************************************************************\
 * Tasmota Functions (Helpers)
\*********************************************************************************************/

/*
Callback to handle received data
*/
void espilightCallback(const String &protocol, const String &message, int status,size_t repeats, const String &deviceID) {
  if(status == VALID){
    ResponseTime_P(PSTR(",\"" D_JSON_RFRECEIVED "\":{\"" D_JSON_IR_PROTOCOL "\":\"%s\",\"" D_JSON_DATA "\":%s,\"" D_JSON_STATUS "\":%d,\"" D_CMND_DEVICENAME "\":\"%s\"}}"),protocol.c_str(), message.c_str(), status, deviceID.c_str());
    MqttPublishPrefixTopicRulesProcess_P(RESULT_OR_TELE, PSTR(D_JSON_RFRECEIVED));
  }
}

/* 
Initialize the library
*/
void espilightInit(){
  if (PinUsed(GPIO_ESPILIGHT_RX)) {
    ESPiLight.setCallback(espilightCallback);
    ESPiLight.initReceiver(Pin(GPIO_ESPILIGHT_RX));
  }
}

/*********************************************************************************************\
 * Interface
\*********************************************************************************************/

bool Xdrv102(uint32_t function)
{
  bool result = false;

  if (PinUsed(GPIO_ESPILIGHT_RX) || PinUsed(GPIO_ESPILIGHT_TX)) {
    switch (function) {

      case FUNC_EVERY_50_MSECOND:
        if (PinUsed(GPIO_ESPILIGHT_RX)) {
          ESPiLight.loop();
        }
        break;

      case FUNC_COMMAND:
        result = DecodeCommand(espilightCommands, espilightCommand);
        break;

      case FUNC_INIT:
        espilightInit();
        break;
    }
  }
  return result;
}

#endif