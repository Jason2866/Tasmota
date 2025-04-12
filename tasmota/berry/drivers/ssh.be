#- Simple SSH server in Berry by Christian Baars
#  this is not working for now
-#

class BIN_PACKET
    var packet_length, padding_length, payload, payload_length, padding, mac, mac_length
    var complete

    def init(buf)
        self.packet_length = buf.geti(0,-4)
        self.padding_length = buf[4]
        self.payload_length = self.packet_length - self.padding_length - 1
        # print(self.packet_length, self.padding_length, self.payload_length)
        self.payload = buf[5 .. 5 + self.payload_length - 1]
        self.padding = buf[5 + self.payload_length .. 5 + self.payload_length + self.padding_length - 1]
        self.mac = buf[5 + self.payload_length + self.padding_length .. ]
        if size(buf) == self.packet_length + 4
            self.complete = true
        else
            self.complete = false
        end
    end

    def append(buf)
        var payload_left = self.payload_length - size(self.payload)
        self.payload .. buf[0..payload_left - 1]
        # print(self.payload, size(self.payload))
        if size(self.payload) == self.payload_length
            self.complete = true
        end
    end

    def create(payload)
        import crypto
        var paylength = size(payload)
        var padlength = 16-((5 + paylength)%16)
        if padlength < 5
            padlength += 16
        end
        # print("padlength", padlength)
        var padding = crypto.random(padlength)
        var bin = bytes(256)
        bin.add(1 + paylength + padlength, -4)
        bin .. padlength
        bin .. payload
        bin .. padding
        return bin
    end
end


class SSH_MSG
    static KEXINIT = 20
    static NEWKEYS = 21
    static KEXDH_INIT = 30
    static KEX_ECDH_REPLY = 31
end

