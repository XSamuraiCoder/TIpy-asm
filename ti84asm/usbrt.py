"""Runtime for ti84.usb and ti84.serial: CEdev's USB libraries through LibLoad, and the classic link port.

On the CE, a TIpy program reaches usbdrvce and srldrvce the way CEdev's C
programs do: LibLoad finds the libraries on the calculator and patches a jump
table in the program. Those libraries use the C calling convention: arguments
pushed right to left as 3-byte words, the caller pops them, and the result in
HL (A for 8-bit results). They preserve IX and IY, but may change IY's value
in between, so the helpers reset IY to the OS flags after each call.

The event handler is called by usbdrvce, so it follows the same convention in
reverse: it keeps IX and IY, and returns USB_SUCCESS in HL.

On the classic calculators, serial uses the link port through the OS's own
byte protocol (_SendAByte and _RecAByteIO), so any program that uses the same
calls on the other calculator can talk to it. A link error, such as no
calculator on the other end, is caught with the OS error handler, so it
returns a failure instead of showing ERR:LINK.
"""

from __future__ import annotations

# The libraries' exports, in the order of CEdev's lib/libload/*.lib files. LibLoad
# finds a function by its position in this list, so the order must not change.
USBDRVCE_EXPORTS = (
    "usb_Init", "usb_Cleanup", "usb_PollTransfers", "usb_HandleEvents", "usb_WaitForEvents",
    "usb_WaitForInterrupt", "usb_RefDevice", "usb_UnrefDevice", "usb_GetDeviceHub", "usb_SetDeviceData",
    "usb_GetDeviceData", "usb_GetDeviceFlags", "usb_FindDevice", "usb_ResetDevice", "usb_DisableDevice",
    "usb_GetDeviceAddress", "usb_GetDeviceSpeed", "usb_GetConfigurationDescriptorTotalLength",
    "usb_GetDescriptor", "usb_SetDescriptor", "usb_GetStringDescriptor", "usb_SetStringDescriptor",
    "usb_GetConfiguration", "usb_SetConfiguration", "usb_GetInterface", "usb_SetInterface",
    "usb_SetEndpointHalt", "usb_ClearEndpointHalt", "usb_GetDeviceEndpoint", "usb_GetEndpointDevice",
    "usb_SetEndpointData", "usb_GetEndpointData", "usb_GetEndpointAddress", "usb_GetEndpointTransferType",
    "usb_GetEndpointMaxPacketSize", "usb_GetEndpointInterval", "usb_SetEndpointFlags", "usb_GetEndpointFlags",
    "usb_GetRole", "usb_GetFrameNumber", "usb_ControlTransfer", "usb_Transfer", "usb_ScheduleControlTransfer",
    "usb_ScheduleTransfer", "usb_MsToCycles", "usb_GetCycleCounter", "usb_GetCounter", "usb_StopTimer",
    "usb_StartTimerCycles", "usb_RepeatTimerCycles",
)
SRLDRVCE_EXPORTS = ("srl_Open", "srl_Close", "srl_Read", "srl_Write", "srl_GetCDCStandardDescriptors",
                    "srl_UsbEventCallback")
LIBRARIES = {"USBDRVCE": USBDRVCE_EXPORTS, "SRLDRVCE": SRLDRVCE_EXPORTS}

# usbdrvce constants (usbdrvce.h).
USB_DEFAULT_INIT_FLAGS = 0x8D0A    # OS heap, 256-entry frame list, ASST 1, EOF1 3, EOF2 0, unknown bit
USB_SKIP_HUBS = 1 << 3
USB_SKIP_DISABLED = 1 << 0
USB_ROLE_DEVICE = 1 << 4
USB_DEVICE_DESCRIPTOR = 1
USB_CONFIGURATION_DESCRIPTOR = 2
EVENTS = {
    "ROLE_CHANGED": 0, "DEVICE_DISCONNECTED": 1, "DEVICE_CONNECTED": 2, "DEVICE_DISABLED": 3,
    "DEVICE_ENABLED": 4, "HUB_LOCAL_POWER_GOOD": 5, "HUB_LOCAL_POWER_LOST": 6, "DEVICE_RESUMED": 7,
    "DEVICE_SUSPENDED": 8, "DEVICE_OVERCURRENT_DEACTIVATED": 9, "DEVICE_OVERCURRENT_ACTIVATED": 10,
    "DEFAULT_SETUP": 11, "HOST_CONFIGURE": 12,
}
SRL_INTERFACE_ANY = 0xFF
SRL_BUFFER_SIZE = 512
SRL_DEVICE_SIZE = 64               # srl_device_t is 58 bytes; keep room
CONFIG_BUFFER_SIZE = 256           # largest configuration descriptor usb.configure() reads
LIBLOAD_MIN_VERSION = 30           # 3.0 added the header that is safe to jump into


