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
    static DISCONNECT = 1
    static SERVICE_REQUEST = 5
    static SERVICE_ACCEPT = 6
    static KEXINIT = 20
    static NEWKEYS = 21
    static KEXDH_INIT = 30
    static KEX_ECDH_REPLY = 31
    static USERAUTH_REQUEST = 50
    static USERAUTH_FAILURE = 51
    static USERAUTH_SUCCESS = 52
    static USERAUTH_BANNER = 53

    static def get_name_list(buffer, index, length)
        import string
        if length == 0 || length > (size(buffer) - 5)
            return nil
        end
        var names = buffer[index + 4 .. index + 3 + length]
        print(names.asstring())
        return string.split(names.asstring(),",")
    end

    static def get_string(buffer, index, length)
        import string
        if length == 0 || length > (size(buffer) - 5)
            return nil
        end
        var name = buffer[index + 4 .. index + 3 + length]
        return name.asstring()
    end

    static def get_item_length(buf)
        return buf.geti(0,-4)
    end

    static def add_string(buf, str_entry)
        buf.add(size(str_entry),-4)
        buf .. str_entry
    end

    static def add_mpint(buf, entry)
        if entry[0] & 128 != 0
            entry = bytes("00") + entry
        end
        buf.add(size(entry),-4)
        buf .. entry
    end

    static def make_mpint(buf)
        var mpint = bytes(size(buf) + 5)
        if buf[0] & 128 != 0
            buf = bytes("00") + buf
        end
        mpint.add(size(buf),-4)
        mpint .. buf
        return mpint
    end
end

