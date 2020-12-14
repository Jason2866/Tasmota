/*
  xdrv_48_BLE_EQ3_TRV.ino - EQ3 radiator valve sense and control via BLE_ESP32 support for Tasmota

  Copyright (C) 2020  Simon Hailes

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

  --------------------------------------------------------------------------------------------
  Version yyyymmdd  Action    Description
  --------------------------------------------------------------------------------------------
  0.0.0.0 20201213  created - initial version
*/
//#define VSCODE_DEV

#ifdef VSCODE_DEV
#define ESP32
#define USE_BLE_ESP32
#define USE_EQ3_ESP32
#endif

// for testing of BLE_ESP32, we remove xsns_62_MI_ESP32.ino completely, and instead add this modified xsns_52_ibeacon_BLE_ESP32.ino
#ifdef USE_EQ3_ESP32
#ifdef ESP32                       // ESP32 only. Use define USE_HM10 for ESP8266 support
#ifdef USE_BLE_ESP32

#define XDRV_48                    48
#define D_CMND_EQ3 "trv"

#define EQ3_DEBUG

namespace EQ3_ESP32 {

void CmndTrv(void);

const char kEQ3_Commands[] PROGMEM = D_CMND_EQ3"|"
  "";

void (*const EQ3_Commands[])(void) PROGMEM = {
  &CmndTrv };


int EQ3GenericOpCompleteFn(BLE_ESP32::generic_sensor_t *pStruct);

const char EQ3_Svc[] PROGMEM = "3e135142-654f-9090-134a-a6ff5bb77046";
const char EQ3_rw_Char[] PROGMEM = "3fa4585a-ce4a-3bad-db4b-b8df8179ea09";
const char EQ3_notify_Char[] PROGMEM = "d0e8434d-cd29-0996-af41-6c90f4e0eb2a";

struct eq3_device_tag{
  uint8_t addr[6];
  char RSSI;
  uint64_t timeoutTime;
  uint8_t pairing;
} eq3_device_t;


/*********************************************************************************************\
 * variables to control operation
\*********************************************************************************************/
int retries = 0;

uint8_t pairingaddr[6] = {0,0,0,0,0,0};
uint8_t pairing = 0;

#define EQ3_NUM_DEVICESLOTS 8
eq3_device_tag EQ3Devices[EQ3_NUM_DEVICESLOTS];
void *EQ3mutex = nullptr;


/*********************************************************************************************\
 * Functions
\*********************************************************************************************/

bool EQ3Operation(const uint8_t *MAC, const uint8_t *data = nullptr, int datalen = 0, int retries_in = 0) {
  BLE_ESP32::generic_sensor_t *op = nullptr;

  // ALWAYS use this function to create a new one.
  int res = BLE_ESP32::newOperation(&op);
  if (!res){
    AddLog_P(LOG_LEVEL_ERROR,PSTR("EQ3:Can't get a newOperation from BLE"));
    retries = 0;
    return 0;
  } else {
#ifdef EQ3_DEBUG
    AddLog_P(LOG_LEVEL_DEBUG,PSTR("EQ3:got a newOperation from BLE"));
#endif
  }

  NimBLEAddress addr((uint8_t *)MAC);
  op->addr = addr;

  bool havechar = false;
  op->serviceUUID = NimBLEUUID(EQ3_Svc);
  op->characteristicUUID = NimBLEUUID(EQ3_rw_Char);
  op->notificationCharacteristicUUID = NimBLEUUID(EQ3_notify_Char);

  if (data && datalen) {
    op->writelen = datalen;
    memcpy(op->dataToWrite, data, datalen);
  } else {
    op->writelen = 1;
    op->dataToWrite[0] = 0x03; // just request status
  }

  // this op will call us back on complete or failure.
  op->completecallback = (void *)EQ3GenericOpCompleteFn;
  op->context = nullptr;

  res = BLE_ESP32::extQueueOperation(&op);
  if (!res){
    // if it fails to add to the queue, do please delete it
    BLE_ESP32::freeOperation(&op);
    AddLog_P(LOG_LEVEL_ERROR,PSTR("Failed to queue new operation - deleted"));
    retries = 0;
  } else {
    if (retries_in){
      retries = retries_in;
    }
  }

  return res;
}


int EQ3ParseOp(BLE_ESP32::generic_sensor_t *op, bool success){
  char *p = TasmotaGlobal.mqtt_data;
  int maxlen = sizeof(TasmotaGlobal.mqtt_data);

  strcpy(p, "{\"trv\":");
  p += strlen(p);
  NimBLEAddress addr = NimBLEAddress(op->addr);

  *(p++) = '\"';
  strcpy(p, addr.toString().c_str());
  p += strlen(p);
  *(p++) = '\"';

  *(p++) = ',';

  if (success) {
    sprintf(p, "\"temp\":%f,", ((float)op->dataNotify[5])/2);
    p += strlen(p);

    int stat = op->dataNotify[2];
    sprintf(p, "\"mode\":\"%s\",", (!(stat & 3))?"auto":((stat & 1)?"manual":"holiday") );
    p += strlen(p);

    sprintf(p, "\"boost\":\"%s\",", (stat & 4)?"active":"inactive");
    p += strlen(p);

    sprintf(p, "\"state\":\"%s\",", (stat & 8)?"locked":"unlocked");
    p += strlen(p);

    sprintf(p, "\"window\":\"%s\",", (stat & 16)?"open":"closed");
    p += strlen(p);

    sprintf(p, "\"battery\":\"%s\"}", (stat & 128)?"LOW":"GOOD");
    p += strlen(p);
    *(p++) = 0;
    MqttPublishPrefixTopic_P(TELE, PSTR("EQ3"), false);
    return 1;
  } else {
    sprintf(p, "\"failed\":%d}", op->state);
    p += strlen(p);
    *(p++) = 0;
    MqttPublishPrefixTopic_P(TELE, PSTR("EQ3"), false);
    return 0;
  }
}

int EQ3GenericOpCompleteFn(BLE_ESP32::generic_sensor_t *op){
  uint32_t context = (uint32_t) op->context;

  if (op->state <= GEN_STATE_FAILED){
    if (retries > 1){
      retries--;
      EQ3Operation(op->addr.getNative(), op->dataToWrite, op->writelen);
      AddLog_P(LOG_LEVEL_ERROR,PSTR("operation failed - retrying %d"), op->state);
    } else {
      AddLog_P(LOG_LEVEL_ERROR,PSTR("operation failed - no more retries %d"), op->state);
      EQ3ParseOp(op, false);
    }
    return 0;
  }

  retries = 0;

  EQ3ParseOp(op, true);
  return 0;
}



/*********************************************************************************************\
 * Functons actualy called from within the BLE task
\*********************************************************************************************/

int TaskEQ3AddDevice(const uint8_t *payload, int payloadlen, int RSSI, const uint8_t* addr){
  int free = -1;
  int i = 0;
  uint64_t now = esp_timer_get_time();

  for(i = 0; i < EQ3_NUM_DEVICESLOTS; i++){
    if(memcmp(addr,EQ3Devices[i].addr,6)==0){
      break;
    }
    if (EQ3Devices[i].timeoutTime && (EQ3Devices[i].timeoutTime < now)) {
#ifdef EQ3_DEBUG
    BLE_ESP32::SafeAddLog_P(LOG_LEVEL_DEBUG,PSTR("EQ3 timeout at %d"), i);
#endif
      EQ3Devices[i].timeoutTime = 0L;
    }
    if (!EQ3Devices[i].timeoutTime){
      if (free == -1){
        free = i;
      }
    }
  }

  if (i == EQ3_NUM_DEVICESLOTS){
    if (free >= 0){
      i = free;
    } else {
      BLE_ESP32::SafeAddLog_P(LOG_LEVEL_ERROR,PSTR("EQ3: no more space for devices"));
      return 0;
    }
  }
  
  EQ3Devices[i].timeoutTime = now + (1000L*1000L)*60L;
  memcpy(EQ3Devices[i].addr, addr, 6);
  EQ3Devices[i].RSSI = RSSI;

  if (payloadlen > 17 && payload[17]){
    EQ3Devices[i].pairing = 1;
  } else {
    EQ3Devices[i].pairing = 0;
  }

  if (EQ3Devices[i].pairing){
    memcpy(pairingaddr, addr, 6);
    pairing = 1;
  }

#ifdef EQ3_DEBUG
  BLE_ESP32::SafeAddLog_P(LOG_LEVEL_INFO,PSTR("EQ3 added at %d"), i);
#endif

  return 1;
}


const char *EQ3Names[] = {
  "CC-RT-BLE",
  "CC-RT-BLE-EQ",
  "CC-RT-M-BLE"
};

int TaskEQ3advertismentCallback(BLE_ESP32::ble_advertisment_t *pStruct)
{
  // we will try not to use this...
  BLEAdvertisedDevice *advertisedDevice = pStruct->advertisedDevice;

  std::string name = advertisedDevice->getName();

  bool found = false;
  const char *nameStr = name.c_str();
  for (int i = 0; i < sizeof(EQ3Names)/sizeof(*EQ3Names); i++){
    if (!strcmp(nameStr, EQ3Names[i])){
      found = true;
      break;
    }
  }
  if (!found) return 0;

  int RSSI = pStruct->RSSI;
  const uint8_t *addr = pStruct->addr;
  uint8_t* payload = advertisedDevice->getPayload();
  size_t payloadlen = advertisedDevice->getPayloadLength();
#ifdef EQ3_DEBUG
  BLE_ESP32::SafeAddLog_P(LOG_LEVEL_DEBUG,PSTR("EQ3Device: saw %s"),advertisedDevice->getAddress().toString().c_str());
#endif

  // this will take and keep the mutex until the function is over
  BLE_ESP32::BLEAutoMutex localmutex(EQ3mutex);
  TaskEQ3AddDevice(payload, payloadlen, RSSI, addr);
  return 0;
}




/*********************************************************************************************\
 * Helper functions
\*********************************************************************************************/

/**
 * @brief Remove all colons from null terminated char array
 *
 * @param _string Typically representing a MAC-address like AA:BB:CC:DD:EE:FF
 */
void EQ3stripColon(char* _string){
  uint32_t _length = strlen(_string);
  uint32_t _index = 0;
  while (_index < _length) {
    char c = _string[_index];
    if(c==':'){
      memmove(_string+_index,_string+_index+1,_length-_index);
    }
    _index++;
  }
  _string[_index] = 0;
}


/*********************************************************************************************\
 * init
\*********************************************************************************************/
void EQ3Init(void) {
  memset(&EQ3Devices, 0, sizeof(EQ3Devices));
  BLE_ESP32::BLEAutoMutex::init(&EQ3mutex);
  BLE_ESP32::registerForAdvertismentCallbacks((const char *)"EQ3", TaskEQ3advertismentCallback);
#ifdef EQ3_DEBUG
  AddLog_P(LOG_LEVEL_INFO,PSTR("EQ3: init: request callbacks"));
#endif
  return;
}

/***********************************************************************\
 * Regular
\***********************************************************************/

void EQ3Every50mSecond(){

}

/**
 * @brief Main loop of the driver, "high level"-loop
 *
 */

void EQ3EverySecond(bool restart){
  if (pairing){
    pairing = 0;
    char *p = TasmotaGlobal.mqtt_data;
    int maxlen = sizeof(TasmotaGlobal.mqtt_data);

    strcpy(p, "{\"pairing\":");
    p += strlen(p);
    *(p++) = '\"';
    BLE_ESP32::dump(p, 20, pairingaddr, 6);
    p += strlen(p);
    *(p++) = '\"';
    *(p++) = '}';
    *(p++) = 0;

    MqttPublishPrefixTopic_P(TELE, PSTR("EQ3"), false);
  }
}


/*********************************************************************************************\
 * Presentation
\*********************************************************************************************/
int EQ3SendCurrentDevices(){
  // send the active devices

  char *p = TasmotaGlobal.mqtt_data;
  int maxlen = sizeof(TasmotaGlobal.mqtt_data);

  strcpy(p, "{\"devices\":{");
  p += strlen(p);

  int added = 0;
  for(int i = 0; i < EQ3_NUM_DEVICESLOTS; i++){
    if (!EQ3Devices[i].timeoutTime)
      continue;
    if (added){
      *(p++) = ',';
    }
    *(p++) = '\"';
    BLE_ESP32::dump(p, 20, EQ3Devices[i].addr, 6);
    p += strlen(p);
    *(p++) = '\"';
    *(p++) = ':';
    *(p++) = 0x30+EQ3Devices[i].pairing;
    added = 1;
  }
  *(p++) = '}';
  *(p++) = '}';
  *(p++) = 0;

  MqttPublishPrefixTopic_P(TELE, PSTR("EQ3"), false);

  return 0;
}

/*********************************************************************************************\
 * Commands
\*********************************************************************************************/

//
// great description here:
// https://reverse-engineering-ble-devices.readthedocs.io/en/latest/protocol_description/00_protocol_description.html
// not all implemented yet.
//
int EQ3Send(const uint8_t* addr, const char *cmd, const char* param, const char* param2){

#ifdef EQ3_DEBUG
  if (!param) param = "";
  AddLog_P(LOG_LEVEL_INFO,PSTR("EQ3 cmd: %s %s"), cmd, param);
#endif
  uint8_t d[12];
  int dlen = 0;
  do {
    if (!strcmp(cmd, "settime")){
      if (!param || param[0] == 0){
        time_t now = 0;
        struct tm timeinfo = { 0 };
        time(&now);
        localtime_r(&now, &timeinfo);
        d[0] = 0x03;
        d[1] = timeinfo.tm_year - 100;
        d[2] = timeinfo.tm_mon + 1;
        d[3] = timeinfo.tm_mday;
        d[4] = timeinfo.tm_hour;
        d[5] = timeinfo.tm_min;
        d[6] = timeinfo.tm_sec;
      } else {
        BLE_ESP32::fromHex(d, param, 6);
      }
      dlen = 7;
      break;
    }

    if (!strcmp(cmd, "settemp")){
      if (!param || param[0] == 0){
        return -1;
      }
      float ftemp = 20;
      sscanf(param, "%f", &ftemp);
      if (ftemp < 5) ftemp = 5;
      ftemp *= 2;
      uint8_t ctemp = (uint8_t) ftemp;
      d[0] = 0x41; d[1] = ctemp; dlen = 2;
      break; 
    }

    if (!strcmp(cmd, "offset")){
      if (!param || param[0] == 0){
        return 0;
      }
      float ftemp = 20;
      sscanf(param, "%f", &ftemp);
      ftemp *= 2;
      uint8_t ctemp = (uint8_t) ftemp;
      ctemp += 7;
      d[0] = 0x13; d[1] = ctemp; dlen = 2;
      break; 
    }

    if (!strcmp(cmd, "setdaynight")){
      if (!param || param[0] == 0){
        return -1;
      }
      if (!param2 || param2[0] == 0){
        return -1;
      }
      float ftemp = 15;
      sscanf(param, "%f", &ftemp);
      if (ftemp < 5) ftemp = 5;
      ftemp *= 2;
      uint8_t dtemp = (uint8_t) ftemp;

      ftemp = 20;
      sscanf(param2, "%f", &ftemp);
      if (ftemp < 5) ftemp = 5;
      ftemp *= 2;
      uint8_t ntemp = (uint8_t) ftemp;

      d[0] = 0x11; d[1] = dtemp; d[1] = ntemp; dlen = 3;
      break; 
    }

    if (!strcmp(cmd, "setwopen")){
      if (!param || param[0] == 0){
        return -1;
      }
      if (!param2 || param2[0] == 0){
        return -1;
      }
      float ftemp = 15;
      sscanf(param, "%f", &ftemp);
      if (ftemp < 5) ftemp = 5;
      ftemp *= 2;
      uint8_t temp = (uint8_t) ftemp;

      int dur = 0;
      sscanf(param2, "%d", &dur);
      d[0] = 0x14; d[1] = temp; d[1] = (dur/5); dlen = 3;
      break; 
    }

    if (!strcmp(cmd, "boost"))    { d[0] = 0x45; d[1] = 0x01; dlen = 2; break; }
    if (!strcmp(cmd, "unboost"))  { d[0] = 0x45; d[1] = 0x00; dlen = 2; break; }
    if (!strcmp(cmd, "lock"))     { d[0] = 0x80; d[1] = 0x01; dlen = 2; break; }
    if (!strcmp(cmd, "unlock"))   { d[0] = 0x80; d[1] = 0x00; dlen = 2; break; }
    if (!strcmp(cmd, "auto"))     { d[0] = 0x40; d[1] = 0x00; dlen = 2; break; }
    if (!strcmp(cmd, "manual"))   { d[0] = 0x40; d[1] = 0x40; dlen = 2; break; }
    if (!strcmp(cmd, "eco"))      { d[0] = 0x40; d[1] = 0x80; dlen = 2; break; }
    if (!strcmp(cmd, "on"))       { d[0] = 0x41; d[1] = 0x3c; dlen = 2; break; }
    if (!strcmp(cmd, "off"))      { d[0] = 0x41; d[1] = 0x09; dlen = 2; break; }
    if (!strcmp(cmd, "day"))      { d[0] = 0x43; dlen = 1; break; }
    if (!strcmp(cmd, "night"))    { d[0] = 0x44; dlen = 1; break; }
    break;
  } while(0);

  if (dlen){
    return EQ3Operation(addr, d, dlen, 4);
  }

  return -1;
}



void CmndTrv(void) {

  switch(XdrvMailbox.index){
    case 0: {
      // only allow one command in progress
      if (retries){
        ResponseCmndChar("cmdinprogress");
        return;
      }

      char *p = strtok(XdrvMailbox.data, " ");
      bool trigger = false;

      if (!strcmp(p, "scan")){
#ifdef EQ3_DEBUG
        AddLog_P(LOG_LEVEL_INFO,PSTR("EQ3 cmd: %s"), p);
#endif
        EQ3SendCurrentDevices();
        ResponseCmndDone();
        return;
      }
      if (!strcmp(p, "devlist")){
#ifdef EQ3_DEBUG
        AddLog_P(LOG_LEVEL_INFO,PSTR("EQ3 cmd: %s"), p);
#endif
        EQ3SendCurrentDevices();
        ResponseCmndDone();
        return;
      }

      if (strlen(p) == 12+5){
        EQ3stripColon(p);  
      }

      uint8_t addrbin[6];
      BLE_ESP32::fromHex(addrbin, p, sizeof(addrbin));

      NimBLEAddress addr(addrbin);

#ifdef EQ3_DEBUG
      AddLog_P(LOG_LEVEL_INFO,PSTR("EQ3 cmd addr: %s"), p);
#endif

      bool found = false;
      int i;
      const uint8_t *native = addr.getNative(); 
      uint8_t addrev[6];
      memcpy(addrev, native, 6);
      BLE_ESP32::ReverseMAC(addrev);


#ifdef EQ3_DEBUG
//      char addrstrrx[20];
//      BLE_ESP32::dump(addrstrrx, 20, addrev, 6);
#endif
      for (i = 0; i < EQ3_NUM_DEVICESLOTS; i++){
#ifdef EQ3_DEBUG
//        char addrstr[20];
//        BLE_ESP32::dump(addrstr, 20, EQ3Devices[i].addr, 6);
//        AddLog_P(LOG_LEVEL_INFO,PSTR("EQ3 compare addr: %s %s"), addrstrrx, addrstr);
#endif
        if (!memcmp(addrev, EQ3Devices[i].addr, 6)){
          found = true;
          break;
        }
      }
#ifdef EQ3_DEBUG
//      AddLog_P(LOG_LEVEL_INFO,PSTR("EQ3 cmd parsed addr: %s"), addr.toString().c_str());
#endif

      if (!found){
        ResponseCmndChar("notfound");
        return;
      }
      if (!EQ3Devices[i].timeoutTime) {
        ResponseCmndChar("forgotten");
        return;
      }

      // get next part of cmd
      const char *cmd = strtok(nullptr, " ");
      if (!cmd){
        ResponseCmndChar("invcmd");
        return;
      }

      const char *param = strtok(nullptr, " ");
      const char *param2 = nullptr;
      if (param){
        param2 = strtok(nullptr, " ");
      }
      int res = EQ3Send(addrev, cmd, param, param2);
      if (res > 0) {
        // succeeded to queue
        ResponseCmndDone();
        return;
      }
      
      if (res < 0) { // invalid in some way
        ResponseCmndChar("invcmd");
        return;
      }

      // failed to queue
      ResponseCmndChar("cmdfail");
      return;
    } break;

    case 1:
      retries = 0;
      ResponseCmndDone();
      break;
  }

  ResponseCmndChar("invidx");
}



} // end namespace XDRV_48

/*********************************************************************************************\
 * Interface
\*********************************************************************************************/

bool Xdrv48(uint8_t function)
{
  bool result = false;

  switch (function) {
    case FUNC_INIT:
      EQ3_ESP32::EQ3Init();
      break;
    case FUNC_EVERY_50_MSECOND:
      EQ3_ESP32::EQ3Every50mSecond();
      break;
    case FUNC_EVERY_SECOND:
      EQ3_ESP32::EQ3EverySecond(false);
      break;
    case FUNC_COMMAND:
      result = DecodeCommand(EQ3_ESP32::kEQ3_Commands, EQ3_ESP32::EQ3_Commands);
      break;
    case FUNC_JSON_APPEND:
      break;
#ifdef USE_WEBSERVER
    case FUNC_WEB_SENSOR:
      break;
#endif  // USE_WEBSERVER
    }
  return result;
}
#endif  // 
#endif  // ESP32

#endif