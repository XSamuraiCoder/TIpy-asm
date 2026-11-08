"""Runtime support shared by generated assembly programs.

Two kinds of helper are linked into a program only when it uses them:

``RAW`` holds the few routines that must be hand-written assembly: arithmetic
the CPU lacks, and direct access to the screen, keypad, and OS. They take
arguments in the static words ``_rt_a0``.. and return a value in HL.

``PRELUDE`` holds everything else, written in TIpy's own Python subset and
compiled like a user function. Clipping and drawing algorithms live there, so
they only need testing once, and the same source works on both CPUs.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Callable

MAX_RAW_ARGS = 5


class LabelRef(ast.expr):
    """An expression whose value is the address of an assembly label."""

    def __init__(self, label: str):
        super().__init__()
        self.label = label


@dataclass(frozen=True)
class Target:
    """Assembler spelling for the two CPUs."""
    name: str

    @property
    def is_ce(self) -> bool:
        return self.name == "ce"

    @property
    def bits(self) -> int:
        return 24 if self.is_ce else 16

    @property
    def word_bytes(self) -> int:
        return 3 if self.is_ce else 2

    def rom(self, routine: str) -> str:
        return f"call ti.{routine}" if self.is_ce else f"bcall(_{routine})"

    def word(self, label: str) -> str:
        return f"{label}: db 0,0,0" if self.is_ce else f"{label}: .dw 0"

    def bytes(self, label: str, *values: int) -> str:
        return f"{label}: {'db' if self.is_ce else '.db'} " + ",".join(str(v) for v in values)


@dataclass(frozen=True)
class Raw:
    args: int
    code: Callable[[Target], str]
    deps: tuple[str, ...] = ()
    words: tuple[str, ...] = ()           # private static words


def _neg(t: Target) -> str:
    return """
_rt_neg:
    ex de,hl
    ld hl,0
    or a
    sbc hl,de
    ret
"""


def _abs(t: Target) -> str:
    # ADD HL,HL moves the sign bit into carry at either register width.
    return """
_rt_abs:
    push hl
    add hl,hl
    pop hl
    ret nc
    jp _rt_neg
"""


def _mul(t: Target) -> str:
    return f"""
_rt_mul:
    push hl
    pop bc
    ld hl,0
    ld a,{t.bits}
_rt_mul_loop:
    add hl,hl
    ex de,hl
    add hl,hl
    ex de,hl
    jr nc,_rt_mul_skip
    add hl,bc
_rt_mul_skip:
    dec a
    jr nz,_rt_mul_loop
    ret
"""


def _udiv(t: Target) -> str:
    # In: HL dividend, DE divisor (nonzero). Out: HL quotient, DE remainder.
    return f"""
_rt_udiv:
    push de
    pop bc
    ld de,0
    ld a,{t.bits}
_rt_udiv_loop:
    add hl,hl
    ex de,hl
    adc hl,hl
    or a
    sbc hl,bc
    jr nc,_rt_udiv_fits
    add hl,bc
    jr _rt_udiv_next
_rt_udiv_fits:
    inc de
_rt_udiv_next:
    ex de,hl
    dec a
    jr nz,_rt_udiv_loop
    ret
"""


def _divmod(t: Target) -> str:
    # Python floor semantics: HL = x // y, DE = x % y. Dividing by zero cannot
    # raise on a calculator, so it is defined as x // 0 == 0 and x % 0 == x.
    return """
_rt_divmod:
    ld (_rt_dm_x),hl
    ex de,hl
    ld (_rt_dm_y),hl
    ld de,0
    or a
    sbc hl,de
    jr nz,_rt_divmod_nonzero
    ld hl,(_rt_dm_x)
    ex de,hl
    ld hl,0
    ret
_rt_divmod_nonzero:
    ld hl,(_rt_dm_y)
    call _rt_abs
    push hl
    ld hl,(_rt_dm_x)
    call _rt_abs
    pop de
    call _rt_udiv
    ld (_rt_dm_q),hl
    ex de,hl
    ld (_rt_dm_r),hl
    ld hl,(_rt_dm_x)
    add hl,hl
    jr nc,_rt_divmod_x_positive
    ld hl,(_rt_dm_r)
    call _rt_neg
    ld (_rt_dm_r),hl
_rt_divmod_x_positive:
    ld hl,(_rt_dm_x)
    add hl,hl
    sbc a,a
    ld b,a
    ld hl,(_rt_dm_y)
    add hl,hl
    sbc a,a
    xor b
    jr z,_rt_divmod_done
    ld hl,(_rt_dm_q)
    call _rt_neg
    ld (_rt_dm_q),hl
    ld hl,(_rt_dm_r)
    ld de,0
    or a
    sbc hl,de
    jr z,_rt_divmod_done
    ld hl,(_rt_dm_q)
    dec hl
    ld (_rt_dm_q),hl
    ld hl,(_rt_dm_r)
    ld de,(_rt_dm_y)
    add hl,de
    ld (_rt_dm_r),hl
_rt_divmod_done:
    ld hl,(_rt_dm_r)
    ex de,hl
    ld hl,(_rt_dm_q)
    ret
"""


def _bitop(mnemonic: str) -> Callable[[Target], str]:
    def code(t: Target) -> str:
        name = f"_rt_{mnemonic}"
        return f"""
{name}:
    ld (_rt_bit_a),hl
    ld (_rt_bit_b),de
    ld hl,_rt_bit_a
    ld de,_rt_bit_b
    ld b,{t.word_bytes}
{name}_loop:
    ld a,(de)
    {mnemonic} (hl)
    ld (hl),a
    inc hl
    inc de
    djnz {name}_loop
    ld hl,(_rt_bit_a)
    ret
"""
    return code


def _shl(t: Target) -> str:
    return """
_rt_shl:
    ld a,e
_rt_shl_loop:
    or a
    ret z
    add hl,hl
    dec a
    jr _rt_shl_loop
"""


def _sar(t: Target) -> str:
    rotate = "    dec hl\n    rr (hl)\n" * (t.word_bytes - 1)
    return f"""
_rt_sar:
    ld (_rt_bit_a),hl
    ld a,e
_rt_sar_loop:
    or a
    jr z,_rt_sar_done
    ld hl,_rt_bit_a+{t.word_bytes - 1}
    sra (hl)
{rotate}    dec a
    jr _rt_sar_loop
