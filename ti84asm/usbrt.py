"""Runtime for ti84.usb and ti84.serial: a built-in USB serial driver on the CE, and the classic link port.

On the CE, TIpy drives the USB controller itself, with no LibLoad and no CE C
libraries. The calculator is a USB device: a CDC-ACM serial port, with the same
descriptors and ID (16C0:05E1) as CEdev's srldrvce, so a computer's standard
serial driver (Windows usbser.sys, Linux cdc_acm, Chrome's Web Serial) uses it
with nothing to install.

The controller is not publicly documented. The register sequences here follow
what CEdev's usbdrvce does in device mode (CE-Programming/toolchain, LGPL-3.0),
cut down to one configuration: control endpoint 0, an interrupt IN endpoint
(0x82), and bulk IN (0x83) and OUT (0x04) endpoints. Endpoint n uses FIFO n - 1.
Data moves by the controller's DMA: received bytes from FIFO 3 into a 256-byte
ring, sent bytes into FIFO 2 in packets of up to 63 bytes, so each packet ends
a transfer. There is no USB host support (keyboards, drives, other devices).

Nothing here uses interrupts: the program polls. serial.connected(),
read_byte(), and the write calls handle pending USB events, and usb.poll()
does it directly, so a program should call one of them often.

On the classic calculators, serial uses the link port through the OS's own
byte protocol (_SendAByte and _RecAByteIO), so any program that uses the same
calls on the other calculator can talk to it. A link error, such as no
calculator on the other end, is caught with the OS error handler, so it
returns a failure instead of showing ERR:LINK.
"""

from __future__ import annotations

EVENTS = {
    "ROLE_CHANGED": 0, "DEVICE_DISCONNECTED": 1, "DEVICE_CONNECTED": 2, "DEVICE_DISABLED": 3,
    "DEVICE_ENABLED": 4, "HUB_LOCAL_POWER_GOOD": 5, "HUB_LOCAL_POWER_LOST": 6, "DEVICE_RESUMED": 7,
    "DEVICE_SUSPENDED": 8, "DEVICE_OVERCURRENT_DEACTIVATED": 9, "DEVICE_OVERCURRENT_ACTIVATED": 10,
    "DEFAULT_SETUP": 11, "HOST_CONFIGURE": 12,
}
USB_ERROR_NOT_SUPPORTED = 6
BUFFER_SIZE = 256              # usb.buffer_get()/buffer_set()
TX_PACKET = 63                 # below the 64-byte maximum, so every packet ends a transfer

# Descriptors, as srldrvce's: a CDC-ACM device, 16C0:05E1.
DEVICE_DESCRIPTOR = bytes.fromhex("120100020200004" "0C016E105200201020001")
CONFIG_DESCRIPTOR = bytes.fromhex(
    "09023e00020100c032"                    # configuration: 2 interfaces, bus powered, 100 mA
    "090400000102020000"                    # interface 0: communications, ACM
    "0524000110" "04240200" "0524060001"    # CDC header, ACM, union (0 -> 1)
    "0705820308" "00ff"                     # endpoint 0x82: interrupt IN, 8 bytes
    "0904010002" "0a020000"                 # interface 1: CDC data
    "0705040240" "0001"                     # endpoint 0x04: bulk OUT, 64 bytes
    "0705830240" "0001")                    # endpoint 0x83: bulk IN, 64 bytes
LANGIDS = bytes.fromhex("04030904")


def _string(text: str) -> bytes:
    return bytes((2 + 2 * len(text), 3)) + text.encode("utf-16-le")


STRINGS = [_string("Texas Instruments Incorporated"), _string("TI-84 Plus CE")]
assert len(CONFIG_DESCRIPTOR) == 0x3E


def _db(label: str, data: bytes) -> str:
    rows = [", ".join(f"${b:02X}" for b in data[i:i + 16]) for i in range(0, len(data), 16)]
    return f"{label}:\n" + "\n".join(f"    db {row}" for row in rows)


