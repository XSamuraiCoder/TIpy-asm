"""A spinning star. LEFT and RIGHT change its speed; CLEAR quits.

Shows the math library's sin and cos, lines and circles at runtime positions,
a color made with color.from_rgb, and a game loop that reads held keys.
"""
from ti84 import color, graphics, keyboard, math

POINTS = 5
RADIUS = graphics.height // 2 - 6
CENTER_X = graphics.width // 2
CENTER_Y = graphics.height // 2
ORANGE = color.from_rgb(255, 140, 0)

point_x = [0] * POINTS
point_y = [0] * POINTS


def place_points(angle):
    """Put the star's points on a circle, starting at `angle` degrees."""
    for index in range(POINTS):
        degrees = (angle + index * 72) % 360
        point_x[index] = CENTER_X + math.cos(degrees) * RADIUS // 256
        point_y[index] = CENTER_Y - math.sin(degrees) * RADIUS // 256


def draw_star(line_color):
    # Join every point to the one two steps ahead, which draws a five-pointed star.
    for index in range(POINTS):
        other = (index + 2) % POINTS
        graphics.line(point_x[index], point_y[index], point_x[other], point_y[other], line_color)


def main():
    angle = 90
    speed = 3
    graphics.begin()
    graphics.fill_screen(graphics.WHITE)
    graphics.circle(CENTER_X, CENTER_Y, RADIUS + 3, graphics.BLACK)
    while not keyboard.is_down(keyboard.CLEAR):
        speed = math.clamp(speed + keyboard.is_down(keyboard.RIGHT) - keyboard.is_down(keyboard.LEFT), 1, 15)
        place_points(angle)
        draw_star(ORANGE)
        graphics.delay(3000)
        draw_star(graphics.WHITE)
        angle = (angle + speed) % 360
    graphics.end()
    print("Final speed:", speed)


main()
