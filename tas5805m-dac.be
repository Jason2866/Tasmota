# TAS5805M DAC Berry-Treiber für Tasmota
# Basiert auf: https://github.com/sonocotta/esp32-tas5805m-dac

class TAS5805M
    # Register-Definitionen aus der ursprünglichen Library
    static var REG_DEVICE_CTRL_1 = 0x02
    static var REG_DEVICE_CTRL_2 = 0x03
    static var REG_SIG_CH_CTRL = 0x28
    static var REG_SAP_CTRL1 = 0x33
    static var REG_SAP_CTRL2 = 0x34
    static var REG_SAP_CTRL3 = 0x35
    static var REG_FS_MON = 0x37
    static var REG_BCK_MON = 0x38
    static var REG_CLKDET_STATUS = 0x39
    static var REG_DIG_VOL_CTRL = 0x4C
    static var REG_DIG_VOL_CTRL2 = 0x4E
    static var REG_DIG_VOL_CTRL3 = 0x4F
    static var REG_AUTO_MUTE_CTRL = 0x50
    static var REG_AUTO_MUTE_TIME = 0x51
    static var REG_ANA_CTRL = 0x53
    static var REG_AGAIN_CTRL = 0x54
    static var REG_ADR_PIN_CTRL = 0x60
    static var REG_ADR_PIN_CONFIG = 0x61
    static var REG_DSP_MISC = 0x66
    static var REG_DIE_ID = 0x67
    static var REG_POWER_STATE = 0x68
    static var REG_AUTOMUTE_STATE = 0x69
    static var REG_PHASE_CTRL = 0x6A
    static var REG_SS_CTRL0 = 0x6B
    static var REG_SS_CTRL1 = 0x6C
    static var REG_SS_CTRL2 = 0x6D
    static var REG_SS_CTRL3 = 0x6E
    static var REG_SS_CTRL4 = 0x6F
    static var REG_CHAN_FAULT = 0x70
    static var REG_GLOBAL_FAULT1 = 0x71
    static var REG_GLOBAL_FAULT2 = 0x72
    static var REG_OT_WARNING = 0x73
    static var REG_PIN_CONTROL1 = 0x74
    static var REG_PIN_CONTROL2 = 0x75
    static var REG_MISC_CONTROL = 0x76
    static var REG_CLOCK_CONTROL = 0x77
    
    # Instanzvariablen
    var i2c_addr
    var wire
    var pdn_pin
    var initialized
    
    def init(address, pdn_gpio)
        self.i2c_addr = address || 0x2D  # Standard I2C Adresse
        self.pdn_pin = pdn_gpio || -1
        self.initialized = false
        
        # I2C Wire initialisieren
        self.wire = tasmota.wire_scan(self.i2c_addr, 0)
        if !self.wire
            print("TAS5805M: I2C Wire nicht verfügbar")
            return false
        end
        
        # PDN Pin konfigurieren falls angegeben
        if self.pdn_pin >= 0
            tasmota.pin_mode(self.pdn_pin, tasmota.OUTPUT)
            self._power_down_sequence()
        end
        
        # Initialisierung durchführen
        return self._initialize_dac()
    end
    
    def _power_down_sequence()
        if self.pdn_pin >= 0
            tasmota.digital_write(self.pdn_pin, 0)
            tasmota.delay(20)
            tasmota.digital_write(self.pdn_pin, 1)
            tasmota.delay(200)
        end
    end
    
    def _initialize_dac()
        # Basis-Initialisierung basierend auf der ursprünglichen Library
        if !self._write_register(self.REG_DEVICE_CTRL_2, 0x02)
            print("TAS5805M: Initialisierung fehlgeschlagen")
            return false
        end
        
        tasmota.delay(50)
        
        if !self._write_register(self.REG_DEVICE_CTRL_2, 0x03)
            print("TAS5805M: Power-On fehlgeschlagen")
            return false
        end
        
        tasmota.delay(100)
        
        # Standard-Konfiguration
        self._write_register(self.REG_SIG_CH_CTRL, 0x00)  # Stereo Mode
        self._write_register(self.REG_SAP_CTRL1, 0x00)    # I2S Format
        self._write_register(self.REG_AUTO_MUTE_CTRL, 0x00) # Auto-Mute aus
        
        self.initialized = true
        print("TAS5805M: Erfolgreich initialisiert auf Adresse", format("0x%02X", self.i2c_addr))
        return true
    end
    
    def _write_register(reg, value)
        if !self.wire
            return false
        end
        
        try
            self.wire.write(self.i2c_addr, reg, value, 1)
            return true
        except .. as e
            print("TAS5805M: Schreibfehler Register", format("0x%02X", reg), ":", e)
            return false
        end
    end
    
    def _read_register(reg)
        if !self.wire
            return nil
        end
        
        try
            self.wire.read(self.i2c_addr, reg, 1)
            return self.wire.read()
        except .. as e
            print("TAS5805M: Lesefehler Register", format("0x%02X", reg), ":", e)
            return nil
        end
    end
    
    # Öffentliche Methoden
    def set_volume(volume)
        if !self.initialized
            return false
        end
        
        # Volume: 0-100 -> 0x00-0xFF (invertiert)
        volume = tasmota.scale_uint(100 - volume, 0, 100, 0, 255)
        return self._write_register(self.REG_DIG_VOL_CTRL, volume)
    end
    
    def get_volume()
        if !self.initialized
            return nil
        end
        
        var vol_reg = self._read_register(self.REG_DIG_VOL_CTRL)
        if vol_reg != nil
            return 100 - tasmota.scale_uint(vol_reg, 0, 255, 0, 100)
        end
        return nil
    end
    
    def mute(enable)
        if !self.initialized
            return false
        end
        
        if enable
            return self._write_register(self.REG_DEVICE_CTRL_2, 0x01)
        else
            return self._write_register(self.REG_DEVICE_CTRL_2, 0x03)
        end
    end
    
    def set_mono_mode(enable)
        if !self.initialized
            return false
        end
        
        if enable
            # Mono: L+R -> beide Kanäle
            return self._write_register(self.REG_SIG_CH_CTRL, 0x01)
        else
            # Stereo
            return self._write_register(self.REG_SIG_CH_CTRL, 0x00)
        end
    end
    
    def set_analog_gain(gain)
        if !self.initialized
            return false
        end
        
        # Analog Gain: 0-4 entspricht verschiedenen dB Werten
        gain = tasmota.scale_uint(gain, 0, 100, 0, 4)
        return self._write_register(self.REG_AGAIN_CTRL, gain)
    end
    
    def power_off()
        if !self.initialized
            return false
        end
        
        var result = self._write_register(self.REG_DEVICE_CTRL_2, 0x00)
        if result && self.pdn_pin >= 0
            tasmota.digital_write(self.pdn_pin, 0)
        end
        return result
    end
    
    def power_on()
        if self.pdn_pin >= 0
            tasmota.digital_write(self.pdn_pin, 1)
            tasmota.delay(200)
        end
        return self._write_register(self.REG_DEVICE_CTRL_2, 0x03)
    end
    
    def get_fault_state()
        if !self.initialized
            return nil
        end
        
        var fault_map = {}
        fault_map['chan_fault'] = self._read_register(self.REG_CHAN_FAULT)
        fault_map['global_fault1'] = self._read_register(self.REG_GLOBAL_FAULT1)
        fault_map['global_fault2'] = self._read_register(self.REG_GLOBAL_FAULT2)
        fault_map['ot_warning'] = self._read_register(self.REG_OT_WARNING)
        
        return fault_map
    end
    
    def clear_fault_state()
        if !self.initialized
            return false
        end
        
        # Fault-Register durch Schreiben von 0x00 löschen
        self._write_register(self.REG_CHAN_FAULT, 0x00)
        self._write_register(self.REG_GLOBAL_FAULT1, 0x00)
        self._write_register(self.REG_GLOBAL_FAULT2, 0x00)
        self._write_register(self.REG_OT_WARNING, 0x00)
        return true
    end
    
    def get_power_state()
        if !self.initialized
            return nil
        end
        
        return self._read_register(self.REG_POWER_STATE)
    end
    
    def get_sample_rate()
        if !self.initialized
            return nil
        end
        
        return self._read_register(self.REG_FS_MON)
    end
    
    def get_bck_ratio()
        if !self.initialized
            return nil
        end
        
        return self._read_register(self.REG_BCK_MON)
    end
    
    def get_device_info()
        if !self.initialized
            return nil
        end
        
        var info = {}
        info['die_id'] = self._read_register(self.REG_DIE_ID)
        info['power_state'] = self.get_power_state()
        info['sample_rate'] = self.get_sample_rate()
        info['bck_ratio'] = self.get_bck_ratio()
        
        return info
    end