class HANDSHAKE
    var state, bin_packet, session
    var kexinit_client
    var kexinit_own

    var   V_C # client's identification string (CR and LF excluded)
    static V_S = "SSH-2.0-TasmotaSSH_0.1" # server's identification string (CR and LF excluded)
    var   I_C # payload of the client's SSH_MSG_KEXINIT
    var   I_S # payload of the server's SSH_MSG_KEXINIT
    var   K_S # server's public host key
    var   Q_C # client's ephemeral public key octet string
    var   Q_S # server's ephemeral public key octet string
    var   K   # shared secret

    var   H   # hash of above

    var   E_S_S # server's ephemeral secret key bytes
    var   E_S_H # server's secret host key bytes


    def init(session)
        self.state = 0
        self.K_S = (bytes().fromb64("AAAAC3NzaC1lZDI1NTE5AAAAIGgTQ3jxXinPuu/JJltK1gRIT1OYUe4WOqu/sszMgI5A"))#[-32..]
        self.E_S_H = bytes("a60c6c7107be5da01ba7f7bc6a08e1d0faa27e1db9327514823fdac5f8e750dd")
        self.session = session
    end


    # def kexinit_from_client()
    #     var buf = self.bin_packet.payload
    #     var k = {}
    #     k["cookie"] = buf[1..16].tohex()
    #     var next_index = 17
    #     var next_length = self.name_list_length(buf[next_index..])
    #     k["kex_algorithms"] = self.get_name_list(buf, next_index, next_length)
    #     next_index += next_length + 4
    #     next_length = self.name_list_length(buf[next_index..])
    #     k["server_host_key_algorithms"] = self.get_name_list(buf, next_index, next_length)
    #     next_index += next_length + 4
    #     next_length = self.name_list_length(buf[next_index..])
    #     k["encryption_algorithms_client_to_server"] = self.get_name_list(buf, next_index, next_length)
    #     next_index += next_length + 4
    #     next_length = self.name_list_length(buf[next_index..])
    #     k["encryption_algorithms_server_to_client"] = self.get_name_list(buf, next_index, next_length)
    #     next_index += next_length + 4
    #     next_length = self.name_list_length(buf[next_index..])
    #     k["mac_algorithms_client_to_server"] = self.get_name_list(buf, next_index, next_length)
    #     next_index += next_length + 4
    #     next_length = self.name_list_length(buf[next_index..])
    #     k["mac_algorithms_server_to_client"] = self.get_name_list(buf, next_index, next_length)
    #     next_index += next_length + 4
    #     next_length = self.name_list_length(buf[next_index..])
    #     k["compression_algorithms_client_to_server"] = self.get_name_list(buf, next_index, next_length)
    #     next_index += next_length + 4
    #     next_length = self.name_list_length(buf[next_index..])
    #     k["compression_algorithms_server_to_client"] = self.get_name_list(buf, next_index, next_length)
    #     next_index += next_length + 4
    #     next_length = self.name_list_length(buf[next_index..])
    #     k["languages_client_to_server"] = self.get_name_list(buf, next_index, next_length)
    #     next_index += next_length + 4
    #     next_length = self.name_list_length(buf[next_index..])
    #     k["languages_server_to_client"] = self.get_name_list(buf, next_index, next_length)
    #     self.kexinit_client = k
    #     # print("SSH: Kexinit from client = ",k)
    # end

    def kexinit_to_client()
        import crypto
        var	cookie  = crypto.random(16)
        var	kex_algorithms = "curve25519-sha256,kex-strict-s-v00@openssh.com,kex-strict-s" #curve25519-sha256@libssh.org
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
        SSH_MSG.add_string(payload,kex_algorithms)
        SSH_MSG.add_string(payload,server_host_key_algorithms)
        SSH_MSG.add_string(payload,encryption_algorithms_client_to_server)
        SSH_MSG.add_string(payload,encryption_algorithms_server_to_client)
        SSH_MSG.add_string(payload,mac_algorithms_client_to_server)
        SSH_MSG.add_string(payload,mac_algorithms_server_to_client)
        SSH_MSG.add_string(payload,compression_algorithms_client_to_server)
        SSH_MSG.add_string(payload,compression_algorithms_client_to_server)
        SSH_MSG.add_string(payload,languages_client_to_server)
        SSH_MSG.add_string(payload,languages_server_to_client)
        payload .. 0 # false - first_kex_follows
        payload.add(0,-4) # reserved
        self.I_S = payload.copy()
        return self.bin_packet.create(payload)
    end

    def create_KEX_ECDH_REPLY()
        import crypto
        var hash = bytes(2048)
        SSH_MSG.add_string(hash, self.V_C)
        SSH_MSG.add_string(hash, self.V_S)
        SSH_MSG.add_string(hash, self.I_C)
        SSH_MSG.add_string(hash, self.I_S)
        SSH_MSG.add_string(hash, self.K_S)
        SSH_MSG.add_string(hash, self.Q_C)
        SSH_MSG.add_string(hash, self.Q_S)
        SSH_MSG.add_mpint(hash, self.K)

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
        self.H = sha256.out()

        var eddsa25519 = crypto.EC_C25519()
        var SIG = eddsa25519.sign(self.H,self.E_S_H,self.K_S[-32..])
        print(SIG)

        var payload = bytes(256)
        payload .. SSH_MSG.KEX_ECDH_REPLY
        # print(self.K_S, size(self.K_S), self.Q_S, size(self.Q_S), H, size(H) )
        SSH_MSG.add_string(payload, self.K_S)
        SSH_MSG.add_string(payload, self.Q_S)
        var HS = bytes(128)
            SSH_MSG.add_string(HS, "ssh-ed25519")
            SSH_MSG.add_string(HS,SIG)
            SSH_MSG.add_string(payload, HS)
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
        self.session.prepare(self.K,self.H)
        return self.bin_packet.create(payload)
    end

    def process(buf)
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
                    # self.kexinit_from_client()
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
            else
                self.session.seq_nr_rx -= 1
            end
            return response
        elif self.state == 2

        end
        log("SSH: unknown packet")
        return bytes("01")
    end
end

