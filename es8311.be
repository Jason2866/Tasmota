# ES8311 Audio Codec Driver für Berry
class ES8311
    var port
    var dev_addr
    
    # Konstruktor
    def init(i2c_port, device_addr)
        self.port = i2c_port
        self.dev_addr = device_addr
    end
    
    # Register schreiben
    def write_reg(reg_addr, value)
        var write_buf = bytes()
        write_buf.add(reg_addr)
        write_buf.add(value)
        return i2c.write(self.port, self.dev_addr, write_buf)
    end
    
    # Register lesen
    def read_reg(reg_addr)
        var addr_buf = bytes()
        addr_buf.add(reg_addr)
        var result = i2c.write_read(self.port, self.dev_addr, addr_buf, 1)
        return result[0]
    end
    
    # Koeffizienten-Tabelle für Clock-Divider
    static coeff_div = [
        # mclk, rate, pre_div, pre_multi, adc_div, dac_div, fs_mode, lrck_h, lrck_l, bclk_div, adc_osr, dac_osr
        [11289600, 8000, 2, 0, 6, 6, 0, 0x6c, 0x00, 9, 0, 4],
        [11289600, 11025, 2, 0, 6, 6, 0, 0x30, 0x00, 8, 0, 4],
        [11289600, 16000, 2, 0, 3, 3, 0, 0x6c, 0x00, 9, 0, 4],
        [11289600, 22050, 2, 0, 3, 3, 0, 0x30, 0x00, 8, 0, 4],
        [11289600, 44100, 2, 0, 3, 3, 0, 0x18, 0x00, 4, 0, 4],
        [11289600, 48000, 2, 0, 3, 3, 0, 0x16, 0x00, 4, 0, 4],
        [12288000, 8000, 2, 0, 6, 6, 0, 0x60, 0x00, 12, 0, 4],
        [12288000, 16000, 2, 0, 3, 3, 0, 0x60, 0x00, 12, 0, 4],
        [12288000, 48000, 2, 0, 2, 2, 0, 0x20, 0x00, 8, 0, 4]
    ]
    
    # Koeffizienten finden
    def get_coeff(mclk, rate)
        for i: 0..size(self.coeff_div)-1
            if self.coeff_div[i][0] == mclk && self.coeff_div[i][1] == rate
                return i
            end
        end
        return -1
    end
    
    # Sample-Frequenz konfigurieren
    def sample_frequency_config(mclk_frequency, sample_frequency)
        var coeff = self.get_coeff(mclk_frequency, sample_frequency)
        if coeff < 0
            print("Fehler: Kann Sample-Rate nicht konfigurieren")
            return false
        end
        
        var selected_coeff = self.coeff_div[coeff]
        
        # Register 0x02
        var regv = self.read_reg(0x02)
        regv &= 0x07
        regv |= (selected_coeff[2] - 1) << 5
        regv |= selected_coeff[3] << 3
        self.write_reg(0x02, regv)
        
        # Register 0x03
        var reg03 = (selected_coeff[6] << 6) | selected_coeff[10]
        self.write_reg(0x03, reg03)
        
        # Register 0x04
        self.write_reg(0x04, selected_coeff[11])
        
        # Register 0x05
        var reg05 = ((selected_coeff[4] - 1) << 4) | (selected_coeff[5] - 1)
        self.write_reg(0x05, reg05)
        
        # Register 0x06
        regv = self.read_reg(0x06)
        regv &= 0xE0
        if selected_coeff[9] < 19
            regv |= (selected_coeff[9] - 1) << 0
        else
            regv |= selected_coeff[9] << 0
        end
        self.write_reg(0x06, regv)
        
        # Register 0x07
        regv = self.read_reg(0x07)
        regv &= 0xC0
        regv |= selected_coeff[7] << 0
        self.write_reg(0x07, regv)
        
        # Register 0x08
        self.write_reg(0x08, selected_coeff[8])
        
        return true
    end
    
    # ES8311 initialisieren
    def init_codec(sample_freq, mclk_freq)
        # Reset ES8311
        self.write_reg(0x00, 0x1F)
        tasmota.delay(20)
        self.write_reg(0x00, 0x00)
        self.write_reg(0x00, 0x80)
        
        # Clock-Konfiguration
        var reg01 = 0x3F  # Alle Clocks aktivieren
        if mclk_freq == nil
            # MCLK von BCLK ableiten
            mclk_freq = sample_freq * 32  # 16-bit * 2 channels
            reg01 |= 0x80  # BCLK als Quelle wählen
        end
        self.write_reg(0x01, reg01)
        
        # Sample-Frequenz konfigurieren
        if !self.sample_frequency_config(mclk_freq, sample_freq)
            return false
        end
        
        # Audio-Format konfigurieren (I2S, 16-bit)
        self.write_reg(0x09, 0x0C)  # SDP In: I2S, 16-bit
        self.write_reg(0x0A, 0x0C)  # SDP Out: I2S, 16-bit
        
        # Analog-Schaltkreise einschalten
        self.write_reg(0x0D, 0x01)  # Analog-Schaltkreise einschalten
        self.write_reg(0x0E, 0x02)  # PGA und ADC-Modulator aktivieren
        self.write_reg(0x12, 0x00)  # DAC einschalten
        self.write_reg(0x13, 0x10)  # Kopfhörer-Ausgang aktivieren
        
        # ADC/DAC-Konfiguration
        self.write_reg(0x1C, 0x6A)  # ADC-Equalizer umgehen
        self.write_reg(0x37, 0x08)  # DAC-Equalizer umgehen
        
        return true
    end
    
    # Lautstärke setzen (0-100)
    def set_volume(volume)
        if volume < 0
            volume = 0
        elif volume > 100
            volume = 100
        end
        
        var reg32
        if volume == 0
            reg32 = 0
        else
            reg32 = ((volume * 256) / 100) - 1
        end
        
        self.write_reg(0x32, reg32)
        return volume
    end
    
    # Lautstärke lesen
    def get_volume()
        var reg32 = self.read_reg(0x32)
        if reg32 == 0
            return 0
        else
            return ((reg32 * 100) / 256) + 1
        end
    end
    
    # Stummschaltung
    def mute(enable)
        var reg31 = self.read_reg(0x31)
        if enable
            reg31 |= 0x60  # Bits 6 und 5 setzen
        else
            reg31 &= ~0x60  # Bits 6 und 5 löschen
        end
        self.write_reg(0x31, reg31)
    end
    
    # Mikrofon-Verstärkung setzen
    def set_mic_gain(gain_db)
        self.write_reg(0x16, gain_db)
    end
    
    # Mikrofon konfigurieren
    def config_microphone(digital_mic)
        var reg14 = 0x1A  # Analog-Mikrofon aktivieren, max PGA-Verstärkung
        if digital_mic
            reg14 |= 0x40  # PDM Digital-Mikrofon aktivieren
        end
        
        self.write_reg(0x17, 0xC8)  # ADC-Verstärkung setzen
        self.write_reg(0x14, reg14)
    end
    
    # Register-Dump für Debugging
    def register_dump()
        print("ES8311 Register Dump:")
        for reg: 0..0x49
            var value = self.read_reg(reg)
            print(f"REG:{reg:02X}: {value:02X}")
        end
    end
end
