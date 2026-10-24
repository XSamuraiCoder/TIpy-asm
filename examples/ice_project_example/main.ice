// ICE example program
// This demonstrates basic ICE syntax

// Include graphics library
#include <gfx.ice>

// Global variable
word counter = 0

// Main function
function main() {
    // Initialize graphics
    gfx_Begin()
    
    // Clear screen
    gfx_FillScreen(gfx_white)
    
    // Draw text
    gfx_PrintStringXY("Hello, ICE!", 50, 50)
    gfx_PrintStringXY("Press any key", 50, 70)
    
    // Wait for key press
    while (!kb_Hit()) {
        counter++
        
        // Draw a pixel
        gfx_SetColor(gfx_red)
        gfx_DrawPixel(counter % 320, 100)
    }
    
    // Clear and exit
    gfx_FillScreen(gfx_white)
    gfx_PrintStringXY("Goodbye!", 100, 100)
    
    // Wait for key press
    while (!kb_Hit())
    
    gfx_End()
}
