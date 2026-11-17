"""The pair code with a stand-in assembler: synthetic words, no PowerPC tools and no game data."""
import os
import unittest
from unittest import mock

with mock.patch.dict(os.environ, {"POKEMELEE_RUNTIME": os.environ.get("POKEMELEE_RUNTIME", "unused")}):
    from pokemelee.native import follower_code

OLD_SWAP_HOOK = 0x8006B848   # Fighter_procUpdate, where the D-pad-down leader swap was


def hooks(lines):
    """the addresses a Gecko text hooks, walking each C2 block by its length as css_doors.gct_hooks
    walks a codes.gct"""
    words = [int(word, 16) for line in lines for word in line.split("#", 1)[0].split()]
    found, i = set(), 0
    while i + 1 < len(words):
        if words[i] >> 24 == 0xC2:
            found.add(0x80000000 | (words[i] & 0x01FFFFFF))
            i += 2 + 2 * words[i + 1]
        else:
            i += 2
    return found


class NoLeaderSwap(unittest.TestCase):
    def setUp(self):
        stand_in = mock.patch.object(follower_code, "assemble", return_value=[0x60000000, 0x60000000, 0x60000000])
        stand_in.start()
        self.addCleanup(stand_in.stop)

    def installed(self):
        """the lines install_project adds for the pairs: the follower code, then the clone alias table"""
        lines = follower_code.build().splitlines()
        self.assertEqual(lines.pop(0), "$!GAMEPLAY | Any Climbers - Generic Follower AI [SSBM Nucleus]")
        return lines + follower_code.alias_ini_lines({27: 23, 28: 23})

    def test_the_pair_code_leaves_the_old_swap_address_alone(self):
        found = hooks(self.installed())
        self.assertNotIn(OLD_SWAP_HOOK, found)
        self.assertEqual(found, set(follower_code.SITES) | {
            follower_code.FOLLOWER_ARM, follower_code.FOLLOWER_SPAWN, follower_code.ALIAS_HOOK,
            follower_code.KIRBY_CAP_PRELOAD_HOOK, follower_code.KIRBY_CAP_LOAD_HOOK, follower_code.PLAYER_KIND_HOOK})
        follower_code.check_no_swap(found)

    def test_a_build_that_hooks_the_old_swap_address_fails(self):
        lines = self.installed() + follower_code.c2_block(OLD_SWAP_HOOK, [0x80630000 | 0x2C])  # lwz r3,0x2C(r3)
        with self.assertRaisesRegex(RuntimeError, "0x8006b848"):
            follower_code.check_no_swap(hooks(lines))

    def test_a_clone_entry_only_aliases_the_kind(self):
        # no clone sets the old swap cooldown (stw r0,0x22F8(r3)) any more
        self.assertEqual(follower_code.alias_words({27: 23, 28: 23}), [
            0x80030004,
            0x2C00001B, 0x40820010, 0x900322F4, 0x38000017, 0x90030004,
            0x2C00001C, 0x40820010, 0x900322F4, 0x38000017, 0x90030004,
            0x8803221F])


if __name__ == "__main__":
    unittest.main()
