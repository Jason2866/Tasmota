ble = BLE()
cbuf = bytes(-64)
def cb()
end 
cbp = tasmota.gen_cb(cb)
ble.conn_cb(cbp,cbuf)

