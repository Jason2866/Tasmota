# TAS5805M DAC Driver für Berry/Tasmota
# Basiert auf: https://github.com/sonocotta/esp32-tas5805m-dac

class TAS5805M
    var i2c_addr
    var pdn_pin
    var fault_pin
    var wire
    
    # Register-Definitionen
    static PAGE_REG = 0x00
    static RESET_REG = 0x01
    static DEVICE_CTRL_1 = 0x02
    static DEVICE_CTRL_2 = 0x03
    static SIG_CH_CTRL = 0x28
    static SAP_CTRL1 = 0x33
    static SAP_CTRL2 = 0x34
    static SAP_CTRL3 = 0x35
    static FS_MON = 0x37
    static BCK_MON = 0x38
    static CLKDET_STATUS = 0x39
    static DIG_VOL_CTRL = 0x4C
    static DIG_VOL_CTRL2 = 0x4D
    static DIG_VOL_CTRL3 = 0x4E
    static AUTO_MUTE_CTRL = 0x50
    static AUTO_MUTE_TIME = 0x51
    static ANA_CTRL = 0x53
    static AGAIN_CTRL = 0x54
    static BQ_WR_CTRL1 = 0x5C
    static ADR_PIN_CTRL = 0x60
    static ADR_PIN_CONFIG = 0x61
    static DSP_MISC = 0x66
    static DIE_ID = 0x67
    static POWER_STATE = 0x68
    static AUTOMUTE_STATE = 0x69
    static PHASE_CTRL = 0x6A
    static SS_CTRL0 = 0x6B
    static SS_CTRL1 = 0x6C
    static SS_CTRL2 = 0x6D
    static SS_CTRL3 = 0x6E
    static SS_CTRL4 = 0x6F
    static CHAN_FAULT = 0x70
    static GLOBAL_FAULT1 = 0x71
    static GLOBAL_FAULT2 = 0x72
    static OT_WARNING = 0x73
    static PIN_CONTROL1 = 0x74
    static PIN_CONTROL2 = 0x75
    static MISC_CONTROL = 0x76
    static FAULT_CLEAR = 0x78
    
    # Konstruktor
    def init(i2c_addr, pdn_pin, fault_pin)
        self.i2c_addr = i2c_addr != nil ? i2c_addr : 0x2D
        self.pdn_pin = pdn_pin != nil ? pdn_pin : 33
        self.fault_pin = fault_pin != nil ? fault_pin : 34
        self.wire = wire
        
        # PDN Pin als Output konfigurieren
        gpio.pin_mode(self.pdn_pin, gpio.OUTPUT)
        
        # Fault Pin als Input konfigurieren (falls definiert)
        if self.fault_pin >= 0
            gpio.pin_mode(self.fault_pin, gpio.INPUT_PULLUP)
        end
        
        # Chip initialisieren
        self.hardware_reset()
        tasmota.delay(200)
        
        return self.device_init()
    end
    
    # Hardware Reset
    def hardware_reset()
        gpio.digital_write(self.pdn_pin, 0)
        tasmota.delay(20)
        gpio.digital_write(self.pdn_pin, 1)
        tasmota.delay(200)
    end
    
    # I2C Register schreiben
    def write_register(reg, value)
        self.wire.write(self.i2c_addr, reg, value, 1)
    end
    
    # I2C Register lesen
    def read_register(reg)
        self.wire.write(self.i2c_addr, reg, 0)
        return self.wire.read(self.i2c_addr, 1)
    end
    
    # Device Initialisierung
    def device_init()
        # Reset durchführen
        self.write_register(self.RESET_REG, 0x01)
        tasmota.delay(100)
        
        # Device Control konfigurieren
        self.write_register(self.DEVICE_CTRL_1, 0x02)
        self.write_register(self.DEVICE_CTRL_2, 0x03)
        
        # Signal Channel Control
        self.write_register(self.SIG_CH_CTRL, 0x00)
        
        # SAP Control konfigurieren
        self.write_register(self.SAP_CTRL1, 0x00)  # I2S Standard
        self.write_register(self.SAP_CTRL2, 0x10)  # 16-bit
        self.write_register(self.SAP_CTRL3, 0x00)
        
        # Auto-Mute deaktivieren
        self.write_register(self.AUTO_MUTE_CTRL, 0x00)
        
        # Analog Control
        self.write_register(self.ANA_CTRL, 0x00)
        
        # Power-up
        self.write_register(self.DEVICE_CTRL_2, 0x03)
        
        tasmota.delay(100)
        return true
    end
    
    # Volume setzen (0-255)
    def set_volume(volume)
        if volume > 255 volume = 255 end
        if volume < 0 volume = 0 end
        
        # Volume in dB umrechnen (-103.5dB bis 24dB)
        # 0 = -103.5dB, 255 = 24dB
        var vol_db = volume
        
        self.write_register(self.DIG_VOL_CTRL, vol_db)
        self.write_register(self.DIG_VOL_CTRL2, vol_db)
    end
    
    # Volume lesen
    def get_volume()
        return self.read_register(self.DIG_VOL_CTRL)
    end
    
    # Mute setzen
    def set_mute(mute)
        var ctrl = self.read_register(self.DEVICE_CTRL_2)
        if mute
            ctrl = ctrl | 0x08  # Mute bit setzen
        else
            ctrl = ctrl & 0xF7  # Mute bit löschen
        end
        self.write_register(self.DEVICE_CTRL_2, ctrl)
    end
    
    # Mute Status lesen
    def get_mute()
        var ctrl = self.read_register(self.DEVICE_CTRL_2)
        return (ctrl & 0x08) != 0
    end
    
    # Power State setzen
    def set_power(power_on)
        if power_on
            self.write_register(self.DEVICE_CTRL_2, 0x03)  # Power up
        else
            self.write_register(self.DEVICE_CTRL_2, 0x01)  # Power down
        end
    end
    
    # Power State lesen
    def get_power_state()
        return self.read_register(self.POWER_STATE)
    end
    
    # Sample Rate lesen
    def get_sample_rate()
        var fs_mon = self.read_register(self.FS_MON)
        var rates = [8000, 16000, 22050, 24000, 32000, 44100, 48000, 88200, 96000, 176400, 192000]
        
        if fs_mon < size(rates)
            return rates[fs_mon]
        end
        return 0
    end
    
    # BCK Ratio lesen
    def get_bck_ratio()
        return self.read_register(self.BCK_MON)
    end
    
    # Fault Status lesen
    def get_fault_status()
        var chan_fault = self.read_register(self.CHAN_FAULT)
        var global_fault1 = self.read_register(self.GLOBAL_FAULT1)
        var global_fault2 = self.read_register(self.GLOBAL_FAULT2)
        
        return {
            'channel': chan_fault,
            'global1': global_fault1,
            'global2': global_fault2
        }
    end
    
    # Fault Status löschen
    def clear_fault()
        self.write_register(self.FAULT_CLEAR, 0x80)
        tasmota.delay(10)
        self.write_register(self.FAULT_CLEAR, 0x00)
    end
    
    # Analog Gain setzen
    def set_analog_gain(gain)
        # Gain: 0 = 19.2dBV, 1 = 20.7dBV, 2 = 22.2dBV, 3 = 23.7dBV
        if gain > 3 gain = 3 end
        if gain < 0 gain = 0 end
        
        var ana_ctrl = self.read_register(self.ANA_CTRL)
        ana_ctrl = (ana_ctrl & 0xFC) | gain
        self.write_register(self.ANA_CTRL, ana_ctrl)
    end
    
    # Analog Gain lesen
    def get_analog_gain()
        var ana_ctrl = self.read_register(self.ANA_CTRL)
        return ana_ctrl & 0x03
    end
    
    # Device ID lesen
    def get_device_id()
        return self.read_register(self.DIE_ID)
    end
    
    # Auto-Mute State lesen
    def get_auto_mute_state()
        return self.read_register(self.AUTOMUTE_STATE)
    end
    
    # Fault Pin Status lesen (falls konfiguriert)
    def get_fault_pin()
        if self.fault_pin >= 0
            return gpio.digital_read(self.fault_pin)
        end
        return nil
    end
    
    # Status-Informationen ausgeben
    def status()
        print("TAS5805M Status:")
        print(f"  Device ID: 0x{self.get_device_id():02X}")
        print(f"  Power State: 0x{self.get_power_state():02X}")
        print(f"  Volume: {self.get_volume()}")
        print(f"  Mute: {self.get_mute()}")
        print(f"  Sample Rate: {self.get_sample_rate()} Hz")
        print(f"  BCK Ratio: {self.get_bck_ratio()}")
        print(f"  Analog Gain: {self.get_analog_gain()}")
        print(f"  Auto-Mute State: 0x{self.get_auto_mute_state():02X}")
        
        var fault = self.get_fault_status()
        print(f"  Fault Status - Channel: 0x{fault['channel']:02X}, Global1: 0x{fault['global1']:02X}, Global2: 0x{fault['global2']:02X}")
        
        if self.fault_pin >= 0
            print(f"  Fault Pin: {self.get_fault_pin()}")
        end
    end
