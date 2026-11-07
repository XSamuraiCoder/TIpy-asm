; CE version: fill the whole 320x240 RGB565 screen in video RAM.

; tipy: def screen_fill(color)
screen_fill:
    ex de,hl
    ld hl,$D40000
    ld (hl),e
    inc hl
    ld (hl),d
    ld hl,$D40000
    ld de,$D40002
    ld bc,320*240*2-2
    ldir
    ret
