"""Source form of KELLZ's accepted 'Skip Slippi SSS' compatibility hooks."""
from .follower_code import assemble, c2_block

NAME = 'Skip Slippi SSS [KELLZ]'


def source():
    lines = []
    for hook, resume in ((0x800166B4, 0x66BC), (0x800163F8, 0x6400)):
        words = assemble(f'''
            lis 12, 0x8001
            ori 12, 12, 0x6204
            mtctr 12
            bctrl
            mr 30, 3
            mflr 0
            stw 0, 4(1)
            stwu 1, -256(1)
            stmw 20, 8(1)
            lis 3, 0x801A
            ori 3, 3, 0x5014
            lwz 3, 0(3)
            lis 4, 0x4082
            ori 4, 4, 0x10
            cmpw 3, 4
            beq done
            lwz 3, 0(1)
            lwz 3, 0(3)
            lwz 3, 0(3)
            lwz 20, 4(3)
            lis 3, 0x8025
            ori 3, 3, 0xA9DC
            cmpw 20, 3
            beq skip
            lis 3, 0x8025
            ori 3, 3, 0xA9EC
            cmpw 20, 3
            beq skip
            b done
        skip:
            lmw 20, 8(1)
            lwz 0, 260(1)
            addi 1, 1, 256
            mtlr 0
            mr 3, 30
            lis 12, 0x8001
            ori 12, 12, {resume}
            mtctr 12
            bctr
        done:
            lmw 20, 8(1)
            lwz 0, 260(1)
            addi 1, 1, 256
            mtlr 0
            mr 3, 30
        ''')
        lines.extend(c2_block(hook, words))
    return '\n'.join(lines)
