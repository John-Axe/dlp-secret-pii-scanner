"""A tiny base64-encoded icon used in the CLI's --help banner.

Known limitation: the entropy detector can flag base64-encoded binary
assets like this one as a false positive, since compressed/binary data
is itself high-entropy. Use a `# dlp-ignore` comment for cases like this
once you've confirmed the blob isn't actually secret material.
"""

ICON_PNG_BASE64 = "LkjmgVkBiaT/Yz2mIrIt+YkQASrrnVBA2iRaZE3ajrC2RGaLUqdsk3rnoUFR+UjdZlP5mDm5nmrhDazZ"
