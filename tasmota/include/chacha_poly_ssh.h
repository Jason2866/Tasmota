/*
chacha-merged.c version 20080118
D. J. Bernstein
Public domain.
*/

// #include <string.h>
// #include <stdlib.h>

struct chacha_ctx {
	uint32_t input[16];
};

#define CHACHA_MINKEYLEN 	16
#define CHACHA_NONCELEN		8
#define CHACHA_CTRLEN		8
#define CHACHA_STATELEN		(CHACHA_NONCELEN+CHACHA_CTRLEN)
#define CHACHA_BLOCKLEN		64

#define SSH_SIZE_CHACHA256_KEY	(2 * 32)
#define SSH_KEYIDX_ENC       1
#define POLY1305_TAGLEN      16
#define POLY1305_KEYLEN      32

// typedef unsigned char uint8_t;
// typedef unsigned int uint32_t;

typedef struct chacha_ctx chacha_ctx;

struct ssh_keys {
	/* 3 == SSH_KEYIDX_IV (len=4), SSH_KEYIDX_ENC, SSH_KEYIDX_INTEG */
	uint8_t key[3][SSH_SIZE_CHACHA256_KEY];

	/* opaque allocation made when cipher activated */
	void *cipher;

	uint8_t MAC_length;
	uint8_t padding_alignment; /* block size */
	uint8_t valid:1;
	uint8_t full_length:1;
};

void
ssh_explicit_bzero(void *p, size_t len)
{
	volatile uint8_t *vp = (uint8_t*)p;

	while (len--)
		*vp++ = 0;
}


#define PEEK_U32(p) \
        (((uint32_t)(((const uint8_t *)(p))[0]) << 24) | \
         ((uint32_t)(((const uint8_t *)(p))[1]) << 16) | \
         ((uint32_t)(((const uint8_t *)(p))[2]) << 8) | \
          (uint32_t)(((const uint8_t *)(p))[3]))

#define POKE_U64(p, v) \
        do { \
                const uint64_t __v = (v); \
                ((uint8_t *)(p))[0] = (uint8_t)((__v >> 56) & 0xff); \
                ((uint8_t *)(p))[1] = (uint8_t)((__v >> 48) & 0xff); \
                ((uint8_t *)(p))[2] = (uint8_t)((__v >> 40) & 0xff); \
                ((uint8_t *)(p))[3] = (uint8_t)((__v >> 32) & 0xff); \
                ((uint8_t *)(p))[4] = (uint8_t)((__v >> 24) & 0xff); \
                ((uint8_t *)(p))[5] = (uint8_t)((__v >> 16) & 0xff); \
                ((uint8_t *)(p))[6] = (uint8_t)((__v >> 8) & 0xff); \
                ((uint8_t *)(p))[7] = (uint8_t)(__v & 0xff); \
        } while (0)

#define U8C(v) (v##U)
#define U32C(v) (v##U)

#define U8V(v) ((uint8_t)((v) & U8C(0xFF)))
#define U32V(v) ((uint32_t)(v) & U32C(0xFFFFFFFF))

#define ROTL32(v, n) \
  (U32V((v) << (n)) | ((v) >> (32 - (n))))

#define U8TO32_LITTLE(p) \
  (((uint32_t)((p)[0])      ) | \
   ((uint32_t)((p)[1]) <<  8) | \
   ((uint32_t)((p)[2]) << 16) | \
   ((uint32_t)((p)[3]) << 24))

#define U32TO8_LITTLE(p, v) \
  do { \
    (p)[0] = U8V((v)      ); \
    (p)[1] = U8V((v) >>  8); \
    (p)[2] = U8V((v) >> 16); \
    (p)[3] = U8V((v) >> 24); \
  } while (0)

#define ROTATE(v,c) (ROTL32(v,c))
#define XOR(v,w) ((v) ^ (w))
#define PLUS(v,w) (U32V((v) + (w)))
#define PLUSONE(v) (PLUS((v),1))