_rt_sar_done:
    ld hl,(_rt_bit_a)
    ret
"""


def _itoa(t: Target) -> str:
    # Returns HL pointing at the NUL-terminated decimal text.
    return f"""
_rt_itoa:
    ld (_rt_it_value),hl
    ld hl,_rt_it_buf+9
    ld (_rt_it_ptr),hl
    ld hl,(_rt_it_value)
    call _rt_abs
_rt_itoa_loop:
    ld de,10
    call _rt_udiv
    push hl
    ld a,e
    add a,48
    ld hl,(_rt_it_ptr)
    dec hl
    ld (hl),a
    ld (_rt_it_ptr),hl
    pop hl
    ld de,0
    or a
    sbc hl,de
    add hl,de
    jr nz,_rt_itoa_loop
    ld hl,(_rt_it_value)
    add hl,hl
    jr nc,_rt_itoa_done
    ld hl,(_rt_it_ptr)
    dec hl
    ld (hl),45
    ld (_rt_it_ptr),hl
_rt_itoa_done:
    ld hl,(_rt_it_ptr)
    ret
{t.bytes("_rt_it_buf", *([0] * 10))}
"""


def _vram(t: Target) -> str:
    # HL = VRAM address of pixel (_rt_a0, _rt_a1). y * 320 = y * 256 + y * 64.
    if not t.is_ce:
        return ""
    return """
_rt_vram:
    ld hl,(_rt_a1)
    add hl,hl
    add hl,hl
    add hl,hl
    add hl,hl
    add hl,hl
    add hl,hl
    push hl
    add hl,hl
    add hl,hl
    pop de
    add hl,de
    ld de,(_rt_a0)
    add hl,de
    add hl,hl
    ld de,$D40000
    add hl,de
    ret
"""


def _pixel(t: Target) -> str:
    width, height = (320, 240) if t.is_ce else (96, 64)
    head = f"""
_rt_pixel:
    ld hl,(_rt_a0)
    ld de,{width}
    or a
    sbc hl,de
    ret nc
    ld hl,(_rt_a1)
    ld de,{height}
    or a
    sbc hl,de
    ret nc
"""
    if t.is_ce:
        return head + """    call _rt_vram
    ld de,(_rt_a2)
    ld (hl),e
    inc hl
    ld (hl),d
    ret
"""
    return head + """    ld a,(_rt_a1)
    ld b,a
    ld a,63
    sub b
    ld c,a
    ld a,(_rt_a0)
    ld b,a
    ld hl,(_rt_a2)
    ld a,h
    or l
    jr z,_rt_pixel_color
    ld a,1
_rt_pixel_color:
    ld d,a
    res plotLoc,(iy+plotFlags)
    set fullScrnDraw,(iy+apiFlg4)
    bcall(_IPoint)
    ret
"""


def _get_pixel(t: Target) -> str:
    return """
_rt_get_pixel:
    ld hl,(_rt_a0)
    ld de,320
    or a
    sbc hl,de
    jr nc,_rt_get_pixel_off
    ld hl,(_rt_a1)
    ld de,240
    or a
    sbc hl,de
    jr nc,_rt_get_pixel_off
    call _rt_vram
    ld (_rt_a0),hl
    jp _rt_peek16
_rt_get_pixel_off:
    ld hl,0
    ret
"""


def _fill_rect(t: Target) -> str:
    # In: x0, y0, x1, y1 (exclusive), color, already clipped and non-empty.
    if t.is_ce:
        return """
_rt_fill_rect:
    ; Write the first pixel, copy it across the first row with LDIR (an
    ; overlapping copy repeats it), then copy that row into each row below.
    call _rt_vram
    ld (_rt_fill_ptr),hl
    ld de,(_rt_a4)
    ld (hl),e
    inc hl
    ld (hl),d
    ld hl,(_rt_a2)
    ld de,(_rt_a0)
    or a,a
    sbc hl,de
    add hl,hl
    ld (_rt_fill_cols),hl        ; bytes in a row
    ld hl,(_rt_a3)
    ld de,(_rt_a1)
    or a,a
    sbc hl,de
    ld (_rt_fill_rows),hl
    ld bc,(_rt_fill_cols)
    dec bc
    dec bc
    ld a,b
    or a,c
    jr z,_rt_fill_down
    ld hl,(_rt_fill_ptr)
    ld de,(_rt_fill_ptr)
    inc de
    inc de
    ldir
_rt_fill_down:
    ld hl,(_rt_fill_rows)
    dec hl
    ld a,h
    or a,l
    ret z
    ld (_rt_fill_rows),hl
    ld hl,(_rt_fill_cols)
    ld de,640
    or a,a
    sbc hl,de
    jr nz,_rt_fill_row
    ; Full-width rows follow each other in VRAM: one copy fills them all.
    ld hl,(_rt_fill_rows)
    add hl,hl
    add hl,hl
    add hl,hl
    add hl,hl
    add hl,hl
    add hl,hl
    add hl,hl                    ; rows * 128
    push hl
    add hl,hl
    add hl,hl                    ; rows * 512
    pop de
    add hl,de                    ; rows * 640
    push hl
    pop bc
    ld hl,(_rt_fill_ptr)
    ld de,640
    add hl,de
    ex de,hl
    ld hl,(_rt_fill_ptr)
    ldir
    ret
_rt_fill_row:
    ld hl,(_rt_fill_ptr)
    ld de,640
    add hl,de
    ex de,hl
    ld hl,(_rt_fill_ptr)
    ld bc,(_rt_fill_cols)
    push de
    ldir
    pop hl
    ld (_rt_fill_ptr),hl
    ld hl,(_rt_fill_rows)
    dec hl
    ld (_rt_fill_rows),hl
    ld a,h
    or a,l
    jr nz,_rt_fill_row
    ret
"""
    return """
_rt_fill_rect:
    ld a,(_rt_a1)
    ld h,a
    ld a,(_rt_a0)
    ld l,a
    ld a,(_rt_a3)
    dec a
    ld d,a
    ld a,(_rt_a2)
    dec a
    ld e,a
    res plotLoc,(iy+plotFlags)
    ld bc,(_rt_a4)
    ld a,b
    or c
    jr z,_rt_fill_clear
    bcall(_FillRect)
    ret
_rt_fill_clear:
    bcall(_ClearRect)
    ret
