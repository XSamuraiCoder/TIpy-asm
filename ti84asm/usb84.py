"""USB serial on the TI-84 Plus and Plus SE: ti84.serial over the calculator's own USB port.

The 84 Plus's USB controller is a Mentor MUSBFDRC on Z80 ports 80h-AFh (80h
address, 81h power, 82h-86h interrupt status, 8Eh endpoint index, 90h-97h the
selected endpoint's control registers, A0h+n endpoint n's FIFO), with power and
PHY controls at 4Ah-5Bh. None of it is documented by TI. The sequences here
follow the community's notes (WikiTI, Brandon Wilson's port notes) and what
Brandon Wilson's Linky does to act as a USB peripheral; the code is TIpy's own.

The calculator becomes a CDC-ACM serial port with the same ID as the CE driver
(16C0:05E1), so the same host software finds it. Endpoints follow the pipes the
TI OS uses on this hardware: bulk IN 0x81 (endpoint 1), bulk OUT 0x02
(endpoint 2), and the notification endpoint 0x83 (endpoint 3).

The OS normally answers a computer itself, as a TI device. serial.begin() turns
off its USB interrupts (port 5Bh) and cable events (port 57h), restarts the
controller as our device, and from then on the program polls: serial.connected(),
read_byte(), and the writes handle endpoint 0 and the data endpoints. serial.end()
and the program's exit hold the controller in reset and give cable events back
to the OS, so it sets itself up again.

A TI-83 Plus has no USB, so serial uses the link port there instead.
"""

from __future__ import annotations

from .usbrt import CONFIG_DESCRIPTOR as _CE_CONFIG
from .usbrt import DEVICE_DESCRIPTOR, LANGIDS, _string

# The CE configuration with this hardware's endpoints: 0x83 interrupt IN,
# 0x02 bulk OUT, 0x81 bulk IN.
CONFIG_DESCRIPTOR = (_CE_CONFIG.replace(bytes.fromhex("0705820308"), bytes.fromhex("0705830308"))
                     .replace(bytes.fromhex("0705040240"), bytes.fromhex("0705020240"))
                     .replace(bytes.fromhex("0705830240"), bytes.fromhex("0705810240")))
STRINGS = [_string("Texas Instruments Incorporated"), _string("TI-84 Plus")]
EP0_PACKET = 64
TX_PACKET = 63          # each bulk IN packet ends a transfer


def _db(label: str, data: bytes) -> str:
    rows = [",".join(str(b) for b in data[i:i + 16]) for i in range(0, len(data), 16)]
    return f"{label}:\n" + "\n".join(f"    .db {row}" for row in rows)


def _zeros(label: str, count: int) -> str:
    return _db(label, bytes(count))


def _delay(label: str, loops: int = 8000) -> str:
    """About 10 ms or more at either CPU speed."""
    return f"""    ld bc,{loops}
{label}:
    dec bc
    ld a,b
    or c
    jr nz,{label}"""


