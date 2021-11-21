ble = BLE()
buf = bytes(-64)
def cb()
end 
cbp = tasmota.gen_cb(cb)
ble.conn_cb(cbp,buf)

