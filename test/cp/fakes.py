# Stand-ins for board objects, for desktop tests.


class FakeBitmap:
    """Same interface as displayio.Bitmap for what radar.py uses."""

    def __init__(self, width=64, height=32):
        self.width, self.height = width, height
        self.px = [[0] * width for _ in range(height)]

    def __setitem__(self, xy, c):
        x, y = xy
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise IndexError("pixel out of range: %r" % (xy,))
        self.px[y][x] = c

    def __getitem__(self, xy):
        return self.px[xy[1]][xy[0]]

    def fill(self, c):
        for row in self.px:
            row[:] = [c] * self.width

    def to_rows(self, colors):
        """Same letters as test/esphome_stub/esphome.h."""
        def ch(i):
            if i == 0:
                return "."
            r, g, b = colors[i]
            if r > 200 and g < 150:
                return "O"
            if g > 150 and r < 100:
                return "G"
            if b > 200 and r < 100:
                return "B"
            if r > 200 and g > 200:
                return "W"
            if r < 60 and g < 60 and b < 60:
                return ","
            return "#"
        return ["".join(ch(i) for i in row) for row in self.px]