class SESSION
    var up
    var H, K, ID
    var bin_packet
    var KEY_C_S_main, KEY_S_C_main, KEY_C_S_header, KEY_S_C_header
    var seq_nr_rx, seq_nr_tx
    static banner = "  / \\    Secure Wireless Serial Interface: ID %u\n"
                    "/ /|\\ \\  SSH Terminal Server\n"
                    "  \\_/    Copyright (C) 2025 Tasmota\n"

    def init()
        self.up = false
        self.seq_nr_rx = -1
        self.seq_nr_tx = -1
    end

    def handle_SR()
        var name = SSH_MSG.get_string(self.bin_packet.payload, 1, SSH_MSG.get_item_length(self.bin_packet.payload[1..]))
        return name
    end

    def process(data)
        var r = bytes()
        var d = self.decrypt(data)
        print(d)
        if self.bin_packet
            self.bin_packet.append(d)
        else
            self.bin_packet = BIN_PACKET(d)
        end
        if self.bin_packet.complete == true
            if self.bin_packet.payload[0] == SSH_MSG.SERVICE_REQUEST
                return self.handle_SR()
            end
        end
        return r
    end

    def decrypt(packet)
        import crypto
        var c = crypto.CHACHA20_POLY1305()
        var length = packet[0..3].copy()
        var iv = bytes(-12)
        iv.seti(8,self.seq_nr_rx,-4)
        c.chacha_run(self.KEY_C_S_header,iv,0,length) # use upper 32 bytes of key material
        var _tag = packet[-16..].copy()
        var data = packet[4..-17].copy()
        c.poly_decrypt1(self.KEY_C_S_main, iv, data , _tag) # lower bytes of key for packet
        return length + data
    end

    def generate_keys(K,H,third,id)
        import crypto
        var sha256 = crypto.SHA256()
        sha256.update(SSH_MSG.make_mpint(K))
        sha256.update(H)
        if classof(third) != bytes
            sha256.update(bytes().fromstring(third))
        else
            sha256.update(third)
        end
        if id != nil
            sha256.update(id)
        end
        return sha256.out()
    end

    def prepare(K,H)
        self.K = K
        self.H = H
        self.ID = H.copy()
        self.KEY_C_S_main = self.generate_keys(K,H,"C",H)
        self.KEY_C_S_header = self.generate_keys(K,H,self.KEY_C_S_main)
        self.KEY_S_C_main = self.generate_keys(K,H,"D",H)
        self.KEY_S_C_header = self.generate_keys(K,H,self.KEY_S_C_main)
        # print("Did create session keys:")
        # print(self.KEY_C_S_main, self.KEY_C_S_header, self.KEY_S_C_main, self.KEY_S_C_header)
        self.up = true
        self.seq_nr_rx = -1 # reset to handle Terrapin attack
        self.seq_nr_tx = -1
    end
end

class SSH : Driver

    var connection, server, client, data_server, data_client, data_ip
    var handshake, session
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
            self.session = SESSION()
            self.handshake = HANDSHAKE(self.session)
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
                #self.abortDataOp()
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

    def deinitConnectServer()
        if self.data_server != nil
            self.data_server.close()
            self.data_server.deinit()
            self.data_server = nil
            log("SSH: Delete server",2)
        end
    end

    def sendResponse(resp)
        self.session.seq_nr_tx += 1
        self.client.write(resp)
        log(f"SSH: {self.session.seq_nr_tx} >>> {resp} _ {size(resp)} bytes",2)
    end

    def handleConnection() # main loop for incoming commands
        var response
        var d = self.client.readbytes()
        if size(d) == 0 return end
        self.session.seq_nr_rx += 1
        log(f"SSH: {self.session.seq_nr_rx} <<< {d} _ {size(d)} bytes",2)
        if self.session.up == true
            response = self.session.process(d)
            if response != ""
                self.sendResponse(response)
            end
        elif self.handshake
            response = self.handshake.process(d)
            if response != ""
                self.sendResponse(response)
                if response[5] == SSH_MSG.NEWKEYS self.handshake = nil end
            end
        end
    end
end

var ssh =  SSH()
