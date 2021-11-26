class BEACON : Driver
    import string
    var cmd_arg
    scan_timer = 0
    buf = bytes(-64)
    var scan_result = {} #--- {"1":{"MAC":AABBCCDDEEFF,"SVC":0x1234,"RSSI":0}, ...} ---
    var beacons = {} #---- {"1":{"MAC":AABBCCDDEEFF,"Time":0}, ...} ---

    def init()
        cbp = tasmota.gen_cb(cb)
        BLE.adv_cb(cbp,buf)
    end

    def cb()
        if scan_timer>0
            add_to_result()
        end
        check_beacons()
        var svc = buf.get(6,2)
        var rssi = 255 - buf.get(8,1)
        var msg = string.format("{\"MAC\":%02X%02X%02X%02X%02X%02X,\"SVC\":%X,\"RSSI\":-%u}",
                    buf[0],buf[1],buf[2],buf[3],buf[4],buf[5],svc,rssi)
        print(msg)
    end

    def add_to_result()
        
    end



    def every_second()
        if scan_timer > 0
            scan_timer -= 1
        end
        if beacons.size(0) > 0
            count_up_time()
        end
    end
end

beacon = BEACON()
tasmota.add_driver(beacon)