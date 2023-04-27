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
#ifdef USE_SMARTRC
/*********************************************************************************************\
 * CC1101 Library https://github.com/LSatan/SmartRC-CC1101-Driver-Lib
\*********************************************************************************************/

#define XDRV_101  101

#define USE_SPI
#include <ELECHOUSE_CC1101_SRC_DRV.h>

struct smartRCConfig {
  int16_t powerLevel;
  float frequency;
  bool CCMode;
  int8_t trxState;
  bool CRC;
  int8_t syncMode;
  int8_t modulation;
};
smartRCConfig smartRCConfig {12, 433.92, 0, 2, 1, 2, 0};

/*********************************************************************************************\
 * Commands
\*********************************************************************************************/

const char smartRCCommands[] PROGMEM = "smartRC|"  // smartRC Prefix
  "testSPI|"
  "setPA|"
  "setMHZ|"
  "setCCMode|"
  "SetTx|"
  "SetRx|"
  "setCrc|"
  "setSyncMode|"
  "setModulation|"
  "sendData|";

void (* const smartRCCommand[])(void) PROGMEM = {
  &CmndsmartRCtestSPI,
  &CmndsmartRCsetPA,
  &CmndsmartRCsetMHZ,
  &CmndsmartRCsetCCMode,
  &CmndsmartRCSetTx,
  &CmndsmartRCSetRx,
  &CmndsmartRCsetCrc,
  &CmndsmartRCsetSyncMode,
  &CmndsmartRCsetModulation,
  &CmndsmartRCsendData};

/*
Check the CC1101 Spi connection.
*/
void CmndsmartRCtestSPI(void) {
  if(ELECHOUSE_cc1101.getCC1101()) {
    AddLog(LOG_LEVEL_INFO, PSTR("CC1101 SPI connected!"));
  }else{
    AddLog(LOG_LEVEL_INFO, PSTR("CC1101 SPI not connected!"));
  }
  ResponseCmndDone();
}

/*
set TxPower. The following settings are possible depending on the frequency band.  
(-30  -20  -15  -10  -6    0    5    7    10   11   12) Default is max (12)!
*/
void CmndsmartRCsetPA(void) {
  if(ELECHOUSE_cc1101.getCC1101()) {
    if(XdrvMailbox.payload > -30 || XdrvMailbox.payload < 12){
      smartRCConfig.powerLevel = XdrvMailbox.payload;
      ELECHOUSE_cc1101.setPA(smartRCConfig.powerLevel);
      ResponseCmndNumber(smartRCConfig.powerLevel);
    } else {
      AddLog(LOG_LEVEL_ERROR, PSTR("Not a valid value!"));
    } 
  } else {
    AddLog(LOG_LEVEL_ERROR, PSTR("CC1101 SPI not connected!"));
  }
}

/*
(default = 433.92).The cc1101 can: 300-348 MHZ, 387-464MHZ and 779-928MHZ
*/
void CmndsmartRCsetMHZ(void) {
  if(ELECHOUSE_cc1101.getCC1101()) {
    if(XdrvMailbox.data_len > 0){
      smartRCConfig.frequency = CharToFloat(XdrvMailbox.data);
      ELECHOUSE_cc1101.setPA(smartRCConfig.frequency);
      ResponseCmndFloat(smartRCConfig.frequency, 2);
    }
  } else {
    AddLog(LOG_LEVEL_ERROR, PSTR("CC1101 SPI not connected!"));
  }
}

/*
set config for internal transmission mode. ON/OFF
*/
void CmndsmartRCsetCCMode(void) {
  if(ELECHOUSE_cc1101.getCC1101()) {
    if(XdrvMailbox.payload > -1 && XdrvMailbox.payload < 2){
      smartRCConfig.CCMode = XdrvMailbox.payload;
      ELECHOUSE_cc1101.setCCMode(smartRCConfig.CCMode);
      ResponseCmndNumber(smartRCConfig.CCMode);
    } else {
      AddLog(LOG_LEVEL_ERROR, PSTR("Not a valid value!"));
    } 
  } else {
    AddLog(LOG_LEVEL_ERROR, PSTR("CC1101 SPI not connected!"));
  }
}

