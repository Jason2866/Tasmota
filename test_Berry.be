# ES8311 Audio Codec Driver in Berry
# Converted from C implementation for Tasmota/ESP32

class ES8311
    # Konstanten
    static var ES8311_ADDR = 0x30
    static var FROM_MCLK_PIN = 0
    static var FROM_SCLK_PIN = 1
    static var INVERT_MCLK = 0
    static var INVERT_SCLK = 0
    static var IS_DMIC = 0
    static var MCLK_DIV_FRE = 256
    
    # Register-Definitionen (Beispiele - vollständige Liste würde hier stehen)
    static var ES8311_RESET_REG00 = 0x00
    static var ES8311_CLK_MANAGER_REG01 = 0x01
    static var ES8311_CLK_MANAGER_REG02 = 0x02
    static var ES8311_DAC_REG31 = 0x31
    static var ES8311_DAC_REG32 = 0x32
    static var ES8311_GPIO_REG44 = 0x44
    
    var i2c_handle
    var dac_vol_handle
    var coeff_div
    
    def init()
        self.i2c_handle = nil
        self.dac_vol_handle = nil
        self.init_coeff_table()
    end
    
    # Clock coefficient table initialization
    def init_coeff_table()
        self.coeff_div = [
            # mclk, rate, pre_div, mult, adc_div, dac_div, fs_mode, lrch, lrcl, bckdiv, osr
            # 8k
            [12288000, 8000, 0x06, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            [18432000, 8000, 0x03, 0x02, 0x03, 0x03, 0x00, 0x05, 0xff, 0x18, 0x10, 0x20],
            # 16k
            [12288000, 16000, 0x03, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            # 44.1k
            [11289600, 44100, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            # 48k
            [12288000, 48000, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10]
            # Weitere Einträge würden hier folgen...
        ]
    end
    
    # I2C Schreibfunktion
    def write_reg(reg_addr, data)
        if self.i2c_handle == nil
            return false
        end
        return self.i2c_handle.write(self.ES8311_ADDR, reg_addr, data, 1)
    end
    
    # I2C Lesefunktion
    def read_reg(reg_addr)
        if self.i2c_handle == nil
            return -1
        end
        var data = self.i2c_handle.read(self.ES8311_ADDR, reg_addr, 1)
        return data != nil ? data : -1
    end
    
    # I2C Initialisierung
    def i2c_init()
        import wire
        self.i2c_handle = wire
        return true
    end
    
    # Coefficient lookup
    def get_coeff(mclk, rate)
        for i: 0..size(self.coeff_div)-1
            if self.coeff_div[i][1] == rate && self.coeff_div[i][0] == mclk
                return i
            end
        end
        return -1
    end
    
    # Mute-Funktion
    def mute(enable)
        var regv = self.read_reg(self.ES8311_DAC_REG31) & 0x9f
        if enable
            self.write_reg(self.ES8311_DAC_REG31, regv | 0x60)
        else
            self.write_reg(self.ES8311_DAC_REG31, regv)
        end
    end
    
    # Suspend-Modus
    def suspend()
        print("ES8311: Entering suspend mode")
        self.write_reg(self.ES8311_DAC_REG32, 0x00)
        self.write_reg(0x17, 0x00)  # ES8311_ADC_REG17
        self.write_reg(0x0E, 0xFF)  # ES8311_SYSTEM_REG0E
        self.write_reg(0x12, 0x02)  # ES8311_SYSTEM_REG12
        self.write_reg(0x14, 0x00)  # ES8311_SYSTEM_REG14
        self.write_reg(0x0D, 0xFA)  # ES8311_SYSTEM_REG0D
        self.write_reg(0x15, 0x00)  # ES8311_ADC_REG15
        self.write_reg(0x45, 0x01)  # ES8311_GP_REG45
    end
    
    # PA Power Control
    def pa_power(enable)
        var pa_gpio = self.get_pa_enable_gpio()
        if pa_gpio == -1
            return true
        end
        
        import gpio
        if enable
            gpio.digital_write(pa_gpio, 1)
        else
            gpio.digital_write(pa_gpio, 0)
        end
        return true
    end
    
    # Codec Initialisierung
    def codec_init(codec_cfg)
        if !self.i2c_init()
            return false
        end
        
        # I2C noise immunity enhancement
        self.write_reg(self.ES8311_GPIO_REG44, 0x08)
        self.write_reg(self.ES8311_GPIO_REG44, 0x08)  # Doppelter Write für Zuverlässigkeit
        
        # Clock manager setup
        self.write_reg(self.ES8311_CLK_MANAGER_REG01, 0x30)
        self.write_reg(self.ES8311_CLK_MANAGER_REG02, 0x00)
        self.write_reg(0x03, 0x10)  # ES8311_CLK_MANAGER_REG03
        self.write_reg(0x16, 0x24)  # ES8311_ADC_REG16
        
        # Reset und Mode-Konfiguration
        self.write_reg(self.ES8311_RESET_REG00, 0x80)
        
        # Master/Slave Mode
        var regv = self.read_reg(self.ES8311_RESET_REG00)
        if codec_cfg.contains("mode") && codec_cfg["mode"] == "master"
            print("ES8311 in Master mode")
            regv |= 0x40
        else
            print("ES8311 in Slave mode")
            regv &= 0xBF
        end
        self.write_reg(self.ES8311_RESET_REG00, regv)
        
        # Sample rate configuration
        var sample_rate = codec_cfg.find("sample_rate", 48000)
        var mclk_freq = sample_rate * self.MCLK_DIV_FRE
        var coeff = self.get_coeff(mclk_freq, sample_rate)
        
        if coeff < 0
            print(f"ES8311: Unable to configure sample rate {sample_rate}Hz")
            return false
        end
        
        # Clock parameter setup basierend auf coeff_div
        self.setup_clock_parameters(coeff)
        
        # System register setup
        self.write_reg(0x13, 0x10)  # ES8311_SYSTEM_REG13
        self.write_reg(0x1B, 0x0A)  # ES8311_ADC_REG1B
        self.write_reg(0x1C, 0x6A)  # ES8311_ADC_REG1C
        
        # PA GPIO setup
        self.setup_pa_gpio()
        
        # Volume control initialization
        self.init_volume_control()
        
        return true
    end
    
    # Clock parameter setup
    def setup_clock_parameters(coeff)
        var coeff_data = self.coeff_div[coeff]
        
        # Pre-divider setup
        var regv = self.read_reg(self.ES8311_CLK_MANAGER_REG02) & 0x07
        regv |= (coeff_data[2] - 1) << 5  # pre_div
        
        # Pre-multiplier
        var datmp = 0
        var pre_multi = coeff_data[3]
        if pre_multi == 1
            datmp = 0
        elif pre_multi == 2
            datmp = 1
        elif pre_multi == 4
            datmp = 2
        elif pre_multi == 8
            datmp = 3
        end
        
        regv |= datmp << 3
        self.write_reg(self.ES8311_CLK_MANAGER_REG02, regv)
        
        # Weitere Clock-Parameter würden hier konfiguriert...
    end
    
    # Volume control
    def set_voice_volume(volume)
        if volume < 0 || volume > 100
            return false
        end
        
        # Volume mapping (vereinfacht)
        var reg_value = int((volume * 191) / 100)  # 0-191 Register range
        return self.write_reg(self.ES8311_DAC_REG32, reg_value)
    end
    
    def get_voice_volume()
        var reg_value = self.read_reg(self.ES8311_DAC_REG32)
        if reg_value < 0
            return 0
        end
        return int((reg_value * 100) / 191)
    end
    
    # Mute control
    def set_voice_mute(enable)
        self.mute(enable)
        return true
    end
    
    # Start/Stop functions
    def start(mode)
        print(f"ES8311: Starting in mode {mode}")
        
        # Interface setup
        var dac_iface = self.read_reg(0x09) & 0xBF  # ES8311_SDPIN_REG09
        var adc_iface = self.read_reg(0x0A) & 0xBF  # ES8311_SDPOUT_REG0A
        
        dac_iface |= 0x40  # BIT(6)
        adc_iface |= 0x40
        
        if mode == "adc" || mode == "both"
            adc_iface &= ~0x40
        end
        if mode == "dac" || mode == "both"
            dac_iface &= ~0x40
        end
        
        self.write_reg(0x09, dac_iface)
        self.write_reg(0x0A, adc_iface)
        
        # System startup sequence
        self.write_reg(0x17, 0xBF)  # ES8311_ADC_REG17
        self.write_reg(0x0E, 0x02)  # ES8311_SYSTEM_REG0E
        self.write_reg(0x12, 0x00)  # ES8311_SYSTEM_REG12
        self.write_reg(0x14, 0x1A)  # ES8311_SYSTEM_REG14
        
        return true
    end
    
    def stop(mode)
        print("ES8311: Stopping")
        self.suspend()
        return true
    end
    
    # Helper functions
    def get_pa_enable_gpio()
        # Diese Funktion müsste board-spezifisch implementiert werden
        return -1  # Kein PA GPIO definiert
    end
    
    def setup_pa_gpio()
        var pa_gpio = self.get_pa_enable_gpio()
        if pa_gpio != -1
            import gpio
            gpio.pin_mode(pa_gpio, gpio.OUTPUT)
            self.pa_power(true)
        end
    end
    
    def init_volume_control()
        # Volume control initialization
        # Vereinfachte Implementierung
        self.dac_vol_handle = {
            "max_volume": 32,
            "min_volume": -95.5,
            "current_volume": 0
        }
    end
    
    # Debug function
    def read_all_registers()
        print("ES8311 Register Dump:")
        for i: 0..0x4A-1
            var reg_val = self.read_reg(i)
            print(f"REG[0x{i:02X}] = 0x{reg_val:02X}")
        end
    end
end

# Usage example:
# var codec = ES8311()
# var config = {"mode": "slave", "sample_rate": 48000}
# codec.codec_init(config)
# codec.set_voice_volume(50)
# codec.start("both")