"""


def _blit_row(t: Target) -> str:
    # Copy opaque RGB565 pixels from _rt_a2 to pixel (_rt_a0, _rt_a1), for
    # _rt_a3 pixels. Color 0 is transparent. Clipping happens in the prelude.
    return """
_rt_blit_row:
    call _rt_vram
    ex de,hl
    ld hl,(_rt_a3)
    add hl,hl
    push hl
    pop bc                       ; BC = bytes to copy
    ld hl,(_rt_a2)
_rt_blit_next:
    ld a,(hl)
    inc hl
    or a,(hl)
    dec hl
    jr z,_rt_blit_clear
    ldi
    ldi
    jp pe,_rt_blit_next          ; P/V stays set until BC reaches 0
    ret
_rt_blit_clear:
    inc hl
    inc hl
    inc de
    inc de
    dec bc
    dec bc
    ld a,b
    or a,c
    jr nz,_rt_blit_next
    ret
"""


def _peek16(t: Target) -> str:
    return """
_rt_peek16:
    ld hl,(_rt_a0)
    ld e,(hl)
    inc hl
    ld d,(hl)
    ld hl,0
    ld l,e
    ld h,d
    ret
"""


def _delay(t: Target) -> str:
    return """
_rt_delay:
    ld hl,(_rt_a0)
    push hl
    pop bc
_rt_delay_loop:
    dec bc
    ld a,b
    or c
    jr nz,_rt_delay_loop
    ret
"""


def _kbd_row(t: Target) -> str:
    # Return the raw row of key bits, 1 = held, for scan-code row _rt_a0 (0-6).
    if t.is_ce:
        # As CEdev's keypadc kb_ScanGroup: with interrupts off, request one scan
        # (mode 2), wait for the keypad to return to idle, then read the group.
        # Leaving the keypad scanning continuously crashes the OS. Interrupts stay
        # off, as with keypadc; program_exit turns them back on.
        return """
_rt_kbd_row:
    ld a,(_rt_a0)
    ld c,a
    ld a,7
    sub a,c
    add a,a
    add a,$10
    ld c,a
    di
    ld hl,$F50200
    ld (hl),h
    xor a,a
_rt_kbd_wait:
    cp a,(hl)
    jr nz,_rt_kbd_wait
    ld l,c
    ld a,(hl)
    ld hl,0
    ld l,a
    ret
"""
    return """
_rt_kbd_row:
    ld a,(_rt_a0)
    ld b,a
    inc b
    ld a,254
    jr _rt_kbd_mask_test
_rt_kbd_mask:
    rlca
_rt_kbd_mask_test:
    djnz _rt_kbd_mask
    ld b,a
    di
    ld a,255
    out (1),a
    ld a,b
    out (1),a
    nop
    nop
    in a,(1)
    ei
    cpl
    ld l,a
    ld h,0
    ret
"""


def _find_var(t: Target) -> str:
    # In: HL = OP1-format name. Out: carry set if missing (or, on classic,
    # archived); otherwise HL = the variable's size word.
    if t.is_ce:
        return """
_rt_find_var:
    call ti.Mov9ToOP1
    call ti.ChkFindSym
    ret c
    ; Archived data lives below RAM ($D00000). Check the address, as Cesium and the
    ; app_tools installer do; B is not a reliable archive flag on the CE.
    ld (_rt_var_found),de
    ex de,hl
    ld a,(_rt_var_found + 2)
    cp a,$D0
    jr c,_rt_find_var_archived
    xor a,a
    ld (_rt_var_archived),a
    ret
_rt_find_var_archived:
    ld a,1
    ld (_rt_var_archived),a
    ld de,9
    add hl,de
    ld a,(hl)
    ld de,0
    ld e,a
    add hl,de
    inc hl
    or a,a
    ret
"""
    return """
_rt_find_var:
    bcall(_Mov9ToOP1)
    bcall(_ChkFindSym)
    ret c
    ld a,b
    ld (_rt_var_archived),a
    ex de,hl
    or a
    ret z
    scf
    ret
"""


def _var_address(t: Target) -> str:
    # In: _rt_a0 name, _rt_a1 byte offset. Out: HL = that byte. A missing
    # variable or an out-of-range offset ends the program safely.
    return """
_rt_var_address:
    ld hl,(_rt_a0)
    call _rt_find_var
    jp c,program_exit
    ld de,0
    ld e,(hl)
    inc hl
    ld d,(hl)
    inc hl
    push hl
    ld hl,(_rt_a1)
    or a
    sbc hl,de
    pop hl
    jp nc,program_exit
    ld de,(_rt_a1)
    add hl,de
    ret
"""


def _var_read(t: Target) -> str:
    return """
_rt_var_read:
    call _rt_var_address
    ld a,(hl)
    ld hl,0
    ld l,a
    ret
"""


def _var_write(t: Target) -> str:
    # Archived variables live in flash, so a write there must not be attempted.
    return """
_rt_var_write:
    call _rt_var_address
    ld a,(_rt_var_archived)
    or a
    jp nz,program_exit
    ld a,(_rt_a2)
    ld (hl),a
    ret
"""


def _var_create(t: Target) -> str:
    # In: _rt_a0 name, _rt_a1 size. An existing variable is left untouched.
    rom = t.rom
    return f"""
_rt_var_create:
    ld hl,(_rt_a0)
    {rom("Mov9ToOP1")}
    {rom("ChkFindSym")}
    ret nc
    ld hl,(_rt_a0)
    {rom("Mov9ToOP1")}
    ld hl,(_rt_a1)
    {rom("CreateAppVar")}
    ex de,hl
    inc hl
    inc hl
    ld bc,(_rt_a1)
    ; Zero the data with a loop. The OS's MemSet runs LDIR on count - 1, so a
    ; 1-byte AppVar would make it copy 16 MB and wipe RAM.
_rt_var_create_zero:
    ld (hl),0
    inc hl
    dec bc
    ld a,b
    or a,c
    jr nz,_rt_var_create_zero
    ret
"""


def _var_exists(t: Target) -> str:
    return """
_rt_var_exists:
    ld hl,(_rt_a0)
    call _rt_find_var
    ld hl,0
    ret c
    inc hl
    ret
"""


def _var_size(t: Target) -> str:
    return """