#define QUARTERROUND(a,b,c,d) \
  a = PLUS(a,b); d = ROTATE(XOR(d,a),16); \
  c = PLUS(c,d); b = ROTATE(XOR(b,c),12); \
  a = PLUS(a,b); d = ROTATE(XOR(d,a), 8); \
  c = PLUS(c,d); b = ROTATE(XOR(b,c), 7);

static const char sigma[16] = {0x65, 0x78, 0x70, 0x61, 0x6E, 0x64, 0x20, 0x33, 0x32, 0x2D, 0x62, 0x79, 0x74, 0x65, 0x20, 0x6B}; //"expand 32-byte k";
static const char tau[16] = {0x65, 0x78, 0x70, 0x61, 0x6E, 0x64, 0x20, 0x31, 0x36, 0x2D, 0x62, 0x79, 0x74, 0x65, 0x20, 0x6B};//"expand 16-byte k";

#define mul32x32_64(a,b) ((uint64_t)(a) * (b))

#define U8TO32_LE(p) \
	(((uint32_t)((p)[0])) | \
	 ((uint32_t)((p)[1]) <<  8) | \
	 ((uint32_t)((p)[2]) << 16) | \
	 ((uint32_t)((p)[3]) << 24))

#define U32TO8_LE(p, v) \
	do { \
		(p)[0] = (uint8_t)((v)); \
		(p)[1] = (uint8_t)((v) >>  8); \
		(p)[2] = (uint8_t)((v) >> 16); \
		(p)[3] = (uint8_t)((v) >> 24); \
	} while (0)