end

# Globale Instanz erstellen
tas5805m = nil

# Initialisierungsfunktion
def init_tas5805m(i2c_addr, pdn_pin, fault_pin)
    tas5805m = TAS5805M()
    return tas5805m.init(i2c_addr, pdn_pin, fault_pin)
end

# Tasmota-Kommandos registrieren
def tas5805m_commands()
    if tas5805m == nil
        print("TAS5805M nicht initialisiert. Verwende: init_tas5805m()")
        return
    end
    
    tasmota.add_cmd('TAS5805M_Volume', def (cmd, idx, payload)
        if payload != ""
            var vol = int(payload)
            tas5805m.set_volume(vol)
            return f"Volume auf {vol} gesetzt"
        else
            return f"Aktuelles Volume: {tas5805m.get_volume()}"
        end
    end)
    
    tasmota.add_cmd('TAS5805M_Mute', def (cmd, idx, payload)
        if payload != ""
            var mute = payload == "1" || payload == "true"
            tas5805m.set_mute(mute)
            return f"Mute: {mute}"
        else
            return f"Mute Status: {tas5805m.get_mute()}"
        end
    end)
    
    tasmota.add_cmd('TAS5805M_Power', def (cmd, idx, payload)
        if payload != ""
            var power = payload == "1" || payload == "true"
            tas5805m.set_power(power)
            return f"Power: {power}"
        else
            return f"Power State: 0x{tas5805m.get_power_state():02X}"
        end
    end)
    
    tasmota.add_cmd('TAS5805M_Status', def (cmd, idx, payload)
        tas5805m.status()
        return "Status ausgegeben"
    end)
    
    tasmota.add_cmd('TAS5805M_Gain', def (cmd, idx, payload)
        if payload != ""
            var gain = int(payload)
            tas5805m.set_analog_gain(gain)
            return f"Analog Gain auf {gain} gesetzt"
        else
            return f"Aktueller Analog Gain: {tas5805m.get_analog_gain()}"
        end
    end)
end

# Auto-Initialisierung bei Tasmota-Start
def tas5805m_init()
    # Standard-Pins für ESP32 (anpassbar)
    var i2c_addr = 0x2D  # Standard I2C-Adresse
    var pdn_pin = 33     # Power Down Pin
    var fault_pin = 34   # Fault Pin (optional)
    
    if init_tas5805m(i2c_addr, pdn_pin, fault_pin)
        print("TAS5805M erfolgreich initialisiert")
        tas5805m_commands()
    else
        print("TAS5805M Initialisierung fehlgeschlagen")
    end
end

# Bei Tasmota-Start ausführen
tasmota.add_driver(tas5805m_init)