# A DMA transfer between memory and a FIFO: A = FIFO select, HL = address,
# BC = length, E = direction (ti.usbDmaMem2Fifo or ti.usbDmaFifo2Mem).
# Interrupts stay off while it runs, as usbdrvce does.
_DMA = """
_rt_usb_dma:
    push af
    ld a,i
    di
    push af
    pop iy                       ; keep the interrupt state (P/V) in IY
    pop af
    ld (ti.mpUsbDmaFifo),a
    ld (ti.mpUsbDmaAddr),hl
    ld (ti.mpUsbDmaLen),bc
    ld hl,ti.mpUsbDmaCtrl
    ld (hl),e
    set ti.bUsbDmaStart,(hl)
    ld hl,ti.mpUsbDevIsr
    ld bc,0
_rt_usb_dma_wait:
    bit ti.bUsbIntDevDmaFin,(hl)
    jr nz,_rt_usb_dma_done
    inc hl
    bit ti.bUsbIntDevDmaErr-8,(hl)
    dec hl
    jr nz,_rt_usb_dma_error
    dec bc
    ld a,b
    or a,c
    jr nz,_rt_usb_dma_wait
_rt_usb_dma_error:
    ld a,ti.bmUsbIntDevDmaErr shr 8
    ld (ti.mpUsbDevIsr+1),a
    ld a,ti.bmUsbDmaClrFifo or ti.bmUsbDmaAbort
    ld (ti.mpUsbDmaCtrl),a
    scf
    jr _rt_usb_dma_end
_rt_usb_dma_done:
    ld (hl),ti.bmUsbIntDevDmaFin
    or a,a
_rt_usb_dma_end:
    ld a,ti.bmUsbDmaNoFifo
    ld (ti.mpUsbDmaFifo),a
    push iy
    pop hl
    bit 2,l                      ; P/V: interrupts were on
    jr z,_rt_usb_dma_no_ei
    ei
_rt_usb_dma_no_ei:
    ld iy,ti.flags
    ret
"""


