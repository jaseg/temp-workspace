
import textwrap

from gerbonara.utils import Tag
from gerbonara.layers import LayerStack

def make_transparent_svg(footprint):
    stack = LayerStack()
    footprint.render(stack)
    root_tag = stack.to_svg(margin=5, colors={
           'top copper': 'hsl(240 90% 65%)',
        'bottom copper': 'hsl(  0 90% 65%)',
            'drill pth': 'hsl(120 60% 50%)',
        })

    root_tag.children[0].attrs['opacity'] = '98%'
    root_tag.children[1].attrs['opacity'] = '98%'
    root_tag.children[1].attrs['style'] = 'mix-blend-mode: multiply'
    return root_tag

