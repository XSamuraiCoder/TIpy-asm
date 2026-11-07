; These instructions mean the same on the Z80 and the eZ80, so this one file
; serves both targets. Arguments arrive in HL, DE, and BC; results go in HL.

; tipy: def sum3(a, b, c)
sum3:
    add hl,de
    add hl,bc
    ret

; Count the set bits. Shifting 24 times covers the CE's 24-bit integers, and on
; the classic's 16-bit registers the extra shifts only move zeros.
; tipy: def popcount(value)
popcount:
    ex de,hl
    ld hl,0
    ld b,24
popcount_next:
    ex de,hl
    add hl,hl
    ex de,hl
    jr nc,popcount_skip
    inc hl
popcount_skip:
    djnz popcount_next
    ret
