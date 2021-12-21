lamps =[
        {"MAC":"CD313030292F"}
        ]

class GOVEE : Driver
    var ble, cbp, buf

    def init()
        if size(lamps) > 0
            for idx:0..size(lamps)-1
                var _tmp = lamps[idx]['MAC']
                print(_tmp)
                lamps[idx]['MAC'] = bytes(_tmp)
            end
        end
        self.buf = bytes(-21)
        self.buf[0] = 20
        self.buf[1] = 0x33
        self.cbp = tasmota.gen_cb(/e-> self.cb(e))
        self.ble = BLE()
        self.ble.conn_cb(self.cbp,self.buf)
    end

    def cb(error)
           print(error)
    end

    def chksum()
        var cs = 0;
        for i:1..19
            cs ^= self.buf[i]
        end
        self.buf[20] = cs
    end

    def clr()
        for i:2..19
            self.buf[i] = 0
        end
    end

    def writeBuf()
        var _mac = lamps[0]['MAC']
        print(_mac)
        self.ble.set_MAC(_mac)
        self.ble.set_svc("00010203-0405-0607-0809-0a0b0c0d1910")
        self.ble.set_chr("00010203-0405-0607-0809-0a0b0c0d2b11")
        self.chksum()
        print(self.buf)
        self.ble.run(112) #addrType: 1 (random) , op: 12 (write)
    end

    def every_second()
    end
end

gv = GOVEE()
tasmota.add_driver(gv)

def gv_power(cmd, idx, payload, payload_json)
    if int(payload) > 1
        return 'error'
    end
    gv.clr()
    gv.buf[2] = 1 # power cmd
    gv.buf[3] = int(payload)
    gv.writeBuf()
end

def gv_bright(cmd, idx, payload, payload_json)
    if int(payload) > 255
        return 'error'
    end
    gv.clr()
    gv.buf[2] = 4 # brightness
    gv.buf[3] = int(payload)
    gv.writeBuf()
end

def gv_rgb(cmd, idx, payload, payload_json)
    var rgb = bytes(payload)
    print(rgb)
    gv.clr()
    gv.buf[2] = 5 # color
    gv.buf[3] = 5 # manual
    gv.buf[4] = rgb[0]
    gv.buf[5] = rgb[1]
    gv.buf[6] = rgb[2]
    gv.buf[7] = rgb[3]
    gv.writeBuf()
end

def gv_scn(cmd, idx, payload, payload_json)
    gv.clr()
    gv.buf[2] = 5 # color
    gv.buf[3] = 4 # scene
    gv.buf[4] = int(payload)
    gv.writeBuf()
end

def gv_mus(cmd, idx, payload, payload_json)
    var rgb = bytes(payload)
    print(rgb)
    gv.clr()
    gv.buf[2] = 5 # color
    gv.buf[3] = 1 # music
    gv.buf[4] = rgb[0]
    gv.buf[5] = 0
    gv.buf[6] = rgb[1]
    gv.buf[7] = rgb[2]
    gv.buf[8] = rgb[3]
    gv.writeBuf()
end


tasmota.add_cmd('gpower', gv_power) # only on/off
tasmota.add_cmd('bright', gv_bright) # brightness 0 - 255
tasmota.add_cmd('color', gv_rgb) # white + color 0000FF00  -- does not really work.
tasmota.add_cmd('scene', gv_scn) # scene 0 - 15
tasmota.add_cmd('music', gv_mus) # music 00 - 0f + color 000000   -- does not work at all!!!

#   POWER      = 0x01
#   BRIGHTNESS = 0x04

#   COLOR      = 0x05
    #   MANUAL     = 0x02
    #   MICROPHONE = 0x01
    #   SCENES     = 0x04


