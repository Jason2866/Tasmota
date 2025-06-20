# ES8311 Audio Codec Driver für Berry
# Konvertiert von der ESP-IDF C-Implementierung

import gpio
import i2c

# ES8311 Register-Definitionen
class ES8311_REG
    static var RESET_REG00 = 0x00
    static var CLK_MANAGER_REG01 = 0x01
    static var CLK_MANAGER_REG02 = 0x02
    static var CLK_MANAGER_REG03 = 0x03
    static var CLK_MANAGER_REG04 = 0x04
    static var CLK_MANAGER_REG05 = 0x05
    static var CLK_MANAGER_REG06 = 0x06
    static var CLK_MANAGER_REG07 = 0x07
    static var CLK_MANAGER_REG08 = 0x08
    static var SDPIN_REG09 = 0x09
    static var SDPOUT_REG0A = 0x0A
    static var SYSTEM_REG0D = 0x0D
    static var SYSTEM_REG0E = 0x0E
    static var SYSTEM_REG12 = 0x12
    static var SYSTEM_REG13 = 0x13
    static var SYSTEM_REG14 = 0x14
    static var ADC_REG15 = 0x15
    static var ADC_REG16 = 0x16
    static var ADC_REG17 = 0x17
    static var ADC_REG1C = 0x1C
    static var DAC_REG31 = 0x31
    static var DAC_REG32 = 0x32
    static var DAC_REG37 = 0x37
end

# Auflösungs-Enumerationen
class ES8311_RESOLUTION
    static var RES_16 = 16
    static var RES_18 = 18
    static var RES_20 = 20
    static var RES_24 = 24
    static var RES_32 = 32
end

# Mikrofon-Verstärkung
class ES8311_MIC_GAIN
    static var GAIN_0DB = 0x00
    static var GAIN_6DB = 0x01
    static var GAIN_12DB = 0x02
    static var GAIN_18DB = 0x03
    static var GAIN_24DB = 0x04
    static var GAIN_30DB = 0x05
    static var GAIN_36DB = 0x06
    static var GAIN_42DB = 0x07
end

# Fade-Konfiguration
class ES8311_FADE
    static var FADE_DISABLE = 0
    static var FADE_ENABLE = 1
end

# Clock-Koeffizienten-Tabelle
var coeff_div = [
    # mclk, rate, pre_div, pre_multi, adc_div, dac_div, fs_mode, lrck_h, lrck_l, bclk_div, adc_osr, dac_osr
    [12288000, 8000, 6, 1, 1, 1, 0, 0x06, 0x00, 9, 32, 32],
    [12288000, 12000, 4, 1, 1, 1, 0, 0x04, 0x00, 9, 32, 32],
    [12288000, 16000, 3, 1, 1, 1, 0, 0x03, 0x00, 9, 32, 32],
    [12288000, 24000, 2, 1, 1, 1, 0, 0x02, 0x00, 9, 32, 32],
    [12288000, 32000, 3, 1, 2, 2, 0, 0x01, 0x80, 9, 32, 32],
    [12288000, 48000, 1, 1, 1, 1, 0, 0x01, 0x00, 9, 32, 32],
    [12288000, 96000, 1, 1, 2, 2, 1, 0x00, 0x80, 9, 32, 32]
]