def usb_init(_t) -> str:
    # Start the device controller. Returns 0.
    return f"""
_rt_usb_init:
    ld a,(_rt_usb_active)
    or a,a
    jp nz,_rt_usb_init_ok
    call ti.usb_DisableTimer
    ; Take the controller from the OS, as usbdrvce does: mark the OS's USB state
    ; invalid, so it resets its own stack when the program gives it back.
    ld a,1
    call _rt_usb_os_state
    ld hl,ti.flags+$1B
    set 5,(hl)
    ; Stop the host controller (EHCI section 2.3), which device mode does not use.
    xor a,a
    ld (ti.mpUsbIntEn),a
    ld (ti.mpUsbCmd),a
    ld bc,0
_rt_usb_init_halt:
    ld a,(ti.mpUsbSts+1)
    bit ti.bUsbHcHalted-8,a
    jr nz,_rt_usb_init_halted
    dec bc
    ld a,b
    or a,c
    jr nz,_rt_usb_init_halt
_rt_usb_init_halted:
    ld hl,ti.mpUsbCmd
    ld (hl),ti.bmUsbHcReset
    ld bc,0
_rt_usb_init_reset:
    bit ti.bUsbHcReset,(hl)
    jr z,_rt_usb_init_device
    dec bc
    ld a,b
    or a,c
    jr nz,_rt_usb_init_reset
_rt_usb_init_device:
    ; FIFOs off; FIFO n serves endpoint n + 1, and endpoint n uses FIFO n - 1 both ways.
    ld hl,ti.mpUsbFifo0Cfg
    xor a,a
    ld (hl),a
    inc hl
    ld (hl),a
    inc hl
    ld (hl),a
    inc hl
    ld (hl),a
    ld hl,ti.mpUsbFifo0Map
    ld (hl),$01
    inc hl
    ld (hl),$02
    inc hl
    ld (hl),$03
    inc hl
    ld (hl),$04
    ld hl,ti.mpUsbEp1Map
    ld (hl),$00
    inc hl
    ld (hl),$11
    inc hl
    ld (hl),$22
    inc hl
    ld (hl),$33
    ld a,7
    ld (ti.mpUsbIdle),a
    ld a,ti.bmUsbDevForceFullSpd shr 8
    ld (ti.mpUsbDevCtrl+1),a
    ld a,ti.bmUsbDevReset or ti.bmUsbDevEn or ti.bmUsbGirqEn or ti.bmUsbRemoteWake
    ld (ti.mpUsbDevCtrl),a
    ; Look unplugged, so a computer forgets the OS's own USB device first.
    ld a,ti.bmUsbUnplug
    ld (ti.mpUsbPhyTmsr),a
    xor a,a
    ld (ti.mpUsbGimr),a
    ld (ti.mpUsbCxImr),a
    ld (ti.mpUsbFifoRxImr),a
    ld (ti.mpUsbDevImr),a
    ld a,ti.bmUsbFifoTxInts
    ld (ti.mpUsbFifoTxImr),a
    ld a,ti.bmUsbIntDevIdle shr 8
    ld (ti.mpUsbDevImr+1),a
    ld a,ti.bmUsbIntBSrpComplete or ti.bmUsbIntASrpDetect or ti.bmUsbIntAVbusErr
    ld (ti.mpUsbOtgIer),a
    ld a,(ti.bmUsbIntRoleChg or ti.bmUsbIntIdChg or ti.bmUsbIntOvercurr or ti.bmUsbIntBPlugRemoved or ti.bmUsbIntAPlugRemoved) shr 8
    ld (ti.mpUsbOtgIer+1),a
    ld a,ti.usbIntLevelHigh
    ld (ti.mpUsbImr),a
    ; The bus state of a device (usbdrvce's _PowerVbusForRole, device side).
    ld hl,ti.mpUsbOtgCsr
    res ti.bUsbASrpEn,(hl)
    set ti.bUsbABusDrop,(hl)
    res ti.bUsbABusReq,(hl)
    ld de,_rt_usb_role_byte
    call $021C68
    ld iy,ti.flags
    xor a,a
    ld (_rt_usb_configured),a
    ld (_rt_usb_rx_head),a
    ld (_rt_usb_rx_tail),a
    inc a
    ld (_rt_usb_active),a
    ; Stay unplugged for 100 ms, then let a computer see the serial device.
    ld b,10
_rt_usb_init_wait:
    push bc
    call ti.Delay10ms
    pop bc
    djnz _rt_usb_init_wait
    ld hl,ti.mpUsbPhyTmsr
    res ti.bUsbUnplug,(hl)
_rt_usb_init_ok:
    or a,a
    sbc hl,hl
    ret

; Fill the OS's USB area and its "initialized" byte with A.
_rt_usb_os_state:
    ld hl,ti.usbArea
    ld (hl),a
    ld de,ti.usbArea+1
    ld bc,ti.usbInited-ti.usbArea
    ldir
    ret

_rt_usb_active: db 0
_rt_usb_configured: db 0
_rt_usb_role_byte: db 0
_rt_usb_event: db 255,255,255
_rt_usb_rx_head: db 0
_rt_usb_rx_tail: db 0
_rt_usb_rx: rb 256
_rt_usb_packet: rb 64
_rt_usb_setup: db 0,0,0,0,0,0,0,0
_rt_usb_line_coding: db $00,$C2,$01,$00,$00,$00,$08    ; 115200 8N1
_rt_usb_zero: db 0,0
{_db("_rt_usb_device_descriptor", DEVICE_DESCRIPTOR)}
{_db("_rt_usb_config_descriptor", CONFIG_DESCRIPTOR)}
{_db("_rt_usb_langids", LANGIDS)}
{_db("_rt_usb_string1", STRINGS[0])}
{_db("_rt_usb_string2", STRINGS[1])}
{_DMA}"""


def usb_end(_t) -> str:
    # Give the controller back to the OS, as usbdrvce's usb_Cleanup does.
    return """
_rt_usb_end:
    ld a,(_rt_usb_active)
    or a,a
    ret z
    xor a,a
    ld (_rt_usb_active),a
    ld (_rt_usb_configured),a
    ld (ti.mpUsbGimr),a
    ld (ti.mpUsbDevImr+1),a
    ld a,ti.bmUsbFifoRxInts
    ld (ti.mpUsbFifoRxImr),a
    ld a,ti.bmUsbFifoTxInts
    ld (ti.mpUsbFifoTxImr),a
    xor a,a
    ld (ti.mpUsbIntEn),a
    ld (ti.mpUsbCmd),a
    call _rt_usb_os_state
    ld hl,ti.flags+$1B
    res 5,(hl)
    ret
"""


