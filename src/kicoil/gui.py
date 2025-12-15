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
# This file was created using claude.ai because hand-writing GUI code sucks. The rest of kicoil is written by hand.
#

""" GUI for generating KiCad footprints using kicoil. """

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import sys
import logging
import warnings
import traceback
from pathlib import Path
from contextlib import contextmanager
from io import BytesIO

from .geometry import PlanarInductor, divisors, CircleShape
from .svg import make_transparent_svg

try:
    # for rendering gerbonara's svg output to PNG
    import cairosvg
    # for scaling the rendered PNGs to the UI's resolution since tkinter is very limited there
    from PIL import Image, ImageTk
    HAS_PREVIEW = True
except ImportError:
    HAS_PREVIEW = False


class TextWidgetHandler(logging.Handler):
    """Custom logging handler that writes to a tkinter Text widget"""
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
        self.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
        
    def emit(self, record):
        msg = self.format(record)

        # Determine tag based on log level
        if record.levelno >= logging.ERROR:
            tag = 'error'
        elif record.levelno >= logging.WARNING:
            tag = 'warning'
        else:
            tag = 'info'

        # Temporarily enable widget to insert text
        self.text_widget['state'] = 'normal'
        self.text_widget.insert(tk.END, msg + '\n', tag)
        self.text_widget.see(tk.END)
        self.text_widget['state'] = 'disabled'
        self.text_widget.update_idletasks()


# https://stackoverflow.com/questions/27820178/how-to-add-placeholder-to-an-entry-in-tkinter
class EntryWithPlaceholder(tk.Entry):
    def __init__(self, master=None, placeholder="empty", color='grey', *args, **kwargs):
        # Initialize parent Entry with all provided arguments
        super().__init__(master, *args, **kwargs)

        self.placeholder = placeholder
        self.placeholder_color = color
        self.showing_placeholder = False

        # Get the default foreground color from the created widget
        self.default_fg_color = self['fg']

        self.bind("<FocusIn>", self.foc_in)
        self.bind("<FocusOut>", self.foc_out)

        # Check initial state and show placeholder if empty
        # Use a small delay to ensure the widget is fully initialized
        self.after(1, self._check_initial_state)

    def _check_initial_state(self):
        if not super().get():
            self.put_placeholder()

    def put_placeholder(self):
        self.showing_placeholder = True
        self['fg'] = self.placeholder_color
        super().delete(0, 'end')
        super().insert(0, self.placeholder)

    def update_placeholder(self, new_placeholder):
        self.placeholder = new_placeholder
        # If currently showing placeholder, update the display
        if self.showing_placeholder:
            super().delete(0, 'end')
            super().insert(0, self.placeholder)

    def foc_in(self, *args):
        if self.showing_placeholder:
            self.showing_placeholder = False
            self['fg'] = self.default_fg_color
            super().delete(0, 'end')

    def foc_out(self, *args):
        if not super().get():
            self.put_placeholder()
        else:
            self.showing_placeholder = False

    def get(self):
        if self.showing_placeholder:
            return ''
        return super().get()


