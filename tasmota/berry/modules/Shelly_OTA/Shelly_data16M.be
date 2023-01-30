
import partition_core
import flash
var p = partition_core.Partition()
var err = 0

var aux = p.slots[-2]     # 6 emdata           FS               01 82 00510000 00aec000
if (aux.sz != 0xaec000 && aux.label != "aux")
    print("BRY: Unexpected length of",aux.label,aux.sz," - should be 'aux' with size of",0xC000)
    err += 1
else
    var f = open('aux.bin', 'w')
    for i:0..((0xc000/0x1000)-1)
        var buf = flash.read(0x510000 + (0x1000 * i), 0x1000)
        f.write(buf)
    end
    f.close()
end

var shelly = p.slots[-1] # 7 shelly           Unknown data     01 88 00ffc000 00004000
if (shelly.sz != 0x4000 && shelly.label != "shelly")
    print("BRY: Unexpected length of",shelly.label,shelly.sz," - should be 'shelly' with size of",0x4000)
    err += 1
else
    var f = open('shelly.bin', 'w')
    for i:0..((0x4000/0x1000)-1)
        var buf = flash.read(0xffc000 + (0x1000 * i), 0x1000)
        f.write(buf)
    end
    f.close()
end
if err == 0
    print("BRY: Did save calibration data to 'aux.bin' and cloud key data to 'shelly.bin'")
end