_rt_var_size:
    ld hl,(_rt_a0)
    call _rt_find_var
    jr c,_rt_var_size_missing
    ld (_rt_a0),hl
    jp _rt_peek16
_rt_var_size_missing:
    ld hl,0
    ret
"""


def _var_delete(t: Target) -> str:
    rom = t.rom
    return f"""
_rt_var_delete:
    ld hl,(_rt_a0)
    {rom("Mov9ToOP1")}
    {rom("ChkFindSym")}
    ret c
    {rom("DelVarArc")}
    ret
"""


def _var_data(t: Target) -> str:
    # HL = first data byte of variable _rt_a0, or 0 if it does not exist.
    return """
_rt_var_data:
    ld hl,(_rt_a0)
    call _rt_find_var
    jr c,_rt_var_data_missing
    inc hl
    inc hl
    ret
_rt_var_data_missing:
    ld hl,0
    ret
"""


RAW: dict[str, Raw] = {
    "_rt_neg": Raw(0, _neg),
    "_rt_abs": Raw(0, _abs, ("_rt_neg",)),
    "_rt_mul": Raw(0, _mul),
    "_rt_udiv": Raw(0, _udiv),
    "_rt_divmod": Raw(0, _divmod, ("_rt_abs", "_rt_neg", "_rt_udiv"),
                      ("_rt_dm_x", "_rt_dm_y", "_rt_dm_q", "_rt_dm_r")),
    "_rt_and": Raw(0, _bitop("and"), (), ("_rt_bit_a", "_rt_bit_b")),
    "_rt_or": Raw(0, _bitop("or"), (), ("_rt_bit_a", "_rt_bit_b")),
    "_rt_xor": Raw(0, _bitop("xor"), (), ("_rt_bit_a", "_rt_bit_b")),
    "_rt_shl": Raw(0, _shl),
    "_rt_sar": Raw(0, _sar, (), ("_rt_bit_a",)),
    "_rt_itoa": Raw(0, _itoa, ("_rt_abs", "_rt_udiv"), ("_rt_it_value", "_rt_it_ptr")),
    "_rt_vram": Raw(2, _vram),
    "_rt_pixel": Raw(3, _pixel, ("_rt_vram",)),
    "_rt_get_pixel": Raw(2, _get_pixel, ("_rt_peek16", "_rt_vram")),
    "_rt_fill_rect": Raw(5, _fill_rect, ("_rt_vram",), ("_rt_fill_ptr", "_rt_fill_cols", "_rt_fill_rows")),
    "_rt_blit_row": Raw(4, _blit_row, ("_rt_vram",)),
    "_rt_peek16": Raw(1, _peek16),
    "_rt_delay": Raw(1, _delay),
    "_rt_kbd_row": Raw(1, _kbd_row),
    "_rt_find_var": Raw(0, _find_var, (), ("_rt_var_archived", "_rt_var_found")),
    "_rt_var_address": Raw(2, _var_address, ("_rt_find_var",)),
    "_rt_var_read": Raw(2, _var_read, ("_rt_var_address",)),
    "_rt_var_write": Raw(3, _var_write, ("_rt_var_address",)),
    "_rt_var_create": Raw(2, _var_create),
    "_rt_var_exists": Raw(1, _var_exists, ("_rt_find_var",)),
    "_rt_var_size": Raw(1, _var_size, ("_rt_find_var", "_rt_peek16")),
    "_rt_var_delete": Raw(1, _var_delete),
    "_rt_var_data": Raw(1, _var_data, ("_rt_find_var",)),
}


def _usb_raw() -> dict[str, Raw]:
    """ti84.usb and ti84.serial helpers (see usbrt.py): _rt_usb_ and _rt_srl_ on the CE, _rt_link_ on classic."""
    from . import usbrt as u

    usb = ("_rt_usb_init",)
    poll = ("_rt_usb_poll", "_rt_usb_setup_packet", *usb)
    return {
        "_rt_usb_init": Raw(0, u.usb_init),
        "_rt_usb_end": Raw(0, u.usb_end, usb),
        "_rt_usb_poll": Raw(0, u.usb_poll, poll),
        "_rt_usb_setup_packet": Raw(0, u.usb_setup, usb),
        "_rt_usb_send": Raw(2, u.usb_send, poll),
        "_rt_usb_role": Raw(0, u.usb_role),
        "_rt_usb_buffer": Raw(0, u.usb_buffer),
        "_rt_usb_peek": Raw(1, u.usb_peek, ("_rt_usb_buffer",)),
        "_rt_usb_poke": Raw(2, u.usb_poke, ("_rt_usb_buffer",)),
        "_rt_srl_connected": Raw(0, u.srl_connected, poll),
        "_rt_srl_read_byte": Raw(0, u.srl_read_byte, poll),
        "_rt_srl_write_byte": Raw(1, u.srl_write_byte, ("_rt_usb_send", *poll)),
        "_rt_link_send": Raw(0, u.link_send),
        "_rt_link_write": Raw(2, u.link_write, ("_rt_link_send",)),
        "_rt_link_write_byte": Raw(1, u.link_write_byte, ("_rt_link_send",)),
        "_rt_link_read_byte": Raw(0, u.link_read_byte),
    }


RAW.update(_usb_raw())


def _font_glyph(t: Target) -> str:
    # Draw character _rt_a1 of the FontLibC font at _rt_a0 at pixel (_rt_a2, _rt_a3)
    # in color _rt_a4, leaving the background; HL = its width, or 0 if the font lacks it.
    # Font: +1 height, +2 glyph count (0 = 256), +3 first glyph, +4 widths offset,
    # +7 bitmap table offset, +11 space above. Each bitmap entry, plus 3, minus the
    # bytes per row, gives the first row; each row's bytes run right to left.
    if not t.is_ce:
        return ""
    return """
_rt_font_glyph:
    push ix
    ld hl,(_rt_a0)
    ld (_rt_fg_font),hl
    ld de,0
    or a,a
    sbc hl,de
    jp z,_rt_fg_none
    ld ix,(_rt_fg_font)
    ld hl,(_rt_a1)
    ld de,256
    or a,a
    sbc hl,de
    jp nc,_rt_fg_none
    ld a,(_rt_a1)
    sub a,(ix+3)
    jp c,_rt_fg_none
    ld c,a
    ld a,(ix+2)
    or a,a
    jp z,_rt_fg_in_range
    ld a,c
    cp a,(ix+2)
    jp nc,_rt_fg_none