/*
Set to transmit mode
trxstate = 1 (TX)
*/
void CmndsmartRCSetTx(void){
  if(ELECHOUSE_cc1101.getCC1101()) {
    smartRCConfig.trxState = 1;
    ELECHOUSE_cc1101.SetTx();
    ResponseCmndNumber(ELECHOUSE_cc1101.getMode());
  } else {
    AddLog(LOG_LEVEL_ERROR, PSTR("CC1101 SPI not connected!"));
  }
}

/*
Set to receive mode
trxstate = 2 (RX)
*/
void CmndsmartRCSetRx(void){
  if(ELECHOUSE_cc1101.getCC1101()) {
    smartRCConfig.trxState = 2;
    ELECHOUSE_cc1101.SetRx();
    ResponseCmndNumber(ELECHOUSE_cc1101.getMode());
  } else {
    AddLog(LOG_LEVEL_ERROR, PSTR("CC1101 SPI not connected!"));
  }
}

/*
1 = CRC calculation in TX and CRC check in RX enabled. 0 = CRC disabled for TX and RX.
CRC Check. If "setCrc(false)" crc returns always OK!
*/
void CmndsmartRCsetCrc(void) {
  if(ELECHOUSE_cc1101.getCC1101()) {
    if(XdrvMailbox.payload > -1 && XdrvMailbox.payload < 2){
      smartRCConfig.CRC = XdrvMailbox.payload;
      ELECHOUSE_cc1101.setCrc(smartRCConfig.CRC);
      ResponseCmndNumber(smartRCConfig.CRC);
    } else {
      AddLog(LOG_LEVEL_ERROR, PSTR("Not a valid value!"));
    } 
  } else {
    AddLog(LOG_LEVEL_ERROR, PSTR("CC1101 SPI not connected!"));
  }
}

/*
Combined sync-word qualifier mode. 
0 = No preamble/sync. 
1 = 16 sync word bits detected. 
2 = 16/16 sync word bits detected. 
3 = 30/32 sync word bits detected. 
4 = No preamble/sync, carrier-sense above threshold. 
5 = 15/16 + carrier-sense above threshold. 
6 = 16/16 + carrier-sense above threshold. 
7 = 30/32 + carrier-sense above threshold.
*/
void CmndsmartRCsetSyncMode(void) {
  if(ELECHOUSE_cc1101.getCC1101()) {
    if(XdrvMailbox.payload > -1 && XdrvMailbox.payload < 8){
      smartRCConfig.syncMode = XdrvMailbox.payload;
      ELECHOUSE_cc1101.setSyncMode(smartRCConfig.syncMode);
      ResponseCmndNumber(smartRCConfig.syncMode);
    } else {
      AddLog(LOG_LEVEL_ERROR, PSTR("Not a valid value!"));
    } 
  } else {
    AddLog(LOG_LEVEL_ERROR, PSTR("CC1101 SPI not connected!"));
  }
}

/*
set modulation mode. 0 = 2-FSK, 1 = GFSK, 2 = ASK/OOK, 3 = 4-FSK, 4 = MSK.
*/
void CmndsmartRCsetModulation(void) {
  if(ELECHOUSE_cc1101.getCC1101()) {
    if(XdrvMailbox.payload > -1 && XdrvMailbox.payload < 5){
      smartRCConfig.modulation = XdrvMailbox.payload;
      ELECHOUSE_cc1101.setModulation(smartRCConfig.modulation);
      ResponseCmndNumber(smartRCConfig.modulation);
    } else {
      AddLog(LOG_LEVEL_ERROR, PSTR("Not a valid value!"));
    } 
  } else {
    AddLog(LOG_LEVEL_ERROR, PSTR("CC1101 SPI not connected!"));
  }
}


/*
Senddata via old Method with GD0
size: number of data to send, no more than 61
*/
void CmndsmartRCsendData(void) {
  if(ELECHOUSE_cc1101.getCC1101()) {
    if(XdrvMailbox.data_len > 0 && XdrvMailbox.data_len < 62){
      ELECHOUSE_cc1101.SendData(XdrvMailbox.data);
      ResponseCmndDone();
    } else {
      AddLog(LOG_LEVEL_ERROR, PSTR("Not a valid value!"));
    } 
  } else {
    AddLog(LOG_LEVEL_ERROR, PSTR("CC1101 SPI not connected!"));
  }
}