class HANDSHAKE
    var state, bin_packet
    var kexinit_client
    var kexinit_own
    static banner = "  / \\    Secure Wireless Serial Interface: ID %u\n"
                    "/ /|\\ \\  SSH Terminal Server\n"
                    "  \\_/    Copyright (C) 2025 Tasmota\n"

    var   V_C # client's identification string (CR and LF excluded)
    static V_S = "SSH-2.0-TasmotaSSH_0.1" # server's identification string (CR and LF excluded)
    var   I_C # payload of the client's SSH_MSG_KEXINIT
    var   I_S # payload of the server's SSH_MSG_KEXINIT
    var   K_S # server's public host key
    var   Q_C # client's ephemeral public key octet string
    var   Q_S # server's ephemeral public key octet string
    var   K   # shared secret

    var   E_S_S # server's ephemeral secret key bytes
    var   E_S_H # server's secret host key bytes


    def init()
        self.state = 0
        self.K_S = (bytes().fromb64("AAAAC3NzaC1lZDI1NTE5AAAAIGgTQ3jxXinPuu/JJltK1gRIT1OYUe4WOqu/sszMgI5A"))#[-32..]
        self.E_S_H = bytes("a60c6c7107be5da01ba7f7bc6a08e1d0faa27e1db9327514823fdac5f8e750dd")
    end

    def get_name_list(buffer, index, length)
        import string
        if length == 0 || length > (size(buffer) - 5)
            return nil
        end
        var names = buffer[index + 4 .. index + 3 + length]
        print(names.asstring())
        return string.split(names.asstring(),",")
    end

    def name_list_length(buf)
        return buf.geti(0,-4)
    end

    def add_string(buf, str_entry)
        buf.add(size(str_entry),-4)
        buf .. str_entry
    end

    def add_mpint(buf, str_entry)
        if str_entry[0] & 128 != 0
            str_entry = bytes("00") + str_entry
        end
        buf.add(size(str_entry),-4)
        buf .. str_entry
    end

    def kexinit_from_client()
        var buf = self.bin_packet.payload
        var k = {}
        k["cookie"] = buf[1..16].tohex()
        var next_index = 17
        var next_length = self.name_list_length(buf[next_index..])
        k["kex_algorithms"] = self.get_name_list(buf, next_index, next_length)
        next_index += next_length + 4
        next_length = self.name_list_length(buf[next_index..])
        k["server_host_key_algorithms"] = self.get_name_list(buf, next_index, next_length)
        next_index += next_length + 4
        next_length = self.name_list_length(buf[next_index..])
        k["encryption_algorithms_client_to_server"] = self.get_name_list(buf, next_index, next_length)
        next_index += next_length + 4
        next_length = self.name_list_length(buf[next_index..])
        k["encryption_algorithms_server_to_client"] = self.get_name_list(buf, next_index, next_length)
        next_index += next_length + 4
        next_length = self.name_list_length(buf[next_index..])
        k["mac_algorithms_client_to_server"] = self.get_name_list(buf, next_index, next_length)
        next_index += next_length + 4
        next_length = self.name_list_length(buf[next_index..])
        k["mac_algorithms_server_to_client"] = self.get_name_list(buf, next_index, next_length)
        next_index += next_length + 4
        next_length = self.name_list_length(buf[next_index..])
        k["compression_algorithms_client_to_server"] = self.get_name_list(buf, next_index, next_length)
        next_index += next_length + 4
        next_length = self.name_list_length(buf[next_index..])
        k["compression_algorithms_server_to_client"] = self.get_name_list(buf, next_index, next_length)
        next_index += next_length + 4
        next_length = self.name_list_length(buf[next_index..])
        k["languages_client_to_server"] = self.get_name_list(buf, next_index, next_length)
        next_index += next_length + 4
        next_length = self.name_list_length(buf[next_index..])
        k["languages_server_to_client"] = self.get_name_list(buf, next_index, next_length)
        self.kexinit_client = k
        # print("SSH: Kexinit from client = ",k)
    end

    def kexinit_to_client()
        import crypto
        var	cookie  = crypto.random(16)
        var	kex_algorithms = "curve25519-sha256@libssh.org"
        var	server_host_key_algorithms = "ssh-ed25519" # "-cert-v01@openssh.com"
        var	encryption_algorithms_client_to_server = "chacha20-poly1305@openssh.com"
        var	encryption_algorithms_server_to_client = "chacha20-poly1305@openssh.com"
        var	mac_algorithms_client_to_server = "hmac-sha2-256"
        var	mac_algorithms_server_to_client = "hmac-sha2-256"
        var compression_algorithms_client_to_server = "none"
        var compression_algorithms_server_to_client = "none"
        var	languages_client_to_server = ""
        var languages_server_to_client = ""

        var payload = bytes(256)
        payload .. SSH_MSG.KEXINIT
        payload .. cookie
        self.add_string(payload,kex_algorithms)
        self.add_string(payload,server_host_key_algorithms)
        self.add_string(payload,encryption_algorithms_client_to_server)
        self.add_string(payload,encryption_algorithms_server_to_client)
        self.add_string(payload,mac_algorithms_client_to_server)
        self.add_string(payload,mac_algorithms_server_to_client)
        self.add_string(payload,compression_algorithms_client_to_server)
        self.add_string(payload,compression_algorithms_client_to_server)
        self.add_string(payload,languages_client_to_server)
        self.add_string(payload,languages_server_to_client)
        payload .. 0 # false
        payload.add(0,-4) # reserved
        self.I_S = payload.copy()
        return self.bin_packet.create(payload)
    end

    def create_KEX_ECDH_REPLY()
        import crypto
        var hash = bytes(2048)
        self.add_string(hash, self.V_C)
        self.add_string(hash, self.V_S)
        self.add_string(hash, self.I_C)
        self.add_string(hash, self.I_S)
        self.add_string(hash, self.K_S)
        self.add_string(hash, self.Q_C)
        self.add_string(hash, self.Q_S)
        self.add_mpint(hash, self.K)

        # print("name client",self.V_C)
        # print("name server",self.V_S)
        # print("kex init client",self.I_C)
        # print("kex init server",self.I_S)
        # print("server key bytes K_S",self.K_S)
        # print("ephemeral client", self.Q_C)
        # print("ephemeral server",self.Q_S)
        # print("shared secret K", self.K,size(self.K))

        var sha256 = crypto.SHA256()
        sha256.update(hash)
        var H = sha256.out()

        var eddsa25519 = crypto.EC_C25519()
        var SIG = eddsa25519.sign(H,self.E_S_H,self.K_S[-32..])
        print(SIG)

        var payload = bytes(256)
        payload .. SSH_MSG.KEX_ECDH_REPLY
        # print(self.K_S, size(self.K_S), self.Q_S, size(self.Q_S), H, size(H) )
        self.add_string(payload, self.K_S)
        self.add_string(payload, self.Q_S)
        var HS = bytes(128)
            self.add_string(HS, "ssh-ed25519")
            self.add_string(HS,SIG)
        self.add_string(payload, HS)
        return self.bin_packet.create(payload)
    end

    def create_ephemeral(payload)
        log("SSH: will create ephemeral keys",2)
        import crypto
        self.E_S_S = crypto.random(32)
        self.Q_S = (crypto.EC_C25519().public_key(self.E_S_S))
        self.Q_C = payload[5..]
        self.K = (crypto.EC_C25519().shared_key(self.E_S_S, self.Q_C))
        print(self.E_S_S, self.Q_S, self.K)
        return self.create_KEX_ECDH_REPLY()
    end

    def send_NEWKEYS()
        log("SSH: confirm to be ready for new keys",2)
        var payload = bytes(-1)
        payload[0] = SSH_MSG.NEWKEYS
        return self.bin_packet.create(payload)
    end

    def process(buf)
        # log(buf)
        # print(buf[0],size(buf) )
        var response = bytes()
        if self.state == 0
            self.state = 1
            self.V_C  = buf[0..-3].asstring() # strip LF
            return f"{self.V_S}\r\n"
        elif self.state == 1
            if self.bin_packet
                self.bin_packet.append(buf)
            else
                self.bin_packet = BIN_PACKET(buf)
            end
            if self.bin_packet.complete == true
                print(self.bin_packet.payload, self.bin_packet.payload_length)
                if self.bin_packet.payload[0] == SSH_MSG.KEXINIT
                    self.I_C = self.bin_packet.payload.copy()
                    self.kexinit_from_client()
                    response = self.kexinit_to_client()
                elif self.bin_packet.payload[0] == SSH_MSG.KEXDH_INIT
                    response = self.create_ephemeral(self.bin_packet.payload)
                elif self.bin_packet.payload[0] == SSH_MSG.NEWKEYS
                    response = self.send_NEWKEYS()
                    self.state = 2
                else
                    print("SSH: unknown packet type", self.bin_packet.payload[0])
                end
                self.bin_packet = nil
            end
            return response
        elif self.state == 2

        end
        log("SSH: unknown packet")
        return bytes("01")
    end
