#pragma once
#include <cstdint>

const uint8_t *xinput_device_descriptor();
const uint8_t *xinput_configuration_descriptor(const uint8_t *base, uint16_t size, uint8_t interval);
bool xinput_report_ready();
void xinput_send_report(const uint8_t *dualsense_report);