class KiCoilGUI:
    def __init__(self, root, kicad_inst=None):
        self.kicad_inst = kicad_inst
        self.root = root
        self.root.title("KiCoil - Planar Inductor Generator")
        self.root.geometry("1000x650")

        style = ttk.Style()
        style.theme_use('clam')

        main_container = ttk.Frame(root)
        main_container.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        main_container.columnconfigure(0, weight=0)  # Left panel doesn't grow horizontally
        main_container.columnconfigure(1, weight=1)  # Preview panel grows to fill space
        main_container.rowconfigure(0, weight=1)

        main_frame = ttk.Frame(main_container, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        title_frame = ttk.Frame(main_frame)
        title_frame.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        ttk.Label(title_frame, text="Planar Inductor Generator",
                 font=('Helvetica', 16, 'bold')).pack(side=tk.LEFT)

        self.preview_visible = tk.BooleanVar(value=True)
        self.preview_button = ttk.Button(title_frame, text="Hide Preview",
                  command=self.toggle_preview, width=15)
        self.preview_button.pack(side=tk.RIGHT)

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)

        geometry_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(geometry_frame, text="Geometry")
        self.create_geometry_params(geometry_frame)

        traces_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(traces_frame, text="Traces")
        self.create_trace_params(traces_frame)

        via_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(via_frame, text="Vias")
        self.create_via_params(via_frame)

        output_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(output_frame, text="Output")
        self.create_output_params(output_frame)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=3, pady=10)
        
        ttk.Button(button_frame, text="Show Valid Twists", 
                  command=self.show_valid_twists, width=20).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Save Footprint File", 
                  command=self.save_footprint_file, width=20).pack(side=tk.LEFT, padx=5)
        #if self.kicad_inst: FIXME
        #    ttk.Button(button_frame, text="Update Footprint on Board", 
        #              command=self.update_board_footprint, width=20).pack(side=tk.LEFT, padx=5)
        
        status_label = ttk.Label(main_frame, text="Output:", font=('Helvetica', 10, 'bold'))
        status_label.grid(row=3, column=0, sticky=tk.W, pady=(10, 0))
        
        self.output_text = scrolledtext.ScrolledText(main_frame, height=8, width=80, state='disabled')
        self.output_text.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        self.output_text.tag_config('error', foreground='red')
        self.output_text.tag_config('warning', foreground='orange')
        self.output_text.tag_config('info', foreground='black')

        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=0)  # Notebook doesn't grow vertically
        main_frame.rowconfigure(4, weight=1)  # Output area takes all vertical space

        self.preview_frame = ttk.LabelFrame(main_container, text="Preview", padding=10)

        if HAS_PREVIEW:
            # Create canvas for image display
            self.preview_canvas = tk.Canvas(self.preview_frame, bg='white')
            self.preview_canvas.pack(fill=tk.BOTH, expand=True)
            self.preview_image = None  # Store reference to prevent garbage collection
            self.preview_raw_image = None  # Store unscaled image for rescaling

            # Bind canvas resize event to update preview
            self.preview_canvas.bind('<Configure>', self._on_preview_resize)
        
        else:
            info_text = "Preview not available\n\nInstall dependencies:\npip install cairosvg pillow"
            self.preview_label = ttk.Label(self.preview_frame, text=info_text,
                                           justify=tk.CENTER, anchor=tk.CENTER)
            self.preview_label.pack(fill=tk.BOTH, expand=True)

        self.preview_frame.grid(row=0, column=1, sticky=(tk.N, tk.S, tk.E, tk.W), padx=(10, 10), pady=10)
                
        self.current_model = None
        self._validation_after_id = None
        self.setup_logging()
        self.setup_traces()
        self.root.after(100, self.validate_parameters)

    def _on_preview_resize(self, event):
        # Debounce resize events - only update after resize is complete
        if hasattr(self, '_resize_after_id') and self._resize_after_id is not None:
            self.root.after_cancel(self._resize_after_id)
        self._resize_after_id = self.root.after(100, self._rescale_preview)

    def _rescale_preview(self):
        canvas_width = self.preview_canvas.winfo_width()
        canvas_height = self.preview_canvas.winfo_height()
        if canvas_width <= 1 or canvas_height <= 1 or self.preview_raw_image is None:
            self.preview_canvas.delete("all")
            return

        # Calculate scaling to fit within canvas
        image = self.preview_raw_image.copy()
        img_ratio = image.width / image.height
        canvas_ratio = canvas_width / canvas_height

        if img_ratio > canvas_ratio:
            # Image is wider than canvas
            new_width = int(canvas_width * 0.95)
            new_height = int(new_width / img_ratio)
        else:
            # Image is taller than canvas
            new_height = int(canvas_height * 0.95)
            new_width = int(new_height * img_ratio)

        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

        self.preview_image = ImageTk.PhotoImage(image)
        self.preview_canvas.create_image(
            canvas_width // 2, canvas_height // 2,
            image=self.preview_image, anchor=tk.CENTER
        )

    def toggle_preview(self):
        if self.preview_visible.get():
            self.preview_frame.grid_forget()
            self.preview_visible.set(False)
            self.preview_button.config(text="Show Preview")

            current_width = self.root.winfo_width()
            current_height = self.root.winfo_height()
            new_width = max(680, current_width - 400)
            self.root.geometry(f"{new_width}x{current_height}")

        else:
            self.preview_frame.grid(row=0, column=1, sticky=(tk.N, tk.S, tk.E, tk.W), padx=(10, 0), pady=10)
            self.preview_visible.set(True)
            self.preview_button.config(text="Hide Preview")

            current_width = self.root.winfo_width()
            current_height = self.root.winfo_height()
            new_width = current_width + 400  # Add ~400px for preview
            self.root.geometry(f"{new_width}x{current_height}")

    def create_geometry_params(self, parent):
        row = 0

        # Turns
        ttk.Label(parent, text="Number of Turns:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.turns_var = tk.IntVar(value=7)
        ttk.Spinbox(parent, from_=1, to=100, textvariable=self.turns_var,
                   width=15).grid(row=row, column=1, sticky=tk.W, pady=5)
        ttk.Label(parent, text="Number of spiral turns",
                 foreground='gray').grid(row=row, column=2, sticky=tk.W, padx=(10, 0))
        row += 1

        # Twists
        ttk.Label(parent, text="Twists per Revolution:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.twists_var = tk.IntVar(value=4)
        ttk.Spinbox(parent, from_=0, to=50, textvariable=self.twists_var,
                   width=15).grid(row=row, column=1, sticky=tk.W, pady=5)
        ttk.Label(parent, text="Must be co-prime to turns",
                 foreground='gray').grid(row=row, column=2, sticky=tk.W, padx=(10, 0))
        row += 1

        # Outer Diameter
        ttk.Label(parent, text="Outer Diameter (mm):").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.outer_dia_var = tk.DoubleVar(value=50.0)
        ttk.Spinbox(parent, from_=1, to=500, increment=0.5,
                   textvariable=self.outer_dia_var, width=15).grid(row=row, column=1, sticky=tk.W, pady=5)
        ttk.Label(parent, text="Outside diameter of coil",
                 foreground='gray').grid(row=row, column=2, sticky=tk.W, padx=(10, 0))
        row += 1

        # Inner Diameter
        ttk.Label(parent, text="Inner Diameter (mm):").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.inner_dia_var = tk.DoubleVar(value=25.0)
        ttk.Spinbox(parent, from_=0, to=500, increment=0.5,
                   textvariable=self.inner_dia_var, width=15).grid(row=row, column=1, sticky=tk.W, pady=5)
        ttk.Label(parent, text="Inside diameter of coil",
                 foreground='gray').grid(row=row, column=2, sticky=tk.W, padx=(10, 0))
        row += 1

        # Layer Mode
        ttk.Label(parent, text="Layer Mode:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.layer_mode_var = tk.IntVar(value=2)
        layer_frame = ttk.Frame(parent)
        layer_frame.grid(row=row, column=1, columnspan=2, sticky=tk.W, pady=5)
        ttk.Radiobutton(layer_frame, text="Two Layer", variable=self.layer_mode_var,
                       value=2).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(layer_frame, text="Single Layer", variable=self.layer_mode_var,
                       value=1).pack(side=tk.LEFT)
        row += 1

        # Direction
        ttk.Label(parent, text="Winding Direction:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.direction_var = tk.StringVar(value="counter-clockwise")
        dir_frame = ttk.Frame(parent)
        dir_frame.grid(row=row, column=1, columnspan=2, sticky=tk.W, pady=5)
        ttk.Radiobutton(dir_frame, text="Counter-Clockwise", variable=self.direction_var,
                       value="counter-clockwise").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(dir_frame, text="Clockwise", variable=self.direction_var,
                       value="clockwise").pack(side=tk.LEFT)
        row += 1

    def create_trace_params(self, parent):
        row = 0

        # Trace Width
        ttk.Label(parent, text="Trace Width (mm):").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.trace_width_entry = EntryWithPlaceholder(parent, placeholder="automatic", width=15)
        self.trace_width_entry.grid(row=row, column=1, sticky=tk.W, pady=5)
        row += 1

        # Clearance
        ttk.Label(parent, text="Clearance (mm):").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.clearance_entry = EntryWithPlaceholder(parent, placeholder="automatic", width=15)
        self.clearance_entry.grid(row=row, column=1, sticky=tk.W, pady=5)
        row += 1

        # Copper Thickness (in µm)
        ttk.Label(parent, text="Copper Thickness (µm):").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.copper_thickness_var = tk.DoubleVar(value=35.0)  # 35µm = 0.035mm = 1 Oz
        ttk.Spinbox(parent, from_=1, to=1000, increment=1, format="%.1f",
                   textvariable=self.copper_thickness_var, width=15).grid(row=row, column=1, sticky=tk.W, pady=5)
        ttk.Label(parent, text="35µm = 1 Oz copper",
                 foreground='gray').grid(row=row, column=2, sticky=tk.W, padx=(10, 0))
        row += 1
        
    def create_via_params(self, parent):
        """Create via parameter controls"""
        row = 0
        
        # Via Diameter
        ttk.Label(parent, text="Via Diameter (mm):").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.via_diameter_var = tk.DoubleVar(value=0.6)
        ttk.Spinbox(parent, from_=0.1, to=5.0, increment=0.1, format="%.2f",
                   textvariable=self.via_diameter_var, width=15).grid(row=row, column=1, sticky=tk.W, pady=5)
        row += 1
        
        # Via Drill
        ttk.Label(parent, text="Via Drill (mm):").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.via_drill_entry = EntryWithPlaceholder(parent, placeholder="automatic", width=15)
        self.via_drill_entry.grid(row=row, column=1, sticky=tk.W, pady=5)
        row += 1

        # Via Offset
        ttk.Label(parent, text="Via Offset (mm):").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.via_offset_entry = EntryWithPlaceholder(parent, placeholder="automatic", width=15)
        self.via_offset_entry.grid(row=row, column=1, sticky=tk.W, pady=5)
        row += 1
        
        # Stagger Inner Vias
        self.stagger_inner_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(parent, text="Stagger inner via ring", 
                       variable=self.stagger_inner_var).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5)
        row += 1
        
        # Stagger Outer Vias
        self.stagger_outer_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(parent, text="Stagger outer via ring", 
                       variable=self.stagger_outer_var).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5)
        row += 1
        
    def create_output_params(self, parent):
        row = 0

        # Footprint Name
        ttk.Label(parent, text="Footprint Name:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.footprint_name_entry = EntryWithPlaceholder(parent, placeholder="automatic")
        self.footprint_name_entry.grid(row=row, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        row += 1

        # KiCad layer names
        copper_layers = ['F.Cu', 'B.Cu'] + [f'In{i}.Cu' for i in range(1, 31)]

        # Top Layer
        ttk.Label(parent, text="Top Layer:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.top_layer_var = tk.StringVar(value="F.Cu")
        top_layer_combo = ttk.Combobox(parent, textvariable=self.top_layer_var,
                                        values=copper_layers, state='readonly', width=23)
        top_layer_combo.grid(row=row, column=1, sticky=tk.W, pady=5)
        row += 1

        # Bottom Layer
        ttk.Label(parent, text="Bottom Layer:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.bottom_layer_var = tk.StringVar(value="B.Cu")
        bottom_layer_combo = ttk.Combobox(parent, textvariable=self.bottom_layer_var,
                                           values=copper_layers, state='readonly', width=23)
        bottom_layer_combo.grid(row=row, column=1, sticky=tk.W, pady=5)
        row += 1

        # Circle Segments
        ttk.Label(parent, text="Circle Segments:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.circle_segments_var = tk.IntVar(value=64)
        ttk.Spinbox(parent, from_=8, to=360, textvariable=self.circle_segments_var,
                   width=15).grid(row=row, column=1, sticky=tk.W, pady=5)
        ttk.Label(parent, text="Points per 360° for arc interpolation",
                 foreground='gray').grid(row=row, column=2, sticky=tk.W, padx=(10, 0))
        row += 1

        # Arc Tolerance
        ttk.Label(parent, text="Arc Tolerance (mm):").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.arc_tolerance_var = tk.DoubleVar(value=0.02)
        ttk.Spinbox(parent, from_=0.001, to=1.0, increment=0.001, format="%.3f",
                   textvariable=self.arc_tolerance_var, width=15).grid(row=row, column=1, sticky=tk.W, pady=5)
        row += 1

        # Keepout Zone
        ttk.Label(parent, text="Keepout Zone:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.keepout_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(parent, text="Add keepout area",
                       variable=self.keepout_var).grid(row=row, column=1, sticky=tk.W, pady=5)
        row += 1

        # Keepout Margin
        ttk.Label(parent, text="Keepout Margin (mm):").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.keepout_margin_var = tk.DoubleVar(value=5.0)
        ttk.Spinbox(parent, from_=0, to=50, increment=0.5,
                   textvariable=self.keepout_margin_var, width=15).grid(row=row, column=1, sticky=tk.W, pady=5)
        ttk.Label(parent, text="Margin around coil",
                 foreground='gray').grid(row=row, column=2, sticky=tk.W, padx=(10, 0))
        row += 1
        
    def get_parameters(self):
        shape_params = {
            'outer_diameter'     : self.outer_dia_var.get(),
            'inner_diameter'     : self.inner_dia_var.get(),
        }

        params = {
            'shape'              : CircleShape(**shape_params),
            'turns'              : self.turns_var.get(),
            'layers'             : self.layer_mode_var.get(),
            'twists'             : self.twists_var.get(),
            'clockwise'          : (self.direction_var.get() == "clockwise"),
            'copper_thickness'   : self.copper_thickness_var.get() / 1000.0,  # µm -> mm
            'keepout_zone'       : self.keepout_var.get(),
            'keepout_margin'     : self.keepout_margin_var.get(),
            'via_diameter'       : self.via_diameter_var.get(),
            'stagger_inner_vias' : self.stagger_inner_var.get(),
            'stagger_outer_vias' : self.stagger_outer_var.get(),
            'layer_pair'         : f"{self.top_layer_var.get()},{self.bottom_layer_var.get()}",
        }

        if (trace_width_value := self.trace_width_entry.get()):
            params['trace_width'] = float(trace_width_value)

        if (clearance_value := self.clearance_entry.get()):
            params['clearance'] = float(clearance_value)

        if (via_drill_value := self.via_drill_entry.get()):
            params['via_drill'] = float(via_drill_value)

        if (via_offset_value := self.via_offset_entry.get()):
            params['via_offset'] = float(via_offset_value)

        return params
    
    def setup_logging(self):
        """Set up logging handler to capture kicoil logger output for display in the output text widget"""
        self.kicoil_logger = logging.getLogger('kicoil')
        self.kicoil_logger.setLevel(logging.INFO)
        self.kicoil_logger.handlers.clear()
        self.log_handler = TextWidgetHandler(self.output_text)
        self.kicoil_logger.addHandler(self.log_handler)
    
    @contextmanager
    def capture_warnings(self):
        """Context manager to capture kicoil's warnings to the output text widget"""
        def show_warning(message, category, filename, lineno, file=None, line=None):
            self.output_text['state'] = 'normal'
            self.output_text.insert(tk.END, f'{message}\n', 'warning')
            self.output_text.see(tk.END)
            self.output_text['state'] = 'disabled'
            self.output_text.update_idletasks()

        old_showwarning, warnings.showwarning = warnings.showwarning, show_warning
        try:
            yield
        finally:
            warnings.showwarning = old_showwarning
    
    def setup_traces(self):
        for var in [
                    self.turns_var,
                    self.outer_dia_var,
                    self.inner_dia_var,
                    self.layer_mode_var,
                    self.direction_var,
                    self.twists_var,
                    self.copper_thickness_var,
                    self.keepout_var,
                    self.keepout_margin_var,
                    self.via_diameter_var,
                    self.stagger_inner_var,
                    self.stagger_outer_var,
                    self.top_layer_var,
                    self.bottom_layer_var]:
            var.trace_add('write', self._on_parameter_change)

        for entry in [self.trace_width_entry, self.clearance_entry,
                      self.via_drill_entry, self.via_offset_entry,
                      self.footprint_name_entry]:
            entry.bind('<KeyRelease>', lambda e: self._on_parameter_change())
    
    def _on_parameter_change(self, *args):
        # Schedule validation to avoid too many rapid calls
        if self._validation_after_id is not None:
            self.root.after_cancel(self._validation_after_id)
        self._validation_after_id = self.root.after(200, self.validate_parameters)
    
    def validate_parameters(self):
        """Validate parameters by creating PlanarInductor instance"""
        try:
            self.output_text['state'] = 'normal'
            self.output_text.delete('1.0', tk.END)

            with self.capture_warnings():
                self.current_model = PlanarInductor(**self.get_parameters())

            # If we got here, parameters are valid
            self.output_text.insert(tk.END, "Parameters valid\n", 'info')
            self.update_placeholders()
            self.update_preview()
            return True

        except ValueError as e:
            self.output_text.insert(tk.END, f"ERROR: {e}\n", 'error')
            self.output_text.see(tk.END)

            self.current_model = None
            self.update_placeholders()
            return False
            
        except Exception as e:
            tb = traceback.format_exc()
            self.output_text.insert(tk.END, f"Unexpected error:\n{tb}\n", 'error')
            self.output_text.see(tk.END)

            print(tb, file=sys.stderr)

            self.current_model = None
            self.update_placeholders()
            return True

        finally:
            self.output_text['state'] = 'disabled'

    def update_placeholders(self):
        if self.current_model is None:
            self.trace_width_entry.update_placeholder("automatic")
            self.clearance_entry.update_placeholder("automatic")
            self.via_drill_entry.update_placeholder("automatic")
            self.via_offset_entry.update_placeholder("automatic")
            self.footprint_name_entry.update_placeholder("automatic")
        
        else:
            if not self.trace_width_entry.get():
                self.trace_width_entry.update_placeholder(f"auto: {self.current_model.trace_width:.2f}")

            if not self.clearance_entry.get():
                self.clearance_entry.update_placeholder(f"auto: {self.current_model.clearance:.2f}")

            if not self.via_drill_entry.get():
                self.via_drill_entry.update_placeholder(f"auto: {self.current_model.via_drill:.2f}")

            if not self.via_offset_entry.get():
                self.via_offset_entry.update_placeholder(f"auto: {self.current_model.via_offset:.2f}")

            if not self.footprint_name_entry.get():
                self.footprint_name_entry.update_placeholder(self.current_model.default_footprint_name)

    def update_preview(self):
        if not HAS_PREVIEW:
            return

        arc_tolerance = self.arc_tolerance_var.get()
        circle_segments = self.circle_segments_var.get()

        footprint = self.current_model.render_footprint(None, arc_tolerance, circle_segments)
        svg_tag = make_transparent_svg(footprint)
        viewbox = svg_tag.attrs.get('viewBox', '0 0 800 800')
        _, _, svg_width, svg_height = map(float, viewbox.split())
        min_dimension = 800
        scale = max(min_dimension / svg_width, min_dimension / svg_height)
        output_width = int(svg_width * scale)
        output_height = int(svg_height * scale)
        svg_tag.attrs['width'] = f'{output_width}px'
        svg_tag.attrs['height'] = f'{output_height}px'

        png_data = cairosvg.svg2png(bytestring=str(svg_tag).encode('utf-8'))
        self.preview_raw_image = Image.open(BytesIO(png_data))
        self._rescale_preview()

    
    def show_valid_twists(self):
        turns = self.turns_var.get()
        valid_twists = list(divisors(turns, turns))

        self.output_text['state'] = 'normal'
        self.output_text.delete('1.0', tk.END)
        self.output_text.insert('1.0', f'Valid twist counts for {turns} turns:\n')
        for d in valid_twists:
            self.output_text.insert(tk.END, f'  {d}\n')
        self.output_text['state'] = 'disabled'
    
    def update_board_footprint(self):
        if not self.validate_parameters():
            messagebox.showerror("Error", "Cannot generate model. Please check the output for warnings or errors.")
            return

        from kipy.board_types import FootprintInstance, Footprint, Pad, BoardArc, BoardSegment, FootprintAttributes,\
                PadStack, PadStackLayer, PadStackType, PadStackShape, DrillProperties, PadType
        from kipy.geometry import Vector2
        from kipy.common_types import GraphicAttributes, StrokeAttributes
        from kipy.util import from_mm
        from kipy.util.board_layer import CANONICAL_LAYER_NAMES

        from gerbonara.cad.kicad.footprints import Atom

        board = self.kicad_inst.get_board()
        selected = [item for item in board.get_selection() if isinstance(item, FootprintInstance)]

        if not selected:
            messagebox.showerror("Error", "No footprint selected. Select one footprint to replace in KiCad's PCB editor.")
            return
        elif len(selected) > 1:
            messagebox.showerror("Error", "More than one footprint selected. Select only the footprint you want to replace.")
            return

        selected_footprint, = selected

        footprint_name = self.footprint_name_entry.get() or None
        arc_tolerance = self.arc_tolerance_var.get()
        circle_segments = self.circle_segments_var.get()

        self.output_text['state'] = 'normal'
        self.output_text.insert(tk.END, "Rendering footprint...\n", 'info')
        self.output_text.see(tk.END)

        model = self.current_model.render_footprint(footprint_name, arc_tolerance, circle_segments)
        selected_footprint.attributes.exclude_from_bill_of_materials = True
        layer_map = {v: k for k, v in CANONICAL_LAYER_NAMES.items()}
        items = []

        for line in model.lines:
            seg = BoardSegment()
            seg.start = Vector2.from_xy(from_mm(line.start.x), from_mm(line.start.y))
            seg.end = Vector2.from_xy(from_mm(line.end.x), from_mm(line.end.y))
            seg.attributes.stroke.width = from_mm(line.stroke.width)
            seg.layer = layer_map[line.layer]
            selected_footprint.definition.add_item(seg)
            items.append(seg)

        for ref in model.arcs:
            arc = BoardArc()
            arc.start = Vector2.from_xy(from_mm(ref.start.x), from_mm(ref.start.y))
            arc.mid = Vector2.from_xy(from_mm(ref.mid.x), from_mm(ref.mid.y))
            arc.end = Vector2.from_xy(from_mm(ref.end.x), from_mm(ref.end.y))
            arc.attributes.stroke.width = from_mm(ref.stroke.width)
            arc.layer = layer_map[ref.layer]
            selected_footprint.definition.add_item(arc)
            items.append(arc)

        for ref in model.pads:
            pad = Pad() 
            pad.number = ref.number
            pad.position = Vector2.from_xy(from_mm(ref.at.x), from_mm(ref.at.y))
            pad.type = PadType.PT_SMD if ref.type == Atom.smd else PadType.PT_PTH
            pad.padstack.type = PadStackType.PST_NORMAL
            pad.padstack.layers = [layer_map[name] for name in ref.layers]
            layer = pad.padstack.copper_layers[0]
            layer.shape = PadStackShape.PSS_CIRCLE
            layer.size = Vector2.from_xy(from_mm(ref.size.x), from_mm(ref.size.y))
            layer.layer = layer_map[ref.layers[0]] # ? duplicate
            if ref.drill:
                pad.padstack.drill.diameter = Vector2.from_xy(from_mm(ref.drill.diameter), from_mm(ref.drill.diameter))
            selected_footprint.definition.add_item(pad)
            items.append(pad)

        commit = board.begin_commit()
        board.create_items(items)
        board.update_items([selected_footprint])
        board.push_commit(commit, 'Updated planar coil footprint')
        self.output_text.insert(tk.END, "Done.", 'info')
        self.output_text['state'] = 'disabled'
        self.output_text.see(tk.END)

    def save_footprint_file(self):
        if not self.validate_parameters():
            messagebox.showerror("Error", "Cannot generate model. Please check the output for warnings or errors.")
            return
        
        try:
            footprint_name = self.footprint_name_entry.get() or None
            arc_tolerance = self.arc_tolerance_var.get()
            circle_segments = self.circle_segments_var.get()

            self.output_text['state'] = 'normal'
            self.output_text.insert(tk.END, "Rendering footprint...\n\n", 'info')

            footprint = self.current_model.render_footprint(footprint_name, arc_tolerance, circle_segments)
            default_name = footprint_name or self.current_model.default_footprint_name
            output_file = filedialog.asksaveasfilename(
                title="Save KiCad Footprint",
                defaultextension=".kicad_mod",
                initialfile=f"{default_name}.kicad_mod",
                filetypes=[("KiCad Footprint", "*.kicad_mod"), ("All files", "*.*")]
            )

            if not output_file:
                self.output_text.insert(tk.END, "\nSave cancelled.\n", 'info')
                return

            Path(output_file).write_text(footprint.serialize())
            self.output_text.insert(tk.END, f"\nSuccess! Footprint saved to:\n  {output_file}\n", 'info')

        except Exception as e:
            tb = traceback.format_exc()
            self.output_text['state'] = 'normal'
            self.output_text.insert(tk.END, f"\nError generating footprint:\n{tb}\n", 'error')
            self.output_text.see(tk.END)

            print(tb, file=sys.stderr)

            messagebox.showerror("Error", f"Error generating footprint: {e}")

        finally:
            self.output_text['state'] = 'disabled'


def main(kicad_inst=None):
    from kipy import KiCad
    from kipy.errors import ConnectionError
    kicad_inst = KiCad()
    root = tk.Tk()
    app = KiCoilGUI(root, kicad_inst)
    root.mainloop()
