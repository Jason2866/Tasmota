import crypto
e = crypto.EC_C25519()
secret_key = bytes("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
message = bytes()
public_key = bytes("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
signature = e.sign(message, secret_key, public_key)
assert(signature == bytes("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"))

# https://boringssl.googlesource.com/boringssl/+/2e2a226ac9201ac411a84b5e79ac3a7333d8e1c9/crypto/cipher_extra/test/chacha20_poly1305_tests.txt
import crypto
c = crypto.CHACHA()
key = bytes("808182838485868788898a8b8c8d8e8f909192939495969798999a9b9c9d9e9f")
iv =bytes("070000004041424344454647")
aad= bytes("50515253c0c1c2c3c4c5c6c7")
_msg = "Ladies and Gentlemen of the class of '99: If I could offer you only one tip for the future, sunscreen would be it."
msg = bytes().fromstring(_msg)
ct = bytes("d31a8d34648e60db7b86afbc53ef7ec2a4aded51296e08fea9e2b5a736ee62d63dbea45e8ca9671282fafb69da92728b1a71de0a9e060b2905d6a5b67ecd3b3692ddbd7f2d778b8c9803aee328091b58fab324e4fad675945585808b4831d7bc3ff4def08e4b7a9de576d26586cec64b6116")
tag = bytes("1ae10b594f09e26a7e902ecbd0600691")
_tag = bytes(-16)
c.encrypt1(key,iv,msg,_tag,aad)
assert(_tag == tag)

