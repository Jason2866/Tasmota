/*
 * bssl_hal_select.h — central selector for BearSSL HW HAL vs SW
 *
 * When -DUSE_SHA_ROM is active on an ESP32 family target, the files
 *   src/hash/_sha_hal_idf5x.c
 *   src/ec/_ec_c25519_m15.c
 *   src/ec/_ec_p256_m15.c
 * provide hardware-accelerated implementations of the same public
 * symbols (br_sha*_init / _update / _out / _state / _set_state / _vtable
 * and br_ec_*_m15). Without a coordinating guard, the portable software
 * TUs (sha1.c, sha2small.c, sha2big.c, ec_p256_m15.c, ec_c25519_m15.c)
 * emit the same symbols, producing either a "multiple definition" link
 * failure or — when the static archive resolver picks members in an
 * unspecified order — a half-SW/half-HAL Frankenstein chain whose
 * midstate byte layout is inconsistent. The latter manifests as broken
 * SHA/HMAC/ECDHE results during the TLS handshake (bad MAC, bad
 * finished, bad certificate signature).
 *
 * This header defines a small set of macros that exactly mirror the
 * conditions under which the HAL TUs emit symbols. The portable SW
 * TUs include this header (transitively via t_inner.h) and skip the
 * conflicting definitions when the matching macro is defined.
 *
 * We require the HAL to cover an *entire* algorithm family (SHA-1,
 * SHA-224+SHA-256, SHA-384+SHA-512) before letting it take over,
 * because mixing SW state with HAL update functions inside one family
 * gives incompatible midstate encodings (SW stores host-order u32
 * words → BE on save, HAL stores LE-encoded byte image). Chips that
 * have only partial HW coverage of a family cannot currently use
 * USE_SHA_ROM for that family; the build fails with a clear message
 * so the user knows to disable the option.
 */
#ifndef BSSL_HAL_SELECT_H__
#define BSSL_HAL_SELECT_H__

#if defined(USE_SHA_ROM) && defined(ESP_PLATFORM) && !defined(ESP8266)

# if __has_include("soc/sha_caps.h")
#  include "soc/sha_caps.h"
# elif __has_include("soc/soc_caps.h")
#  include "soc/soc_caps.h"
# else
#  error "USE_SHA_ROM: cannot find soc/sha_caps.h or soc/soc_caps.h"
# endif

/* ---------- SHA family selection ---------- */

/* The SHA HAL only emits anything if the IDF reports resumeable SHA. */
# if defined(SOC_SHA_SUPPORT_RESUME) && SOC_SHA_SUPPORT_RESUME

#  if defined(SOC_SHA_SUPPORT_SHA1) && SOC_SHA_SUPPORT_SHA1
#   define BR_HAL_PROVIDES_SHA1 1
#  endif

/* SHA-224 + SHA-256 form one inseparable family in BearSSL: the SHA-256
 * vtable references br_sha224_update / _state / _set_state. Require
 * both to be HW-supported before letting HAL own the family. */
#  if defined(SOC_SHA_SUPPORT_SHA256) && SOC_SHA_SUPPORT_SHA256
#   if !defined(SOC_SHA_SUPPORT_SHA224) || !SOC_SHA_SUPPORT_SHA224
#    error "USE_SHA_ROM: this chip has HW SHA-256 but no HW SHA-224; mixing SW SHA-224 with HAL SHA-256 corrupts the midstate. Disable -DUSE_SHA_ROM."
#   endif
#   define BR_HAL_PROVIDES_SHA256_FAMILY 1
#  endif

/* SHA-384 + SHA-512 likewise: SHA-512 vtable reuses br_sha384_update.
 * Require both before letting HAL own the family. */
#  if defined(SOC_SHA_SUPPORT_SHA512) && SOC_SHA_SUPPORT_SHA512
#   if !defined(SOC_SHA_SUPPORT_SHA384) || !SOC_SHA_SUPPORT_SHA384
#    error "USE_SHA_ROM: this chip has HW SHA-512 but no HW SHA-384; mixing SW SHA-384 with HAL SHA-512 corrupts the midstate. Disable -DUSE_SHA_ROM."
#   endif
#   define BR_HAL_PROVIDES_SHA512_FAMILY 1
#  endif

# endif /* SOC_SHA_SUPPORT_RESUME */

/* ---------- EC family selection ---------- */

/* The ROM bigint EC HAL TUs always emit br_ec_p256_m15 and
 * br_ec_c25519_m15 if the chip has an MPI accelerator. */
# if defined(SOC_MPI_SUPPORTED) && SOC_MPI_SUPPORTED
#  define BR_HAL_PROVIDES_EC_C25519 1
#  define BR_HAL_PROVIDES_EC_P256   1
# endif

#endif /* USE_SHA_ROM && ESP_PLATFORM && !ESP8266 */

#endif /* BSSL_HAL_SELECT_H__ */