def u84_begin(_t) -> str:
    # Returns 0 when USB is ready, or 1 when this calculator has no USB (the link
    # port is used then). Either way, serial works afterwards.
    return f"""
_rt_u84_begin:
    ld a,(_rt_u84_mode)
    or a
    jp nz,_rt_u84_begin_ok
    ; USB exists on the 84 Plus and Plus SE: port 2 bit 7 (not an 83 Plus) and
    ; port 21h bits 0-1 (not an 83 Plus SE).
    in a,(2)
    bit 7,a
    jr z,_rt_u84_begin_none
    in a,(21h)
    and 3
    jr nz,_rt_u84_begin_usb
_rt_u84_begin_none:
    ld hl,1
    ret
_rt_u84_begin_usb:
    di
    ; Keep the OS out: no USB protocol interrupts, no cable events.
    xor a
    out (5Bh),a
    out (57h),a
    ; Hold the controller in reset (the computer sees the OS's device leave),
    ; power down the PHY, and set the D- switches to their default.
    out (4Ch),a
    ld a,2
    out (54h),a
    ld a,20h
    out (4Ah),a
    ; Charge pump: the internal one, unless port 3Ah bit 3 says there is an external one.
    xor a
    out (4Bh),a
    in a,(3Ah)
    bit 3,a
    jr z,_rt_u84_begin_pump
    ld a,20h
    out (4Bh),a
_rt_u84_begin_pump:
    xor a
    out (54h),a
{_delay("_rt_u84_begin_wait1")}
    in a,(3Ah)
    bit 3,a
    jr z,_rt_u84_begin_clock
    ld a,44h
    out (54h),a
_rt_u84_begin_clock:
    ld a,0C4h                    ; 48 MHz clock on, PHY powered up
    out (54h),a
{_delay("_rt_u84_begin_wait2")}
    ; Release the controller from reset and wait for its clock.
    ld a,8
    out (4Ch),a
    ld de,0
_rt_u84_begin_clock_wait:
    in a,(4Ch)
    res 6,a
    cp 1Ah
    jr z,_rt_u84_begin_ready
    dec de
    ld a,d
    or e
    jr nz,_rt_u84_begin_clock_wait
_rt_u84_begin_ready:
    ld a,0FFh
    out (87h),a                  ; transmit events
    xor a
    out (92h),a
    ld a,0Eh
    out (89h),a                  ; receive events, endpoints 1-3
    ld a,5
    out (8Bh),a                  ; bus suspend and reset events
    in a,(81h)
    set 0,a
    out (81h),a
    in a,(54h)
    set 0,a
    out (54h),a
    xor a
    out (80h),a
    ld (_rt_u84_configured),a
    ld (_rt_u84_state),a
    ld (_rt_u84_new_address),a
    ld (_rt_u84_rx_head),a
    ld (_rt_u84_rx_tail),a
    ld a,2
    ld (_rt_u84_mode),a
    ei
_rt_u84_begin_ok:
    ld hl,0
    ret

"""


def u84_data(_t) -> str:
    # The driver's state, descriptors, and receive ring, in the data section.
    return f"""
_rt_u84_mode: .db 0              ; 0 not started, 1 link port, 2 USB
_rt_u84_configured: .db 0
_rt_u84_state: .db 0             ; endpoint 0: 0 idle, 1 sending, 2 receiving line coding
_rt_u84_new_address: .db 0       ; nonzero: write it after the status stage
_rt_u84_send_ptr: .dw 0
_rt_u84_send_left: .dw 0
_rt_u84_rx_head: .db 0
_rt_u84_rx_tail: .db 0
_rt_u84_setup: .db 0,0,0,0,0,0,0,0
_rt_u84_line_coding: .db 0,0C2h,1,0,0,0,8
_rt_u84_zero: .db 0,0
{_db("_rt_u84_device_descriptor", DEVICE_DESCRIPTOR)}
{_db("_rt_u84_config_descriptor", CONFIG_DESCRIPTOR)}
{_db("_rt_u84_langids", LANGIDS)}
{_db("_rt_u84_string1", STRINGS[0])}
{_db("_rt_u84_string2", STRINGS[1])}
{_zeros("_rt_u84_rx", 256)}
"""


def u84_end(_t) -> str:
    # Give USB back to the OS, as Linky does when it stops.
    return """
_rt_u84_end:
    ld a,(_rt_u84_mode)
    cp 2
    jr nz,_rt_u84_end_done
    di
    xor a
    out (5Bh),a
    out (4Ch),a                  ; controller held in reset
    ld a,2
    out (54h),a                  ; PHY powered down
    in a,(39h)
    and 0F8h
    out (39h),a
    ; Cable events back to the OS: plug-ins if the bus is powered, else the
    ; OS's own power-off set.
    in a,(4Dh)
    bit 6,a
    ld a,50h
    jr nz,_rt_u84_end_events
    ld a,0D3h
_rt_u84_end_events:
    out (57h),a
    ei
_rt_u84_end_done:
    xor a
    ld (_rt_u84_mode),a
    ld (_rt_u84_configured),a
    ret
"""