end

# Globale Instanz erstellen
var tas5805m = nil

# Initialisierungsfunktion
def init_tas5805m(i2c_addr, pdn_pin)
    tas5805m = TAS5805M()
    if tas5805m.init(i2c_addr, pdn_pin)
        print("TAS5805M: Bereit für Verwendung")
        return true
    else
        print("TAS5805M: Initialisierung fehlgeschlagen")
        tas5805m = nil
        return false
    end
end

# Tasmota-Kommandos registrieren
tasmota.add_cmd('TAS5805M_Init', def(cmd, idx, payload)
    var params = string.split(payload, ',')
    var addr = 0x2D
    var pdn = -1
    
    if size(params) >= 1 && params[0] != ""
        addr = int(params[0])
    end
    if size(params) >= 2 && params[1] != ""
        pdn = int(params[1])
    end
    
    if init_tas5805m(addr, pdn)
        tasmota.resp_cmnd_done()
    else
        tasmota.resp_cmnd_error()
    end
end)

tasmota.add_cmd('TAS5805M_Volume', def(cmd, idx, payload)
    if tas5805m == nil
        tasmota.resp_cmnd_error()
        return
    end
    
    if payload == ""
        var vol = tas5805m.get_volume()
        if vol != nil
            tasmota.resp_cmnd(str(vol))
        else
            tasmota.resp_cmnd_error()
        end
    else
        var volume = int(payload)
        if volume >= 0 && volume <= 100
            if tas5805m.set_volume(volume)
                tasmota.resp_cmnd_done()
            else
                tasmota.resp_cmnd_error()
            end
        else
            tasmota.resp_cmnd_error()
        end
    end
end)