def usb_poll(_t) -> str:
    # Handle pending device events. Returns 0, or -1 before usb.begin()/serial.begin().
    return f"""
_rt_usb_poll:
    ld a,(_rt_usb_active)
    or a,a
    jr nz,_rt_usb_poll_active
    scf
    sbc hl,hl
    ret
_rt_usb_poll_active:
    ; A computer's power arrived: show the device.
    ld hl,ti.mpUsbDevIsr+1
    bit ti.bUsbIntDevWakeup-8,(hl)
    jr z,_rt_usb_poll_reset
    ld (hl),ti.bmUsbIntDevWakeup shr 8
    ld hl,ti.mpUsbPhyTmsr
    res ti.bUsbUnplug,(hl)
    ld a,{EVENTS["DEVICE_RESUMED"]}
    call _rt_usb_note
_rt_usb_poll_reset:
    ld hl,ti.mpUsbDevIsr
    bit ti.bUsbIntDevReset,(hl)
    jr z,_rt_usb_poll_suspend
    ; Bus reset: back to address 0, unconfigured, with empty FIFOs.
    ld (hl),ti.bmUsbIntDevReset
    xor a,a
    ld (ti.mpUsbDevAddr),a
    ld (_rt_usb_configured),a
    ld a,ti.bmUsbDmaClrFifo or ti.bmUsbDmaAbort
    ld (ti.mpUsbDmaCtrl),a
    ld hl,ti.mpUsbCxFifo
    set ti.bCxFifoClr,(hl)
    ld a,{EVENTS["DEVICE_DISCONNECTED"]}
    call _rt_usb_note
_rt_usb_poll_suspend:
    ld hl,ti.mpUsbDevIsr
    ld a,(hl)
    and a,ti.bmUsbIntDevSuspend or ti.bmUsbIntDevResume or ti.bmUsbIntDevZlpTx or ti.bmUsbIntDevZlpRx
    jr z,_rt_usb_poll_cx
    ld (hl),a
    xor a,a
    ld (ti.mpUsbTxZlp),a
    ld (ti.mpUsbRxZlp),a
_rt_usb_poll_cx:
    ld hl,ti.mpUsbCxIsr
    bit ti.bUsbIntCxSetup,(hl)
    call nz,_rt_usb_setup_packet
    ld hl,ti.mpUsbCxIsr
    bit ti.bUsbIntCxEnd,(hl)
    jr z,_rt_usb_poll_cx_rest
    ld a,ti.bmCxFifoFin
    ld (ti.mpUsbCxFifo),a
    ld (hl),ti.bmUsbIntCxEnd
_rt_usb_poll_cx_rest:
    ld a,(hl)
    and a,ti.bmUsbIntCxIn or ti.bmUsbIntCxOut or ti.bmUsbIntCxErr or ti.bmUsbIntCxAbort
    jr z,_rt_usb_poll_rx
    ld (hl),a
_rt_usb_poll_rx:
    call _rt_usb_receive
    ; Role changes and plug events: note them and acknowledge.
    ld hl,ti.mpUsbOtgIsr
    ld a,(hl)
    or a,a
    jr z,_rt_usb_poll_otg_high
    ld (hl),a
_rt_usb_poll_otg_high:
    inc hl
    ld a,(hl)
    or a,a
    jr z,_rt_usb_poll_ack
    ld (hl),a
    ld a,{EVENTS["ROLE_CHANGED"]}
    call _rt_usb_note
_rt_usb_poll_ack:
    ld a,ti.bmUsbDevIntCx or ti.bmUsbDevIntFifo or ti.bmUsbDevIntDev
    ld (ti.mpUsbGisr),a
    ld a,ti.bmUsbIntDev or ti.bmUsbIntOtg or ti.bmUsbIntHost
    ld (ti.mpUsbIsr),a
    ld a,ti.intUsb shr 8
    ld (ti.mpIntAck+1),a
    or a,a
    sbc hl,hl
    ret

_rt_usb_note:
    ld hl,0
    ld l,a
    ld (_rt_usb_event),hl
    ret

; Move a received packet from FIFO 3 (endpoint 0x04) into the ring, if it fits.
_rt_usb_receive:
    ld a,(ti.mpUsbFifoRxIsr)
    and a,ti.bmUsbIntFifo3Out or ti.bmUsbIntFifo3Spk
    ret z
    ld hl,(ti.mpUsbFifo3Csr)
    ld a,h
    and a,7
    ld b,a
    ld c,l                       ; BC = bytes in the FIFO
    ld a,b
    or a,c
    jr z,_rt_usb_receive_ack
    ; Room: 255 - (head - tail) bytes.
    ld a,(_rt_usb_rx_head)
    ld hl,_rt_usb_rx_tail
    sub a,(hl)
    cpl
    cp a,c
    ret c                        ; no room yet: leave it, so the computer waits
    push bc
    ld a,1 shl 3
    ld hl,_rt_usb_packet
    ld e,ti.usbDmaFifo2Mem
    call _rt_usb_dma
    pop bc
    jr c,_rt_usb_receive_ack
    ld hl,_rt_usb_packet
    ld b,c
_rt_usb_receive_copy:
    push hl
    ld de,0
    ld a,(_rt_usb_rx_head)
    ld e,a
    ld hl,_rt_usb_rx
    add hl,de
    ex de,hl
    pop hl
    ld a,(hl)
    ld (de),a
    inc hl
    ld a,(_rt_usb_rx_head)
    inc a
    ld (_rt_usb_rx_head),a
    djnz _rt_usb_receive_copy
_rt_usb_receive_ack:
    ld a,ti.bmUsbIntFifo3Out or ti.bmUsbIntFifo3Spk
    ld (ti.mpUsbFifoRxIsr),a
    ret
"""