/*********************************************************************************************\
 * Tasmota Functions (Helpers)
\*********************************************************************************************/

/* 
Initialize the CC1101
*/
void smartRCInit(){
  if (PinUsed(GPIO_SPI_CLK) && PinUsed(GPIO_SPI_MISO) && PinUsed(GPIO_SPI_MOSI) && PinUsed(GPIO_SPI_CS)) {
    //may be used with VSPI (18, 19, 23, 5)
    ELECHOUSE_cc1101.setSpiPin(Pin(GPIO_SPI_CLK), Pin(GPIO_SPI_MISO), Pin(GPIO_SPI_MOSI), Pin(GPIO_SPI_CS));
    if(ELECHOUSE_cc1101.getCC1101()) {
      ELECHOUSE_cc1101.Init();
      ELECHOUSE_cc1101.setMHZ(smartRCConfig.frequency);
      ELECHOUSE_cc1101.setPA(smartRCConfig.powerLevel);
    }
    if (PinUsed(GPIO_CC1101_GDO0) && PinUsed(GPIO_CC1101_GDO2)){
      ELECHOUSE_cc1101.setGDO(Pin(GPIO_CC1101_GDO0),Pin(GPIO_CC1101_GDO2));
    }
  }

  //TX e.g. GPIO 2
  if (PinUsed(GPIO_CC1101_GDO0) && smartRCConfig.trxState == 1){
    ELECHOUSE_cc1101.SetTx();
  }

  //RX e.g. GPIO 4
  if (PinUsed(GPIO_CC1101_GDO2) && smartRCConfig.trxState == 2){
    ELECHOUSE_cc1101.SetRx();
  }
}

/* 
Check if a message can be received.
*/
void smartRCReceive(){
  if (ELECHOUSE_cc1101.CheckReceiveFlag()){
    if (ELECHOUSE_cc1101.CheckCRC()){
      int8_t lqi = ELECHOUSE_cc1101.getLqi();
      int16_t rssi = ELECHOUSE_cc1101.getRssi();
      uint8_t rxBuffer[61] = {0};
      uint8_t len = ELECHOUSE_cc1101.ReceiveData(rxBuffer);
      ResponseTime_P(PSTR(",\"" D_JSON_RFRECEIVED "\":{\"" D_JSON_DATA "\":%s,\"" D_JSON_SIZE "\":%d,\"" D_JSON_SIGNALSTRENGTH "\":%d,\"" D_JSON_RSSI "\":%d}}"), rxBuffer, len, lqi, rssi);
      MqttPublishPrefixTopicRulesProcess_P(RESULT_OR_TELE, PSTR(D_JSON_RFRECEIVED));
    }else{
      AddLog(LOG_LEVEL_INFO, PSTR("CC1101 received message with invalid CRC."));
    }
  }
}

/* 
Reconfigure the module to the current smartRCConfig
This is needed if you change settings temporarily, e.g. for sending with a different library
*/
void smartRCreconfigure(){
  ELECHOUSE_cc1101.setCCMode(smartRCConfig.CCMode);
  switch(smartRCConfig.trxState){
    case 0:
      ELECHOUSE_cc1101.setSidle();
      break;
    case 1:
      ELECHOUSE_cc1101.SetTx();
      break;
    case 2:
      ELECHOUSE_cc1101.SetRx();
      break;    
  }
}

/*********************************************************************************************\
 * Interface
\*********************************************************************************************/

bool Xdrv101(uint32_t function)
{
  bool result = false;

  if (PinUsed(GPIO_SPI_CLK) && PinUsed(GPIO_SPI_MISO) && PinUsed(GPIO_SPI_MOSI) && PinUsed(GPIO_SPI_CS)) {
    switch (function) {

      case FUNC_EVERY_50_MSECOND:
        if (PinUsed(GPIO_CC1101_GDO2) && smartRCConfig.trxState == 2 && smartRCConfig.CCMode == 1) {
          smartRCReceive();
        }
        break;

      case FUNC_COMMAND:
        result = DecodeCommand(smartRCCommands, smartRCCommand);
        break;

      case FUNC_INIT:
        smartRCInit();
        break;
    }
  }
  return result;
}

#endif