def lib_label(function: str) -> str:
    """The program's jump-table entry that LibLoad patches to point at ``function``."""
    return f"_lib_{function}"


def c_call(function: str, *arguments: str, keep_iy: bool = False) -> str:
    """Call a library function with 3-byte arguments, each an operand for ``ld hl,...``."""
    lines = []
    for argument in reversed(arguments):
        lines.append(f"    ld hl,{argument}")
        lines.append("    push hl")
    lines.append(f"    call {lib_label(function)}")
    lines.extend("    pop de" for _ in arguments)
    if not keep_iy:
        lines.append("    ld iy,ti.flags")
    return "\n".join(lines)


def libload(libraries: list[str]) -> str:
    """Load ``libraries`` with LibLoad. The program calls _rt_libload first thing."""
    table = []
    for name in libraries:
        table.append(f"    db $C0,\"{name}\",0,0")
        for index, function in enumerate(LIBRARIES[name]):
            table.append(f"{lib_label(function)}:")
            table.append(f"    jp {index * 3}")
    return f"""
; LibLoad, as CEdev's C programs use it: find the archived LibLoad AppVar, check
; its version, and jump to its header with DE pointing at the table below.
; LibLoad links each library, patches the jumps, and continues after the table.
_rt_libload:
    ld hl,_rt_libload_name
    call ti.Mov9ToOP1
    call ti.ChkFindSym
    jp c,_rt_libload_missing
    call ti.ChkInRam
    jr nz,_rt_libload_archived
    call ti.PushOP1
    call ti.Arc_Unarc
    call ti.PopOP1
    jr _rt_libload
_rt_libload_archived:
    ; DE is the archive entry: 9 header bytes, the name's length and 7 letters,
    ; the 2-byte size, then the data: 2 magic bytes and the version.
    ld hl,9 + 1 + 7 + 2 + 2
    add hl,de
    ld a,(hl)
    cp a,{LIBLOAD_MIN_VERSION}
    jp c,_rt_libload_missing
    dec hl
    dec hl
    ld de,_rt_libload_table
    ld bc,_rt_libload_failed
    push bc
    jp (hl)
_rt_libload_table:
{chr(10).join(table)}
_rt_libload_done:
    ; LibLoad continues here once every library is linked.
    pop hl
    ld iy,ti.flags
    ret
_rt_libload_missing:
    call ti.ClrScrn
    call ti.HomeUp
    ld hl,_rt_libload_message
    call ti.PutS
    call ti.NewLine
    ld hl,_rt_libload_url
    call ti.PutS
    call ti.NewLine
_rt_libload_failed:
    ; LibLoad showed which library is missing, and returned here.
    ld iy,ti.flags
    jp program_exit
_rt_libload_name:
    db ti.AppVarObj,"LibLoad",0
_rt_libload_message:
    db "Needs LibLoad and the CE C",0
_rt_libload_url:
    db "libraries: tiny.cc/clibs",0
"""


# ---------------------------------------------------------------- USB (CE)

