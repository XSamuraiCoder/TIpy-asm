; Classic version: the screen is 1 bit per pixel, so any nonzero color is black.
; Fill the graph buffer, then copy it to the LCD.

; tipy: def screen_fill(color)
screen_fill:
    ld a,h
    or l
    jr z,screen_fill_set
    ld a,$FF
screen_fill_set:
    ld hl,plotSScreen
    ld (hl),a
    ld de,plotSScreen+1
    ld bc,767
    ldir
    bcall(_GrBufCpy)
    ret