def usb_setup(_t) -> str:
    # Answer a setup packet on endpoint 0: the standard requests a computer sends
    # while it sets the device up, and the CDC serial line requests.
    def cases() -> str:
        return """
    ld hl,(_rt_usb_setup)        ; L = bmRequestType, H = bRequest
    ld a,l
    cp a,$80
    jp z,_rt_usb_setup_in
    cp a,$00
    jp z,_rt_usb_setup_device_out
    cp a,$81
    jp z,_rt_usb_setup_interface_in
    cp a,$82
    jp z,_rt_usb_setup_status_zero
    cp a,$01
    jp z,_rt_usb_setup_ack
    cp a,$02
    jp z,_rt_usb_setup_ack
    cp a,$21
    jp z,_rt_usb_setup_class_out
    cp a,$A1
    jp z,_rt_usb_setup_class_in
    jp _rt_usb_setup_stall
"""
    return f"""
_rt_usb_setup_packet:
    ; Read the 8-byte setup packet through the control FIFO, as usbdrvce does.
    ld a,i
    di
    push af
    ld a,ti.bmUsbDmaCxFifo
    ld (ti.mpUsbDmaFifo),a
    ld hl,ti.mpUsbEp0Data+4
    ld de,_rt_usb_setup+4
    ld b,4
_rt_usb_setup_fetch:
    dec hl
    dec de
    ld a,(hl)
    ld (de),a
    push de
    inc de
    inc de
    inc de
    inc de
    ld a,(hl)
    ld (de),a
    pop de
    djnz _rt_usb_setup_fetch
    xor a,a
    ld (ti.mpUsbDmaFifo),a
    pop af
    jp po,_rt_usb_setup_no_ei
    ei
_rt_usb_setup_no_ei:
    ld hl,ti.mpUsbCxFifo
    set ti.bCxFifoClr,(hl)
    ld a,{EVENTS["DEFAULT_SETUP"]}
    call _rt_usb_note
{cases()}
_rt_usb_setup_in:                ; standard device-to-host
    ld a,h
    cp a,6                       ; GET_DESCRIPTOR
    jr z,_rt_usb_setup_descriptor
    cp a,8                       ; GET_CONFIGURATION
    jr z,_rt_usb_setup_get_config
    or a,a                       ; GET_STATUS
    jp z,_rt_usb_setup_status_zero
    jp _rt_usb_setup_stall
_rt_usb_setup_get_config:
    ld hl,_rt_usb_configured
    ld bc,1
    jp _rt_usb_setup_send
_rt_usb_setup_descriptor:
    ld a,(_rt_usb_setup+3)       ; descriptor type
    cp a,1
    jr nz,_rt_usb_setup_not_device
    ld hl,_rt_usb_device_descriptor
    ld bc,{len(DEVICE_DESCRIPTOR)}
    jp _rt_usb_setup_send
_rt_usb_setup_not_device:
    cp a,2
    jr nz,_rt_usb_setup_not_config
    ld hl,_rt_usb_config_descriptor
    ld bc,{len(CONFIG_DESCRIPTOR)}
    jp _rt_usb_setup_send
_rt_usb_setup_not_config:
    cp a,3
    jp nz,_rt_usb_setup_stall
    ld a,(_rt_usb_setup+2)       ; string index
    ld hl,_rt_usb_langids
    ld bc,{len(LANGIDS)}
    or a,a
    jp z,_rt_usb_setup_send
    ld hl,_rt_usb_string1
    ld bc,{len(STRINGS[0])}
    dec a
    jp z,_rt_usb_setup_send
    ld hl,_rt_usb_string2
    ld bc,{len(STRINGS[1])}
    dec a
    jp z,_rt_usb_setup_send
    jp _rt_usb_setup_stall
_rt_usb_setup_device_out:        ; standard host-to-device
    ld a,h
    cp a,5                       ; SET_ADDRESS
    jr nz,_rt_usb_setup_not_address
    ld a,(_rt_usb_setup+2)
    and a,$7F
    ld (ti.mpUsbDevAddr),a
    jp _rt_usb_setup_ack
_rt_usb_setup_not_address:
    cp a,9                       ; SET_CONFIGURATION
    jp nz,_rt_usb_setup_ack      ; features: accept
    ld a,(_rt_usb_setup+2)
    or a,a
    jr z,_rt_usb_setup_unconfigure
    call _rt_usb_configure_endpoints
    ld a,1
    ld (_rt_usb_configured),a
    ld hl,ti.mpUsbDevAddr
    set 7,(hl)
    ld a,{EVENTS["HOST_CONFIGURE"]}
    call _rt_usb_note
    jp _rt_usb_setup_ack
_rt_usb_setup_unconfigure:
    ld (_rt_usb_configured),a
    ld hl,ti.mpUsbDevAddr
    res 7,(hl)
    jp _rt_usb_setup_ack
_rt_usb_setup_interface_in:      ; GET_STATUS or GET_INTERFACE of an interface
    ld a,h
    cp a,$0A
    jp nz,_rt_usb_setup_status_zero
    ld hl,_rt_usb_zero
    ld bc,1
    jp _rt_usb_setup_send
_rt_usb_setup_status_zero:
    ld hl,_rt_usb_zero
    ld bc,2
    jp _rt_usb_setup_send
_rt_usb_setup_class_out:         ; CDC: SET_LINE_CODING takes 7 bytes; others need none
    ld a,h
    cp a,$20
    jp nz,_rt_usb_setup_ack
    ld hl,_rt_usb_line_coding
    ld bc,7
    ld e,ti.usbDmaFifo2Mem
    jr _rt_usb_setup_data
_rt_usb_setup_class_in:          ; CDC: GET_LINE_CODING
    ld a,h
    cp a,$21
    jp nz,_rt_usb_setup_stall
    ld hl,_rt_usb_line_coding
    ld bc,7
_rt_usb_setup_send:
    ld e,ti.usbDmaMem2Fifo
_rt_usb_setup_data:
    ; Send or receive at most wLength bytes through the control FIFO.
    push hl
    ld hl,(_rt_usb_setup+6)
    ex.s de,hl                   ; DE = wLength, L = direction
    ld a,l
    ld hl,0
    add hl,de
    or a,a
    sbc hl,bc
    jr nc,_rt_usb_setup_fits
    push de
    pop bc
_rt_usb_setup_fits:
    ld e,a
    pop hl
    ld a,b
    or a,c
    jr z,_rt_usb_setup_ack
    ld a,ti.bmUsbDmaCxFifo
    call _rt_usb_dma
    jr c,_rt_usb_setup_stall
_rt_usb_setup_ack:
    ld a,ti.bmCxFifoFin
    jr _rt_usb_setup_done
_rt_usb_setup_stall:
    ld a,ti.bmCxFifoStall
_rt_usb_setup_done:
    ld (ti.mpUsbCxFifo),a
    ld a,ti.bmUsbIntCxSetup
    ld (ti.mpUsbCxIsr),a
    ret

; Set up the three endpoints of the configuration: 0x82 interrupt IN on FIFO 1,
; 0x83 bulk IN on FIFO 2, and 0x04 bulk OUT on FIFO 3.
_rt_usb_configure_endpoints:
    ld hl,ti.mpUsbDevTest
    set ti.bUsbTstClrFifo,(hl)
    res ti.bUsbTstClrFifo,(hl)
    ld hl,ti.mpUsbFifo1Map
    ld a,(hl)
    and a,not ti.bmUsbFifoDir
    or a,ti.usbFifoIn
    ld (hl),a
    inc hl
    ld a,(hl)
    and a,not ti.bmUsbFifoDir
    or a,ti.usbFifoIn
    ld (hl),a
    inc hl
    ld a,(hl)
    and a,not ti.bmUsbFifoDir
    ld (hl),a
    ld a,3 or ti.bmUsbFifoEn     ; interrupt
    ld (ti.mpUsbFifo1Cfg),a
    ld a,2 or ti.bmUsbFifoEn     ; bulk
    ld (ti.mpUsbFifo2Cfg),a
    ld (ti.mpUsbFifo3Cfg),a
    ld hl,ti.mpUsbInEp1+4*1      ; endpoint 2 IN: 8 bytes
    ld de,8
    call _rt_usb_endpoint_size
    ld hl,ti.mpUsbInEp1+4*2      ; endpoint 3 IN: 64 bytes
    ld de,64
    call _rt_usb_endpoint_size
    ld hl,ti.mpUsbOutEp1+4*3     ; endpoint 4 OUT: 64 bytes
    ld de,64
_rt_usb_endpoint_size:
    ; Reset the endpoint, then set its maximum packet size.
    inc hl
    ld (hl),ti.bmUsbEpReset shr 8
    ld a,d
    and a,ti.bmUsbEpMaxPktSz shr 8
    ld (hl),a
    dec hl
    ld (hl),e
    ret
"""