def usb_init(_t) -> str:
    # usb_Init(handler, NULL, descriptors in _rt_a0, flags). Calling it again
    # restarts the driver, so serial.begin() can follow usb.begin().
    return f"""
_rt_usb_init:
    ld a,(_rt_usb_active)
    or a,a
    jr z,_rt_usb_init_fresh
    xor a,a
    ld (_rt_srl_open),a
_rt_usb_init_fresh:
{c_call("usb_Init", "_rt_usb_handler", "0", "(_rt_a0)", str(USB_DEFAULT_INIT_FLAGS))}
    ld de,0
    or a,a
    sbc hl,de
    jp nz,_rt_usb_init_failed
    ld a,1
    ld (_rt_usb_active),a
    ret
_rt_usb_init_failed:
    push hl
{c_call("usb_Cleanup")}
    xor a,a
    ld (_rt_usb_active),a
    pop hl
    ret
_rt_usb_active: db 0
_rt_srl_open: db 0
; ti84.serial sets these, so a program without it links none of its code.
_rt_usb_hook: db 0,0,0             ; called by the event handler
_rt_usb_poll_hook: db 0,0,0        ; called after usb_HandleEvents
_rt_usb_close_hook: db 0,0,0       ; called before usb_Cleanup
_rt_usb_event: db 255,255,255
"""


def usb_handler(_t) -> str:
    # usb_error_t handler(usb_event_t event, void *event_data, void *callback_data)
    return f"""
_rt_usb_handler:
    push ix
    push iy
    ld ix,0
    add ix,sp
    ; IX+6 return address, IX+9 event, IX+12 event data, IX+15 callback data.
    ld hl,(ix+9)
    ld (_rt_usb_event),hl
    ld hl,(_rt_usb_hook)
    ld de,0
    or a,a
    sbc hl,de
    jr z,_rt_usb_handler_reset
    call _rt_usb_call_hl
    ld de,0
    or a,a
    sbc hl,de
    jr nz,_rt_usb_handler_return
_rt_usb_handler_reset:
    ; As the host, reset each connected device so the driver enables it.
    ld a,(ix+9)
    cp a,{EVENTS["DEVICE_CONNECTED"]}
    jr nz,_rt_usb_handler_success
{c_call("usb_GetRole", keep_iy=True)}
    ld a,l
    and a,{USB_ROLE_DEVICE}
    jr nz,_rt_usb_handler_success
{c_call("usb_ResetDevice", "(ix+12)", keep_iy=True)}
_rt_usb_handler_success:
    ld hl,0
_rt_usb_handler_return:
    pop iy
    pop ix
    ret
_rt_usb_call_hl:
    jp (hl)
"""


def usb_end(_t) -> str:
    return f"""
_rt_usb_end:
    ld a,(_rt_usb_active)
    or a,a
    ret z
    ld hl,(_rt_usb_close_hook)
    ld de,0
    or a,a
    sbc hl,de
    call nz,_rt_usb_call_hl
{c_call("usb_Cleanup")}
    xor a,a
    ld (_rt_usb_active),a
    ld (_rt_srl_open),a
    ret
"""


def usb_poll(_t) -> str:
    # usb_HandleEvents(), then open or close a serial device the handler noticed.
    return f"""
_rt_usb_poll:
    ld a,(_rt_usb_active)
    or a,a
    jr nz,_rt_usb_poll_active
    ld hl,-1                     ; usb.begin() or serial.begin() was not called
    ret
_rt_usb_poll_active:
{c_call("usb_HandleEvents")}
    push hl
    ld hl,(_rt_usb_poll_hook)
    ld de,0
    or a,a
    sbc hl,de
    call nz,_rt_usb_call_hl
    pop hl
    ret
"""


def usb_find(_t) -> str:
    # The next enabled non-hub device after _rt_a0, or the first when it is 0.
    return f"""
_rt_usb_find:
{c_call("usb_FindDevice", "0", "(_rt_a0)", str(USB_SKIP_HUBS | USB_SKIP_DISABLED))}
    ret
"""


def usb_role(_t) -> str:
    return f"""
_rt_usb_role:
    ld a,(_rt_usb_active)
    or a,a
    ld hl,0
    ret z
{c_call("usb_GetRole")}
    ret
"""


def usb_address(_t) -> str:
    return f"""
_rt_usb_address:
{c_call("usb_GetDeviceAddress", "(_rt_a0)")}
    or a,a
    sbc hl,hl
    ld l,a
    ret
"""


def usb_speed(_t) -> str:
    # int8_t: -1 unknown, 0 full speed, 16 low speed.
    return f"""
_rt_usb_speed:
{c_call("usb_GetDeviceSpeed", "(_rt_a0)")}
    or a,a
    sbc hl,hl
    ld l,a
    bit 7,a
    ret z
    ld de,-256                   ; sign-extend the int8_t
    add hl,de
    ret
"""


