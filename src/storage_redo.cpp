#include "storage_redo.h"
#include "flash_map.h"
#include "utils.h"
#include <cstring>

namespace {
constexpr uint32_t magic = 0x5245444f;
alignas(4) uint8_t work[FLASH_SECTOR_SIZE];
struct Header { uint32_t tag, target, checksum, header_checksum; };
const uint8_t *at(uint32_t offset) { return reinterpret_cast<const uint8_t *>(XIP_BASE + offset); }
bool target_valid(uint32_t offset) {
    if (offset == MACRO_FLASH_OFFSET) return true;
    for (unsigned i = 0; i < SLOT_COUNT / SLOTS_PER_SECTOR; ++i)
        if (offset == slot_sector_offset_at(i)) return true;
    return false;
}
}

bool storage_redo_recover() {
    Header h;
    memcpy(&h, at(STORAGE_REDO_META), sizeof(h));
    if (h.tag != magic || h.header_checksum != crc32(reinterpret_cast<const uint8_t *>(&h), 12)) return true;
    if (!target_valid(h.target) || crc32(at(STORAGE_REDO_DATA), FLASH_SECTOR_SIZE) != h.checksum) return false;
    if (memcmp(at(h.target), at(STORAGE_REDO_DATA), FLASH_SECTOR_SIZE) != 0) {
        memcpy(work, at(STORAGE_REDO_DATA), sizeof(work));
        flash_range_erase(h.target, FLASH_SECTOR_SIZE);
        flash_range_program(h.target, work, sizeof(work));
        if (memcmp(at(h.target), work, sizeof(work)) != 0) return false;
    }
    flash_range_erase(STORAGE_REDO_META, FLASH_SECTOR_SIZE);
    return true;
}

bool storage_redo_write(uint32_t target, const uint8_t *image, uint32_t bytes) {
    extern const uint8_t __flash_binary_end[];
    if (reinterpret_cast<uintptr_t>(__flash_binary_end) > XIP_BASE + STORAGE_REDO_META ||
        !target_valid(target) || !image || bytes > FLASH_SECTOR_SIZE) return false;
    if (!storage_redo_recover()) return false;
    alignas(4) static uint8_t page[FLASH_PAGE_SIZE];
    memset(work, 0xff, sizeof(work));
    memcpy(work, image, bytes);
    if (!memcmp(at(target), work, sizeof(work))) return true;
    // Commit the new image before touching the only live copy.
    flash_range_erase(STORAGE_REDO_META, FLASH_SECTOR_SIZE);
    flash_range_erase(STORAGE_REDO_DATA, FLASH_SECTOR_SIZE);
    flash_range_program(STORAGE_REDO_DATA, work, sizeof(work));
    if (memcmp(at(STORAGE_REDO_DATA), work, sizeof(work))) return false;
    Header h{magic, target, crc32(work, sizeof(work)), 0};
    h.header_checksum = crc32(reinterpret_cast<const uint8_t *>(&h), 12);
    memset(page, 0xff, sizeof(page));
    memcpy(page, &h, sizeof(h));
    flash_range_program(STORAGE_REDO_META, page, sizeof(page));
    if (memcmp(at(STORAGE_REDO_META), page, sizeof(page))) return false;
    return storage_redo_recover();
}