def usb_send(_t) -> str:
    # Send _rt_a1 bytes from _rt_a0 on endpoint 0x83, in packets that each end a
    # transfer. Returns how many were sent, or -1 if no computer has configured it.
    return f"""
_rt_usb_send:
    call _rt_usb_poll
    ld a,(_rt_usb_configured)
    or a,a
    jr nz,_rt_usb_send_start
    scf
    sbc hl,hl
    ret
_rt_usb_send_start:
    ld hl,0
    ld (_rt_usb_sent),hl
_rt_usb_send_loop:
    ld hl,(_rt_a1)
    ld de,(_rt_usb_sent)
    or a,a
    sbc hl,de
    jr z,_rt_usb_send_done
    push hl
    ld de,{TX_PACKET}
    or a,a
    sbc hl,de
    pop hl
    jr c,_rt_usb_send_size
    ld hl,{TX_PACKET}
_rt_usb_send_size:
    push hl
    pop bc                       ; BC = this packet's length
    ; Wait until FIFO 2 is empty, handling events meanwhile.
    ld hl,0
    ld (_rt_usb_wait),hl
_rt_usb_send_wait:
    ld a,(ti.mpUsbFifoTxIsr)
    and a,ti.bmUsbIntFifo2In
    jr nz,_rt_usb_send_packet
    push bc
    call _rt_usb_poll
    pop bc
    ld a,(_rt_usb_configured)
    or a,a
    jr z,_rt_usb_send_done
    ld hl,(_rt_usb_wait)
    inc hl
    ld (_rt_usb_wait),hl
    ld de,20000
    or a,a
    sbc hl,de
    jr c,_rt_usb_send_wait
    jr _rt_usb_send_done         ; the computer is not reading: give up for now
_rt_usb_send_packet:
    push bc
    ld hl,(_rt_a0)
    ld de,(_rt_usb_sent)
    add hl,de
    ld a,1 shl 2
    ld e,ti.usbDmaMem2Fifo
    call _rt_usb_dma
    pop bc
    jr c,_rt_usb_send_done
    ld a,ti.bmUsbIntFifo2In
    ld (ti.mpUsbFifoTxIsr),a
    ld hl,(_rt_usb_sent)
    add hl,bc
    ld (_rt_usb_sent),hl
    jr _rt_usb_send_loop
_rt_usb_send_done:
    ld hl,(_rt_usb_sent)
    ret
_rt_usb_sent: db 0,0,0
_rt_usb_wait: db 0,0,0
"""