_rt_fg_in_range:
    ld de,0
    ld e,c
    ld (_rt_fg_index),de
    ld hl,(ix+4)
    ld de,(_rt_fg_font)
    add hl,de
    ld de,(_rt_fg_index)
    add hl,de
    ld a,(hl)
    ld (_rt_fg_width),a
    or a,a
    jp z,_rt_fg_none
    add a,7
    srl a
    srl a
    srl a
    ld (_rt_fg_columns),a
    ld hl,(ix+7)
    ld de,(_rt_fg_font)
    add hl,de
    ld de,(_rt_fg_index)
    add hl,de
    add hl,de
    ld de,0
    ld e,(hl)
    inc hl
    ld d,(hl)
    ld hl,(_rt_fg_font)
    add hl,de
    ld de,2                      ; + 3 - columns, then + columns - 1 for the row's last byte
    add hl,de
    ld (_rt_fg_last),hl
    ld hl,(_rt_a2)
    ld (_rt_fg_x),hl
    ld hl,(_rt_a4)
    ld (_rt_fg_color),hl
    ld hl,(_rt_a3)
    ld de,0
    ld e,(ix+11)
    add hl,de
    ld (_rt_fg_y),hl
    ld a,(ix+1)
    ld (_rt_fg_rows),a
_rt_fg_row:
    ld a,(_rt_fg_rows)
    or a,a
    jp z,_rt_fg_done
    ld hl,(_rt_fg_y)
    ld de,240
    or a,a
    sbc hl,de
    jp nc,_rt_fg_next_row        ; above or below the screen
    ld hl,0
    ld (_rt_a0),hl
    ld hl,(_rt_fg_y)
    ld (_rt_a1),hl
    call _rt_vram
    ld (_rt_fg_base),hl
    ld hl,(_rt_fg_last)
    ld (_rt_fg_ptr),hl
    ld hl,(_rt_fg_x)
    ld (_rt_fg_px),hl
    ld a,(_rt_fg_width)
    ld b,a
    ld c,0
_rt_fg_pixel:
    ld a,c
    or a,a
    jp nz,_rt_fg_have_bits
    ld hl,(_rt_fg_ptr)
    ld a,(hl)
    dec hl
    ld (_rt_fg_ptr),hl
    ld (_rt_fg_bits),a
    ld c,$80
_rt_fg_have_bits:
    ld a,(_rt_fg_bits)
    and a,c
    jp z,_rt_fg_skip
    ld hl,(_rt_fg_px)
    ld de,320
    or a,a
    sbc hl,de
    jp nc,_rt_fg_skip            ; left or right of the screen
    ld hl,(_rt_fg_px)
    add hl,hl
    ld de,(_rt_fg_base)
    add hl,de
    ld de,(_rt_fg_color)
    ld (hl),e
    inc hl
    ld (hl),d
_rt_fg_skip:
    ld hl,(_rt_fg_px)
    inc hl
    ld (_rt_fg_px),hl
    srl c
    djnz _rt_fg_pixel
_rt_fg_next_row:
    ld hl,(_rt_fg_last)
    ld de,0
    ld a,(_rt_fg_columns)
    ld e,a
    add hl,de
    ld (_rt_fg_last),hl
    ld hl,(_rt_fg_y)
    inc hl
    ld (_rt_fg_y),hl
    ld hl,_rt_fg_rows
    dec (hl)
    jp _rt_fg_row
_rt_fg_done:
    pop ix
    or a,a
    sbc hl,hl
    ld a,(_rt_fg_width)
    ld l,a
    ret
_rt_fg_none:
    pop ix
    or a,a
    sbc hl,hl
    ret
"""


def _line(t: Target) -> str:
    # Bresenham's line from (_rt_a0, _rt_a1) to (_rt_a2, _rt_a3) in color _rt_a4,
    # skipping the pixels off the screen.
    if not t.is_ce:
        return ""
    return """
_rt_line:
    ld hl,(_rt_a0)
    ld (_rt_ln_x),hl
    ld hl,(_rt_a1)
    ld (_rt_ln_y),hl
    ld hl,(_rt_a2)
    ld de,(_rt_a0)
    or a,a
    sbc hl,de
    ld bc,1
    jp p,_rt_ln_dx_known
    ex de,hl
    or a,a
    sbc hl,hl
    sbc hl,de
    ld bc,-1
_rt_ln_dx_known:
    ld (_rt_ln_dx),hl            ; |x2 - x1|
    ld (_rt_ln_sx),bc
    ld hl,(_rt_a3)
    ld de,(_rt_a1)
    or a,a
    sbc hl,de
    ld bc,-1
    jp m,_rt_ln_dy_known
    ex de,hl
    or a,a
    sbc hl,hl
    sbc hl,de
    ld bc,1
_rt_ln_dy_known:
    ld (_rt_ln_dy),hl            ; -|y2 - y1|
    ld (_rt_ln_sy),bc
    ld de,(_rt_ln_dx)
    add hl,de
    ld (_rt_ln_err),hl
_rt_ln_loop:
    ld hl,(_rt_ln_x)
    ld de,320
    or a,a
    sbc hl,de
    jr nc,_rt_ln_moved
    ld hl,(_rt_ln_y)
    ld de,240
    or a,a
    sbc hl,de
    jr nc,_rt_ln_moved
    ld hl,(_rt_ln_x)
    ld (_rt_a0),hl
    ld hl,(_rt_ln_y)
    ld (_rt_a1),hl
    call _rt_vram
    ld de,(_rt_a4)
    ld (hl),e
    inc hl
    ld (hl),d
_rt_ln_moved:
    ld hl,(_rt_ln_x)
    ld de,(_rt_a2)
    or a,a
    sbc hl,de
    jr nz,_rt_ln_step
    ld hl,(_rt_ln_y)
    ld de,(_rt_a3)
    or a,a
    sbc hl,de
    ret z
_rt_ln_step:
    ld hl,(_rt_ln_err)
    add hl,hl
    ld (_rt_ln_e2),hl
    ld de,(_rt_ln_dy)
    or a,a
    sbc hl,de
    jp m,_rt_ln_no_x             ; e2 < dy
    ld hl,(_rt_ln_err)
    add hl,de
    ld (_rt_ln_err),hl
    ld hl,(_rt_ln_x)
    ld de,(_rt_ln_sx)
    add hl,de
    ld (_rt_ln_x),hl