def usb_descriptor_word(_t) -> str:
    # Read the 18-byte device descriptor of device _rt_a0; return the 16-bit word
    # at offset _rt_a1 (8 vendor ID, 10 product ID, 12 device version), or -1.
    return f"""
_rt_usb_descriptor_word:
{c_call("usb_GetDescriptor", "(_rt_a0)", str(USB_DEVICE_DESCRIPTOR), "0", "_rt_usb_buffer", "18",
        "_rt_usb_transferred")}
    ld de,0
    or a,a
    sbc hl,de
    jp nz,_rt_usb_descriptor_failed
    ld hl,(_rt_usb_transferred)
    ld de,18
    or a,a
    sbc hl,de
    jp nz,_rt_usb_descriptor_failed
    ld hl,(_rt_a1)
    ld de,_rt_usb_buffer
    add hl,de
    ld de,0
    ld e,(hl)
    inc hl
    ld d,(hl)
    ex de,hl
    ret
_rt_usb_descriptor_failed:
    ld hl,-1
    ret
"""


def usb_configure(_t) -> str:
    # Read device _rt_a0's first configuration descriptor and select it, as a host
    # must before using a device's other endpoints. Returns a usb_error_t.
    return f"""
_rt_usb_configure:
{c_call("usb_GetConfigurationDescriptorTotalLength", "(_rt_a0)", "0")}
    ld (_rt_usb_length),hl
    ld de,{CONFIG_BUFFER_SIZE + 1}
    or a,a
    sbc hl,de
    jr c,_rt_usb_configure_fits
    ld hl,6                      ; USB_ERROR_OVERFLOW
    ret
_rt_usb_configure_fits:
{c_call("usb_GetDescriptor", "(_rt_a0)", str(USB_CONFIGURATION_DESCRIPTOR), "0", "_rt_usb_buffer",
        "(_rt_usb_length)", "_rt_usb_transferred")}
    ld de,0
    or a,a
    sbc hl,de
    ret nz
{c_call("usb_SetConfiguration", "(_rt_a0)", "_rt_usb_buffer", "(_rt_usb_length)")}
    ret
_rt_usb_length: db 0,0,0
"""


def usb_buffer(_t) -> str:
    return f"""
_rt_usb_transferred: db 0,0,0
_rt_usb_buffer: rb {CONFIG_BUFFER_SIZE}
"""


def usb_transfer(_t) -> str:
    # Transfer _rt_a3 bytes at offset _rt_a2 of the RAM AppVar named at _rt_a1,
    # through endpoint address _rt_a4 of device _rt_a0. Returns the bytes moved, or -1.
    return f"""
_rt_usb_transfer:
    ld hl,(_rt_a1)
    call _rt_find_var
    jp c,_rt_usb_transfer_failed
    ld a,(_rt_var_archived)
    or a,a
    jp nz,_rt_usb_transfer_failed
    ; HL is the AppVar's size word: check offset + length against the size.
    push hl
    ld de,0
    ld e,(hl)
    inc hl
    ld d,(hl)
    ld hl,(_rt_a2)
    ld bc,(_rt_a3)
    add hl,bc
    ex de,hl
    or a,a
    sbc hl,de
    pop hl
    jp c,_rt_usb_transfer_failed
    inc hl
    inc hl
    ld de,(_rt_a2)
    add hl,de
    ld (_rt_usb_data),hl
{c_call("usb_GetDeviceEndpoint", "(_rt_a0)", "(_rt_a4)")}
    ld de,0
    or a,a
    sbc hl,de
    jp z,_rt_usb_transfer_failed
    add hl,de
    ld (_rt_usb_endpoint),hl
{c_call("usb_Transfer", "(_rt_usb_endpoint)", "(_rt_usb_data)", "(_rt_a3)", "3", "_rt_usb_transferred")}
    ld de,0
    or a,a
    sbc hl,de
    jp nz,_rt_usb_transfer_failed
    ld hl,(_rt_usb_transferred)
    ret
_rt_usb_transfer_failed:
    ld hl,-1
    ret
_rt_usb_data: db 0,0,0
_rt_usb_endpoint: db 0,0,0
"""


