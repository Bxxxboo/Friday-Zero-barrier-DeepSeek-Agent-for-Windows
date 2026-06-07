# UTF-8 version metadata for PyInstaller (Windows exe properties / tooltip)
# 与 friday/version.py 保持一致
# pylint: disable=invalid-name
VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=(1, 1, 1, 0),
        prodvers=(1, 1, 1, 0),
        mask=0x3F,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "080404B0",
                    [
                        StringStruct("CompanyName", "Friday"),
                        StringStruct("FileDescription", "星期五 - AI 电脑管家"),
                        StringStruct("FileVersion", "1.1.1.0"),
                        StringStruct("InternalName", "Friday"),
                        StringStruct("LegalCopyright", ""),
                        StringStruct("OriginalFilename", "Friday.exe"),
                        StringStruct("ProductName", "星期五"),
                        StringStruct("ProductVersion", "1.1.1.0"),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [2052, 1200])]),
    ],
)
