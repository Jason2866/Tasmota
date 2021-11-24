#-------------------------------------------------------------
 - Removed Commands as Berry functions
 -------------------------------------------------------------#
 
ble = BLE()
m = MI32()

cbuf = bytes(-64)
def cb()
print(cbuf)
end

cbp = tasmota.gen_cb(cb)
ble.conn_cb(cbp,cbuf)

def SetMACfromSlot(slot)
    if slot+1>m.devices()
        return "out of bounds"
    end
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
    ble.run(12)
end

def MI32Unit(slot,unit)
    SetMACfromSlot(slot)
    ble.set_svc("EBE0CCB0-7A0A-4B0C-8A1A-6FF2997DA3A6")
    ble.set_chr("EBE0CCBE-7A0A-4B0C-8A1A-6FF2997DA3A6")
    cbuf[0] = 1
    cbuf[1] = unit
    ble.run(12)
end

