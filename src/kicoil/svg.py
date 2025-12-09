
# Copyright 2025 Jan Sebastian Götte <code@jaseg.de>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import textwrap

from gerbonara.utils import Tag
from gerbonara.layers import LayerStack

def make_transparent_svg(footprint):
    stack = LayerStack()
    footprint.render(stack)
    root_tag = stack.to_svg(margin=5, colors={
           'top copper': '#eb5c5c',
        'bottom copper': '#5c5ceb',
            'drill pth': '#52cc52',
        })

    root_tag.children[0].attrs['opacity'] = '0.7'
    root_tag.children[1].attrs['opacity'] = '0.7'
    root_tag.children[1].attrs['style'] = 'mix-blend-mode: multiply'
    return root_tag