_rt_ln_no_x:
    ld hl,(_rt_ln_dx)
    ld de,(_rt_ln_e2)
    or a,a
    sbc hl,de
    jp m,_rt_ln_loop             ; e2 > dx
    ld hl,(_rt_ln_err)
    ld de,(_rt_ln_dx)
    add hl,de
    ld (_rt_ln_err),hl
    ld hl,(_rt_ln_y)
    ld de,(_rt_ln_sy)
    add hl,de
    ld (_rt_ln_y),hl
    jp _rt_ln_loop
"""


def _vat(t: Target) -> str:
    # Walk the variable table with os.NextSymEntry, keeping each variable's name in
    # OP1 form (type, name, 0) so _rt_var_data can find its data.
    if not t.is_ce:
        return ""
    return """
_rt_vat_start:
    push ix
    call ti.os.GetSymTablePtr
    pop ix
    ld iy,ti.flags
    ret
_rt_vat_next:
    push ix
    ld de,_rt_vat_data
    push de
    ld de,_rt_vat_name+1
    push de
    ld de,_rt_vat_length
    push de
    ld de,_rt_vat_type
    push de
    ld hl,(_rt_a0)
    push hl
    call ti.os.NextSymEntry
    pop bc
    pop bc
    pop bc
    pop bc
    pop bc
    pop ix
    ld iy,ti.flags
    ld de,0
    or a,a
    sbc hl,de
    ret z
    add hl,de
    push hl
    ld hl,(_rt_vat_length)
    ld de,9
    or a,a
    sbc hl,de
    jr c,_rt_vat_name_fits
    xor a,a
    ld (_rt_vat_type),a          ; too long for an AppVar: skip it
_rt_vat_name_fits:
    ld a,(_rt_vat_type)
    and a,$1F
    ld (_rt_vat_name),a
    ld hl,(_rt_vat_length)
    ld de,_rt_vat_name+1
    add hl,de
    ld (hl),0
    pop hl
    ret
; The address of the current variable's OP1-form name if it is an AppVar, else 0.
_rt_vat_appvar:
    ld a,(_rt_vat_name)
    cp a,ti.AppVarObj
    ld hl,_rt_vat_name
    ret z
    or a,a
    sbc hl,hl
    ret
