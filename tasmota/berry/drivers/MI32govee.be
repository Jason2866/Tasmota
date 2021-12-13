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
        self.buf[2] = 1
        self.cbp = tasmota.gen_cb(/-> self.cb())
        self.ble = BLE()
        self.ble.conn_cb(self.cbp,self.buf)
    end

    def cb()
        print('writing done!')
    end

    def chksum()
        var cs = 0;
        for i:1..19
            cs ^= self.buf[i]
        end
        self.buf[20] = cs
    end

    def writeBuf(payload)
        var _mac = lamps[0]['MAC']
        print(_mac)
        self.ble.set_MAC(_mac)
        self.ble.set_svc("00010203-0405-0607-0809-0a0b0c0d1910")
        self.ble.set_chr("00010203-0405-0607-0809-0a0b0c0d2b11")
        self.buf[3] = payload
        self.chksum()
        self.ble.run(112) #addrType: 1 (random) , op: write
    end

    def every_second()
    end
end

gv = GOVEE()
tasmota.add_driver(gv)

def gv_set(cmd, idx, payload, payload_json)
    if int(payload) > 1
        return 'error'
    end
    gv.writeBuf(int(payload))
end

tasmota.add_cmd('govee', gv_set) # only on/off
