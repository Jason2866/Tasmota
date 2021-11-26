#-------------------------------------------------------------
 - Removed Commands as Berry functions
 -------------------------------------------------------------#

ble = BLE()
m = MI32()
j = 0
sl = 0

cbuf = bytes(-64)
def cb()
    if j == 0
        print(cbuf)
    end
    if j == 1
        var temp = cbuf.get(1,2)/100.0
        var hum = cbuf.get(3,1)*1.0
        var bat = (cbuf.get(4,2)-2100)/12
        m.set_temp(sl,temp)
        m.set_hum(sl,hum)
        m.set_bat(sl,bat)
    end
    if j == 4
        var bat = cbuf.get(1,1)
        m.set_bat(sl,bat)
    end
end

cbp = tasmota.gen_cb(cb)
ble.conn_cb(cbp,cbuf)

def SetMACfromSlot(slot)
    if slot+1>m.devices()
        return "out of bounds"
    end
    sl = slot
    var _m = m.get_MAC(slot)
    ble.set_MAC(_m)
end

def MI32Time(slot)
    SetMACfromSlot(slot)
    ble.set_svc("EBE0CCB0-7A0A-4B0C-8A1A-6FF2997DA3A6")
    ble.set_chr("EBE0CCB7-7A0A-4B0C-8A1A-6FF2997DA3A6")
    cbuf[0] = 5
    var t = tasmota.rtc()
    var utc = t.item("utc")
    var tz = t.item("timezone")/60
    cbuf.set(1,utc,4)
    cbuf.set(5,tz,1)
    j = 0
    ble.run(12)
end

def MI32Unit(slot,unit)
    SetMACfromSlot(slot)
    ble.set_svc("EBE0CCB0-7A0A-4B0C-8A1A-6FF2997DA3A6")
    ble.set_chr("EBE0CCBE-7A0A-4B0C-8A1A-6FF2997DA3A6")
    cbuf[0] = 1
    cbuf[1] = unit
    j = 0
    ble.run(12)
end

def MI32Bat(slot)
    SetMACfromSlot(slot)
    var name = m.get_name(slot)
    if name == "LYWSD03"
        ble.set_svc("ebe0ccb0-7A0A-4B0C-8A1A-6FF2997DA3A6")
        ble.set_chr("ebe0ccc1-7A0A-4B0C-8A1A-6FF2997DA3A6")
        j = 1
        ble.run(13)
    end
    if name == "MHOC401"
        ble.set_svc("ebe0ccb0-7A0A-4B0C-8A1A-6FF2997DA3A6")
        ble.set_chr("ebe0ccc1-7A0A-4B0C-8A1A-6FF2997DA3A6")
        j = 1
        ble.run(13)
    end
    if name == "LYWSD02"
        ble.set_svc("ebe0ccb0-7A0A-4B0C-8A1A-6FF2997DA3A6")
        ble.set_chr("ebe0ccc1-7A0A-4B0C-8A1A-6FF2997DA3A6")
        j = 2
        ble.run(11)
    end
    if name == "FLORA"
        ble.set_svc("00001204-0000-1000-8000-00805f9b34fb")
        ble.set_chr("00001a02-0000-1000-8000-00805f9b34fb")
        j = 3
        ble.run(11)
    end
    if name == "CGD1"
        ble.set_svc("180F")
        ble.set_chr("2A19")
        j = 4
        ble.run(11)
    end
end

