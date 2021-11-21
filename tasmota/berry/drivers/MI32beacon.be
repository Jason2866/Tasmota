ble = BLE()
buf = bytes(-62)
def cb()
import string
var svc = buf.get(6,2)
var rssi = 255 - buf.get(8,1)
var msg = string.format("{\"MAC\":%02X%02X%02X%02X%02X%02X,\"SVC\":%X,\"RSSI\":-%u}",
              buf[0],buf[1],buf[2],buf[3],buf[4],buf[5],svc,rssi)
print(msg)
end 
cbp = tasmota.gen_cb(cb)
ble.adv_cb(cbp,buf)

