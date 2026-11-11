import unittest
from studio_shift import reserved_input, validate_reserved_inputs, SHIFT, SHIFT_KEY


def row(chord, flags=0, output=1):
    r = [0] * 35
    r[:4] = chord.to_bytes(4, 'little')
    r[5], r[17] = flags, output
    return r


class ReservedInputs(unittest.TestCase):
    def test_ps_policy(self):
        r = row(1 << 16)
        self.assertTrue(reserved_input(r, {}, 0, True))
        self.assertFalse(reserved_input(r, {}, 0, False))
        self.assertTrue(reserved_input(row((1 << 16) | (1 << 12)), {}, 0))

    def test_edge_reserved_combinations(self):
        for fn in (19, 20):
            for key in (*range(8), 13):
                self.assertTrue(reserved_input(row((1 << fn) | (1 << key)), {}, 0))
            self.assertFalse(reserved_input(row((1 << fn) | (1 << 8)), {}, 0))

    def test_shift_expansion_and_disabled_shift(self):
        records = {'0': row(1 << 19, output=SHIFT_KEY), '1': row(1 << 4, SHIFT)}
        self.assertTrue(reserved_input(records['1'], records, 0))
        self.assertFalse(reserved_input(records['1'], records, 1))
        with self.assertRaises(ValueError):
            validate_reserved_inputs(records, {'macro_disable': 0})
        validate_reserved_inputs(records, {'macro_disable': 3})

    def test_mute_shift_ps_allowed_without_builtin_shortcut(self):
        records = {'0': row(1 << 18, output=SHIFT_KEY), '1': row(1 << 16, SHIFT)}
        self.assertFalse(reserved_input(records['1'], records, 0, False))
        self.assertTrue(reserved_input(records['1'], records, 0, True))


if __name__ == '__main__':
    unittest.main()