def usb_control(_t) -> str:
    # A control transfer on device _rt_a0 with the 8-byte setup packet at
    # _rt_usb_setup, and the data stage in _rt_usb_buffer. Returns the bytes moved, or -1.
    return f"""
_rt_usb_control:
{c_call("usb_GetDeviceEndpoint", "(_rt_a0)", "0")}
    ld de,0
    or a,a
    sbc hl,de
    jp z,_rt_usb_control_failed
    add hl,de
    ld (_rt_usb_endpoint0),hl
{c_call("usb_ControlTransfer", "(_rt_usb_endpoint0)", "_rt_usb_setup", "_rt_usb_buffer", "3",
        "_rt_usb_transferred")}
    ld de,0
    or a,a
    sbc hl,de
    jp nz,_rt_usb_control_failed
    ld hl,(_rt_usb_transferred)
    ret
_rt_usb_control_failed:
    ld hl,-1
    ret
_rt_usb_endpoint0: db 0,0,0
_rt_usb_setup: db 0,0,0,0,0,0,0,0
"""


def usb_peek(_t) -> str:
    # Byte _rt_a0 of the shared data buffer.
    return f"""
_rt_usb_peek:
    ld hl,(_rt_a0)
    ld de,{CONFIG_BUFFER_SIZE}
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
    ld de,{CONFIG_BUFFER_SIZE}
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


def usb_setup(_t) -> str:
    # Store a setup packet: request type, request, value, index, length.
    return f"""
_rt_usb_set_setup:
    ld hl,_rt_usb_setup
    ld a,(_rt_a0)
    ld (hl),a
    inc hl
    ld a,(_rt_a1)
    ld (hl),a
    inc hl
    ld de,(_rt_a2)
    ld (hl),e
    inc hl
    ld (hl),d
    inc hl
    ld de,(_rt_a3)
    ld (hl),e
    inc hl
    ld (hl),d
    inc hl
    ; The data stage goes in the shared buffer, so keep the length within it.
    push hl
    ld hl,(_rt_a4)
    ld de,{CONFIG_BUFFER_SIZE} + 1
    or a,a
    sbc hl,de
    ld de,(_rt_a4)
    jr c,_rt_usb_set_setup_fits
    ld de,{CONFIG_BUFFER_SIZE}
_rt_usb_set_setup_fits:
    pop hl
    ld (hl),e
    inc hl
    ld (hl),d
    ret
"""


# ---------------------------------------------------------------- serial (CE)

def srl_begin(_t) -> str:
    # Start USB with the serial (CDC) descriptors, so the calculator works as a
    # device for a computer, or as the host for an Arduino or another calculator.
    return f"""
_rt_srl_begin:
    ld hl,(_rt_a0)
    ld (_rt_srl_baud),hl
    ld hl,_rt_srl_event
    ld (_rt_usb_hook),hl
    ld hl,_rt_srl_service
    ld (_rt_usb_poll_hook),hl
    ld hl,_rt_srl_close
    ld (_rt_usb_close_hook),hl
{c_call("srl_GetCDCStandardDescriptors")}
    ld (_rt_a0),hl
    jp _rt_usb_init
_rt_srl_close:
    ld a,(_rt_srl_open)
    or a,a
    ret z
    xor a,a
    ld (_rt_srl_open),a
{c_call("srl_Close", "_rt_srl_device")}
    ret
_rt_srl_baud: db 0,0,0
_rt_srl_pending: db 0,0,0
_rt_srl_lost: db 0
_rt_srl_byte: db 0
_rt_srl_device: rb {SRL_DEVICE_SIZE}
_rt_srl_buffer: rb {SRL_BUFFER_SIZE}
"""


def srl_event(_t) -> str:
    # Called from _rt_usb_handler with its IX frame. As CEdev's srl_echo example
    # does, but srl_Open runs later in _rt_srl_service, not in the handler.
    return f"""
_rt_srl_event:
{c_call("srl_UsbEventCallback", "(ix+9)", "(ix+12)", "(ix+15)", keep_iy=True)}
    ld de,0
    or a,a
    sbc hl,de
    ret nz
    ld a,(ix+9)
    cp a,{EVENTS["HOST_CONFIGURE"]}
    jr z,_rt_srl_event_configured
    cp a,{EVENTS["DEVICE_ENABLED"]}
    jr z,_rt_srl_event_enabled
    cp a,{EVENTS["DEVICE_DISCONNECTED"]}
    jr z,_rt_srl_event_disconnected
    ld hl,0
    ret