def usb_role(_t) -> str:
    # The OTG role and plug bits, which match usb.DEVICE (16) and usb.PLUG_B (32).
    return """
_rt_usb_role:
    ld a,(ti.mpUsbOtgCsr+2)
    and a,(ti.bmUsbRole or ti.bmUsbId) shr 16
    or a,a
    sbc hl,hl
    ld l,a
    ret
"""


def usb_peek(_t) -> str:
    # Byte _rt_a0 of the 256-byte USB buffer.
    return f"""
_rt_usb_peek:
    ld hl,(_rt_a0)
    ld de,{BUFFER_SIZE}
    or a,a
    sbc hl,de
    ld hl,-1
    ret nc
    ld hl,(_rt_a0)
    ld de,_rt_usb_buffer
    add hl,de
    ld a,(hl)
    or a,a
    sbc hl,hl
    ld l,a
    ret
"""


def usb_poke(_t) -> str:
    return f"""
_rt_usb_poke:
    ld hl,(_rt_a0)
    ld de,{BUFFER_SIZE}
    or a,a
    sbc hl,de
    ret nc
    ld hl,(_rt_a0)
    ld de,_rt_usb_buffer
    add hl,de
    ld a,(_rt_a1)
    ld (hl),a
    ret
"""


def usb_buffer(_t) -> str:
    return f"""
_rt_usb_buffer: rb {BUFFER_SIZE}
"""


