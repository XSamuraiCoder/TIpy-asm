"""SAX for CE: a Cemetech SAX chat client, ported from SAX-CE's C program to TIpy.

The calculator talks to the SAX-CE bridge (the web/ folder of SAX-CE) over USB
serial, one line per message:

    calc -> PC   "H <nick>"  hello / nick change     "M <text>"  chat message
    PC -> calc   "M <nick>\\t<text>"  chat message    "S <text>"  status    "R"  send hello

Text is kept as character codes in integer arrays, and every fixed message is in
tables.py. Fonts: the OS font, or the fonts of the SAXFONT font pack (y= cycles).

Keys: letters type; alpha cycles abc/ABC/123; 2nd shows the on-screen keyboard;
del erases; enter or graph sends; up/down scroll; y= changes font; mode changes
the nickname; clear clears the line, or quits when it is empty.
"""
from ti84 import file, font, graphics, keyboard, serial

from tables import (FONT_BUILTIN, FONT_PACK, FONT_PACKED, HINT_CHAT, HINT_NICK, KEPT,
                    KEY_DEL, KEY_LOWER, KEY_NUMBER, KEY_SEND, KEY_SHIFT, KEY_SPACE, KEY_SYM, LINKED,
                    MODE_ABC, MSG_LEN, MSG_START, MSG_TEXT, MORE, NICK_BAD, NICK_CANCEL, NICK_EMPTY,
                    NICK_HELP1, NICK_HELP2, NICK_HELP3, NICK_LABEL, NICK_SAVE, NICK_TITLE, NO_FONTS,
                    NO_LINK, ONLINE, OSK_CHARS, PLUG_IN, PROMPT, SHORTENED, TITLE, TYPE_FIRST, UNKNOWN,
                    UNLINKED, WELCOME)

# Layout
SCREEN_W = 320
SCREEN_H = 240
CW = 8                  # the OS font's cell width; SAX-CE used an 8-pixel monospace font
OSK_ROWS = 5
WRAP_W = SCREEN_W - 2

# Colors (RGB565), as SAX-CE's palette
C_BG = 0x1083
C_HEADER = 0x21AC
C_TEXT = 0xE73C
C_NICK = 0x7DFF
C_STATUS = 0xF64B
C_SELF = 0x8F31
C_DIM = 0x7BF1
C_OK = 0x5EED
C_BAD = 0xE28A
C_KEY = 0x2988
C_KEYON = 0x2230

# Limits
NICK_MAX = 8
WHO_MAX = 15
TEXT_MAX = 200
LOG_MAX = 16
RX_MAX = WHO_MAX + TEXT_MAX + 8
CFG_MAX = 40

# Entry kinds: chat, status, and an echo of our own message
K_CHAT = 77             # M
K_STATUS = 83           # S
K_ECHO = 69             # E

# The on-screen keyboard's bottom row
OSK_SPECIAL_W = (64, 48, 112, 48, 48)
OSK_SPECIAL_MSG = (KEY_SHIFT, KEY_SYM, KEY_SPACE, KEY_DEL, KEY_SEND)
S_SHIFT = 0
S_SYM = 1
S_SPACE = 2
S_DEL = 3

# Line editor results
ED_NONE = 0
ED_CHANGED = 1
ED_SUBMIT = 2

nick = [0] * (NICK_MAX + 1)
text_in = [0] * (TEXT_MAX + 1)
log_kind = [0] * LOG_MAX
log_who = [0] * (LOG_MAX * WHO_MAX)
log_who_len = [0] * LOG_MAX
log_text = [0] * (LOG_MAX * TEXT_MAX)
log_text_len = [0] * LOG_MAX
rx = [0] * (RX_MAX + 1)
cfg = [0] * CFG_MAX

nick_len = 0
text_len = 0
mode = 0                # alpha keys: 0 abc, 1 ABC, 2 123
osk_on = 0
osk_layer = 0           # 0 lower, 1 upper, 2 symbols
osk_row = 1
osk_col = 0
log_head = 0
log_count = 0
scroll = 0
rx_len = 0
linked = 0
hello_sent = 0
dirty = 1
nick_changed = 0
entry_color = 0
font_index = 0          # 0 is the OS font; n is font n - 1 of SAXFONT
font_handle = 0
line_h = 14