void
poly1305_auth(char out[POLY1305_TAGLEN],
	      const char *m, size_t inlen,
	      const char key[POLY1305_KEYLEN])
{
	uint32_t t0,t1,t2,t3;
	uint32_t h0,h1,h2,h3,h4;
	uint32_t r0,r1,r2,r3,r4;
	uint32_t s1,s2,s3,s4;
	uint32_t b, nb;
	size_t j;
	uint64_t t[5];
	uint64_t f0,f1,f2,f3;
	uint32_t g0,g1,g2,g3,g4;
	uint64_t c;
	unsigned char mp[16];

	/* clamp key */
	t0 = U8TO32_LE(key + 0);
	t1 = U8TO32_LE(key + 4);
	t2 = U8TO32_LE(key + 8);
	t3 = U8TO32_LE(key + 12);

	/* precompute multipliers */
	r0 = t0 & 0x3ffffff; t0 >>= 26; t0 |= t1 << 6;
	r1 = t0 & 0x3ffff03; t1 >>= 20; t1 |= t2 << 12;
	r2 = t1 & 0x3ffc0ff; t2 >>= 14; t2 |= t3 << 18;
	r3 = t2 & 0x3f03fff; t3 >>= 8;
	r4 = t3 & 0x00fffff;

	s1 = r1 * 5;
	s2 = r2 * 5;
	s3 = r3 * 5;
	s4 = r4 * 5;

	/* init state */
	h0 = 0;
	h1 = 0;
	h2 = 0;
	h3 = 0;
	h4 = 0;

	/* full blocks */
	if (inlen < 16)
		goto poly1305_donna_atmost15bytes;

poly1305_donna_16bytes:
	m += 16;
	inlen -= 16;

	t0 = U8TO32_LE(m - 16);
	t1 = U8TO32_LE(m - 12);
	t2 = U8TO32_LE(m - 8);
	t3 = U8TO32_LE(m - 4);

	h0 += t0 & 0x3ffffff;
	h1 += (uint32_t)(((((uint64_t)t1 << 32) | t0) >> 26) & 0x3ffffff);
	h2 += (uint32_t)(((((uint64_t)t2 << 32) | t1) >> 20) & 0x3ffffff);
	h3 += (uint32_t)(((((uint64_t)t3 << 32) | t2) >> 14) & 0x3ffffff);
	h4 += (uint32_t)((t3 >> 8) | (1 << 24));

poly1305_donna_mul:
	t[0]  = mul32x32_64(h0,r0) + mul32x32_64(h1,s4) +
		mul32x32_64(h2,s3) + mul32x32_64(h3,s2) +
		mul32x32_64(h4,s1);
	t[1]  = mul32x32_64(h0,r1) + mul32x32_64(h1,r0) +
		mul32x32_64(h2,s4) + mul32x32_64(h3,s3) +
		mul32x32_64(h4,s2);
	t[2]  = mul32x32_64(h0,r2) + mul32x32_64(h1,r1) +
		mul32x32_64(h2,r0) + mul32x32_64(h3,s4) +
		mul32x32_64(h4,s3);
	t[3]  = mul32x32_64(h0,r3) + mul32x32_64(h1,r2) +
		mul32x32_64(h2,r1) + mul32x32_64(h3,r0) +
		mul32x32_64(h4,s4);
	t[4]  = mul32x32_64(h0,r4) + mul32x32_64(h1,r3) +
		mul32x32_64(h2,r2) + mul32x32_64(h3,r1) +
		mul32x32_64(h4,r0);

		    h0 = (uint32_t)t[0] & 0x3ffffff; c =           (t[0] >> 26);
	t[1] += c;  h1 = (uint32_t)t[1] & 0x3ffffff; b = (uint32_t)(t[1] >> 26);
	t[2] += b;  h2 = (uint32_t)t[2] & 0x3ffffff; b = (uint32_t)(t[2] >> 26);
	t[3] += b;  h3 = (uint32_t)t[3] & 0x3ffffff; b = (uint32_t)(t[3] >> 26);
	t[4] += b;  h4 = (uint32_t)t[4] & 0x3ffffff; b = (uint32_t)(t[4] >> 26);
	h0 += b * 5;

	if (inlen >= 16)
		goto poly1305_donna_16bytes;

	/* final bytes */
poly1305_donna_atmost15bytes:
	if (!inlen)
		goto poly1305_donna_finish;

	for (j = 0; j < inlen; j++)
		mp[j] = m[j];
	mp[j++] = 1;
	for (; j < 16; j++)
		mp[j] = 0;
	inlen = 0;

	t0 = U8TO32_LE(mp + 0);
	t1 = U8TO32_LE(mp + 4);
	t2 = U8TO32_LE(mp + 8);
	t3 = U8TO32_LE(mp + 12);

	h0 += t0 & 0x3ffffff;
	h1 += (uint32_t)(((((uint64_t)t1 << 32) | t0) >> 26) & 0x3ffffff);
	h2 += (uint32_t)(((((uint64_t)t2 << 32) | t1) >> 20) & 0x3ffffff);
	h3 += (uint32_t)(((((uint64_t)t3 << 32) | t2) >> 14) & 0x3ffffff);
	h4 += (uint32_t)(t3 >> 8);

	goto poly1305_donna_mul;

poly1305_donna_finish:
	             b = h0 >> 26; h0 = h0 & 0x3ffffff;
	h1 +=     b; b = h1 >> 26; h1 = h1 & 0x3ffffff;
	h2 +=     b; b = h2 >> 26; h2 = h2 & 0x3ffffff;
	h3 +=     b; b = h3 >> 26; h3 = h3 & 0x3ffffff;
	h4 +=     b; b = h4 >> 26; h4 = h4 & 0x3ffffff;
	h0 += b * 5; b = h0 >> 26; h0 = h0 & 0x3ffffff;
	h1 +=     b;

	g0 = h0 + 5; b = g0 >> 26; g0 &= 0x3ffffff;
	g1 = h1 + b; b = g1 >> 26; g1 &= 0x3ffffff;
	g2 = h2 + b; b = g2 >> 26; g2 &= 0x3ffffff;
	g3 = h3 + b; b = g3 >> 26; g3 &= 0x3ffffff;
	g4 = h4 + b - (1 << 26);

	b = (g4 >> 31) - 1;
	nb = ~b;
	h0 = (h0 & nb) | (g0 & b);
	h1 = (h1 & nb) | (g1 & b);
	h2 = (h2 & nb) | (g2 & b);
	h3 = (h3 & nb) | (g3 & b);
	h4 = (h4 & nb) | (g4 & b);

	f0 = ((h0      ) | (h1 << 26)) + (uint64_t)U8TO32_LE(&key[16]);
	f1 = ((h1 >>  6) | (h2 << 20)) + (uint64_t)U8TO32_LE(&key[20]);
	f2 = ((h2 >> 12) | (h3 << 14)) + (uint64_t)U8TO32_LE(&key[24]);
	f3 = ((h3 >> 18) | (h4 <<  8)) + (uint64_t)U8TO32_LE(&key[28]);

	U32TO8_LE(&out[ 0], f0); f1 += (f0 >> 32);
	U32TO8_LE(&out[ 4], f1); f2 += (f1 >> 32);
	U32TO8_LE(&out[ 8], f2); f3 += (f2 >> 32);
	U32TO8_LE(&out[12], f3);
}

