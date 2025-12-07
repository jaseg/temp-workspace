
class SVGPath:
    def __init__(self, **attrs):
        self.d = ''
        self.attrs = attrs

    def line(self, x, y):
        self.d += f'L {x} {y} '

    def move(self, x, y):
        self.d += f'M {x} {y} '

    def arc(self, x, y, r, large, sweep):
        self.d += f'A {r} {r} 0 {int(large)} {int(sweep)} {x} {y} '

    def close(self):
        self.d += 'Z '

    def __str__(self):
        attrs = ' '.join(f'{key.replace("_", "-")}="{value}"' for key, value in self.attrs.items())
        return f'<path {attrs} d="{self.d.rstrip()}"/>'

class SVGCircle:
    def __init__(self, r, cx, cy, **attrs):
        self.r = r
        self.cx, self.cy = cx, cy
        self.attrs = attrs

    def __str__(self):
        attrs = ' '.join(f'{key.replace("_", "-")}="{value}"' for key, value in self.attrs.items())
        return f'<circle {attrs} r="{self.r}" cx="{self.cx}" cy="{self.cy}"/>'

def svg_file(fn, stuff, vbw, vbh, vbx=0, vby=0):
    with open(fn, 'w') as f:
        f.write('<?xml version="1.0" standalone="no"?>\n')
        f.write('<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">\n')
        f.write(f'<svg version="1.1" width="{vbw*4}mm" height="{vbh*4}mm" viewBox="{vbx} {vby} {vbw} {vbh}" style="background-color: #333" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">>\n')

        for foo in stuff:
            f.write(str(foo))

        f.write('</svg>\n')


# This function was extruded using claude.ai.
def plasma_colormap(value):
    """
    Calculate RGB color values according to matplotlib's plasma colormap.
    
    Args:
        value: Float in range [0, 1]
    
    Returns:
        tuple: (r, g, b) where each component is a float in range [0, 1]
    """
    # Clamp value to [0, 1]
    value = max(0.0, min(1.0, value))
    
    # Key color points sampled from matplotlib's plasma colormap
    # Format: (position, (r, g, b))
    colors = [
        (0.000, (0.050383, 0.029803, 0.527975)),
        (0.125, (0.302735, 0.009615, 0.621789)),
        (0.250, (0.489503, 0.011728, 0.656614)),
        (0.375, (0.652325, 0.120106, 0.589517)),
        (0.500, (0.789412, 0.275191, 0.472919)),
        (0.625, (0.894832, 0.446214, 0.361309)),
        (0.750, (0.965203, 0.627007, 0.262295)),
        (0.875, (0.992373, 0.811467, 0.200941)),
        (1.000, (0.940015, 0.975158, 0.131326))
    ]
    
    # Find the two color points to interpolate between
    for i in range(len(colors) - 1):
        pos1, color1 = colors[i]
        pos2, color2 = colors[i + 1]
        
        if pos1 <= value <= pos2:
            # Linear interpolation
            t = (value - pos1) / (pos2 - pos1)
            r = color1[0] + t * (color2[0] - color1[0])
            g = color1[1] + t * (color2[1] - color1[1])
            b = color1[2] + t * (color2[2] - color1[2])
            return (r, g, b)