# ---------------------------------------------------------------- text

def apply_font():
    global font_handle, line_h, font_index
    font_handle = 0
    line_h = 14
    if font_index > 0:
        font_handle = font.load("SAXFONT", font_index - 1)
        if font_handle == 0:
            font_index = 0
        else:
            line_h = font.height(font_handle) + 1


def glyph_w(code):
    if font_handle == 0:
        return CW
    width = font.width(font_handle, code)
    return width if width else font.width(font_handle, 63)


def draw_code(code, x, y, fg, bg):
    """Draw one character; return its width. The OS font paints its own background."""
    if font_handle == 0:
        graphics.char(code, x, y, fg, bg)
        return CW
    width = font.char(font_handle, code, x, y, fg)
    return width if width else font.char(font_handle, 63, x, y, fg)


def text_h():
    return line_h - 1


def header_h():
    return text_h() + 4


def log_y():
    return header_h() + 2


def osk_row_h():
    h = text_h() + 5
    return h if h > 17 else 17


def osk_y():
    return SCREEN_H - OSK_ROWS * osk_row_h()


def input_y():
    return osk_y() - line_h - 3 if osk_on else SCREEN_H - 2 * line_h - 6


def log_rows():
    rows = (input_y() - 4 - log_y()) // line_h
    return rows if rows > 0 else 1


def msg_w(msg):
    width = 0
    for i in range(MSG_LEN[msg]):
        width += glyph_w(MSG_TEXT[MSG_START[msg] + i])
    return width


def draw_msg(msg, x, y, fg, bg):
    """Draw a message from tables.py; return the x after it."""
    for i in range(MSG_LEN[msg]):
        x += draw_code(MSG_TEXT[MSG_START[msg] + i], x, y, fg, bg)
    return x


def draw_para(msg, x, y, fg, bg):
    """Draw a message, wrapping at the screen's edge; return the y below it."""
    left = x
    for i in range(MSG_LEN[msg]):
        code = MSG_TEXT[MSG_START[msg] + i]
        width = glyph_w(code)
        if x + width > SCREEN_W - 4 and x > left:
            x = left
            y += line_h
        x += draw_code(code, x, y, fg, bg)
    return y + line_h


def draw_nick(x, y, fg, bg):
    for i in range(nick_len):
        x += draw_code(nick[i], x, y, fg, bg)
    return x


# ---------------------------------------------------------------- the chat log

def clean(code):
    return code if 32 <= code <= 126 else 63


def log_start(kind):
    """Start a log entry; return its slot. Copy its nick and text in with the log_ functions."""
    global log_head, log_count, scroll, dirty
    slot = log_head
    log_kind[slot] = kind
    log_who_len[slot] = 0
    log_text_len[slot] = 0
    log_head = (log_head + 1) % LOG_MAX
    if log_count < LOG_MAX:
        log_count += 1
    scroll = 0
    dirty = 1
    return slot


def log_who_add(slot, code):
    n = log_who_len[slot]
    if n < WHO_MAX:
        log_who[slot * WHO_MAX + n] = clean(code)
        log_who_len[slot] = n + 1


def log_text_add(slot, code):
    n = log_text_len[slot]
    if n < TEXT_MAX:
        log_text[slot * TEXT_MAX + n] = clean(code)
        log_text_len[slot] = n + 1


def log_status(msg):
    slot = log_start(K_STATUS)
    for i in range(MSG_LEN[msg]):
        log_text_add(slot, MSG_TEXT[MSG_START[msg] + i])


def entry_prefix(slot):
    return 0 if log_kind[slot] == K_STATUS else log_who_len[slot] + 2


def entry_char(slot, i):
    """Character i of an entry as shown: "nick: text", or the text of a status line."""
    global entry_color
    prefix = entry_prefix(slot)
    if i < prefix:
        entry_color = C_SELF if log_kind[slot] == K_ECHO else C_NICK
        n = prefix - 2
        if i < n:
            return log_who[slot * WHO_MAX + i]
        return 58 if i == n else 32
    entry_color = C_STATUS if log_kind[slot] == K_STATUS else C_TEXT
    return log_text[slot * TEXT_MAX + i - prefix]


