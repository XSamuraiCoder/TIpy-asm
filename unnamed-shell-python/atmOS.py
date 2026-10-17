"""Python first port of the atmOS desktop shell.

This milestone ports the home screen, dock navigation, pointer movement, and
the three app windows. Files, note editing, and persistent settings are next.
"""

from ti84 import graphics, keyboard

cursor_x = 160
cursor_y = 100
active_app = 0
pointer_step = 4
show_tips = 1
running = 1
scene_dirty = 1

while running == 1:
    graphics.restore_cursor()
    if scene_dirty == 1:
        # Match the C shell's 16-step vertical wallpaper gradient.
        graphics.fill_rect(0, 15, 320, 12, 65040)
        graphics.fill_rect(0, 27, 320, 13, 65008)
        graphics.fill_rect(0, 40, 320, 12, 64976)
        graphics.fill_rect(0, 52, 320, 13, 64945)
        graphics.fill_rect(0, 65, 320, 12, 64881)
        graphics.fill_rect(0, 77, 320, 13, 64849)
        graphics.fill_rect(0, 90, 320, 12, 64817)
        graphics.fill_rect(0, 102, 320, 13, 64786)
        graphics.fill_rect(0, 115, 320, 13, 64754)
        graphics.fill_rect(0, 128, 320, 12, 64722)
        graphics.fill_rect(0, 140, 320, 13, 64659)
        graphics.fill_rect(0, 153, 320, 12, 64627)
        graphics.fill_rect(0, 165, 320, 13, 64595)
        graphics.fill_rect(0, 178, 320, 12, 62516)
        graphics.fill_rect(0, 190, 320, 13, 62484)
        graphics.fill_rect(0, 203, 320, 13, 62452)
        graphics.fill_rect(0, 0, 320, 14, 65138)
        if active_app == 0:
            graphics.text("ATMOS", 6, 3)
        if active_app == 1:
            graphics.text("FILES", 6, 3)
        if active_app == 2:
            graphics.text("NOTES", 6, 3)
        if active_app == 3:
            graphics.text("SETTING", 6, 3)
        graphics.text("1:12 AM", 263, 3)
        graphics.rect(235, 3, 18, 8, graphics.BLACK)
        graphics.fill_rect(237, 5, 3, 4, graphics.GREEN)
        graphics.fill_rect(241, 5, 3, 4, graphics.GREEN)
        graphics.fill_rect(245, 5, 3, 4, graphics.GREEN)

        # Bottom dock with the three built-in apps.
        graphics.fill_rect(0, 216, 320, 24, 57244)
        graphics.fill_rect(130, 220, 16, 16, graphics.BLUE)
        graphics.fill_rect(152, 220, 16, 16, graphics.ORANGE)
        graphics.fill_rect(174, 220, 16, 16, graphics.GRAY)
        # Files folder glyph.
        graphics.fill_rect(133, 224, 10, 8, graphics.WHITE)
        graphics.fill_rect(133, 222, 5, 3, graphics.WHITE)
        # Notes page glyph and writing lines.
        graphics.fill_rect(156, 222, 8, 12, graphics.WHITE)
        graphics.fill_rect(158, 225, 5, 1, graphics.ORANGE)
        graphics.fill_rect(158, 228, 5, 1, graphics.ORANGE)
        graphics.fill_rect(158, 231, 4, 1, graphics.ORANGE)
        # Settings gear glyph, drawn with the built-in monochrome primitives.
        graphics.circle(182, 228, 4, graphics.WHITE)
        graphics.fill_rect(181, 226, 3, 5, graphics.GRAY)

        # C shell window geometry: inset from the screen edges with a filled body.
        if active_app != 0:
            # Rounded outer border and light content panel.
            graphics.fill_rect(16, 14, 288, 202, 48632)
            graphics.fill_rect(8, 22, 304, 186, 48632)
            graphics.fill_circle(16, 22, 8, 48632)
            graphics.fill_circle(303, 22, 8, 48632)
            graphics.fill_circle(16, 207, 8, 48632)
            graphics.fill_circle(303, 207, 8, 48632)
            graphics.fill_rect(17, 15, 286, 200, 65503)
            graphics.fill_rect(9, 23, 302, 184, 65503)
            graphics.fill_circle(17, 23, 7, 65503)
            graphics.fill_circle(302, 23, 7, 65503)
            graphics.fill_circle(17, 206, 7, 65503)
            graphics.fill_circle(302, 206, 7, 65503)
            # Rounded title bar; the lower half is squared like the C version.
            graphics.fill_rect(16, 14, 288, 24, 65138)
            graphics.fill_rect(8, 22, 304, 16, 65138)
            graphics.fill_circle(16, 22, 8, 65138)
            graphics.fill_circle(303, 22, 8, 65138)
            graphics.fill_rect(8, 30, 304, 8, 48632)
            graphics.fill_circle(18, 22, 4, 64234)
            if active_app == 1:
                graphics.text("Files", 148, 18)
                graphics.fill_rect(18, 42, 90, 19, 57244)
                graphics.fill_rect(115, 42, 90, 19, 57244)
                graphics.fill_rect(212, 42, 90, 19, 57244)
                graphics.text("PRGMS", 39, 47)
                graphics.text("APPVARS", 130, 47)
                graphics.text("APPS", 239, 47)
                graphics.text("No files found", 123, 106)
                graphics.text("Calculator files appear here", 91, 122)
            if active_app == 2:
                graphics.text("Notes", 148, 18)
                graphics.text("Your notes", 24, 48)
                graphics.fill_rect(18, 65, 284, 1, 48632)
                graphics.text("No notes yet", 130, 105)
                graphics.text("Press Enter to create a note", 78, 121)
            if active_app == 3:
                graphics.text("Settings", 142, 18)
                graphics.fill_rect(18, 42, 90, 19, 57244)
                graphics.fill_rect(115, 42, 90, 19, 57244)
                graphics.fill_rect(212, 42, 90, 19, 57244)
                graphics.text("LOOK", 47, 47)
                graphics.text("TASKBAR", 134, 47)
                graphics.text("SYSTEM", 236, 47)
                graphics.text("Pointer speed", 26, 76)
                graphics.text("SLOW      NORMAL      FAST", 28, 94)
                graphics.text("Clock format", 26, 122)
                graphics.text("12 hour       24 hour", 28, 140)
                graphics.text("Settings save automatically", 80, 181)

        scene_dirty = 0

    graphics.save_cursor(cursor_x, cursor_y)
    # This cursor is a fixed sprite. Horizontal spans avoid rasterizing two
    # general triangles for every key press.
    graphics.fill_rect(cursor_x, cursor_y, 1, 1, graphics.BLACK)
    graphics.fill_rect(cursor_x, cursor_y + 1, 2, 1, graphics.BLACK)
    graphics.fill_rect(cursor_x, cursor_y + 2, 3, 1, graphics.BLACK)
    graphics.fill_rect(cursor_x, cursor_y + 3, 4, 1, graphics.BLACK)
    graphics.fill_rect(cursor_x, cursor_y + 4, 5, 1, graphics.BLACK)
    graphics.fill_rect(cursor_x, cursor_y + 5, 6, 1, graphics.BLACK)
    graphics.fill_rect(cursor_x, cursor_y + 6, 7, 1, graphics.BLACK)
    graphics.fill_rect(cursor_x, cursor_y + 7, 8, 1, graphics.BLACK)
    graphics.fill_rect(cursor_x, cursor_y + 8, 9, 1, graphics.BLACK)
    graphics.fill_rect(cursor_x, cursor_y + 9, 10, 1, graphics.BLACK)
    graphics.fill_rect(cursor_x, cursor_y + 10, 11, 1, graphics.BLACK)
    graphics.fill_rect(cursor_x, cursor_y + 11, 12, 1, graphics.BLACK)
    graphics.fill_rect(cursor_x, cursor_y + 12, 9, 1, graphics.BLACK)
    graphics.fill_rect(cursor_x, cursor_y + 13, 6, 1, graphics.BLACK)
    graphics.fill_rect(cursor_x, cursor_y + 14, 3, 1, graphics.BLACK)
    graphics.fill_rect(cursor_x, cursor_y + 15, 1, 1, graphics.BLACK)
    graphics.fill_rect(cursor_x + 2, cursor_y + 4, 1, 1, graphics.WHITE)
    graphics.fill_rect(cursor_x + 2, cursor_y + 5, 2, 1, graphics.WHITE)
    graphics.fill_rect(cursor_x + 2, cursor_y + 6, 3, 1, graphics.WHITE)
    graphics.fill_rect(cursor_x + 2, cursor_y + 7, 4, 1, graphics.WHITE)
    graphics.fill_rect(cursor_x + 2, cursor_y + 8, 5, 1, graphics.WHITE)
    graphics.fill_rect(cursor_x + 2, cursor_y + 9, 6, 1, graphics.WHITE)
    graphics.fill_rect(cursor_x + 2, cursor_y + 10, 4, 1, graphics.WHITE)
    graphics.fill_rect(cursor_x + 2, cursor_y + 11, 1, 1, graphics.WHITE)

    key = keyboard.read()
    if key == keyboard.LEFT:
        cursor_x -= pointer_step
    if key == keyboard.RIGHT:
        cursor_x += pointer_step
    if key == keyboard.UP:
        cursor_y -= pointer_step
    if key == keyboard.DOWN:
        cursor_y += pointer_step

    # Keep the pointer inside the calculator display.
    if cursor_x < 0:
        cursor_x = 0
    if cursor_x > 308:
        cursor_x = 308
    if cursor_y < 15:
        cursor_y = 15
    if cursor_y > 224:
        cursor_y = 224

    if key == keyboard.ENTER:
        if cursor_y >= 216:
            if cursor_x < 150:
                if active_app != 1:
                    active_app = 1
                    scene_dirty = 1
            if cursor_x >= 150:
                if cursor_x < 172:
                    if active_app != 2:
                        active_app = 2
                        scene_dirty = 1
                if cursor_x >= 172:
                    if active_app != 3:
                        active_app = 3
                        scene_dirty = 1
        else:
            if active_app != 0:
                if active_app == 3:
                    if cursor_y >= 80:
                        if cursor_y <= 101:
                            if pointer_step == 2:
                                pointer_step = 4
                            else:
                                if pointer_step == 4:
                                    pointer_step = 8
                                else:
                                    pointer_step = 2
                            scene_dirty = 1
                        if cursor_y >= 126:
                            if cursor_y <= 147:
                                if show_tips == 1:
                                    show_tips = 0
                                else:
                                    show_tips = 1
                                scene_dirty = 1
                    else:
                        active_app = 0
                        scene_dirty = 1
                else:
                    active_app = 0
                    scene_dirty = 1

    if key == keyboard.CLEAR:
        if active_app != 0:
            active_app = 0
            scene_dirty = 1
        else:
            running = 0