tasmota.add_cmd('TAS5805M_Mute', def(cmd, idx, payload)
    if tas5805m == nil
        tasmota.resp_cmnd_error()
        return
    end
    
    var mute_state = (payload == "1" || payload == "ON")
    if tas5805m.mute(mute_state)
        tasmota.resp_cmnd_done()
    else
        tasmota.resp_cmnd_error()
    end
end)

tasmota.add_cmd('TAS5805M_Mono', def(cmd, idx, payload)
    if tas5805m == nil
        tasmota.resp_cmnd_error()
        return
    end
    
    var mono_state = (payload == "1" || payload == "ON")
    if tas5805m.set_mono_mode(mono_state)
        tasmota.resp_cmnd_done()
    else
        tasmota.resp_cmnd_error()
    end
end)

tasmota.add_cmd('TAS5805M_Status', def(cmd, idx, payload)
    if tas5805m == nil
        tasmota.resp_cmnd_error()
        return
    end
    
    var info = tas5805m.get_device_info()
    var faults = tas5805m.get_fault_state()
    
    if info != nil && faults != nil
        var response = {
            'device_info': info,
            'faults': faults,
            'volume': tas5805m.get_volume()
        }
        tasmota.resp_cmnd(json.dump(response))
    else
        tasmota.resp_cmnd_error()
    end
end)

print("TAS5805M Berry-Treiber geladen")
print("Verwendung: TAS5805M_Init [i2c_addr],[pdn_pin]")
print("Beispiel: TAS5805M_Init 45,33")