_rt_vat_type: db 0,0,0
_rt_vat_length: db 0,0,0
_rt_vat_data: db 0,0,0
_rt_vat_name: db 0,0,0,0,0,0,0,0,0,0,0
"""


RAW["_rt_vat_start"] = Raw(0, _vat)
RAW["_rt_vat_next"] = Raw(1, lambda t: "", ("_rt_vat_start",))
RAW["_rt_vat_appvar"] = Raw(0, lambda t: "", ("_rt_vat_start",))


RAW["_rt_line"] = Raw(5, _line, ("_rt_vram",), ("_rt_ln_x", "_rt_ln_y", "_rt_ln_dx", "_rt_ln_dy", "_rt_ln_sx",
                                              "_rt_ln_sy", "_rt_ln_err", "_rt_ln_e2"))


RAW["_rt_font_glyph"] = Raw(5, _font_glyph, ("_rt_vram",),
                            ("_rt_fg_font", "_rt_fg_index", "_rt_fg_width", "_rt_fg_columns", "_rt_fg_last",
                             "_rt_fg_x", "_rt_fg_y", "_rt_fg_color", "_rt_fg_rows", "_rt_fg_base", "_rt_fg_ptr",
                             "_rt_fg_px", "_rt_fg_bits"))

# sin(0..90 degrees) * 256, matching the Flash App runtime's table.
SIN_TABLE = (
    "_TIPY_SIN = (0, 4, 9, 13, 18, 22, 27, 31, 36, 40, 44, 49, 53, 58, 62, 66, 71, 75, 79, 83, "
    "88, 92, 96, 100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 139, 143, 147, 150, 154, 158, "
    "161, 165, 168, 171, 175, 178, 181, 184, 187, 190, 193, 196, 199, 202, 204, 207, 210, 212, "
    "215, 217, 219, 222, 224, 226, 228, 230, 232, 234, 236, 237, 239, 241, 242, 243, 245, 246, "
    "247, 248, 249, 250, 251, 252, 253, 254, 254, 255, 255, 255, 256, 256, 256, 256)\n"
)

PRELUDE = SIN_TABLE + r'''
def _tipy_fill_rect(x, y, w, h, c):
    x1 = x + w
    y1 = y + h
    if x < 0:
        x = 0
    if y < 0:
        y = 0
    if x1 > SCREEN_W:
        x1 = SCREEN_W
    if y1 > SCREEN_H:
        y1 = SCREEN_H
    if x < x1 and y < y1:
        _rt_fill_rect(x, y, x1, y1, c)

def _tipy_rect(x, y, w, h, c):
    _tipy_fill_rect(x, y, w + 1, 1, c)
    _tipy_fill_rect(x, y + h, w + 1, 1, c)
    _tipy_fill_rect(x, y, 1, h + 1, c)
    _tipy_fill_rect(x + w, y, 1, h + 1, c)

def _tipy_line(x1, y1, x2, y2, c):
    dx = abs(x2 - x1)
    dy = -abs(y2 - y1)
    sx = 1 if x1 < x2 else -1
    sy = 1 if y1 < y2 else -1
    err = dx + dy
    while True:
        _rt_pixel(x1, y1, c)
        if x1 == x2 and y1 == y2:
            break
        e2 = err + err
        if e2 >= dy:
            err += dy
            x1 += sx
        if e2 <= dx:
            err += dx
            y1 += sy

def _tipy_circle(cx, cy, r, c):
    x = r
    y = 0
    err = 1 - r
    while x >= y:
        _rt_pixel(cx + x, cy + y, c)
        _rt_pixel(cx + y, cy + x, c)
        _rt_pixel(cx - y, cy + x, c)
        _rt_pixel(cx - x, cy + y, c)
        _rt_pixel(cx - x, cy - y, c)
        _rt_pixel(cx - y, cy - x, c)
        _rt_pixel(cx + y, cy - x, c)
        _rt_pixel(cx + x, cy - y, c)
        y += 1
        if err < 0:
            err += y + y + 1
        else:
            x -= 1
            err += (y - x) + (y - x) + 1

def _tipy_fill_circle(cx, cy, r, c):
    x = r
    y = 0
    err = 1 - r
    while x >= y:
        _tipy_fill_rect(cx - x, cy + y, x + x + 1, 1, c)
        _tipy_fill_rect(cx - x, cy - y, x + x + 1, 1, c)
        _tipy_fill_rect(cx - y, cy + x, y + y + 1, 1, c)
        _tipy_fill_rect(cx - y, cy - x, y + y + 1, 1, c)
        y += 1
        if err < 0:
            err += y + y + 1
        else:
            x -= 1
            err += (y - x) + (y - x) + 1

def _tipy_edge(ax, ay, bx, by, scan):
    if ay == by:
        return ax
    return ax + (scan - ay) * (bx - ax) // (by - ay)

def _tipy_triangle(x0, y0, x1, y1, x2, y2, c):
    if y1 < y0:
        x0, y0, x1, y1 = x1, y1, x0, y0
    if y2 < y1:
        x1, y1, x2, y2 = x2, y2, x1, y1
    if y1 < y0:
        x0, y0, x1, y1 = x1, y1, x0, y0
    scan = max(y0, 0)
    stop = min(y2, SCREEN_H - 1)
    while scan <= stop:
        a = _tipy_edge(x0, y0, x2, y2, scan)
        if scan < y1:
            b = _tipy_edge(x0, y0, x1, y1, scan)
        else:
            b = _tipy_edge(x1, y1, x2, y2, scan)
        left = min(a, b)
        _tipy_fill_rect(left, scan, max(a, b) - left + 1, 1, c)
        scan += 1

def _tipy_is_down(key):
    if key < 1 or key > 56:
        return 0
    return (_rt_kbd_row((key - 1) >> 3) >> ((key - 1) & 7)) & 1

def _tipy_sqrt(value):
    if value <= 0:
        return 0
    n = value
    bit = SQRT_BIT
    result = 0
    while bit > n:
        bit >>= 2
    while bit > 0:
        if n >= result + bit:
            n -= result + bit
            result = (result >> 1) + bit
        else:
            result >>= 1
        bit >>= 2
    return result

def _tipy_pow(base, exponent):
    if exponent < 0:
        return 0
    result = 1
    while exponent > 0:
        result *= base
        exponent -= 1
    return result

def _tipy_sin(degrees):
    degrees %= 360
    negative = 0
    if degrees >= 180:
        negative = 1
        degrees -= 180
    if degrees > 90:
        degrees = 180 - degrees
    value = _TIPY_SIN[degrees]
    return -value if negative else value

def _tipy_cos(degrees):
    return _tipy_sin(degrees + 90)

def _tipy_seed(seed):
    global _tipy_rng
    _tipy_rng = seed & 0xFFFF
    if _tipy_rng == 0:
        _tipy_rng = 0xACE1

def _tipy_next():
    global _tipy_rng
    if _tipy_rng == 0:
        _tipy_rng = 0xACE1
    x = _tipy_rng
    x = (x ^ (x << 7)) & 0xFFFF
    x = x ^ ((x >> 9) & 127)
    x = (x ^ (x << 8)) & 0xFFFF
    _tipy_rng = x
    return x & 0x7FFF

def _tipy_randrange(limit):
    if limit <= 0:
        return 0
    return _tipy_next() % limit

def _tipy_randint(low, high):
    return low + _tipy_randrange(high - low + 1)

def _tipy_min(a, b):
    return a if a < b else b

def _tipy_max(a, b):
    return a if a > b else b

def _tipy_sprite_draw(sprite, x, y):
    if sprite == 0:
        return
    w = _rt_peek16(sprite)
    h = _rt_peek16(sprite + 2)
    skip = 0
    count = w
    if x < 0:
        skip = -x
        count += x
        x = 0
    if x + count > SCREEN_W:
        count = SCREEN_W - x
    if count <= 0:
        return
    row = 0
    if y < 0:
        row = -y
    while row < h and y + row < SCREEN_H:
        _rt_blit_row(x, y + row, sprite + 4 + (row * w + skip) * 2, count)
        row += 1

def _tipy_sprite_load(name, index):
    # Skip `index` sprites of a pack, and return 0 past its end.
    sprite = _rt_var_data(name)
    if sprite == 0 or index < 0:
        return 0
    left = _rt_peek16(sprite - 2)
    while index > 0:
        step = 4 + _rt_peek16(sprite) * _rt_peek16(sprite + 2) * 2
        sprite += step
        left -= step
        index -= 1
    if left < 4:
        return 0
    return sprite

def _tipy_os_color(c):
    # The OS font routines take colors with red and blue swapped.
    return ((c & 31) << 11) | (c & 0x7E0) | ((c >> 11) & 31)

def _tipy_byte(address):
    return _rt_peek16(address) & 255

def _tipy_word24(address):
    return _rt_peek16(address) | (_tipy_byte(address + 2) << 16)

def _tipy_font_pack(name):
    # The AppVar's data, if it is a FONTPACK as convfont and the font asset kind write.
    return _tipy_font_pack_at(_rt_var_data(name))

def _tipy_font_pack_at(pack):
    if pack == 0:
        return 0
    if _rt_peek16(pack) != 0x4F46 or _rt_peek16(pack + 2) != 0x544E:
        return 0
    if _rt_peek16(pack + 4) != 0x4150 or _rt_peek16(pack + 6) != 0x4B43:
        return 0
    return pack

def _tipy_font_count(name):
    return _tipy_font_count_in(_tipy_font_pack(name))

def _tipy_font_count_in(pack):
    return _tipy_byte(pack + 11) if pack else 0

def _tipy_font_load(name, index):
    return _tipy_font_in(_tipy_font_pack(name), index)

def _tipy_font_in(pack, index):
    if pack == 0 or index < 0 or index >= _tipy_byte(pack + 11):
        return 0
    font = pack + _tipy_word24(pack + 12 + index * 3)
    return font if _tipy_byte(font) == 0 else 0

def _tipy_font_find(n):
    # The n-th font pack AppVar on the calculator, in the order the OS keeps them.
    entry = _rt_vat_start()
    while True:
        entry = _rt_vat_next(entry)
        if entry == 0:
            return 0
        name = _rt_vat_appvar()
        if name:
            pack = _tipy_font_pack_at(_rt_var_data(name))
            if pack:
                if n == 0:
                    return pack
                n -= 1

def _tipy_font_family(pack):
    # The address of the pack's family name, from its metadata; 0 if it has none.
    if pack == 0:
        return 0
    meta = _tipy_word24(pack + 8)
    if meta == 0:
        return 0
    name = _tipy_word24(pack + meta + 3)
    return pack + name if name else 0

def _tipy_font_by_style(pack, min_height, max_height, min_weight, max_weight, styles_set, styles_unset):
    # As fontlib_GetFontByStyle: the first font whose height, weight, and style match.
    count = _tipy_font_count_in(pack)
    index = 0
    while index < count:
        font = _tipy_font_in(pack, index)
        if font:
            height = _tipy_byte(font + 1)
            weight = _tipy_byte(font + 13)
            style = _tipy_byte(font + 14)
            if min_height <= height <= max_height and min_weight <= weight <= max_weight:
                if (style & styles_set) == styles_set and (style & styles_unset) == 0:
                    return font
        index += 1
    return 0

def _tipy_font_by_style_named(name, min_height, max_height, min_weight, max_weight, styles_set, styles_unset):
    return _tipy_font_by_style(_tipy_font_pack(name), min_height, max_height, min_weight, max_weight,
                               styles_set, styles_unset)

def _tipy_font_put(font, code, x, y, color, background):
    # One character, over a background of the line's height unless it is -1.
    if background >= 0:
        _tipy_fill_rect(x, y, _tipy_font_width(font, code), _tipy_font_height(font), background)
    return _rt_font_glyph(font, code, x, y, color)

def _tipy_font_text(font, text, x, y, color, background):
    code = _tipy_byte(text)
    while code:
        x += _tipy_font_put(font, code, x, y, color, background)
        text += 1
        code = _tipy_byte(text)
    return x

def _tipy_font_text_width(font, text):
    width = 0
    code = _tipy_byte(text)
    while code:
        width += _tipy_font_width(font, code)
        text += 1
        code = _tipy_byte(text)
    return width

def _tipy_font_paragraph(font, text, x, y, width, color, background):
    # Word-wrap text into lines of at most width pixels; return the y below it.
    left = x
    right = x + width
    line = _tipy_font_height(font)
    code = _tipy_byte(text)
    while code:
        if code == 10:
            x = left
            y += line
            text += 1
        elif code == 32:
            if x > left:
                x += _tipy_font_put(font, 32, x, y, color, background)
            text += 1
        else:
            end = text
            word = 0
            ch = code
            while ch != 0 and ch != 32 and ch != 10:
                word += _tipy_font_width(font, ch)
                end += 1
                ch = _tipy_byte(end)
            if x + word > right and x > left:
                x = left
                y += line
            while text < end:
                x += _tipy_font_put(font, _tipy_byte(text), x, y, color, background)
                text += 1
        code = _tipy_byte(text)
    return y + line

def _tipy_font_height(font):
    # A line: the glyphs' height plus the font's space above and below.
    if font == 0:
        return 0
    return _tipy_byte(font + 1) + _tipy_byte(font + 11) + _tipy_byte(font + 12)

def _tipy_font_glyph(font, code):
    first = _tipy_byte(font + 3)
    total = _tipy_byte(font + 2)
    if total == 0:
        total = 256
    index = code - first
    if index < 0 or index >= total:
        return -1
    return index

def _tipy_font_width(font, code):
    if font == 0:
        return 0
    index = _tipy_font_glyph(font, code)
    if index < 0:
        return 0
    return _tipy_byte(font + _tipy_word24(font + 4) + index)

def _tipy_sprite_width(sprite):
    return _rt_peek16(sprite) if sprite else 0

def _tipy_sprite_height(sprite):
    return _rt_peek16(sprite + 2) if sprite else 0

def _tipy_luma(c):
    return (((c >> 11) & 31) * 77 + ((c >> 5) & 63) * 75 + (c & 31) * 29) >> 8

def _tipy_from_rgb(r, g, b):
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)

def _tipy_from_rgb_mono(r, g, b):
    return 0 if (r * 3 + g * 6 + b) // 10 >= 128 else 1

def _tipy_invert(c):
    return c ^ 0xFFFF

def _tipy_grayscale(c):
    y = _tipy_luma(c)
    return (y << 11) | (y << 6) | y

def _tipy_to_mono(c):
    return 0 if _tipy_luma(c) >= 16 else 1

def _tipy_from_mono(m):
    return 0xFFFF if m == 0 else 0

def _tipy_bool(m):
    return 0 if m == 0 else 1

def _tipy_read_u16(name, offset):
    return _rt_var_read(name, offset) | (_rt_var_read(name, offset + 1) << 8)

def _tipy_write_u16(name, offset, value):
    _rt_var_write(name, offset, value & 255)
    _rt_var_write(name, offset + 1, (value >> 8) & 255)

def _tipy_file_clear(name):
    size = _rt_var_size(name)
    for offset in range(size):
        _rt_var_write(name, offset, 0)

def _tipy_is_valid(c):
    return 1 if 0 <= c and c <= 0xFFFF else 0
'''


def prelude_tree(target: Target) -> ast.Module:
    width, height = (320, 240) if target.is_ce else (96, 64)
    source = (PRELUDE.replace("SCREEN_W", str(width)).replace("SCREEN_H", str(height))
              .replace("SQRT_BIT", str(1 << (target.bits - 2))))
    return ast.parse(source)


def render(names: set[str], target: Target) -> tuple[list[str], list[str]]:
    """Return the assembly for ``names`` plus their dependencies, and their data."""
    pending, seen = list(names), set()
    while pending:
        name = pending.pop()
        if name not in seen:
            seen.add(name)
            pending.extend(RAW[name].deps)
    code = [text for text in (RAW[name].code(target).rstrip() for name in sorted(seen)) if text]
    words = sorted({word for name in seen for word in RAW[name].words})
    args = max((RAW[name].args for name in seen), default=0)
    data = [target.word(word) for word in words] + [target.word(f"_rt_a{i}") for i in range(args)]
    if "_rt_find_var" in seen:
        data = [line for line in data if not line.startswith("_rt_var_archived")]
        data.append(target.bytes("_rt_var_archived", 0))
    return code, data