def u84_poll(_t) -> str:
    # Handle bus resets, endpoint 0, and received bulk data.
    return f"""
_rt_u84_poll:
    ld a,(_rt_u84_mode)
    cp 2
    ret nz
    in a,(86h)                   ; bus events (reading clears them)
    bit 2,a
    jr z,_rt_u84_poll_ep0
    ; Bus reset: address 0, not configured, control pipe on.
    xor a
    out (80h),a
    ld (_rt_u84_configured),a
    ld (_rt_u84_state),a
    ld (_rt_u84_new_address),a
    in a,(87h)
    or 1
    out (87h),a
_rt_u84_poll_ep0:
    in a,(82h)                   ; transmit events; bit 0 is endpoint 0
    bit 0,a
    call nz,_rt_u84_ep0
    jp _rt_u84_receive

_rt_u84_ep0:
    xor a
    out (8Eh),a
    in a,(91h)                   ; CSR0
    bit 2,a
    jr z,_rt_u84_ep0_not_stalled
    and 0FBh                     ; clear SentStall
    out (91h),a
    xor a
    ld (_rt_u84_state),a
    ret
_rt_u84_ep0_not_stalled:
    bit 4,a
    jr z,_rt_u84_ep0_no_setupend
    ld b,a
    ld a,80h                     ; ServicedSetupEnd
    out (91h),a
    xor a
    ld (_rt_u84_state),a
    ld a,b
_rt_u84_ep0_no_setupend:
    bit 0,a
    jr nz,_rt_u84_ep0_packet
    ; No packet: the previous request finished, or a data packet went out.
    ld a,(_rt_u84_new_address)
    or a
    jr z,_rt_u84_ep0_continue
    out (80h),a
    xor a
    ld (_rt_u84_new_address),a
_rt_u84_ep0_continue:
    ld a,(_rt_u84_state)
    cp 1
    jp z,_rt_u84_ep0_send_next
    ret
_rt_u84_ep0_packet:
    ld a,(_rt_u84_state)
    cp 2
    jp z,_rt_u84_ep0_line_coding
    ; A setup packet: read its 8 bytes.
    ld hl,_rt_u84_setup
    ld b,8
_rt_u84_ep0_read:
    in a,(0A0h)
    ld (hl),a
    inc hl
    djnz _rt_u84_ep0_read
    xor a
    ld (_rt_u84_state),a
    ld hl,(_rt_u84_setup)        ; L = bmRequestType, H = bRequest
    ld a,l
    cp 80h
    jr z,_rt_u84_ep0_in
    cp 81h
    jp z,_rt_u84_ep0_interface_in
    cp 82h
    jp z,_rt_u84_ep0_status_zero
    or a
    jp z,_rt_u84_ep0_device_out
    cp 1
    jp z,_rt_u84_ep0_finish
    cp 2
    jp z,_rt_u84_ep0_finish
    cp 21h
    jp z,_rt_u84_ep0_class_out
    cp 0A1h
    jp z,_rt_u84_ep0_class_in
    jp _rt_u84_ep0_stall
_rt_u84_ep0_in:
    ld a,h
    cp 6
    jr z,_rt_u84_ep0_descriptor
    cp 8
    jr nz,_rt_u84_ep0_not_config
    ld hl,_rt_u84_configured
    ld de,1
    jp _rt_u84_ep0_start_send
_rt_u84_ep0_not_config:
    or a
    jp z,_rt_u84_ep0_status_zero
    jp _rt_u84_ep0_stall
_rt_u84_ep0_descriptor:
    ld a,(_rt_u84_setup+3)
    cp 1
    jr nz,_rt_u84_ep0_desc2
    ld hl,_rt_u84_device_descriptor
    ld de,{len(DEVICE_DESCRIPTOR)}
    jp _rt_u84_ep0_start_send
_rt_u84_ep0_desc2:
    cp 2
    jr nz,_rt_u84_ep0_desc3
    ld hl,_rt_u84_config_descriptor
    ld de,{len(CONFIG_DESCRIPTOR)}
    jp _rt_u84_ep0_start_send
_rt_u84_ep0_desc3:
    cp 3
    jp nz,_rt_u84_ep0_stall
    ld a,(_rt_u84_setup+2)
    ld hl,_rt_u84_langids
    ld de,{len(LANGIDS)}
    or a
    jp z,_rt_u84_ep0_start_send
    ld hl,_rt_u84_string1
    ld de,{len(STRINGS[0])}
    dec a
    jp z,_rt_u84_ep0_start_send
    ld hl,_rt_u84_string2
    ld de,{len(STRINGS[1])}
    dec a
    jp z,_rt_u84_ep0_start_send
    jp _rt_u84_ep0_stall
_rt_u84_ep0_interface_in:
    ld a,h
    cp 0Ah                       ; GET_INTERFACE
    jp nz,_rt_u84_ep0_status_zero
    ld hl,_rt_u84_zero
    ld de,1
    jp _rt_u84_ep0_start_send
_rt_u84_ep0_status_zero:
    ld hl,_rt_u84_zero
    ld de,2
    jp _rt_u84_ep0_start_send
_rt_u84_ep0_device_out:
    ld a,h
    cp 5                         ; SET_ADDRESS: write it after the status stage
    jr nz,_rt_u84_ep0_not_address
    ld a,(_rt_u84_setup+2)
    and 7Fh
    ld (_rt_u84_new_address),a
    jp _rt_u84_ep0_finish
_rt_u84_ep0_not_address:
    cp 9                         ; SET_CONFIGURATION
    jp nz,_rt_u84_ep0_finish
    ld a,(_rt_u84_setup+2)
    ld (_rt_u84_configured),a
    or a
    call nz,_rt_u84_endpoints
    jp _rt_u84_ep0_finish
_rt_u84_ep0_class_out:
    ld a,h
    cp 20h                       ; SET_LINE_CODING: 7 bytes follow
    jp nz,_rt_u84_ep0_finish
    ld a,2
    ld (_rt_u84_state),a
    ld a,40h                     ; ServicedRxPktRdy
    out (91h),a
    ret
_rt_u84_ep0_line_coding:
    in a,(96h)
    ld b,a
    ld hl,_rt_u84_line_coding
    ld c,7
_rt_u84_ep0_line_read:
    ld a,b
    or a
    jr z,_rt_u84_ep0_line_done
    in a,(0A0h)
    dec b
    ld e,a
    ld a,c
    or a
    jr z,_rt_u84_ep0_line_read
    ld (hl),e
    inc hl
    dec c
    jr _rt_u84_ep0_line_read
_rt_u84_ep0_line_done:
    xor a
    ld (_rt_u84_state),a
    jp _rt_u84_ep0_finish
_rt_u84_ep0_class_in:
    ld a,h
    cp 21h                       ; GET_LINE_CODING
    jp nz,_rt_u84_ep0_stall
    ld hl,_rt_u84_line_coding
    ld de,7
_rt_u84_ep0_start_send:
    ; Send at most wLength bytes, 64 at a time.
    push hl
    ld hl,(_rt_u84_setup+6)
    or a
    sbc hl,de
    jr nc,_rt_u84_ep0_length_ok
    ld de,(_rt_u84_setup+6)
_rt_u84_ep0_length_ok:
    pop hl
    ld (_rt_u84_send_ptr),hl
    ld (_rt_u84_send_left),de
    ld a,1
    ld (_rt_u84_state),a
    ld a,40h                     ; ServicedRxPktRdy
    out (91h),a
_rt_u84_ep0_send_next:
    xor a
    out (8Eh),a
    in a,(91h)
    bit 1,a                      ; the last chunk still waiting to go
    ret nz
    ld hl,(_rt_u84_send_left)
    ld a,h
    or l
    jr nz,_rt_u84_ep0_chunk
    xor a
    ld (_rt_u84_state),a
    ret
_rt_u84_ep0_chunk:
    ld de,{EP0_PACKET}
    or a
    sbc hl,de
    jr nc,_rt_u84_ep0_full
    add hl,de
    ld b,l                       ; the last, short chunk
    ld hl,0
    jr _rt_u84_ep0_write
_rt_u84_ep0_full:
    ld b,{EP0_PACKET}
_rt_u84_ep0_write:
    ld (_rt_u84_send_left),hl
    ld hl,(_rt_u84_send_ptr)
_rt_u84_ep0_out:
    ld a,(hl)
    out (0A0h),a
    inc hl
    djnz _rt_u84_ep0_out
    ld (_rt_u84_send_ptr),hl
    ld hl,(_rt_u84_send_left)
    ld a,h
    or l
    ld a,2                       ; TxPktRdy
    jr nz,_rt_u84_ep0_go
    ld a,0Ah                     ; TxPktRdy and DataEnd: the last chunk
    ld hl,_rt_u84_state
    ld (hl),0
_rt_u84_ep0_go:
    out (91h),a
    ret
_rt_u84_ep0_finish:
    ; No data stage: ServicedRxPktRdy and DataEnd, with the reads Linky needs.
    xor a
    out (8Eh),a
    in a,(91h)
    ld a,48h
    out (91h),a
    in a,(91h)
    ret
_rt_u84_ep0_stall:
    xor a
    out (8Eh),a
    ld a,60h                     ; ServicedRxPktRdy and SendStall
    out (91h),a
    ret

; The configuration's endpoints: 1 bulk IN, 3 interrupt IN, 2 bulk OUT.
_rt_u84_endpoints:
    ld a,1
    out (8Eh),a
    ld a,21h
    out (98h),a
    ld a,8                       ; 64 bytes
    out (90h),a
    ld a,48h                     ; clear data toggle, flush
    out (91h),a
    xor a
    out (92h),a
    ld a,3
    out (8Eh),a
    ld a,33h
    out (98h),a
    ld a,1                       ; 8 bytes
    out (90h),a
    ld a,48h
    out (91h),a
    xor a
    out (92h),a
    ld a,2
    out (8Eh),a
    ld a,22h
    out (9Ah),a
    ld a,8
    out (93h),a
    ld a,90h                     ; clear data toggle, flush
    out (94h),a
    xor a
    out (95h),a
    ret

; Move a received packet from endpoint 2 into the ring, if it fits.
_rt_u84_receive:
    ld a,(_rt_u84_configured)
    or a
    ret z
    ld a,2
    out (8Eh),a
    in a,(94h)
    bit 6,a                      ; SentStall
    jr z,_rt_u84_receive_ok
    and 0BFh
    out (94h),a
    ret
_rt_u84_receive_ok:
    bit 0,a                      ; RxPktRdy
    ret z
    in a,(96h)
    ld b,a
    ld a,(_rt_u84_rx_head)
    ld hl,_rt_u84_rx_tail
    sub (hl)
    cpl                          ; room: 255 - (head - tail)
    cp b
    ret c                        ; no room yet: the computer waits
    ld a,b
    or a
    jr z,_rt_u84_receive_done
_rt_u84_receive_copy:
    in a,(0A2h)
    ld c,a
    ld a,(_rt_u84_rx_head)
    ld e,a
    ld d,0
    ld hl,_rt_u84_rx
    add hl,de
    ld (hl),c
    inc a
    ld (_rt_u84_rx_head),a
    djnz _rt_u84_receive_copy
_rt_u84_receive_done:
    ld a,2
    out (8Eh),a
    in a,(94h)
    and 0FEh                     ; clear RxPktRdy
    out (94h),a
    ret
"""