_rt_srl_event_configured:
    ; A computer configured the calculator: use the device that stands for it.
{c_call("usb_FindDevice", "0", "0", str(USB_SKIP_HUBS), keep_iy=True)}
    jr _rt_srl_event_pending
_rt_srl_event_enabled:
{c_call("usb_GetRole", keep_iy=True)}
    ld a,l
    and a,{USB_ROLE_DEVICE}
    ld hl,0
    ret nz
    ld hl,(ix+12)
_rt_srl_event_pending:
    ; Remember the device; _rt_srl_service opens it outside the handler.
    ld a,(_rt_srl_open)
    or a,a
    jr nz,_rt_srl_event_success
    ld (_rt_srl_pending),hl
_rt_srl_event_success:
    ld hl,0
    ret
_rt_srl_event_disconnected:
    ld a,(_rt_srl_open)
    or a,a
    jr z,_rt_srl_event_success
    ld hl,(ix+12)
    ld de,(_rt_srl_device)
    or a,a
    sbc hl,de
    jr nz,_rt_srl_event_success
    ld a,1
    ld (_rt_srl_lost),a
    jr _rt_srl_event_success
"""


def srl_service(_t) -> str:
    return f"""
_rt_srl_service:
    ld a,(_rt_srl_lost)
    or a,a
    jr z,_rt_srl_service_open
    xor a,a
    ld (_rt_srl_lost),a
    ld (_rt_srl_open),a
{c_call("srl_Close", "_rt_srl_device")}
_rt_srl_service_open:
    ld a,(_rt_srl_open)
    or a,a
    ret nz
    ld hl,(_rt_srl_pending)
    ld de,0
    or a,a
    sbc hl,de
    ret z
    add hl,de
    ld (_rt_srl_pending_device),hl
    ld (_rt_srl_pending),de
{c_call("srl_Open", "_rt_srl_device", "(_rt_srl_pending_device)", "_rt_srl_buffer", str(SRL_BUFFER_SIZE),
        str(SRL_INTERFACE_ANY), "(_rt_srl_baud)")}
    ld de,0
    or a,a
    sbc hl,de
    ret nz
    ld a,1
    ld (_rt_srl_open),a
    ret
_rt_srl_pending_device: db 0,0,0
"""


def srl_connected(_t) -> str:
    return """
_rt_srl_connected:
    call _rt_usb_poll
    ld a,(_rt_srl_open)
    or a,a
    sbc hl,hl
    ld l,a
    ret
"""


def link_send(_t) -> str:
    # Classic: send the byte in _rt_link_byte; 1 if the other calculator took it, else 0.
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


def srl_write(_t) -> str:
    # Write _rt_a1 bytes from address _rt_a0; return how many were written, or -1.
    return f"""
_rt_srl_write:
    call _rt_usb_poll
    ld a,(_rt_srl_open)
    or a,a
    jr z,_rt_srl_write_failed
{c_call("srl_Write", "_rt_srl_device", "(_rt_a0)", "(_rt_a1)")}
    push hl
    call _rt_usb_poll
    pop hl
    ret
_rt_srl_write_failed:
    ld hl,-1
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
    call _rt_srl_write
    ld de,1
    or a,a
    sbc hl,de
    ld hl,1
    ret z
    dec hl
    ret
"""


def srl_read_byte(_t) -> str:
    # The next received byte, or -1 if none has arrived.
    return f"""
_rt_srl_read_byte:
    call _rt_usb_poll
    ld a,(_rt_srl_open)
    or a,a
    jr z,_rt_srl_read_none
{c_call("srl_Read", "_rt_srl_device", "_rt_srl_byte", "1")}
    ld de,1
    or a,a
    sbc hl,de
    jr nz,_rt_srl_read_none
    ld a,(_rt_srl_byte)
    or a,a
    sbc hl,hl
    ld l,a
    ret
_rt_srl_read_none:
    ld hl,-1
    ret
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
