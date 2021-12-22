beacons =[
        {"MAC":"582D34508AF6","Timer":999},
        {"MAC":"A4C1382AC8B3","Timer":999}
        ]

ibeacons =  [
            {"UID":0,"maj":0,"min":0}
            ]

class BEACON : Driver
    var ble, cbp, buf
    var scan_timer, scan_result


    def init()
        self.buf = bytes(-64)
        self.scan_timer = 0
        self.scan_result = []
        if size(beacons) > 0
            for idx:0..size(beacons)-1
                var _tmp = beacons[idx]['MAC']
                print(_tmp)
                beacons[idx]['MAC'] = bytes(_tmp)
            end
        end
        self.cbp = tasmota.gen_cb(/-> self.cb())
        self.ble = BLE()
        self.ble.adv_cb(self.cbp,self.buf)
    end

    def cb()
        if self.scan_timer > 0
            self.add_to_result()
        end
        self.check_beacons()
        #self.check_ibeacons()
    end

    def add_to_result()
        if size(self.scan_result) > 0
            for i:0..size(self.scan_result)-1
                if self.buf[0..5] == self.scan_result[i]['MAC']
                    #print('known entry')
                    return
                end
            end
        end
        var entry = {}
        entry.insert('MAC',self.buf[0..5])
        entry.insert('Type',self.buf[6])
        var svc = self.buf.get(7,2)
        entry.insert('SVC',svc)
        var rssi = (255 - self.buf.get(9,1)) * -1
        entry.insert('RSSI',rssi)
        var len_s =  self.buf.get(10,1)
        var len_c = 0
        if len_s == 0 && svc == 0
            len_c = self.buf.get(11,1)
        end
        if len_c != 0 
            entry.insert('CID',self.buf.get(12,2))
        else
            entry.insert('CID',0)
        end
        self.scan_result.push(entry)
        print(self.buf)
    end

    def check_beacons()
        if size(beacons) > 0
            for i:0..size(beacons)-1
                if self.buf[0..5] == beacons[i]['MAC']
                    beacons[i]['Timer'] = 0
                    print(beacons[i])
                    return
                end
            end
        end
    end

    def check_ibeacons()
        if self.buf.get(12,4) == 352452684
            var uid = self.buf[16..31]
            var maj = self.buf.get(32,2)
            var min = self.buf.get(34,2)
            var tx = self.buf.get(36,1)
            print(uid)
            print(maj)
            print(min)
            print(tx)
            print(self.buf[32..36])
        end
    end

    def count_up_time()
        if size(beacons) > 0
            for idx:0..size(beacons)-1
                beacons[idx]['Timer'] += 1
            end
        end
    end

    def show_scan()
        import string
        if size(self.scan_result) > 0
            var msg = '{'
            for i:0..size(self.scan_result)-1
                var entry = self.scan_result[i]
                var msg_e = string.format("{\"MAC\":\"%02X%02X%02X%02X%02X%02X\",\"Type\":%02X,\"SVC\":\"%04X\",\"CID\":\"%04X\",\"RSSI\":%i},",
                entry['MAC'][0],entry['MAC'][1],entry['MAC'][2],entry['MAC'][3],
                entry['MAC'][4],entry['MAC'][5],entry['Type'],entry['SVC'],entry['CID'],entry['RSSI'])
                msg += msg_e
            end
            msg += '}'
            print(msg)
        end
    end

    def every_second()
        if self.scan_timer > 0
            if self.scan_timer == 1
                self.show_scan()
            end
            self.scan_timer -= 1
        end
        if beacons.size(0) > 0
            self.count_up_time()
        end
    end
end

beacon = BEACON()
tasmota.add_driver(beacon)

def scan(cmd, idx, payload, payload_json)
    if int(payload) == 0
        beacon.scan_result = []
    end
    beacon.scan_timer = int(payload)
end

tasmota.add_cmd('Mi32Scan', scan)
