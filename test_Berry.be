# ES8311 Audio Codec Driver - Complete Berry Implementation
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
    
    # Vollständige Register-Definitionen
    static var ES8311_RESET_REG00 = 0x00
    static var ES8311_CLK_MANAGER_REG01 = 0x01
    static var ES8311_CLK_MANAGER_REG02 = 0x02
    static var ES8311_CLK_MANAGER_REG03 = 0x03
    static var ES8311_CLK_MANAGER_REG04 = 0x04
    static var ES8311_CLK_MANAGER_REG05 = 0x05
    static var ES8311_CLK_MANAGER_REG06 = 0x06
    static var ES8311_CLK_MANAGER_REG07 = 0x07
    static var ES8311_CLK_MANAGER_REG08 = 0x08
    static var ES8311_SDPIN_REG09 = 0x09
    static var ES8311_SDPOUT_REG0A = 0x0A
    static var ES8311_SYSTEM_REG0B = 0x0B
    static var ES8311_SYSTEM_REG0C = 0x0C
    static var ES8311_SYSTEM_REG0D = 0x0D
    static var ES8311_SYSTEM_REG0E = 0x0E
    static var ES8311_SYSTEM_REG10 = 0x10
    static var ES8311_SYSTEM_REG11 = 0x11
    static var ES8311_SYSTEM_REG12 = 0x12
    static var ES8311_SYSTEM_REG13 = 0x13
    static var ES8311_SYSTEM_REG14 = 0x14
    static var ES8311_ADC_REG15 = 0x15
    static var ES8311_ADC_REG16 = 0x16
    static var ES8311_ADC_REG17 = 0x17
    static var ES8311_ADC_REG1B = 0x1B
    static var ES8311_ADC_REG1C = 0x1C
    static var ES8311_DAC_REG31 = 0x31
    static var ES8311_DAC_REG32 = 0x32
    static var ES8311_DAC_REG37 = 0x37
    static var ES8311_GPIO_REG44 = 0x44
    static var ES8311_GP_REG45 = 0x45
    
    # Audio HAL Konstanten
    static var AUDIO_HAL_08K_SAMPLES = 8000
    static var AUDIO_HAL_11K_SAMPLES = 11025
    static var AUDIO_HAL_16K_SAMPLES = 16000
    static var AUDIO_HAL_22K_SAMPLES = 22050
    static var AUDIO_HAL_24K_SAMPLES = 24000
    static var AUDIO_HAL_32K_SAMPLES = 32000
    static var AUDIO_HAL_44K_SAMPLES = 44100
    static var AUDIO_HAL_48K_SAMPLES = 48000
    
    # I2S Format Konstanten
    static var AUDIO_HAL_I2S_NORMAL = 0
    static var AUDIO_HAL_I2S_LEFT = 1
    static var AUDIO_HAL_I2S_RIGHT = 2
    static var AUDIO_HAL_I2S_DSP = 3
    
    # Bit Length Konstanten
    static var AUDIO_HAL_BIT_LENGTH_16BITS = 16
    static var AUDIO_HAL_BIT_LENGTH_24BITS = 24
    static var AUDIO_HAL_BIT_LENGTH_32BITS = 32
    
    # Mode Konstanten
    static var AUDIO_HAL_MODE_MASTER = 0
    static var AUDIO_HAL_MODE_SLAVE = 1
    
    # Module Konstanten
    static var ES_MODULE_ADC = 1
    static var ES_MODULE_DAC = 2
    static var ES_MODULE_ADC_DAC = 3
    static var ES_MODULE_LINE = 4
    
    var i2c_handle
    var dac_vol_handle
    var coeff_div
    var tag
    
    def init()
        self.i2c_handle = nil
        self.dac_vol_handle = nil
        self.tag = "ES8311"
        self.init_coeff_table()
    end
    
    # Vollständige Clock coefficient table
    def init_coeff_table()
        self.coeff_div = [
            # mclk, rate, pre_div, pre_multi, adc_div, dac_div, fs_mode, lrck_h, lrck_l, bclk_div, adc_osr, dac_osr
            # 8k
            [12288000, 8000, 0x06, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            [18432000, 8000, 0x03, 0x02, 0x03, 0x03, 0x00, 0x05, 0xff, 0x18, 0x10, 0x20],
            [16384000, 8000, 0x08, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            [8192000, 8000, 0x04, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            [6144000, 8000, 0x03, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            [4096000, 8000, 0x02, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            [3072000, 8000, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            [2048000, 8000, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            [1536000, 8000, 0x03, 0x04, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            [1024000, 8000, 0x01, 0x02, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            
            # 11.025k
            [11289600, 11025, 0x04, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            [5644800, 11025, 0x02, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            [2822400, 11025, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            [1411200, 11025, 0x01, 0x02, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            
            # 12k
            [12288000, 12000, 0x04, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            [6144000, 12000, 0x02, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            [3072000, 12000, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            [1536000, 12000, 0x01, 0x02, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            
            # 16k
            [12288000, 16000, 0x03, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            [18432000, 16000, 0x03, 0x02, 0x03, 0x03, 0x00, 0x02, 0xff, 0x0c, 0x10, 0x20],
            [16384000, 16000, 0x04, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            [8192000, 16000, 0x02, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            [6144000, 16000, 0x03, 0x02, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            [4096000, 16000, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            [3072000, 16000, 0x03, 0x04, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            [2048000, 16000, 0x01, 0x02, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            [1536000, 16000, 0x03, 0x08, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            [1024000, 16000, 0x01, 0x04, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x20],
            
            # 22.05k
            [11289600, 22050, 0x02, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [5644800, 22050, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [2822400, 22050, 0x01, 0x02, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [1411200, 22050, 0x01, 0x04, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            
            # 24k
            [12288000, 24000, 0x02, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [18432000, 24000, 0x03, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [6144000, 24000, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [3072000, 24000, 0x01, 0x02, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [1536000, 24000, 0x01, 0x04, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            
            # 32k
            [12288000, 32000, 0x03, 0x02, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [18432000, 32000, 0x03, 0x04, 0x03, 0x03, 0x00, 0x02, 0xff, 0x0c, 0x10, 0x10],
            [16384000, 32000, 0x02, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [8192000, 32000, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [6144000, 32000, 0x03, 0x04, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [4096000, 32000, 0x01, 0x02, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [3072000, 32000, 0x03, 0x08, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [2048000, 32000, 0x01, 0x04, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [1536000, 32000, 0x03, 0x08, 0x01, 0x01, 0x01, 0x00, 0x7f, 0x02, 0x10, 0x10],
            [1024000, 32000, 0x01, 0x08, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            
            # 44.1k
            [11289600, 44100, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [5644800, 44100, 0x01, 0x02, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [2822400, 44100, 0x01, 0x04, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [1411200, 44100, 0x01, 0x08, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            
            # 48k
            [12288000, 48000, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [18432000, 48000, 0x03, 0x02, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [6144000, 48000, 0x01, 0x02, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [3072000, 48000, 0x01, 0x04, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [1536000, 48000, 0x01, 0x08, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            
            # 64k
            [12288000, 64000, 0x03, 0x04, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [18432000, 64000, 0x03, 0x04, 0x03, 0x03, 0x01, 0x01, 0x7f, 0x06, 0x10, 0x10],
            [16384000, 64000, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [8192000, 64000, 0x01, 0x02, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [6144000, 64000, 0x01, 0x04, 0x03, 0x03, 0x01, 0x01, 0x7f, 0x06, 0x10, 0x10],
            [4096000, 64000, 0x01, 0x04, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [3072000, 64000, 0x01, 0x08, 0x03, 0x03, 0x01, 0x01, 0x7f, 0x06, 0x10, 0x10],
            [2048000, 64000, 0x01, 0x08, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [1536000, 64000, 0x01, 0x08, 0x01, 0x01, 0x01, 0x00, 0xbf, 0x03, 0x18, 0x18],
            [1024000, 64000, 0x01, 0x08, 0x01, 0x01, 0x01, 0x00, 0x7f, 0x02, 0x10, 0x10],
            
            # 88.2k
            [11289600, 88200, 0x01, 0x02, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [5644800, 88200, 0x01, 0x04, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [2822400, 88200, 0x01, 0x08, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [1411200, 88200, 0x01, 0x08, 0x01, 0x01, 0x01, 0x00, 0x7f, 0x02, 0x10, 0x10],
            
            # 96k
            [12288000, 96000, 0x01, 0x02, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [18432000, 96000, 0x03, 0x04, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [6144000, 96000, 0x01, 0x04, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [3072000, 96000, 0x01, 0x08, 0x01, 0x01, 0x00, 0x00, 0xff, 0x04, 0x10, 0x10],
            [1536000, 96000, 0x01, 0x08, 0x01, 0x01, 0x01, 0x00, 0x7f, 0x02, 0x10, 0x10]
        ]
    end
    
    # I2C Funktionen
    def write_reg(reg_addr, data)
        if self.i2c_handle == nil
            return false
        end
        return self.i2c_handle.write(self.ES8311_ADDR, reg_addr, data, 1) == 0
    end
    
    def read_reg(reg_addr)
        if self.i2c_handle == nil
            return -1
        end
        var data = self.i2c_handle.read(self.ES8311_ADDR, reg_addr, 1)
        return data != nil ? data[0] : -1
    end
    
    def i2c_init()
        import wire
        self.i2c_handle = wire
        # I2C-Konfiguration für ESP32
        if !self.i2c_handle.enabled()
            # Standard I2C Pins für ESP32
            self.i2c_handle.begin(21, 22, 100000)  # SDA=21, SCL=22, 100kHz
        end
        return true
    end
    
    def get_es8311_mclk_src()
        # Board-spezifische Implementierung
        return self.FROM_MCLK_PIN
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
        print(f"{self.tag}: Mute = {enable}")
    end
    
    # Suspend-Modus
    def suspend()
        print(f"{self.tag}: Entering suspend mode")
        self.write_reg(self.ES8311_DAC_REG32, 0x00)
        self.write_reg(self.ES8311_ADC_REG17, 0x00)
        self.write_reg(self.ES8311_SYSTEM_REG0E, 0xFF)
        self.write_reg(self.ES8311_SYSTEM_REG12, 0x02)
        self.write_reg(self.ES8311_SYSTEM_REG14, 0x00)
        self.write_reg(self.ES8311_SYSTEM_REG0D, 0xFA)
        self.write_reg(self.ES8311_ADC_REG15, 0x00)
        self.write_reg(self.ES8311_GP_REG45, 0x01)
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
    
    def get_pa_enable_gpio()
        # Board-spezifische GPIO-Konfiguration
        # Muss für spezifisches Board angepasst werden
        return -1  # Kein PA GPIO definiert
    end
    
    # Vollständige Codec-Initialisierung
    def codec_init(codec_cfg)
        var ret = true
        
        if !self.i2c_init()
            print(f"{self.tag}: I2C initialization failed")
            return false
        end
        
        # I2C noise immunity enhancement
        ret &= self.write_reg(self.ES8311_GPIO_REG44, 0x08)
        ret &= self.write_reg(self.ES8311_GPIO_REG44, 0x08)  # Doppelter Write
        
        # Initial register setup
        ret &= self.write_reg(self.ES8311_CLK_MANAGER_REG01, 0x30)
        ret &= self.write_reg(self.ES8311_CLK_MANAGER_REG02, 0x00)
        ret &= self.write_reg(self.ES8311_CLK_MANAGER_REG03, 0x10)
        ret &= self.write_reg(self.ES8311_ADC_REG16, 0x24)
        ret &= self.write_reg(self.ES8311_CLK_MANAGER_REG04, 0x10)
        ret &= self.write_reg(self.ES8311_CLK_MANAGER_REG05, 0x00)
        ret &= self.write_reg(self.ES8311_SYSTEM_REG0B, 0x00)
        ret &= self.write_reg(self.ES8311_SYSTEM_REG0C, 0x00)
        ret &= self.write_reg(self.ES8311_SYSTEM_REG10, 0x1F)
        ret &= self.write_reg(self.ES8311_SYSTEM_REG11, 0x7F)
        ret &= self.write_reg(self.ES8311_RESET_REG00, 0x80)
        
        # Master/Slave Mode konfigurieren
        var regv = self.read_reg(self.ES8311_RESET_REG00)
        var mode = codec_cfg.find("mode", self.AUDIO_HAL_MODE_SLAVE)
        
        if mode == self.AUDIO_HAL_MODE_MASTER
            print(f"{self.tag}: ES8311 in Master mode")
            regv |= 0x40
        else
            print(f"{self.tag}: ES8311 in Slave mode")
            regv &= 0xBF
        end
        ret &= self.write_reg(self.ES8311_RESET_REG00, regv)
        
        ret &= self.write_reg(self.ES8311_CLK_MANAGER_REG01, 0x3F)
        
        # Clock source selection
        var mclk_src = self.get_es8311_mclk_src()
        regv = self.read_reg(self.ES8311_CLK_MANAGER_REG01)
        if mclk_src == self.FROM_MCLK_PIN
            regv &= 0x7F
        else
            regv |= 0x80
        end
        ret &= self.write_reg(self.ES8311_CLK_MANAGER_REG01, regv)
        
        # Sample rate konfigurieren
        var sample_rate = codec_cfg.find("sample_rate", self.AUDIO_HAL_48K_SAMPLES)
        var mclk_freq = sample_rate * self.MCLK_DIV_FRE
        var coeff = self.get_coeff(mclk_freq, sample_rate)
        
        if coeff < 0
            print(f"{self.tag}: Unable to configure sample rate {sample_rate}Hz with {mclk_freq}Hz MCLK")
            return false
        end
        
        # Clock parameter setup
        ret &= self.setup_clock_parameters(coeff)
        
        # MCLK/SCLK inversion
        regv = self.read_reg(self.ES8311_CLK_MANAGER_REG01)
        if self.INVERT_MCLK
            regv |= 0x40
        else
            regv &= ~0x40
        end
        ret &= self.write_reg(self.ES8311_CLK_MANAGER_REG01, regv)
        
        regv = self.read_reg(self.ES8311_CLK_MANAGER_REG06)
        if self.INVERT_SCLK
            regv |= 0x20
        else
            regv &= ~0x20
        end
        ret &= self.write_reg(self.ES8311_CLK_MANAGER_REG06, regv)
        
        # Final system setup
        ret &= self.write_reg(self.ES8311_SYSTEM_REG13, 0x10)
        ret &= self.write_reg(self.ES8311_ADC_REG1B, 0x0A)
        ret &= self.write_reg(self.ES8311_ADC_REG1C, 0x6A)
        
        if !ret
            print(f"{self.tag}: ES8311 initialize failed")
            return false
        end
        
        # PA GPIO setup
        self.setup_pa_gpio()
        
        # Volume control initialization
        self.init_volume_control()
        
        print(f"{self.tag}: ES8311 initialized successfully")
        return true
    end
    
    # Vollständige Clock parameter setup
    def setup_clock_parameters(coeff)
        var coeff_data = self.coeff_div[coeff]
        var ret = true
        
        # Pre-divider und multiplier setup
        var regv = self.read_reg(self.ES8311_CLK_MANAGER_REG02) & 0x07
        regv |= (coeff_data[2] - 1) << 5  # pre_div
        
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
        
        if self.get_es8311_mclk_src() == self.FROM_SCLK_PIN
            datmp = 3  # DIG_MCLK = LRCK * 256 = BCLK * 8
        end
        
        regv |= datmp << 3
        ret &= self.write_reg(self.ES8311_CLK_MANAGER_REG02, regv)
        
        # ADC/DAC divider
        regv = self.read_reg(self.ES8311_CLK_MANAGER_REG05) & 0x00
        regv |= (coeff_data[4] - 1) << 4  # adc_div
        regv |= (coeff_data[5] - 1) << 0  # dac_div
        ret &= self.write_reg(self.ES8311_CLK_MANAGER_REG05, regv)
        
        # FS mode und ADC OSR
        regv = self.read_reg(self.ES8311_CLK_MANAGER_REG03) & 0x80
        regv |= coeff_data[6] << 6  # fs_mode
        regv |= coeff_data[10] << 0  # adc_osr
        ret &= self.write_reg(self.ES8311_CLK_MANAGER_REG03, regv)
        
        # DAC OSR
        regv = self.read_reg(self.ES8311_CLK_MANAGER_REG04) & 0x80
        regv |= coeff_data[11] << 0  # dac_osr
        ret &= self.write_reg(self.ES8311_CLK_MANAGER_REG04, regv)
        
        # LRCK divider high
        regv = self.read_reg(self.ES8311_CLK_MANAGER_REG07) & 0xC0
        regv |= coeff_data[7] << 0  # lrck_h
        ret &= self.write_reg(self.ES8311_CLK_MANAGER_REG07, regv)
        
        # LRCK divider low
        regv = self.read_reg(self.ES8311_CLK_MANAGER_REG08) & 0x00
        regv |= coeff_data[8] << 0  # lrck_l
        ret &= self.write_reg(self.ES8311_CLK_MANAGER_REG08, regv)
        
        # BCLK divider
        regv = self.read_reg(self.ES8311_CLK_MANAGER_REG06) & 0xE0
        if coeff_data[9] < 19  # bclk_div
            regv |= (coeff_data[9] - 1) << 0
        else
            regv |= coeff_data[9] << 0
        end
        ret &= self.write_reg(self.ES8311_CLK_MANAGER_REG06, regv)
        
        return ret
    end
    
    # Format-Konfiguration
    def config_fmt(fmt)
        var ret = true
        var adc_iface = self.read_reg(self.ES8311_SDPOUT_REG0A)
        var dac_iface = self.read_reg(self.ES8311_SDPIN_REG09)
        
        if fmt == self.AUDIO_HAL_I2S_NORMAL
            print(f"{self.tag}: ES8311 in I2S Format")
            dac_iface &= 0xFC
            adc_iface &= 0xFC
        elif fmt == self.AUDIO_HAL_I2S_LEFT || fmt == self.AUDIO_HAL_I2S_RIGHT
            print(f"{self.tag}: ES8311 in LJ Format")
            adc_iface &= 0xFC
            dac_iface &= 0xFC
            adc_iface |= 0x01
            dac_iface |= 0x01
        elif fmt == self.AUDIO_HAL_I2S_DSP
            print(f"{self.tag}: ES8311 in DSP-A Format")
            adc_iface &= 0xDC
            dac_iface &= 0xDC
            adc_iface |= 0x03
            dac_iface |= 0x03
        else
            dac_iface &= 0xFC
            adc_iface &= 0xFC
        end
        
        ret &= self.write_reg(self.ES8311_SDPIN_REG09, dac_iface)
        ret &= self.write_reg(self.ES8311_SDPOUT_REG0A, adc_iface)
        
        return ret
    end
    
    # Bit length konfiguration
    def set_bits_per_sample(bits)
        var ret = true
        var adc_iface = self.read_reg(self.ES8311_SDPOUT_REG0A)
        var dac_iface = self.read_reg(self.ES8311_SDPIN_REG09)
        
        if bits == self.AUDIO_HAL_BIT_LENGTH_16BITS
            dac_iface |= 0x0c
            adc_iface |= 0x0c
        elif bits == self.AUDIO_HAL_BIT_LENGTH_24BITS
            # 24-bit default
        elif bits == self.AUDIO_HAL_BIT_LENGTH_32BITS
            dac_iface |= 0x10
            adc_iface |= 0x10
        else
            dac_iface |= 0x0c
            adc_iface |= 0x0c
        end
        
        ret &= self.write_reg(self.ES8311_SDPIN_REG09, dac_iface)
        ret &= self.write_reg(self.ES8311_SDPOUT_REG0A, adc_iface)
        
        return ret
    end
    
    # I2S Interface konfiguration
    def codec_config_i2s(mode, iface)
        var ret = true
        ret &= self.set_bits_per_sample(iface.find("bits", self.AUDIO_HAL_BIT_LENGTH_16BITS))
        ret &= self.config_fmt(iface.find("fmt", self.AUDIO_HAL_I2S_NORMAL))
        return ret
    end
    
    # Codec control state
    def codec_ctrl_state(mode, ctrl_state)
        var ret = true
        var es_mode = self.ES_MODULE_DAC
        
        if mode == "encode"
            es_mode = self.ES_MODULE_ADC
        elif mode == "line_in"
            es_mode = self.ES_MODULE_LINE
        elif mode == "decode"
            es_mode = self.ES_MODULE_DAC
        elif mode == "both"
            es_mode = self.ES_MODULE_ADC_DAC
        else
            es_mode = self.ES_MODULE_DAC
            print(f"{self.tag}: Codec mode not support, default is decode mode")
        end
        
        if ctrl_state == "start"
            ret = self.start(es_mode)
        else
            print(f"{self.tag}: The codec is about to stop")
            ret = self.stop(es_mode)
        end
        
        return ret
    end
    
    # Start function
    def start(mode)
        var ret = true
        
        var adc_iface = self.read_reg(self.ES8311_SDPOUT_REG0A) & 0xBF
        var dac_iface = self.read_reg(self.ES8311_SDPIN_REG09) & 0xBF
        
        adc_iface |= 0x40  # BIT(6)
        dac_iface |= 0x40
        
        if mode == self.ES_MODULE_LINE
            print(f"{self.tag}: The codec es8311 doesn't support ES_MODULE_LINE mode")
            return false
        end
        
        if mode == self.ES_MODULE_ADC || mode == self.ES_MODULE_ADC_DAC
            adc_iface &= ~0x40
        end
        if mode == self.ES_MODULE_DAC || mode == self.ES_MODULE_ADC_DAC
            dac_iface &= ~0x40
        end
        
        ret &= self.write_reg(self.ES8311_SDPIN_REG09, dac_iface)
        ret &= self.write_reg(self.ES8311_SDPOUT_REG0A, adc_iface)
        
        ret &= self.write_reg(self.ES8311_ADC_REG17, 0xBF)
        ret &= self.write_reg(self.ES8311_SYSTEM_REG0E, 0x02)
        ret &= self.write_reg(self.ES8311_SYSTEM_REG12, 0x00)
        ret &= self.write_reg(self.ES8311_SYSTEM_REG14, 0x1A)
        
        # PDM DMIC enable/disable
        var regv = self.read_reg(self.ES8311_SYSTEM_REG14)
        if self.IS_DMIC
            regv |= 0x40
        else
            regv &= ~0x40
        end
        ret &= self.write_reg(self.ES8311_SYSTEM_REG14, regv)
        
        ret &= self.write_reg(self.ES8311_SYSTEM_REG0D, 0x01)
        ret &= self.write_reg(self.ES8311_ADC_REG15, 0x40)
        ret &= self.write_reg(self.ES8311_DAC_REG37, 0x08)
        ret &= self.write_reg(self.ES8311_GP_REG45, 0x00)
        
        # Set internal reference signal
        ret &= self.write_reg(self.ES8311_GPIO_REG44, 0x58)
        
        return ret
    end
    
    # Stop function
    def stop(mode)
        self.suspend()
        return true
    end
    
    # Volume control
    def codec_set_voice_volume(volume)
        if volume < 0 || volume > 100
            return false
        end
        
        var reg = self.audio_codec_get_dac_reg_value(volume)
        var res = self.write_reg(self.ES8311_DAC_REG32, reg)
        print(f"{self.tag}: Set volume: {volume} reg_value: 0x{reg:02X}")
        return res
    end
    
    def codec_get_voice_volume()
        var regv = self.read_reg(self.ES8311_DAC_REG32)
        if regv < 0
            return 0
        end
        
        if regv == self.dac_vol_handle["reg_value"]
            return self.dac_vol_handle["user_volume"]
        else
            return 0
        end
    end
    
    # Mute control
    def set_voice_mute(enable)
        print(f"{self.tag}: SetVoiceMute: {enable}")
        self.mute(enable)
        return true
    end
    
    def get_voice_mute()
        var res = self.read_reg(self.ES8311_DAC_REG31)
        if res >= 0
            return (res & 0x20) >> 5
        end
        return 0
    end
    
    # Microphone gain
    def set_mic_gain(gain_db)
        return self.write_reg(self.ES8311_ADC_REG16, gain_db)
    end
    
    # Deinitialize
    def codec_deinit()
        # I2C cleanup würde hier stehen
        self.dac_vol_handle = nil
        return true
    end
    
    # Helper functions
    def setup_pa_gpio()
        var pa_gpio = self.get_pa_enable_gpio()
        if pa_gpio != -1
            import gpio
            gpio.pin_mode(pa_gpio, gpio.OUTPUT)
            self.pa_power(true)
        end
    end
    
    def init_volume_control()
        self.dac_vol_handle = {
            "max_dac_volume": 32,
            "min_dac_volume": -95.5,
            "board_pa_gain": 0,
            "volume_accuracy": 0.5,
            "dac_vol_symbol": 1,
            "zero_volume_reg": 0xBF,
            "reg_value": 0,
            "user_volume": 0
        }
    end
    
    def audio_codec_get_dac_reg_value(volume)
        # Vereinfachte Volume-zu-Register Konvertierung
        # 0x00: -95.5 dB, 0xBF: 0 dB, 0xFF: 32 dB
        if volume == 0
            return 0x00
        elif volume >= 100
            return 0xFF
        else
            return int((volume * 0xBF) / 100)
        end
    end
    
    # Debug function
    def read_all()
        print(f"{self.tag}: Register Dump:")
        for i: 0..0x4A-1
            var reg_val = self.read_reg(i)
            print(f"REG[0x{i:02X}] = 0x{reg_val:02X}")
        end
    end
end

# Default handle structure (als globale Variable)
var AUDIO_CODEC_ES8311_DEFAULT_HANDLE = {
    "audio_codec_initialize": nil,
    "audio_codec_deinitialize": nil,
    "audio_codec_ctrl": nil,
    "audio_codec_config_iface": nil,
    "audio_codec_set_mute": nil,
    "audio_codec_set_volume": nil,
    "audio_codec_get_volume": nil,
    "audio_codec_enable_pa": nil,
    "audio_hal_lock": nil,
    "handle": nil
}

# Usage example:
# var codec = ES8311()
# var config = {"mode": ES8311.AUDIO_HAL_MODE_SLAVE, "sample_rate": ES8311.AUDIO_HAL_48K_SAMPLES}
# codec.codec_init(config)
# codec.set_voice_volume(50)
# codec.start(ES8311.ES_MODULE_ADC_DAC)