# ES8311 Hauptklasse
class ES8311
    var i2c_port
    var dev_addr
    var i2c_dev
    
    def init(port, addr)
        self.i2c_port = port
        self.dev_addr = addr
        self.i2c_dev = i2c.Bus(port)
    end
    
    # Register schreiben
    def write_reg(reg_addr, reg_value)
        try
            self.i2c_dev.write(self.dev_addr, bytes().add(reg_addr).add(reg_value))
            return true
        except .. as e
            print("ES8311: I2C write error:", e)
            return false
        end
    end
    
    # Register lesen
    def read_reg(reg_addr)
        try
            self.i2c_dev.write(self.dev_addr, bytes().add(reg_addr))
            var result = self.i2c_dev.read(self.dev_addr, 1)
            return result[0]
        except .. as e
            print("ES8311: I2C read error:", e)
            return nil
        end
    end
    
    # Koeffizienten finden
    def get_coeff(mclk, rate)
        for i: 0..size(coeff_div)-1
            if coeff_div[i][0] == mclk && coeff_div[i][1] == rate
                return i
            end
        end
        return -1
    end
    
    # Sample-Frequenz konfigurieren
    def sample_frequency_config(mclk_frequency, sample_frequency)
        var coeff_idx = self.get_coeff(mclk_frequency, sample_frequency)
        if coeff_idx < 0
            print("ES8311: Unable to configure sample rate", sample_frequency, "Hz with", mclk_frequency, "Hz MCLK")
            return false
        end
        
        var selected_coeff = coeff_div[coeff_idx]
        
        # Register 0x02
        var regv = self.read_reg(ES8311_REG.CLK_MANAGER_REG02)
        if regv == nil return false end
        regv &= 0x07
        regv |= (selected_coeff[2] - 1) << 5  # pre_div
        regv |= selected_coeff[3] << 3        # pre_multi
        if !self.write_reg(ES8311_REG.CLK_MANAGER_REG02, regv) return false end
        
        # Register 0x03
        var reg03 = (selected_coeff[6] << 6) | selected_coeff[10]  # fs_mode, adc_osr
        if !self.write_reg(ES8311_REG.CLK_MANAGER_REG03, reg03) return false end
        
        # Register 0x04
        if !self.write_reg(ES8311_REG.CLK_MANAGER_REG04, selected_coeff[11]) return false end  # dac_osr
        
        # Register 0x05
        var reg05 = ((selected_coeff[4] - 1) << 4) | (selected_coeff[5] - 1)  # adc_div, dac_div
        if !self.write_reg(ES8311_REG.CLK_MANAGER_REG05, reg05) return false end
        
        # Register 0x06
        regv = self.read_reg(ES8311_REG.CLK_MANAGER_REG06)
        if regv == nil return false end
        regv &= 0xE0
        if selected_coeff[9] < 19  # bclk_div
            regv |= (selected_coeff[9] - 1) << 0
        else
            regv |= selected_coeff[9] << 0
        end
        if !self.write_reg(ES8311_REG.CLK_MANAGER_REG06, regv) return false end
        
        # Register 0x07
        regv = self.read_reg(ES8311_REG.CLK_MANAGER_REG07)
        if regv == nil return false end
        regv &= 0xC0
        regv |= selected_coeff[7] << 0  # lrck_h
        if !self.write_reg(ES8311_REG.CLK_MANAGER_REG07, regv) return false end
        
        # Register 0x08
        if !self.write_reg(ES8311_REG.CLK_MANAGER_REG08, selected_coeff[8]) return false end  # lrck_l
        
        return true
    end
    
    # Auflösung konfigurieren
    def resolution_config(resolution)
        var reg_value = 0
        if resolution == ES8311_RESOLUTION.RES_16
            reg_value = 3 << 2
        elif resolution == ES8311_RESOLUTION.RES_18
            reg_value = 2 << 2
        elif resolution == ES8311_RESOLUTION.RES_20
            reg_value = 1 << 2
        elif resolution == ES8311_RESOLUTION.RES_24
            reg_value = 0 << 2
        elif resolution == ES8311_RESOLUTION.RES_32
            reg_value = 4 << 2
        else
            return nil
        end
        return reg_value
    end
    
    # ES8311 initialisieren
    def initialize(sample_freq, mclk_freq, res_in, res_out)
        # Frequenz-Validierung
        if sample_freq < 8000 || sample_freq > 96000
            print("ES8311: Sample frequency must be between 8000 and 96000 Hz")
            return false
        end
        
        # Reset ES8311
        if !self.write_reg(ES8311_REG.RESET_REG00, 0x1F) return false end
        tasmota.delay(20)
        if !self.write_reg(ES8311_REG.RESET_REG00, 0x00) return false end
        if !self.write_reg(ES8311_REG.RESET_REG00, 0x80) return false end  # Power-on
        
        # Clock konfigurieren
        var reg01 = 0x3F  # Enable all clocks
        var mclk_hz = mclk_freq != nil ? mclk_freq : sample_freq * res_out * 2
        
        if mclk_freq == nil
            reg01 |= 0x80  # Select BCLK pin
        end
        
        if !self.write_reg(ES8311_REG.CLK_MANAGER_REG01, reg01) return false end
        
        # Sample-Frequenz konfigurieren
        if !self.sample_frequency_config(mclk_hz, sample_freq) return false end
        
        # Format konfigurieren (I2S Slave Mode)
        var reg09 = self.resolution_config(res_in)
        var reg0a = self.resolution_config(res_out)
        if reg09 == nil || reg0a == nil return false end
        
        var reg00 = self.read_reg(ES8311_REG.RESET_REG00)
        if reg00 == nil return false end
        reg00 &= 0xBF
        if !self.write_reg(ES8311_REG.RESET_REG00, reg00) return false end
        
        if !self.write_reg(ES8311_REG.SDPIN_REG09, reg09) return false end
        if !self.write_reg(ES8311_REG.SDPOUT_REG0A, reg0a) return false end
        
        # Analog-Schaltkreise einschalten
        if !self.write_reg(ES8311_REG.SYSTEM_REG0D, 0x01) return false end
        if !self.write_reg(ES8311_REG.SYSTEM_REG0E, 0x02) return false end
        if !self.write_reg(ES8311_REG.SYSTEM_REG12, 0x00) return false end
        if !self.write_reg(ES8311_REG.SYSTEM_REG13, 0x10) return false end
        if !self.write_reg(ES8311_REG.ADC_REG1C, 0x6A) return false end
        if !self.write_reg(ES8311_REG.DAC_REG37, 0x08) return false end
        
        return true
    end
    
    # Lautstärke setzen (0-100)
    def set_volume(volume)
        if volume < 0 volume = 0 end
        if volume > 100 volume = 100 end
        
        var reg32 = volume == 0 ? 0 : ((volume * 256) / 100) - 1
        return self.write_reg(ES8311_REG.DAC_REG32, reg32)
    end
    
    # Lautstärke lesen
    def get_volume()
        var reg32 = self.read_reg(ES8311_REG.DAC_REG32)
        if reg32 == nil return nil end
        return reg32 == 0 ? 0 : ((reg32 * 100) / 256) + 1
    end
    
    # Stummschaltung
    def mute(enable)
        var reg31 = self.read_reg(ES8311_REG.DAC_REG31)
        if reg31 == nil return false end
        
        if enable
            reg31 |= 0x60  # BIT(6) | BIT(5)
        else
            reg31 &= ~0x60
        end
        
        return self.write_reg(ES8311_REG.DAC_REG31, reg31)
    end
    
    # Mikrofon-Verstärkung setzen
    def set_mic_gain(gain)
        return self.write_reg(ES8311_REG.ADC_REG16, gain)
    end
    
    # Mikrofon konfigurieren
    def config_microphone(digital_mic)
        var reg14 = 0x1A  # Enable analog MIC and max PGA gain
        
        if digital_mic
            reg14 |= 0x40  # BIT(6) - PDM digital microphone enable
        end
        
        # ADC Gain setzen
        self.write_reg(ES8311_REG.ADC_REG17, 0xC8)
        return self.write_reg(ES8311_REG.SYSTEM_REG14, reg14)
    end
    
    # Register-Dump für Debugging
    def register_dump()
        print("ES8311 Register Dump:")
        for reg: 0..0x49
            var value = self.read_reg(reg)
            if value != nil
                print(string.format("REG:%02X: %02X", reg, value))
            end
        end
    end
end

# Verwendungsbeispiel:
# var codec = ES8311(0, 0x18)  # I2C Port 0, Adresse 0x18
# codec.initialize(48000, 12288000, ES8311_RESOLUTION.RES_16, ES8311_RESOLUTION.RES_16)
# codec.set_volume(50)
# codec.config_microphone(false)

return ES8311