def entry_layout(slot, top, draw, visible):
    """Wrap an entry by pixel width, drawing the rows from top that are visible; return its rows."""
    length = entry_prefix(slot) + log_text_len[slot]
    row = 0
    x = 1
    for i in range(length):
        code = entry_char(slot, i)
        width = glyph_w(code)
        if x + width > WRAP_W and x > 1:
            row += 1
            x = 1
        r = top + row
        if draw and 0 <= r < visible:
            draw_code(code, x, log_y() + r * line_h, entry_color, C_BG)
        x += width
    return row + 1


def newest(k):
    return (log_head + LOG_MAX - 1 - k) % LOG_MAX


def total_rows():
    rows = 0
    for k in range(log_count):
        rows += entry_layout(newest(k), 0, 0, 0)
    return rows


# ---------------------------------------------------------------- nicknames (IRC rules)

def nick_char_ok(code, first):
    if 97 <= code <= 122 or 65 <= code <= 90:
        return 1
    # [ ] \ ` _ ^ { | }
    if code == 91 or code == 93 or code == 92 or code == 96 or code == 95 or code == 94:
        return 1
    if code == 123 or code == 124 or code == 125:
        return 1
    if first:
        return 0
    return 1 if 48 <= code <= 57 or code == 45 else 0


def input_is_valid_nick():
    if text_len == 0 or text_len > NICK_MAX:
        return 0
    for i in range(text_len):
        if not nick_char_ok(text_in[i], i == 0):
            return 0
    return 1


# ---------------------------------------------------------------- on-screen keyboard

def osk_row_len(row):
    return 5 if row == 4 else 10


def osk_key_x(row, col):
    if row < 4:
        return col * 32
    x = 0
    for i in range(col):
        x += OSK_SPECIAL_W[i]
    return x


def osk_key_w(row, col):
    return 32 if row < 4 else OSK_SPECIAL_W[col]


def osk_move_row(step):
    global osk_row, osk_col
    old_row = osk_row
    center = osk_key_x(old_row, osk_col) + osk_key_w(old_row, osk_col) // 2
    osk_row = (osk_row + step + OSK_ROWS) % OSK_ROWS
    osk_col = 0
    for col in range(osk_row_len(osk_row)):
        left = osk_key_x(osk_row, col)
        right = left + osk_key_w(osk_row, col)
        if left <= center < right:
            osk_col = col