void
chacha_keysetup(chacha_ctx *x,const uint8_t *k,uint32_t kbits)
{
  const char *constants;

  x->input[4] = U8TO32_LITTLE(k + 0);
  x->input[5] = U8TO32_LITTLE(k + 4);
  x->input[6] = U8TO32_LITTLE(k + 8);
  x->input[7] = U8TO32_LITTLE(k + 12);
  if (kbits == 256) { /* recommended */
    k += 16;
    constants = sigma;
  } else { /* kbits == 128 */
    constants = tau;
  }
  x->input[8] = U8TO32_LITTLE(k + 0);
  x->input[9] = U8TO32_LITTLE(k + 4);
  x->input[10] = U8TO32_LITTLE(k + 8);
  x->input[11] = U8TO32_LITTLE(k + 12);
  x->input[0] = U8TO32_LITTLE(constants + 0);
  x->input[1] = U8TO32_LITTLE(constants + 4);
  x->input[2] = U8TO32_LITTLE(constants + 8);
  x->input[3] = U8TO32_LITTLE(constants + 12);
}

void
chacha_ivsetup(chacha_ctx *x, const char *iv, const char *counter)
{
  x->input[12] = counter == NULL ? 0 : U8TO32_LITTLE(counter + 0);
  x->input[13] = counter == NULL ? 0 : U8TO32_LITTLE(counter + 4);
  x->input[14] = U8TO32_LITTLE(iv + 0);
  x->input[15] = U8TO32_LITTLE(iv + 4);
}