def u84_send(_t) -> str:
    # Send _rt_a1 bytes from _rt_a0 on endpoint 1; returns how many went, or -1
    # if no computer has configured the device.
    return f"""
_rt_u84_send:
    call _rt_u84_poll
    ld a,(_rt_u84_configured)
    or a
    jr nz,_rt_u84_send_start
    ld hl,-1
    ret
_rt_u84_send_start:
    ld hl,0
    ld (_rt_u84_sent),hl
_rt_u84_send_loop:
    ld hl,(_rt_a1)
    ld de,(_rt_u84_sent)
    or a
    sbc hl,de
    jr z,_rt_u84_send_done
    ld de,{TX_PACKET}
    push hl
    or a
    sbc hl,de
    pop hl
    jr c,_rt_u84_send_size
    ld hl,{TX_PACKET}
_rt_u84_send_size:
    ld b,l                       ; this packet's length
    ; Wait for endpoint 1's FIFO to be free, handling events meanwhile.
    ld hl,0
    ld (_rt_u84_wait),hl
_rt_u84_send_wait:
    ld a,1
    out (8Eh),a
    in a,(91h)
    bit 0,a                      ; TxPktRdy: the last packet still waiting
    jr z,_rt_u84_send_packet
    push bc
    call _rt_u84_poll
    pop bc
    ld a,(_rt_u84_configured)
    or a
    jr z,_rt_u84_send_done
    ld hl,(_rt_u84_wait)
    inc hl
    ld (_rt_u84_wait),hl
    ld a,h
    cp 30h
    jr c,_rt_u84_send_wait
    jr _rt_u84_send_done         ; the computer is not reading
_rt_u84_send_packet:
    ld hl,(_rt_a0)
    ld de,(_rt_u84_sent)
    add hl,de
    ld c,b
_rt_u84_send_byte:
    ld a,(hl)
    out (0A1h),a
    inc hl
    djnz _rt_u84_send_byte
    ld a,1
    out (8Eh),a
    ld a,1                       ; TxPktRdy
    out (91h),a
    ld hl,(_rt_u84_sent)
    ld b,0
    add hl,bc
    ld (_rt_u84_sent),hl
    jr _rt_u84_send_loop
_rt_u84_send_done:
    ld hl,(_rt_u84_sent)
    ret
_rt_u84_sent: .dw 0
_rt_u84_wait: .dw 0
"""