def draw_osk():
    top = osk_y()
    row_h = osk_row_h()
    for row in range(OSK_ROWS):
        for col in range(osk_row_len(row)):
            x = osk_key_x(row, col)
            w = osk_key_w(row, col)
            y = top + row * row_h
            selected = row == osk_row and col == osk_col
            on = row == 4 and (col == S_SHIFT and osk_layer == 1 or col == S_SYM and osk_layer == 2)
            back = C_SELF if selected else (C_KEYON if on else C_KEY)
            fore = C_BG if selected else C_TEXT
            graphics.fill_rect(x + 1, y + 1, w - 2, row_h - 2, back)
            if row < 4:
                code = OSK_CHARS[osk_layer * 40 + row * 10 + col]
                draw_code(code, x + (w - glyph_w(code)) // 2, y + (row_h - text_h()) // 2, fore, back)
            else:
                msg = OSK_SPECIAL_MSG[col]
                draw_msg(msg, x + (w - msg_w(msg)) // 2, y + (row_h - text_h()) // 2, fore, back)


# ---------------------------------------------------------------- screens

def draw_header(title, show_nick):
    graphics.fill_rect(0, 0, SCREEN_W, header_h(), C_HEADER)
    x = draw_msg(title, 3, 2, C_TEXT, C_HEADER)
    if show_nick:
        draw_nick(x + glyph_w(32), 2, C_SELF, C_HEADER)
        status = ONLINE if linked else NO_LINK
        draw_msg(status, SCREEN_W - 3 - msg_w(status), 2, C_OK if linked else C_BAD, C_HEADER)


def draw_input_line(label, nick_mode):
    y = input_y()
    graphics.fill_rect(0, y - 3, SCREEN_W, 1, C_HEADER)
    x = draw_msg(label, 2, y, C_DIM, C_BG) + 4
    mode_msg = MODE_ABC + mode
    mode_x = SCREEN_W - 2 - msg_w(mode_msg)
    draw_msg(mode_msg, mode_x, y, C_STATUS, C_BG)
    # Show the end of the input, so the cursor is always visible.
    cursor_w = glyph_w(95)
    room = mode_x - 6 - cursor_w - x
    first = text_len
    width = 0
    while first > 0 and width + glyph_w(text_in[first - 1]) <= room:
        first -= 1
        width += glyph_w(text_in[first])
    for i in range(first, text_len):
        x += draw_code(text_in[i], x, y, C_TEXT, C_BG)
    graphics.fill_rect(x, y + text_h() - 1, cursor_w, 2, C_SELF)
    if osk_on:
        draw_osk()
    else:
        draw_msg(HINT_NICK if nick_mode else HINT_CHAT, 2, y + line_h + 2, C_DIM, C_BG)


def draw_chat():
    graphics.fill_rect(0, 0, SCREEN_W, SCREEN_H, C_BG)
    draw_header(TITLE, 1)
    visible = log_rows()
    cursor = visible - 1 + scroll         # the row of the newest entry's last line
    for k in range(log_count):
        slot = newest(k)
        rows = entry_layout(slot, 0, 0, 0)
        first = cursor - rows + 1
        entry_layout(slot, first, 1, visible)
        cursor = first - 1
        if cursor < 0:
            break
    if scroll > 0:
        y = log_y() + (visible - 1) * line_h
        w = msg_w(MORE)
        graphics.fill_rect(SCREEN_W // 2 - w // 2 - 2, y, w + 4, line_h, C_BG)
        draw_msg(MORE, SCREEN_W // 2 - w // 2, y, C_STATUS, C_BG)
    draw_input_line(PROMPT, 0)


# ---------------------------------------------------------------- settings (SAXCFG)
# As SAX-CE: the nick and a 0, the keyboard flag, the font pack's name and a 0, the font index.

def save_cfg():
    file.delete("SAXCFG")
    size = nick_len + 2 + (MSG_LEN[FONT_PACK] + 2 if font_index else 1)
    file.create("SAXCFG", size)
    at = 0
    for i in range(nick_len):
        file.write_byte("SAXCFG", at, nick[i])
        at += 1
    file.write_byte("SAXCFG", at, 0)
    file.write_byte("SAXCFG", at + 1, osk_on)
    at += 2
    if font_index:
        for i in range(MSG_LEN[FONT_PACK]):
            file.write_byte("SAXCFG", at, MSG_TEXT[MSG_START[FONT_PACK] + i])
            at += 1
        file.write_byte("SAXCFG", at, 0)
        file.write_byte("SAXCFG", at + 1, font_index - 1)
    else:
        file.write_byte("SAXCFG", at, 0)


def load_cfg():
    global nick_len, nick_changed, osk_on, font_index
    nick_len = 0
    font_index = 0
    if not file.exists("SAXCFG"):
        return
    size = min(file.size("SAXCFG"), CFG_MAX)
    for i in range(size):
        cfg[i] = file.read_byte("SAXCFG", i)
    # Keep the valid characters of the saved name, and the first 8 of them.
    end = 0
    while end < size and cfg[end] != 0:
        end += 1
    for i in range(end):
        if nick_len < NICK_MAX and nick_char_ok(cfg[i], nick_len == 0):
            nick[nick_len] = cfg[i]
            nick_len += 1
    nick_changed = 1 if nick_len > 0 and nick_len != end else 0
    at = end + 1
    if at < size:
        osk_on = 1 if cfg[at] else 0
        at += 1
    # A font from SAXFONT; SAX-CE's other font packs are not supported.
    if at + MSG_LEN[FONT_PACK] + 1 < size and cfg[at + MSG_LEN[FONT_PACK]] == 0:
        same = 1
        for i in range(MSG_LEN[FONT_PACK]):
            if cfg[at + i] != MSG_TEXT[MSG_START[FONT_PACK] + i]:
                same = 0
        if same:
            font_index = cfg[at + MSG_LEN[FONT_PACK] + 1] + 1


def next_font():
    global font_index
    count = font.count("SAXFONT")
    if count == 0:
        log_status(NO_FONTS)
        return
    font_index = (font_index + 1) % (count + 1)
    apply_font()
    save_cfg()
    log_status(FONT_PACKED if font_index else FONT_BUILTIN)


# ---------------------------------------------------------------- the line editor

def key_char(key):
    if key > 56:
        return 0
    if mode == 2:
        return KEY_NUMBER[key]
    code = KEY_LOWER[key]
    if mode == 1 and 97 <= code <= 122:
        code -= 32
    return code


def insert_char(code, limit, nick_mode):
    global text_len
    if text_len >= limit:
        return
    if nick_mode and not nick_char_ok(code, text_len == 0):
        return
    text_in[text_len] = code
    text_len += 1


def backspace():
    global text_len
    if text_len:
        text_len -= 1


def edit_key(key, limit, nick_mode):
    """The shared line editor for the chat box and the nickname prompt."""
    global osk_on, osk_col, osk_layer, mode
    if key == keyboard.SECOND:
        osk_on = 1 - osk_on
        save_cfg()
        return ED_CHANGED
    if key == keyboard.GRAPH:
        return ED_SUBMIT
    if osk_on:
        if key == keyboard.LEFT:
            osk_col = osk_col - 1 if osk_col else osk_row_len(osk_row) - 1
            return ED_CHANGED
        if key == keyboard.RIGHT:
            osk_col = (osk_col + 1) % osk_row_len(osk_row)
            return ED_CHANGED
        if key == keyboard.UP:
            osk_move_row(-1)
            return ED_CHANGED
        if key == keyboard.DOWN:
            osk_move_row(1)
            return ED_CHANGED
        if key == keyboard.ENTER:
            if osk_row < 4:
                insert_char(OSK_CHARS[osk_layer * 40 + osk_row * 10 + osk_col], limit, nick_mode)
            elif osk_col == S_SHIFT:
                osk_layer = 0 if osk_layer == 1 else 1
            elif osk_col == S_SYM:
                osk_layer = 0 if osk_layer == 2 else 2
            elif osk_col == S_SPACE:
                insert_char(32, limit, nick_mode)
            elif osk_col == S_DEL:
                backspace()
            else:
                return ED_SUBMIT
            return ED_CHANGED
    elif key == keyboard.ENTER:
        return ED_SUBMIT
    if key == keyboard.ALPHA:
        mode = (mode + 1) % 3
        return ED_CHANGED
    if key == keyboard.DEL:
        backspace()
        return ED_CHANGED
    code = key_char(key)
    if code:
        insert_char(code, limit, nick_mode)
        return ED_CHANGED
    return ED_NONE


# ---------------------------------------------------------------- serial

def send_nick_line():
    serial.write("H ")
    for i in range(nick_len):
        serial.write_byte(nick[i])
    serial.write_byte(10)


def send_text_line():
    serial.write("M ")
    for i in range(text_len):
        serial.write_byte(text_in[i])
    serial.write_byte(10)


def handle_line():
    """Act on the line in rx."""
    # "R": the bridge (re)opened the port and wants our hello.
    if rx_len >= 1 and rx[0] == 82 and (rx_len == 1 or rx[1] == 32):
        if nick_len:
            send_nick_line()
        return
    if rx_len < 2 or rx[1] != 32:
        return
    if rx[0] == 77:
        tab = 2
        while tab < rx_len and rx[tab] != 9:
            tab += 1
        slot = log_start(K_CHAT)
        if tab == rx_len:
            log_who_add(slot, 63)
            for i in range(2, rx_len):
                log_text_add(slot, rx[i])
        else:
            for i in range(2, tab):
                log_who_add(slot, rx[i])
            for i in range(tab + 1, rx_len):
                log_text_add(slot, rx[i])
    elif rx[0] == 83:
        slot = log_start(K_STATUS)
        for i in range(2, rx_len):
            log_text_add(slot, rx[i])


def poll_serial():
    """Handle USB events, follow the link, and read whole lines."""
    global linked, hello_sent, rx_len, dirty
    now = serial.connected()
    if now and not linked:
        linked = 1
        hello_sent = 0
        rx_len = 0
        log_status(LINKED)
    elif linked and not now:
        linked = 0
        log_status(UNLINKED)
    if not linked:
        return
    if not hello_sent and nick_len:
        # During the first nickname prompt there is no name to send yet.
        send_nick_line()
        hello_sent = 1
    count = 0
    while count < 64:
        code = serial.read_byte()
        if code < 0:
            break
        count += 1
        if code == 10:
            handle_line()
            rx_len = 0
        elif code != 13 and rx_len < RX_MAX:
            rx[rx_len] = code
            rx_len += 1


# ---------------------------------------------------------------- nickname prompt

def prompt_nick():
    """Ask for a nickname; return 0 if cancelled with none set."""
    global text_len, mode, nick_len
    for i in range(nick_len):
        text_in[i] = nick[i]
    text_len = nick_len
    saved_mode = mode
    mode = 0
    error = -1
    redraw = 1
    while True:
        poll_serial()
        if redraw:
            graphics.fill_rect(0, 0, SCREEN_W, SCREEN_H, C_BG)
            draw_header(NICK_TITLE, 0)
            y = header_h() + 8
            y = draw_para(NICK_HELP1, 8, y, C_TEXT, C_BG) + 2
            y = draw_para(NICK_HELP2, 8, y, C_DIM, C_BG)
            y = draw_para(NICK_HELP3, 8, y, C_DIM, C_BG) + 6
            if error >= 0:
                y = draw_para(error, 8, y, C_BAD, C_BG) + 4
            if not osk_on:
                y = draw_para(NICK_SAVE, 8, y, C_DIM, C_BG)
                draw_para(NICK_CANCEL, 8, y, C_DIM, C_BG)
            draw_input_line(NICK_LABEL, 1)
            redraw = 0
        key = keyboard.get()
        if not key:
            continue
        redraw = 1
        if key == keyboard.CLEAR:
            text_len = 0
            mode = saved_mode
            return 1 if nick_len else 0
        if edit_key(key, NICK_MAX, 1) != ED_SUBMIT:
            continue
        if not input_is_valid_nick():
            error = NICK_BAD if text_len else NICK_EMPTY
            continue
        for i in range(text_len):
            nick[i] = text_in[i]
        nick_len = text_len
        save_cfg()
        text_len = 0
        mode = saved_mode
        return 1


# ---------------------------------------------------------------- main

def send_input():
    global text_len
    if text_len == 0:
        log_status(TYPE_FIRST)
        return
    if not linked:
        log_status(KEPT)        # keep the text, to send once the link is up
        return
    send_text_line()
    slot = log_start(K_ECHO)
    for i in range(nick_len):
        log_who_add(slot, nick[i])
    for i in range(text_len):
        log_text_add(slot, text_in[i])
    text_len = 0


def main():
    global text_len, scroll, dirty
    graphics.begin()
    serial.begin(115200)
    load_cfg()
    apply_font()
    if nick_len == 0 and not prompt_nick():
        serial.end()
        graphics.end()
        return
    log_status(WELCOME)
    log_status(PLUG_IN)
    if nick_changed:
        save_cfg()
        log_status(SHORTENED)
    while True:
        poll_serial()
        key = keyboard.get()
        if key:
            dirty = 1
            if key == keyboard.CLEAR:
                if text_len == 0:
                    break
                text_len = 0
            elif not osk_on and key == keyboard.UP:
                if scroll < total_rows() - log_rows():
                    scroll += 1
            elif not osk_on and key == keyboard.DOWN:
                if scroll > 0:
                    scroll -= 1
            elif key == keyboard.YEQU:
                next_font()
            elif key == keyboard.MODE:
                if prompt_nick() and linked:
                    send_nick_line()
            elif edit_key(key, TEXT_MAX, 0) == ED_SUBMIT:
                send_input()
        if dirty:
            draw_chat()
            dirty = 0
    serial.end()
    graphics.end()


main()