void
chacha_encrypt_bytes(chacha_ctx *x,const char *m,char *c,uint32_t bytes)
{
  uint32_t x0, x1, x2, x3, x4, x5, x6, x7, x8, x9, x10, x11, x12, x13, x14, x15;
  uint32_t j0, j1, j2, j3, j4, j5, j6, j7, j8, j9, j10, j11, j12, j13, j14, j15;
  char *ctarget = NULL;
  char tmp[64];
  uint32_t i;

  if (!bytes) return;

  j0 = x->input[0];
  j1 = x->input[1];
  j2 = x->input[2];
  j3 = x->input[3];
  j4 = x->input[4];
  j5 = x->input[5];
  j6 = x->input[6];
  j7 = x->input[7];
  j8 = x->input[8];
  j9 = x->input[9];
  j10 = x->input[10];
  j11 = x->input[11];
  j12 = x->input[12];
  j13 = x->input[13];
  j14 = x->input[14];
  j15 = x->input[15];

  for (;;) {
    if (bytes < 64) {
      for (i = 0;i < bytes;++i) tmp[i] = m[i];
      m = tmp;
      ctarget = c;
      c = tmp;
    }
    x0 = j0;
    x1 = j1;
    x2 = j2;
    x3 = j3;
    x4 = j4;
    x5 = j5;
    x6 = j6;
    x7 = j7;
    x8 = j8;
    x9 = j9;
    x10 = j10;
    x11 = j11;
    x12 = j12;
    x13 = j13;
    x14 = j14;
    x15 = j15;
    for (i = 20;i > 0;i -= 2) {
      QUARTERROUND( x0, x4, x8,x12)
      QUARTERROUND( x1, x5, x9,x13)
      QUARTERROUND( x2, x6,x10,x14)
      QUARTERROUND( x3, x7,x11,x15)
      QUARTERROUND( x0, x5,x10,x15)
      QUARTERROUND( x1, x6,x11,x12)
      QUARTERROUND( x2, x7, x8,x13)
      QUARTERROUND( x3, x4, x9,x14)
    }
    x0 = PLUS(x0,j0);
    x1 = PLUS(x1,j1);
    x2 = PLUS(x2,j2);
    x3 = PLUS(x3,j3);
    x4 = PLUS(x4,j4);
    x5 = PLUS(x5,j5);
    x6 = PLUS(x6,j6);
    x7 = PLUS(x7,j7);
    x8 = PLUS(x8,j8);
    x9 = PLUS(x9,j9);
    x10 = PLUS(x10,j10);
    x11 = PLUS(x11,j11);
    x12 = PLUS(x12,j12);
    x13 = PLUS(x13,j13);
    x14 = PLUS(x14,j14);
    x15 = PLUS(x15,j15);

    x0 = XOR(x0,U8TO32_LITTLE(m + 0));
    x1 = XOR(x1,U8TO32_LITTLE(m + 4));
    x2 = XOR(x2,U8TO32_LITTLE(m + 8));
    x3 = XOR(x3,U8TO32_LITTLE(m + 12));
    x4 = XOR(x4,U8TO32_LITTLE(m + 16));
    x5 = XOR(x5,U8TO32_LITTLE(m + 20));
    x6 = XOR(x6,U8TO32_LITTLE(m + 24));
    x7 = XOR(x7,U8TO32_LITTLE(m + 28));
    x8 = XOR(x8,U8TO32_LITTLE(m + 32));
    x9 = XOR(x9,U8TO32_LITTLE(m + 36));
    x10 = XOR(x10,U8TO32_LITTLE(m + 40));
    x11 = XOR(x11,U8TO32_LITTLE(m + 44));
    x12 = XOR(x12,U8TO32_LITTLE(m + 48));
    x13 = XOR(x13,U8TO32_LITTLE(m + 52));
    x14 = XOR(x14,U8TO32_LITTLE(m + 56));
    x15 = XOR(x15,U8TO32_LITTLE(m + 60));

    j12 = PLUSONE(j12);
    if (!j12)
      j13 = PLUSONE(j13);
      /* stopping at 2^70 bytes per nonce is user's responsibility */

    U32TO8_LITTLE(c + 0,x0);
    U32TO8_LITTLE(c + 4,x1);
    U32TO8_LITTLE(c + 8,x2);
    U32TO8_LITTLE(c + 12,x3);
    U32TO8_LITTLE(c + 16,x4);
    U32TO8_LITTLE(c + 20,x5);
    U32TO8_LITTLE(c + 24,x6);
    U32TO8_LITTLE(c + 28,x7);
    U32TO8_LITTLE(c + 32,x8);
    U32TO8_LITTLE(c + 36,x9);
    U32TO8_LITTLE(c + 40,x10);
    U32TO8_LITTLE(c + 44,x11);
    U32TO8_LITTLE(c + 48,x12);
    U32TO8_LITTLE(c + 52,x13);
    U32TO8_LITTLE(c + 56,x14);
    U32TO8_LITTLE(c + 60,x15);

    if (bytes <= 64) {
      if (bytes < 64) {
        for (i = 0;i < bytes;++i) ctarget[i] = c[i];
      }
      x->input[12] = j12;
      x->input[13] = j13;
      return;
    }
    bytes -= 64;
    c += 64;
    m += 64;
  }
}

struct ssh_cipher_chacha {
	struct chacha_ctx ccctx[2];
};

#define K_1(_keys) &((struct ssh_cipher_chacha *)_keys->cipher)->ccctx[0]
#define K_2(_keys) &((struct ssh_cipher_chacha *)_keys->cipher)->ccctx[1]

int
ssh_chacha_activate(struct ssh_keys *keys)
{
	if (keys->cipher) {
		free(keys->cipher);
		keys->cipher = NULL;
	}

	keys->cipher = malloc(sizeof(struct ssh_cipher_chacha));
	if (!keys->cipher)
		return 1;

	memset(keys->cipher, 0, sizeof(struct ssh_cipher_chacha));

	/* uses 2 x 256-bit keys, so 512 bits (64 bytes) needed */
	chacha_keysetup(K_2(keys), keys->key[SSH_KEYIDX_ENC], 256);
	chacha_keysetup(K_1(keys), &keys->key[SSH_KEYIDX_ENC][32], 256);

	keys->valid = 1;
	keys->full_length = 1;
	keys->padding_alignment = 8; // CHACHA_BLOCKLEN;
	keys->MAC_length = POLY1305_TAGLEN;

	return 0;
}

