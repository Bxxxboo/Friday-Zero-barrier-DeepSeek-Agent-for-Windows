"""CDN aes_key 编码须与微信客户端解密约定一致。"""

import base64

from friday.weixin.media import aes_key_b64_for_file, aes_key_b64_for_image


def test_aes_key_b64_for_image_is_raw_16_bytes():
    hex_key = "0123456789abcdef0123456789abcdef"
    encoded = aes_key_b64_for_image(hex_key)
    decoded = base64.b64decode(encoded)
    assert decoded == bytes.fromhex(hex_key)
    assert len(decoded) == 16


def test_aes_key_b64_for_file_is_hex_ascii_string():
    hex_key = "0123456789abcdef0123456789abcdef"
    encoded = aes_key_b64_for_file(hex_key)
    decoded = base64.b64decode(encoded)
    assert decoded.decode("ascii") == hex_key
    assert len(decoded) == 32


def test_file_and_image_encodings_differ():
    hex_key = "a" * 32
    assert aes_key_b64_for_file(hex_key) != aes_key_b64_for_image(hex_key)
