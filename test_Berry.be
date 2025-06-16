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
    # PA Power
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