void
ssh_chacha_destroy(struct ssh_keys *keys)
{
	if (keys->cipher) {
		free(keys->cipher);
		keys->cipher = NULL;
	}
}

uint32_t
ssh_chachapoly_get_length(struct ssh_keys *keys, uint32_t seq,
			  const char *in4)
{
        char buf[4], seqbuf[8];

	/*
	 * When receiving a packet, the length must be decrypted first.  When 4
	 * bytes of ciphertext length have been received, they may be decrypted
	 * using the K_1 key, a nonce consisting of the packet sequence number
	 * encoded as a uint64 under the usual SSH wire encoding and a zero
	 * block counter to obtain the plaintext length.
	 */
        POKE_U64(seqbuf, seq);
	chacha_ivsetup(K_1(keys), seqbuf, NULL);
        chacha_encrypt_bytes(K_1(keys), in4, buf, 4);

	return PEEK_U32(buf);
}

/*
 * chachapoly_crypt() operates as following:
 * En/decrypt with header key 'aadlen' bytes from 'src', storing result
 * to 'dest'. The ciphertext here is treated as additional authenticated
 * data for MAC calculation.
 * En/decrypt 'len' bytes at offset 'aadlen' from 'src' to 'dest'. Use
 * POLY1305_TAGLEN bytes at offset 'len'+'aadlen' as the authentication
 * tag. This tag is written on encryption and verified on decryption.
 */
int
chachapoly_crypt(const char *_keys, uint32_t seqnr, char *dest,
    const char *src, uint32_t len, uint32_t aadlen, uint32_t authlen, int do_encrypt)
{
        char seqbuf[8];
        const char one[8] = { 1, 0, 0, 0, 0, 0, 0, 0 }; /* NB little-endian */
        char expected_tag[POLY1305_TAGLEN], poly_key[POLY1305_KEYLEN];
        int r = 1;

        struct ssh_keys *keys = new ssh_keys{};
        memcpy((uint8_t*)keys,(uint8_t*)_keys,64); // TODO: refactor ASAP
        ssh_chacha_activate(keys);

        /*
         * Run ChaCha20 once to generate the Poly1305 key. The IV is the
         * packet sequence number.
         */
        memset(poly_key, 0, sizeof(poly_key));
        POKE_U64(seqbuf, seqnr);
        chacha_ivsetup(K_2(keys), seqbuf, NULL);
        chacha_encrypt_bytes(K_2(keys),
            poly_key, poly_key, sizeof(poly_key));

        /* If decrypting, check tag before anything else */
        if (!do_encrypt) {
                const char *tag = src + aadlen + len;

                poly1305_auth(expected_tag, src, aadlen + len, poly_key);
                if (memcmp(expected_tag, tag, POLY1305_TAGLEN) != 0) {
                        r = 2;
                        // goto out;
                }
        }

        /* Crypt additional data */
        if (aadlen) {
                chacha_ivsetup(K_1(keys), seqbuf, NULL);
                chacha_encrypt_bytes(K_1(keys), src, dest, aadlen);
        }

        /* Set Chacha's block counter to 1 */
        chacha_ivsetup(K_2(keys), seqbuf, one);
        chacha_encrypt_bytes(K_2(keys), src + aadlen, dest + aadlen, len);

        /* If encrypting, calculate and append tag */
        if (do_encrypt) {
                poly1305_auth(dest + aadlen + len, dest, aadlen + len,
                    poly_key);
        }
        r = 0;
 out:
        ssh_explicit_bzero(expected_tag, sizeof(expected_tag));
        ssh_explicit_bzero(seqbuf, sizeof(seqbuf));
        ssh_explicit_bzero(poly_key, sizeof(poly_key));
        ssh_chacha_destroy(keys);
        delete keys;
        return r;
}