def cser(_t) -> str:
    # Classic serial: USB on the 84 Plus/SE, the link port otherwise.
    return """
_rt_cser_connected:
    ld a,(_rt_u84_mode)
    cp 2
    jr z,_rt_cser_connected_usb
    ld hl,1                      ; the link port cannot tell
    ret
_rt_cser_connected_usb:
    call _rt_u84_poll
    ld a,(_rt_u84_configured)
    or a
    ld hl,0
    ret z
    inc hl
    ret
_rt_cser_read_byte:
    ld a,(_rt_u84_mode)
    cp 2
    jp nz,_rt_link_read_byte
    call _rt_u84_poll
    ld a,(_rt_u84_rx_tail)
    ld hl,_rt_u84_rx_head
    cp (hl)
    jr z,_rt_cser_read_none
    ld e,a
    ld d,0
    ld hl,_rt_u84_rx
    add hl,de
    ld e,(hl)
    inc a
    ld (_rt_u84_rx_tail),a
    ex de,hl
    ld h,0
    ret
_rt_cser_read_none:
    ld hl,-1
    ret
_rt_cser_write:
    ld a,(_rt_u84_mode)
    cp 2
    jp nz,_rt_link_write
    jp _rt_u84_send
_rt_cser_write_byte:
    ld a,(_rt_u84_mode)
    cp 2
    jp nz,_rt_link_write_byte
    ld a,(_rt_a0)
    ld (_rt_cser_byte),a
    ld hl,_rt_cser_byte
    ld (_rt_a0),hl
    ld hl,1
    ld (_rt_a1),hl
    call _rt_u84_send
    ld de,1
    or a
    sbc hl,de
    ld hl,1
    ret z
    dec hl
    ret
_rt_cser_byte: .db 0
"""
