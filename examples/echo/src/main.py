"""Echo every byte received back to the sender, and count them. CLEAR quits.

On the CE, plug the calculator into a computer and open its serial port (any
baud rate), or connect an Arduino or another CE with an OTG cable. It needs
LibLoad and the CE C libraries (USBDRVCE, SRLDRVCE) on the calculator.
On classic calculators, connect another calculator with a link cable.
"""
from ti84 import keyboard, serial

count = 0
serial.begin(9600)
print("Echo: CLEAR quits")
while not keyboard.is_down(keyboard.CLEAR):
    if serial.connected():
        byte = serial.read_byte()
        if byte >= 0:
            serial.write_byte(byte)
            count += 1
serial.write("Bye after ")
serial.write_int(count)
serial.end()
print("Echoed", count)