# ---------------------------------------------------------------- serial (CE)

def srl_connected(_t) -> str:
    # Whether a computer has configured the serial device.
    return """
_rt_srl_connected:
    call _rt_usb_poll
    ld a,(_rt_usb_configured)
    or a,a
    sbc hl,hl
    ld l,a
    ret
"""


def srl_read_byte(_t) -> str:
    # The next received byte, or -1 if none has arrived.
    return """
_rt_srl_read_byte:
    call _rt_usb_poll
    ld a,(_rt_usb_rx_tail)
    ld hl,_rt_usb_rx_head
    cp a,(hl)
    jr z,_rt_srl_read_none
    ld de,0
    ld e,a
    ld hl,_rt_usb_rx
    add hl,de
    ld a,(hl)
    ld hl,_rt_usb_rx_tail
    inc (hl)
    or a,a
    sbc hl,hl
    ld l,a
    ret
_rt_srl_read_none:
    scf
    sbc hl,hl
    ret
"""


def srl_write_byte(_t) -> str:
    return """
_rt_srl_write_byte:
    ld a,(_rt_a0)
    ld (_rt_srl_byte),a
    ld hl,_rt_srl_byte
    ld (_rt_a0),hl
    ld hl,1
    ld (_rt_a1),hl
    call _rt_usb_send
    ld de,1
    or a,a
    sbc hl,de
    ld hl,1
    ret z
    dec hl
    ret
_rt_srl_byte: db 0
"""


# ---------------------------------------------------------------- link port (classic)

def link_write(_t) -> str:
    # Send _rt_a1 bytes from address _rt_a0; return how many the other calculator took.
    return """
_rt_link_write:
    ld hl,(_rt_a0)
    ld de,(_rt_a1)
    ld bc,0
_rt_link_write_loop:
    ld a,d
    or e
    jr z,_rt_link_write_done
    push hl
    push de
    push bc
    ld a,(hl)
    ld l,a
    ld h,0
    ld (_rt_link_byte),hl
    call _rt_link_send
    pop bc
    pop de
    ld a,l
    pop hl
    or a
    jr z,_rt_link_write_done
    inc hl
    dec de
    inc bc
    jr _rt_link_write_loop
_rt_link_write_done:
    ld h,b
    ld l,c
    ret
"""


def link_write_byte(_t) -> str:
    return """
_rt_link_write_byte:
    ld hl,(_rt_a0)
    ld (_rt_link_byte),hl
    jp _rt_link_send
"""


def link_read_byte(_t) -> str:
    # The next byte from the link port, or -1 at once if nothing is being sent.
    return """
_rt_link_read_byte:
    ; Both link lines high means nothing is being sent: return at once.
    in a,(0)
    and 3
    cp 3
    jr z,_rt_link_none
    ld hl,_rt_link_none
    call APP_PUSH_ERRORH
    bcall(_RecAByteIO)
    push af                      ; the OS may change A while removing the handler
    call APP_POP_ERRORH
    pop af
    ld l,a
    ld h,0
    ret
_rt_link_none:
    ld hl,-1
    ret
"""


def link_send(_t) -> str:
    # Send the byte in _rt_link_byte; 1 if the other calculator took it, else 0.
    return """
_rt_link_send:
    ld hl,_rt_link_failed
    call APP_PUSH_ERRORH
    ld a,(_rt_link_byte)
    bcall(_SendAByte)
    call APP_POP_ERRORH
    ld hl,1
    ret
_rt_link_failed:
    ld hl,0
    ret
_rt_link_byte: .dw 0
"""
