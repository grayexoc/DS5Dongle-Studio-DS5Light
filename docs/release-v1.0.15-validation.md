# v1.0.15 / Studio v45 validation

The existing latest local Windows x64 ZIP and Pico 2 W UF2 were reused after checking artifact SHA-256, ZIP CRC, required executable/private-preferences exclusion and UF2 structure. All 58 recorded firmware source hashes match the published source. Frozen bytecode for 70 application modules, including app.py, matches the current source, so no redundant rebuild or full regression run was performed for publication.

The prior local validation report records 668 app tests: 661 passed, 7 skipped. A subsequent save-guard change passed its 41 affected checks; English checks passed separately. Both Korean and English final packaged UI smoke passed. Firmware host scripts passed (16), including 160 single and 240 repeated power-cut points; actual hardware brownout behavior is not established by these tests. Firmware built as Pico 2 W / RP2350 ARM Secure / Release / v45 with integrated Native/XInput support.

Not performed for publication: firmware flashing, physical haptics/audio, OLED readability, actual mode transitions, reconnection/sleep or device power-loss tests. Formal models were not rerun; the prior local work used actual production-code fault injection and targeted state tests. These limits remain after publication.
