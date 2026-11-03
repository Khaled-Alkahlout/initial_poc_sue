"""Backend-only model output: DPAPI on Windows, owner-only files on POSIX.

Never served by REST or placed in ordinary application logs. Lives under the
operator's ignored local data directory; remove with local diagnostic artifacts.
"""

import os
from uuid import UUID


def preserve_output(data_dir, run_id, text):
    try:
        payload = text.encode("utf-8")
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            class Blob(ctypes.Structure):
                _fields_ = [
                    ("size", wintypes.DWORD),
                    ("data", ctypes.POINTER(ctypes.c_byte)),
                ]

            buffer = ctypes.create_string_buffer(payload)
            source = Blob(
                len(payload), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))
            )
            target = Blob()
            if not ctypes.windll.crypt32.CryptProtectData(
                ctypes.byref(source),
                "SUE model diagnostics",
                None,
                None,
                None,
                1,
                ctypes.byref(
                    target
                ),  # CRYPTPROTECT_UI_FORBIDDEN; current Windows user only.
            ):
                return False
            try:
                payload = ctypes.string_at(target.data, target.size)
            finally:
                ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
                ctypes.windll.kernel32.LocalFree(target.data)
        folder = data_dir / "private-model-diagnostics"
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != "nt":
            folder.chmod(0o700)
        path = folder / (str(UUID(run_id)) + ".bin")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
        return True
    except (OSError, ValueError):
        return False