end

class SSH : Driver

    var connection, server, client, data_server, data_client, data_ip
    var handshake
    var dir, dir_list, dir_pos
    var file, file_size, file_rename, retries, chunk_size
    var binary_mode, active_ip, active_port, user_input
    var data_buf, data_ptr, fast_loop, data_op
    static port = 22

    static user = "user"
    static password = "pass"

    def init()
        self.server = tcpserver(self.port) # connection for control data
        self.connection = false
        self.data_ip = tasmota.wifi()['ip']
        # self.dir = PATH()
        # self.readDir()
        self.data_ptr = 0
        # self.active_port = nil
        tasmota.add_driver(self)
        log(f"SSH: init server on port {self.port}",1)
    end

    def deinit()
        self.server.deinit()
        self.data_server.deinit()
        tasmota.remove_driver(self)
    end

    def every_50ms()
        if self.connection == true
            self.loop()
        elif self.server.hasclient()
            self.client = self.server.acceptasync()
            self.handshake = HANDSHAKE()
            self.connection = true
            self.pubClientInfo()
        else
            self.handshake = nil
            self.connection = false
        end
    end

    def every_second()
        if self.client && self.connection != false
            if self.client.connected() == false
                self.pubClientInfo()
                self.connection = false
                self.abortDataOp()
            end
        end
    end

    def pubClientInfo()
        import mqtt
        var payload = self.client.info().tostring()
        mqtt.publish("SSH",format("{'server':%s}", payload))
    end

    def loop()
        if self.connection == true
            self.handleConnection()
        end
    end

    def abortDataOp()
        if self.data_op == "d"
            self.finishDownload(true)
        elif self.data_op == "u"
            self.finishUpload(true)
        elif self.data_op == "dir"
            self.finishUpload(false)
        end
    end

    def download() # ESP -> client
        self.data_buf..self.file.readbytes(self.chunk_size)
        if size(self.data_buf) == 0
            self.retries -= 1
            if self.retries > 0
                return
            end
        else
            var written = self.data_client.write(self.data_buf)
            self.data_buf.clear()
            self.data_ptr += written
            if self.data_ptr < self.file_size
                self.file.seek(self.data_ptr)
                if self.retries > 0
                    return
                end
            end
        end
        self.finishDownload()
    end

    def finishDownload(error)
        self.data_client.close()
        tasmota.remove_fast_loop(self.fast_loop)
        self.file.close()
        if error
            self.sendResponse(f"426 Connection closed; transfer aborted after {self.data_ptr} bytes.")
        else
            self.sendResponse(f"250 download done with {self.data_ptr} bytes.")
        end
        self.data_op = nil
        tasmota.gc()
    end

    def upload() # client -> ESP
        self.data_buf..self.data_client.readbytes()

        if size(self.data_buf) > 0
            self.file.write(self.data_buf)
            self.data_ptr += size(self.data_buf)
            self.data_buf.clear()
        else
            log(f"SSH: {self.retries} retries",4)
            self.retries -= 1
            if self.retries > 0
                return
            end
            self.finishUpload()
        end
    end

    def finishUpload(error)
        self.data_client.close()
        tasmota.remove_fast_loop(self.fast_loop)
        self.file.close()
        if error
            self.sendResponse(f"426 Connection closed; transfer after {self.data_ptr} bytes")
        else
            self.sendResponse(f"250 upload done with {self.data_ptr} bytes")
        end
        self.data_op = nil
        tasmota.gc()
    end

    def transferDir(mode)
        import path
        var sz, date, isdir
        var i = self.dir_list[self.dir_pos]
        var url = f"{self.dir.get_url()}{i}"
        isdir = path.isdir(url)
        if isdir == false
            var f = open(url,"r")
            sz = f.size()
            f.close()
            date = path.last_modified(url)
        end
        if self.data_client.connected()
            var dir = ""
            if mode == "MLSD"
                if  isdir
                    dir = "Type=dir;Perm=edlmp; "
                else
                    date = tasmota.time_dump(date)
                    var y = str(date['year'])
                    var m = f"{date['month']:02s}"
                    var d = f"{date['day']:02s}"
                    var h = f"{date['hour']:02s}"
                    var min = f"{date['min']:02s}"
                    var sec = f"{date['sec']:02s}"
                    var modif =f"{y}{m}{d}{h}{min}{sec}"
                    dir = f"Type=file;Perm=rwd;Modify={modif};Size={sz}; "
                end
            elif mode == "LIST"
                var d = "-"
                if isdir
                    d = "d"
                    date = ""
                    sz = ""
                else
                    date = tasmota.strftime("%b %d %H:%M", date)
                end
                dir = f"{d}rw-------  1 all all{sz:14s} {date} "

            elif mode == "NLST"
                dir=self.dir.get_url()
            end
            var entry = f"{dir}{i}"
            log(entry,4)
            self.data_client.write(entry + "\r\n")
            self.dir_pos += 1
        else
            self.finishTransferDir(false)
        end
        if self.dir_pos < size(self.dir_list)
            return
        end
        self.finishTransferDir(true)
    end

    def finishTransferDir(success)
        self.data_client.close()
        if success
            var n = size(self.dir_list)
            self.sendResponse(f"226 {n} files in {self.dir.get_url()}")
        else
            self.sendResponse("426 Transfer aborted")
        end
        self.data_op = nil
        tasmota.remove_fast_loop(self.fast_loop)
        tasmota.gc()
    end

    def readDir()
        import path
        self.dir_list = path.listdir(self.dir.get_url())
    end

    def openFile(name,mode)
        import path
        var url = f"{self.dir.get_url()}{name}"
        if path.isdir(url) == true
            log(f"SSH: {url} is a folder",2)
            return false
        end
        if mode == "r"
            if path.exists(url) != true
                log(f"SSH: {url} not found",2)
                return false
            end
        end
        log(f"SSH: Open file {url} in {mode} mode",3)
        self.file = open(f"{url}",mode)
        if mode == "a"
            if self.data_ptr != 0
                log(f"SSH: Appending file {url} at position {self.data_ptr}",3)
                if self.data_ptr != self.file.size()
                    log(f"SSH: !!! resume position of {self.data_ptr} != file size of {self.file.size()} !!!",2)
                end
            end
        end
        return true
    end

    def close()
        self.sendResponse("221 Closing connection")
        self.connection = false
    end


    def deinitConnectServer()
        if self.data_server != nil
            self.data_server.close()
            self.data_server.deinit()
            self.data_server = nil
            log("SSH: Delete server",2)
        end
    end

    def sendResponse(resp)
        self.client.write(resp)
        log(f"SSH: >>> {resp} _ {size(resp)} bytes",2)
    end

    def handleConnection() # main loop for incoming commands
        var response
        var d = self.client.readbytes()
        if size(d) == 0 return end
        log(f"SSH: <<< {d} _ {size(d)} bytes",2)
        if self.handshake
            response = self.handshake.process(d)
            if response != ""
                self.sendResponse(response)
            end
        end
    end
end

var ssh =  SSH()
