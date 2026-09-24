"""Tkinter wizard for the CFX-Post post-processing toolkit."""
from __future__ import annotations

import queue
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .config import CreatedVariableConfig, ProjectConfig, SectionVariableConfig, ThermalComfortConfig, ToolkitConfig, VisualizationConfig
from .progress import ProgressEvent
from .workflows import run_full_workflow, run_thermal_comfort_directory_workflow, run_visualization_workflow

MODE_FULL = "full"
MODE_THERMAL = "thermal"
MODE_VISUALIZATION = "visualization"

BASE_VARIABLES = [
    ("Temperature", "Temperature"),
    ("Relative Humidity", "Relative Humidity"),
    ("Velocity", "Velocity"),
    ("Radiation Temperature", "Radiation Temperature"),
]
CALCULATED_VARIABLES = {
    "relative_air_speed": [("Relative Air Speed", "Relative_Air_Speed")],
    "pmv_ppd": [("PMV", "PMV"), ("PPD", "PPD")],
    "set": [("SET", "SET")],
    "utci": [("UTCI", "UTCI")],
    "draft_rate": [("Turbulence Intensity", "Turbulence_Intensity"), ("Draft Rate", "Draft_Rate")],
    "clothing_temperature": [
        ("Clothing Surface Temperature", "Clothing_Surface_Temperature"),
        ("Convective HTC", "Convective_HTC"),
        ("Radiative HTC", "Radiative_HTC"),
    ],
    "operative_temperature": [("Operative Temperature", "Operative_Temperature")],
    "psychrometrics": [
        ("Wet Bulb Temperature", "Wet_Bulb_Temperature"),
        ("Dew Point Temperature", "Dew_Point_Temperature"),
        ("Humidity Ratio", "Humidity_Ratio"),
    ],
}

MET_PRESETS = [
    ("Sleeping: 0.7", 0.7), ("Reclining: 0.8", 0.8), ("Seated, quiet: 1.0", 1.0),
    ("Reading, seated: 1.0", 1.0), ("Writing: 1.0", 1.0), ("Typing: 1.1", 1.1),
    ("Standing, relaxed: 1.2", 1.2), ("Filing, seated: 1.2", 1.2),
    ("Flying aircraft, routine: 1.2", 1.2), ("Filing, standing: 1.4", 1.4),
    ("Driving a car: 1.5", 1.5), ("Walking about: 1.7", 1.7), ("Cooking: 1.8", 1.8),
    ("Table sawing: 1.8", 1.8), ("Walking 2mph (3.2km/h): 2.0", 2.0),
    ("Lifting/packing: 2.1", 2.1), ("Seated, heavy limb movement: 2.2", 2.2),
    ("Light machine work: 2.2", 2.2), ("Flying aircraft, combat: 2.4", 2.4),
    ("Walking 3mph (4.8km/h): 2.6", 2.6), ("House cleaning: 2.7", 2.7),
    ("Driving, heavy vehicle: 3.2", 3.2), ("Dancing: 3.4", 3.4), ("Calisthenics: 3.5", 3.5),
    ("Walking 4mph (6.4km/h): 3.8", 3.8), ("Tennis: 3.8", 3.8),
    ("Heavy machine work: 4.0", 4.0), ("Handling 100lb (45 kg) bags: 4.0", 4.0),
    ("Other", None),
]
CLO_PRESETS = [
    ("Walking shorts, short-sleeve shirt: 0.36 clo", 0.36),
    ("Typical summer indoor clothing: 0.5 clo", 0.5),
    ("Knee-length skirt, short-sleeve shirt, sandals, underwear: 0.54 clo", 0.54),
    ("Trousers, short-sleeve shirt, socks, shoes, underwear: 0.57 clo", 0.57),
    ("Trousers, long-sleeve shirt: 0.61 clo", 0.61),
    ("Knee-length skirt, long-sleeve shirt, full slip: 0.67 clo", 0.67),
    ("Sweat pants, long-sleeve sweatshirt: 0.74 clo", 0.74),
    ("Jacket, Trousers, long-sleeve shirt: 0.96 clo", 0.96),
    ("Typical winter indoor clothing: 1.0 clo", 1.0),
    ("Other", None),
]


class ScrollableFrame(ttk.Frame):
    def __init__(self, master, *, height=360):
        super().__init__(master)
        self.canvas = tk.Canvas(self, highlightthickness=0, height=height)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._window, width=e.width))
        self.canvas.grid(row=0, column=0, sticky="nsew"); self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.columnconfigure(0, weight=1); self.rowconfigure(0, weight=1)


class ToolkitWizard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CFX-Post Automation Toolkit")
        self.geometry("1180x820")
        self.minsize(980, 700)
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("vista")
        except tk.TclError:
            pass
        self.style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        self.style.configure("Subtitle.TLabel", font=("Segoe UI", 10))
        self.style.configure("Section.TLabelframe.Label", font=("Segoe UI", 10, "bold"))

        self.mode = tk.StringVar(value=MODE_FULL)
        self.current_page = "mode"
        self.page_history = []
        self.main_directory = tk.StringVar()
        self.export_directory = tk.StringVar()
        self.import_directory = tk.StringVar()
        self.execute_thermal_import = tk.BooleanVar(value=False)

        # Master location registries.
        self.surfaces = []
        self.section_surfaces = []
        self.volumes = []

        # Shared variable registries. Manual variables are existing native/import
        # names; created_variables are CFX USER SCALAR VARIABLE definitions.
        self.manual_variables = []
        self.created_variables = []

        # Panel-specific selection state.
        self.figure_selection = {}
        self.section_variable_selection = {}
        self.section_vector_selection = {}
        self.histogram_surface_selection = {}
        self.histogram_volume_selection = {}
        self.histogram_variable_selection = {}
        self.volume_variable_selection = {}
        self.table_surface_selection = {}
        self.table_volume_selection = {}
        self.table_variable_selection = {}
        self.variable_settings = {}

        self.plan_streamlines = tk.BooleanVar(value=False)
        self.section_streamlines = tk.BooleanVar(value=False)

        self.met_choice = tk.StringVar(value="Walking about: 1.7")
        self.met_other = tk.StringVar(value="1.7")
        self.clo_choice = tk.StringVar(value="Trousers, short-sleeve shirt, socks, shoes, underwear: 0.57 clo")
        self.clo_other = tk.StringVar(value="0.57")
        self.calculate_psychrometrics = tk.BooleanVar(value=False)
        self.calculate_utci = tk.BooleanVar(value=False)
        self.calculate_set = tk.BooleanVar(value=False)
        self.calculate_pmv_ppd = tk.BooleanVar(value=True)
        self.calculate_draft_rate = tk.BooleanVar(value=False)
        self.calculate_clothing_temperature = tk.BooleanVar(value=False)
        self.calculate_operative_temperature = tk.BooleanVar(value=True)

        # Visual types. Histograms are one GUI visual type; surface/volume
        # generation is derived from the selections inside that panel.
        self.visual_plan = tk.BooleanVar(value=True)
        self.visual_sections = tk.BooleanVar(value=False)
        self.visual_hist = tk.BooleanVar(value=False)
        self.visual_table = tk.BooleanVar(value=True)
        self.average_table_name = tk.StringVar(value="Average conditions")

        self.first_figure_number = tk.StringVar(value="1")
        self.camera_scale_factor = tk.StringVar(value="1.0")
        self.camera_margin = tk.StringVar(value="0.5")
        self.clip_plane_z_offset = tk.StringVar(value="0.1")
        self.max_cleaning_distance = tk.StringVar(value="1.0")
        self.image_width = tk.StringVar(value="2400")
        self.image_height = tk.StringVar(value="1600")
        self.velocity_vector_samples = tk.StringVar(value="100")
        self.streamline_samples = tk.StringVar(value="100")
        self.execute_print_session = tk.BooleanVar(value=False)

        self._build_shell()
        self.show_page("mode", push_history=False)

    # ------------------------------------------------------------------
    # Wizard shell / navigation
    # ------------------------------------------------------------------
    def _build_shell(self):
        root = ttk.Frame(self, padding=18)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        header = ttk.Frame(root)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        self.title_label = ttk.Label(header, style="Title.TLabel")
        self.title_label.grid(row=0, column=0, sticky="w")
        self.step_label = ttk.Label(header, style="Subtitle.TLabel")
        self.step_label.grid(row=1, column=0, sticky="w", pady=(3, 0))
        self.content = ttk.Frame(root)
        self.content.grid(row=1, column=0, sticky="nsew")
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)
        ttk.Separator(root).grid(row=2, column=0, sticky="ew", pady=(12, 10))
        buttons = ttk.Frame(root)
        buttons.grid(row=3, column=0, sticky="ew")
        buttons.columnconfigure(1, weight=1)
        self.back_button = ttk.Button(buttons, text="Back", command=self.go_back)
        self.back_button.grid(row=0, column=0)
        ttk.Button(buttons, text="Close", command=self.destroy).grid(row=0, column=2, padx=(8, 0))
        self.next_button = ttk.Button(buttons, text="Next", command=self.go_next)
        self.next_button.grid(row=0, column=3, padx=(8, 0))

    def _clear_content(self):
        for child in self.content.winfo_children():
            child.destroy()

    def _page_title(self, page):
        return {
            "mode": ("Choose workflow", "Select what the toolkit should do"),
            "thermal": ("Thermal comfort / CFX variables", "Configure calculations and optional CFX expression-derived variables"),
            "directories": ("Project directory", "Select the files/folders used by the workflow"),
            "visuals": ("Visual output types", "Choose only the outputs you want to generate"),
            "surfaces": ("Normal / top-view surfaces", "Master surface list and top-view contour variables"),
            "sections": ("Section views", "Section names and variables"),
            "histograms": ("Histograms", "Choose surface and/or volume histograms and their variables"),
            "table": ("Average table", "Choose surface/volume locations and variables"),
            "variable_settings": ("Variable ranges and resolution", "Shared bounds, contour counts and histogram divisions"),
            "controls": ("General controls", "Camera, numbering, cleaning, hardcopy and optional printing"),
        }[page]

    def show_page(self, page, *, push_history=True):
        if push_history and self.current_page != page:
            self.page_history.append(self.current_page)
        self.current_page = page
        self._clear_content()
        title, subtitle = self._page_title(page)
        self.title_label.configure(text=title)
        self.step_label.configure(text=subtitle)
        getattr(self, f"_build_{page}_page")()
        self.back_button.configure(state="normal" if self.page_history else "disabled")
        is_run_page = page == "controls" or (page == "directories" and self.mode.get() == MODE_THERMAL)
        self.next_button.configure(
            text="Run" if is_run_page else "Next",
            command=self.run_workflow if is_run_page else self.go_next,
        )

    def _build_mode_page(self):
        frame = ttk.Frame(self.content, padding=12)
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)
        opts = [
            (MODE_FULL, "Full automation", "Export → thermal comfort → import → selected visuals."),
            (MODE_THERMAL, "Thermal comfort calculations only", "Process existing export CSVs and create import CSV/session."),
            (MODE_VISUALIZATION, "Figures / table / histograms only", "Generate selected visuals from the currently open CFX case using temporary exports."),
        ]
        for r, (value, title, description) in enumerate(opts):
            box = ttk.Frame(frame, padding=12)
            box.grid(row=r, column=0, sticky="ew", pady=6)
            box.columnconfigure(1, weight=1)
            ttk.Radiobutton(box, variable=self.mode, value=value).grid(row=0, column=0, rowspan=2, padx=(0, 10), sticky="n")
            ttk.Label(box, text=title, font=("Segoe UI", 11, "bold")).grid(row=0, column=1, sticky="w")
            ttk.Label(box, text=description, wraplength=860).grid(row=1, column=1, sticky="w")

    # ------------------------------------------------------------------
    # Thermal comfort + optional expression-derived variables
    # ------------------------------------------------------------------
    def _build_thermal_page(self):
        frame = ttk.Frame(self.content, padding=12)
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)
        row = 0

        if self.mode.get() in (MODE_FULL, MODE_THERMAL):
            thermal = ttk.LabelFrame(frame, text="Thermal comfort calculations", padding=12, style="Section.TLabelframe")
            thermal.grid(row=row, column=0, sticky="ew", pady=(0, 12))
            thermal.columnconfigure(0, weight=1)

            occ = ttk.Frame(thermal)
            occ.grid(row=0, column=0, sticky="ew")
            occ.columnconfigure(1, weight=1)
            occ.columnconfigure(4, weight=1)
            ttk.Label(occ, text="Metabolic rate").grid(row=0, column=0, sticky="w")
            met = ttk.Combobox(occ, textvariable=self.met_choice, values=[x[0] for x in MET_PRESETS], state="readonly", width=38)
            met.grid(row=0, column=1, sticky="ew", padx=(8, 12))
            met.bind("<<ComboboxSelected>>", lambda _e: self._toggle_other_inputs())
            ttk.Label(occ, text="Other met").grid(row=0, column=2, sticky="w")
            self.met_other_entry = ttk.Entry(occ, textvariable=self.met_other, width=10)
            self.met_other_entry.grid(row=0, column=3, padx=(6, 18))
            ttk.Label(occ, text="Clothing").grid(row=1, column=0, sticky="w", pady=(10, 0))
            clo = ttk.Combobox(occ, textvariable=self.clo_choice, values=[x[0] for x in CLO_PRESETS], state="readonly", width=58)
            clo.grid(row=1, column=1, columnspan=3, sticky="ew", padx=(8, 12), pady=(10, 0))
            clo.bind("<<ComboboxSelected>>", lambda _e: self._toggle_other_inputs())
            ttk.Label(occ, text="Other clo").grid(row=1, column=4, sticky="w", pady=(10, 0))
            self.clo_other_entry = ttk.Entry(occ, textvariable=self.clo_other, width=10)
            self.clo_other_entry.grid(row=1, column=5, padx=(6, 0), pady=(10, 0))
            self._toggle_other_inputs()

            ttk.Separator(thermal).grid(row=1, column=0, sticky="ew", pady=12)
            calc = ttk.Frame(thermal)
            calc.grid(row=2, column=0, sticky="ew")
            items = [
                ("PMV / PPD", self.calculate_pmv_ppd),
                ("Operative temperature", self.calculate_operative_temperature),
                ("SET", self.calculate_set),
                ("UTCI", self.calculate_utci),
                ("Psychrometrics", self.calculate_psychrometrics),
                ("Draft rate + turbulence intensity", self.calculate_draft_rate),
                ("Clothing surface temperature + HTC", self.calculate_clothing_temperature),
            ]
            for i, (label, var) in enumerate(items):
                ttk.Checkbutton(calc, text=label, variable=var).grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 28), pady=5)
            row += 1

        if self.mode.get() in (MODE_FULL, MODE_VISUALIZATION):
            self._build_created_variables_section(frame, row)

    def _build_created_variables_section(self, parent, row):
        box = ttk.LabelFrame(parent, text="New variables from CFX expressions", padding=12, style="Section.TLabelframe")
        box.grid(row=row, column=0, sticky="nsew")
        box.columnconfigure(0, weight=1)
        ttk.Label(
            box,
            text=("Expressions must be dimensionally consistent in CFX/CEL. The variable object name and its internal "
                  "expression name are kept different automatically."),
            wraplength=980,
            foreground="#555555",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        add = ttk.Frame(box)
        add.grid(row=1, column=0, sticky="ew")
        add.columnconfigure(1, weight=1)
        ttk.Label(add, text="New variable name").grid(row=0, column=0, sticky="w", padx=(0, 8))
        entry = ttk.Entry(add)
        entry.grid(row=0, column=1, sticky="ew")
        def add_created(event=None):
            self._add_created_variable(entry)
            return "break"
        ttk.Button(add, text="Add", command=add_created).grid(row=0, column=2, padx=(8, 0))
        entry.bind("<Return>", add_created)
        entry.bind("<KP_Enter>", add_created)

        scroll = ScrollableFrame(box, height=260)
        scroll.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        inner = scroll.inner
        inner.columnconfigure(2, weight=1)
        ttk.Label(inner, text="Enabled", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, padx=4, sticky="w")
        ttk.Label(inner, text="Variable name", font=("Segoe UI", 9, "bold")).grid(row=0, column=1, padx=4, sticky="w")
        ttk.Label(inner, text="CEL expression", font=("Segoe UI", 9, "bold")).grid(row=0, column=2, padx=4, sticky="w")
        ttk.Label(inner, text="Internal expression name", font=("Segoe UI", 9, "bold")).grid(row=0, column=3, padx=4, sticky="w")

        # Permanent built-in reference row.
        built_enabled = tk.BooleanVar(value=True)
        ttk.Checkbutton(inner, variable=built_enabled, state="disabled").grid(row=1, column=0, padx=4, pady=4)
        ttk.Label(inner, text="Relative Humidity Percentage").grid(row=1, column=1, padx=4, sticky="w")
        ref_expr = ttk.Entry(inner, width=42)
        ref_expr.insert(0, "Relative Humidity*100")
        ref_expr.configure(state="disabled")
        ref_expr.grid(row=1, column=2, sticky="ew", padx=4, pady=4)
        ttk.Label(inner, text="Relative Humidity percentage", foreground="#666666").grid(row=1, column=3, padx=4, sticky="w")

        self.created_enabled_vars = {}
        self.created_expression_vars = {}
        for r, item in enumerate(self.created_variables, start=2):
            enabled = tk.BooleanVar(value=bool(item.get("enabled", True)))
            expr = tk.StringVar(value=item.get("expression", ""))
            self.created_enabled_vars[item["name"]] = enabled
            self.created_expression_vars[item["name"]] = expr
            ttk.Checkbutton(inner, variable=enabled).grid(row=r, column=0, padx=4, pady=4)
            ttk.Label(inner, text=item["name"]).grid(row=r, column=1, padx=4, sticky="w")
            ttk.Entry(inner, textvariable=expr, width=44).grid(row=r, column=2, sticky="ew", padx=4, pady=4)
            ttk.Label(inner, text=item["expression_name"], foreground="#666666").grid(row=r, column=3, padx=4, sticky="w")
            ttk.Button(inner, text="Delete", command=lambda n=item["name"]: self._delete_created_variable(n)).grid(row=r, column=4, padx=(8, 0), pady=2)

        ttk.Label(
            box,
            text=("Relative Humidity Percentage is always created internally, but visual panels continue to show only "
                  "'Relative Humidity'. Enabled user-created variables appear in every visual variable list."),
            wraplength=980,
            foreground="#666666",
        ).grid(row=3, column=0, sticky="w", pady=(8, 0))

    def _toggle_other_inputs(self):
        if hasattr(self, "met_other_entry"):
            self.met_other_entry.configure(state="normal" if self.met_choice.get() == "Other" else "disabled")
        if hasattr(self, "clo_other_entry"):
            self.clo_other_entry.configure(state="normal" if self.clo_choice.get() == "Other" else "disabled")

    def _preset_value(self, choice, presets, other):
        if choice.get() == "Other":
            return float(other.get())
        return next(value for label, value in presets if label == choice.get())

    def _capture_created_variables(self):
        enabled_vars = getattr(self, "created_enabled_vars", {})
        expression_vars = getattr(self, "created_expression_vars", {})
        for item in self.created_variables:
            name = item["name"]
            if name in enabled_vars:
                item["enabled"] = bool(enabled_vars[name].get())
            if name in expression_vars:
                item["expression"] = expression_vars[name].get().strip()

    def _reserved_names_casefold(self, *, include_expression_names=True):
        names = {"Relative Humidity Percentage", "Relative Humidity percentage"}
        for label, name in BASE_VARIABLES:
            names.update((label, name))
        for values in CALCULATED_VARIABLES.values():
            for label, name in values:
                names.update((label, name))
        names.update(self.manual_variables)
        for item in self.created_variables:
            names.add(item["name"])
            if include_expression_names:
                names.add(item["expression_name"])
        return {str(name).strip().casefold() for name in names if str(name).strip()}

    def _generate_expression_name(self, variable_name):
        reserved = self._reserved_names_casefold(include_expression_names=True)
        base = f"{variable_name} expression"
        candidate = base
        index = 2
        while candidate.casefold() in reserved or candidate.casefold() == variable_name.casefold():
            candidate = f"{base} {index}"
            index += 1
        return candidate

    def _validate_new_variable_name(self, name):
        name = str(name).strip()
        if not name:
            raise ValueError("Variable name cannot be blank.")
        if any(ch in name for ch in "\r\n,"):
            raise ValueError("Variable names cannot contain commas or line breaks.")
        if name.casefold() in self._reserved_names_casefold(include_expression_names=True):
            raise ValueError(f"'{name}' conflicts with an existing variable or internal expression name.")
        return name

    def _add_created_variable(self, entry):
        self._capture_created_variables()
        try:
            name = self._validate_new_variable_name(entry.get())
        except ValueError as exc:
            messagebox.showerror("Invalid variable", str(exc))
            return
        self.created_variables.append({
            "name": name,
            "expression": "",
            "expression_name": self._generate_expression_name(name),
            "enabled": True,
        })
        entry.delete(0, "end")
        self.show_page("thermal", push_history=False)

    def _delete_created_variable(self, name):
        self._capture_created_variables()
        self.created_variables = [item for item in self.created_variables if item["name"] != name]
        self._clear_variable_state(name)
        self.show_page("thermal", push_history=False)

    def _enabled_created_names(self):
        return [item["name"] for item in self.created_variables if item.get("enabled", True)]

    # ------------------------------------------------------------------
    # Directories / visual types
    # ------------------------------------------------------------------
    def _build_directories_page(self):
        frame = ttk.Frame(self.content, padding=12)
        frame.grid(sticky="nsew")
        frame.columnconfigure(1, weight=1)
        if self.mode.get() == MODE_THERMAL:
            self._directory_row(frame, 0, "Export CSV directory", self.export_directory)
            self._directory_row(frame, 1, "Import output directory", self.import_directory)
            ttk.Checkbutton(frame, text="Execute generated import session in currently open CFX-Post", variable=self.execute_thermal_import).grid(row=2, column=0, columnspan=3, sticky="w", pady=(15, 5))
            ttk.Label(frame, text="Maximum cleaning distance [m]").grid(row=3, column=0, sticky="w", pady=6)
            ttk.Entry(frame, textvariable=self.max_cleaning_distance, width=12).grid(row=3, column=1, sticky="w")
        else:
            label = "Main project directory" if self.mode.get() == MODE_FULL else "Figures/session output directory"
            self._directory_row(frame, 0, label, self.main_directory)
            note = ("Full automation creates export, import and figures subfolders." if self.mode.get() == MODE_FULL else
                    "Figures-only uses this directory directly for sessions, PNG/table output and temporary files; no export/import/figures subfolders are created.")
            ttk.Label(frame, text=note, wraplength=880).grid(row=1, column=0, columnspan=3, sticky="w", pady=(12, 0))

    def _directory_row(self, parent, row, label, var):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=8)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", pady=8)
        ttk.Button(parent, text="Browse…", command=lambda: self._browse_directory(var)).grid(row=row, column=2, padx=(10, 0))

    def _browse_directory(self, var):
        directory = filedialog.askdirectory(initialdir=var.get().strip() or str(Path.home()))
        if directory:
            var.set(directory)

    def _build_visuals_page(self):
        frame = ttk.Frame(self.content, padding=12)
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)
        box = ttk.LabelFrame(frame, text="Generate", padding=12, style="Section.TLabelframe")
        box.grid(row=0, column=0, sticky="ew")
        items = [
            ("Top-view contours and figures", self.visual_plan),
            ("Section-view contours and figures", self.visual_sections),
            ("Histograms", self.visual_hist),
            ("Averages table", self.visual_table),
        ]
        for i, (label, var) in enumerate(items):
            cb = ttk.Checkbutton(box, text=label, variable=var)
            cb.grid(row=i, column=0, sticky="w", pady=5)
            if i == 0 and self.mode.get() == MODE_FULL:
                var.set(True)
                cb.configure(state="disabled")
        table = ttk.Frame(box)
        table.grid(row=3, column=1, sticky="w", padx=(20, 0))
        ttk.Label(table, text="Table name").grid(row=0, column=0, padx=(0, 6))
        ttk.Entry(table, textvariable=self.average_table_name, width=28).grid(row=0, column=1)

    def _need_normal_surfaces(self):
        return self.visual_plan.get() or self.visual_hist.get() or self.visual_table.get()

    # ------------------------------------------------------------------
    # Master variable helpers
    # ------------------------------------------------------------------
    def _calculated_rows(self):
        if self.mode.get() != MODE_FULL:
            return []
        vals = []
        vals += CALCULATED_VARIABLES["relative_air_speed"]
        if self.calculate_pmv_ppd.get(): vals += CALCULATED_VARIABLES["pmv_ppd"]
        if self.calculate_set.get(): vals += CALCULATED_VARIABLES["set"]
        if self.calculate_utci.get(): vals += CALCULATED_VARIABLES["utci"]
        if self.calculate_draft_rate.get(): vals += CALCULATED_VARIABLES["draft_rate"]
        if self.calculate_clothing_temperature.get(): vals += CALCULATED_VARIABLES["clothing_temperature"]
        if self.calculate_operative_temperature.get(): vals += CALCULATED_VARIABLES["operative_temperature"]
        if self.calculate_psychrometrics.get(): vals += CALCULATED_VARIABLES["psychrometrics"]
        return vals

    def _created_rows(self):
        return [(self._display_variable(name), name) for name in self._enabled_created_names()]

    def _manual_rows(self):
        return [(self._display_variable(name), name) for name in self.manual_variables]

    def _surface_variable_rows(self):
        return list(BASE_VARIABLES) + self._calculated_rows() + self._created_rows() + self._manual_rows()

    def _native_variable_rows(self):
        return list(BASE_VARIABLES) + self._created_rows() + self._manual_rows()

    def _available_variables(self):
        # Kept for compatibility with older internal call sites.
        return list(BASE_VARIABLES) + self._calculated_rows() + self._created_rows()

    def _is_calculated_variable(self, name):
        return any(name == internal for values in CALCULATED_VARIABLES.values() for _, internal in values)

    def _all_surface_variable_names(self):
        return [name for _, name in self._surface_variable_rows()]

    def _all_native_variable_names(self):
        return [name for _, name in self._native_variable_rows()]

    def _clear_variable_state(self, name):
        for mapping in (
            self.figure_selection,
            self.section_variable_selection,
            self.section_vector_selection,
            self.histogram_variable_selection,
            self.volume_variable_selection,
            self.table_variable_selection,
            self.variable_settings,
        ):
            mapping.pop(name, None)

    def _capture_active_variable_page(self):
        if self.current_page == "surfaces":
            self._capture_normal_vars()
        elif self.current_page == "sections":
            self._capture_sections()
        elif self.current_page == "histograms":
            self._capture_histograms()
        elif self.current_page == "table":
            self._capture_table()

    def _add_shared_manual_variable(self, entry, target):
        self._capture_active_variable_page()
        name = entry.get().strip()
        if not name:
            return
        if any(ch in name for ch in "\r\n,"):
            messagebox.showerror("Invalid variable", "Variable names cannot contain commas or line breaks.")
            return
        if name.casefold() in self._reserved_names_casefold(include_expression_names=True):
            messagebox.showinfo("Duplicate/conflict", f"'{name}' is already represented by a built-in, created, manual, or expression name.")
            return
        self.manual_variables.append(name)
        if target == "normal":
            self.figure_selection[name] = True
        elif target == "section":
            self.section_variable_selection[name] = True
        elif target == "histogram":
            self.histogram_variable_selection[name] = True
            self.volume_variable_selection[name] = True
        elif target == "table":
            self.table_variable_selection[name] = True
        entry.delete(0, "end")
        self.show_page(self.current_page, push_history=False)

    def _delete_shared_manual_variable(self, name):
        self._capture_active_variable_page()
        if name in self.manual_variables:
            self.manual_variables.remove(name)
            self._clear_variable_state(name)
            self.show_page(self.current_page, push_history=False)

    # ------------------------------------------------------------------
    # Master normal surfaces + top-view variables
    # ------------------------------------------------------------------
    def _build_surfaces_page(self):
        frame = ttk.Frame(self.content, padding=12)
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(0, weight=1)

        left = ttk.LabelFrame(frame, text="Normal / top-view surfaces", padding=10, style="Section.TLabelframe")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        add = ttk.Frame(left)
        add.grid(row=0, column=0, sticky="ew")
        add.columnconfigure(0, weight=1)
        ent = ttk.Entry(add)
        ent.grid(row=0, column=0, sticky="ew")
        lb = tk.Listbox(left, selectmode="extended")
        lb.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        for item in self.surfaces:
            lb.insert("end", item)
        cnt = ttk.Label(left, text=f"{len(self.surfaces)} item(s)")
        cnt.grid(row=2, column=0, sticky="w", pady=(6, 0))
        def add_surface(event=None):
            self._add_name(self.surfaces, ent, lb, cnt, "surface")
            return "break"
        ttk.Button(add, text="Add", command=add_surface).grid(row=0, column=1, padx=(6, 0))
        ttk.Button(left, text="Delete selected", command=lambda: self._delete_surface_names(lb, cnt)).grid(row=2, column=0, sticky="e")
        ent.bind("<Return>", add_surface)
        ent.bind("<KP_Enter>", add_surface)

        right = ttk.LabelFrame(frame, text="Top-view contour variables", padding=10, style="Section.TLabelframe")
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        if self.visual_plan.get():
            scroll = ScrollableFrame(right, height=330)
            scroll.grid(row=0, column=0, sticky="nsew")
            self.variable_check_vars = {}
            manual_set = set(self.manual_variables)
            for r, (label, name) in enumerate(self._surface_variable_rows()):
                default = name in {"Temperature", "Relative Humidity", "Velocity", "Radiation Temperature", "PMV", "PPD", "Operative_Temperature"}
                var = tk.BooleanVar(value=self.figure_selection.get(name, default))
                self.variable_check_vars[name] = var
                ttk.Checkbutton(scroll.inner, text=label, variable=var).grid(row=r, column=0, sticky="w", pady=3)
                col = 1
                if name == "Velocity":
                    ttk.Checkbutton(scroll.inner, text="Create streamlines", variable=self.plan_streamlines).grid(row=r, column=1, sticky="w", padx=(12, 0))
                    col = 2
                if name in manual_set:
                    ttk.Button(scroll.inner, text="Delete", command=lambda n=name: self._delete_shared_manual_variable(n)).grid(row=r, column=col, sticky="e", padx=(10, 0), pady=2)
        else:
            self.variable_check_vars = {}
            ttk.Label(right, text="Top-view contours are disabled. This page is used only to define the master surface list for histograms/table.", wraplength=450, foreground="#666666").grid(row=0, column=0, sticky="nw")

        manualrow = ttk.Frame(right)
        manualrow.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        manualrow.columnconfigure(0, weight=1)
        ment = ttk.Entry(manualrow)
        ment.grid(row=0, column=0, sticky="ew")
        def addmanual(event=None):
            self._add_shared_manual_variable(ment, "normal")
            return "break"
        ttk.Button(manualrow, text="Add manual variable", command=addmanual).grid(row=0, column=1, padx=(6, 0))
        ment.bind("<Return>", addmanual)
        ment.bind("<KP_Enter>", addmanual)

    def _add_name(self, storage, entry, listbox, count, label):
        name = entry.get().strip()
        if not name:
            return
        if any(existing.casefold() == name.casefold() for existing in storage):
            messagebox.showinfo("Duplicate", f"'{name}' is already listed.")
            return
        storage.append(name)
        listbox.insert("end", name)
        entry.delete(0, "end")
        count.configure(text=f"{len(storage)} item(s)")

    def _delete_surface_names(self, listbox, count):
        for i in reversed(list(listbox.curselection())):
            name = self.surfaces[i]
            del self.surfaces[i]
            listbox.delete(i)
            self.histogram_surface_selection.pop(name, None)
            self.table_surface_selection.pop(name, None)
        count.configure(text=f"{len(self.surfaces)} item(s)")

    def _capture_normal_vars(self):
        for name, var in getattr(self, "variable_check_vars", {}).items():
            self.figure_selection[name] = bool(var.get())

    def _selected_normal_vars(self):
        return [name for name in self._all_surface_variable_names() if self.figure_selection.get(name, False)]

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------
    def _build_sections_page(self):
        frame = ttk.Frame(self.content, padding=12)
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(0, weight=1)

        left = ttk.LabelFrame(frame, text="Section surfaces", padding=10, style="Section.TLabelframe")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        add = ttk.Frame(left); add.grid(row=0, column=0, sticky="ew"); add.columnconfigure(0, weight=1)
        ent = ttk.Entry(add); ent.grid(row=0, column=0, sticky="ew")
        lb = tk.Listbox(left, selectmode="extended"); lb.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        for item in self.section_surfaces: lb.insert("end", item)
        cnt = ttk.Label(left, text=f"{len(self.section_surfaces)} item(s)"); cnt.grid(row=2, column=0, sticky="w", pady=(6, 0))
        def add_location(event=None):
            self._add_name(self.section_surfaces, ent, lb, cnt, "section")
            return "break"
        ttk.Button(add, text="Add", command=add_location).grid(row=0, column=1, padx=(6, 0))
        ttk.Button(left, text="Delete selected", command=lambda: self._delete_names_simple(self.section_surfaces, lb, cnt)).grid(row=2, column=0, sticky="e")
        ent.bind("<Return>", add_location); ent.bind("<KP_Enter>", add_location)

        right = ttk.LabelFrame(frame, text="Section variables", padding=10, style="Section.TLabelframe")
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1); right.rowconfigure(0, weight=1)
        scroll = ScrollableFrame(right, height=340); scroll.grid(row=0, column=0, sticky="nsew")
        self.section_check_vars = {}; self.section_vector_vars = {}
        manual_set = set(self.manual_variables)
        for r, (label, name) in enumerate(self._native_variable_rows()):
            selected = tk.BooleanVar(value=self.section_variable_selection.get(name, name in {"Temperature", "Velocity"}))
            vectors = tk.BooleanVar(value=self.section_vector_selection.get(name, False))
            self.section_check_vars[name] = selected; self.section_vector_vars[name] = vectors
            ttk.Checkbutton(scroll.inner, text=label, variable=selected).grid(row=r, column=0, sticky="w", pady=3)
            ttk.Checkbutton(scroll.inner, text="Add velocity vectors", variable=vectors).grid(row=r, column=1, sticky="w", padx=(12, 0))
            col = 2
            if name == "Velocity":
                ttk.Checkbutton(scroll.inner, text="Create streamlines", variable=self.section_streamlines).grid(row=r, column=2, sticky="w", padx=(12, 0))
                col = 3
            if name in manual_set:
                ttk.Button(scroll.inner, text="Delete", command=lambda n=name: self._delete_shared_manual_variable(n)).grid(row=r, column=col, sticky="e", padx=(10, 0), pady=2)

        manualrow = ttk.Frame(right); manualrow.grid(row=1, column=0, sticky="ew", pady=(8, 0)); manualrow.columnconfigure(0, weight=1)
        ment = ttk.Entry(manualrow); ment.grid(row=0, column=0, sticky="ew")
        def addmanual(event=None):
            self._add_shared_manual_variable(ment, "section")
            return "break"
        ttk.Button(manualrow, text="Add manual variable", command=addmanual).grid(row=0, column=1, padx=(6, 0))
        ment.bind("<Return>", addmanual); ment.bind("<KP_Enter>", addmanual)
        ttk.Label(right, text="Calculated thermal-comfort variables are not available on section views. Created CFX variables and shared manual native variables are available.", wraplength=470, foreground="#666666").grid(row=2, column=0, sticky="w", pady=(6, 0))

    def _delete_names_simple(self, storage, listbox, count):
        for i in reversed(list(listbox.curselection())):
            del storage[i]
            listbox.delete(i)
        count.configure(text=f"{len(storage)} item(s)")

    def _capture_sections(self):
        for name, var in getattr(self, "section_check_vars", {}).items(): self.section_variable_selection[name] = bool(var.get())
        for name, var in getattr(self, "section_vector_vars", {}).items(): self.section_vector_selection[name] = bool(var.get())

    def _selected_section_vars(self):
        return [name for name in self._all_native_variable_names() if self.section_variable_selection.get(name, False)]

    # ------------------------------------------------------------------
    # Shared volume registry
    # ------------------------------------------------------------------
    def _capture_active_volume_page(self):
        if self.current_page == "histograms": self._capture_histograms()
        elif self.current_page == "table": self._capture_table()

    def _add_shared_volume(self, entry, target):
        self._capture_active_volume_page()
        name = entry.get().strip()
        if not name:
            return
        if any(existing.casefold() == name.casefold() for existing in self.volumes):
            messagebox.showinfo("Duplicate", f"'{name}' is already in the shared volume list.")
            return
        self.volumes.append(name)
        if target == "histogram": self.histogram_volume_selection[name] = True
        elif target == "table": self.table_volume_selection[name] = True
        entry.delete(0, "end")
        self.show_page(self.current_page, push_history=False)

    def _delete_shared_volume(self, name):
        self._capture_active_volume_page()
        if name in self.volumes:
            self.volumes.remove(name)
            self.histogram_volume_selection.pop(name, None)
            self.table_volume_selection.pop(name, None)
            self.show_page(self.current_page, push_history=False)

    # ------------------------------------------------------------------
    # Unified histograms panel
    # ------------------------------------------------------------------
    def _build_histograms_page(self):
        frame = ttk.Frame(self.content, padding=12)
        frame.grid(sticky="nsew")
        for c in range(3): frame.columnconfigure(c, weight=1)
        frame.rowconfigure(0, weight=1)

        surfbox = ttk.LabelFrame(frame, text="Surface locations", padding=10, style="Section.TLabelframe")
        surfbox.grid(row=0, column=0, sticky="nsew", padx=(0, 6)); surfbox.columnconfigure(0, weight=1); surfbox.rowconfigure(0, weight=1)
        sscroll = ScrollableFrame(surfbox, height=400); sscroll.grid(row=0, column=0, sticky="nsew")
        self.hist_surface_vars = {}
        for r, surface in enumerate(self.surfaces):
            var = tk.BooleanVar(value=self.histogram_surface_selection.get(surface, False))
            self.hist_surface_vars[surface] = var
            ttk.Checkbutton(sscroll.inner, text=surface, variable=var).grid(row=r, column=0, sticky="w", pady=3)
        ttk.Label(surfbox, text="Surfaces come from the master normal/top-view list.", wraplength=310, foreground="#666666").grid(row=1, column=0, sticky="w", pady=(6, 0))

        volbox = ttk.LabelFrame(frame, text="Volume locations", padding=10, style="Section.TLabelframe")
        volbox.grid(row=0, column=1, sticky="nsew", padx=6); volbox.columnconfigure(0, weight=1); volbox.rowconfigure(1, weight=1)
        add = ttk.Frame(volbox); add.grid(row=0, column=0, sticky="ew"); add.columnconfigure(0, weight=1)
        vent = ttk.Entry(add); vent.grid(row=0, column=0, sticky="ew")
        def addvol(event=None):
            self._add_shared_volume(vent, "histogram")
            return "break"
        ttk.Button(add, text="Add", command=addvol).grid(row=0, column=1, padx=(6, 0)); vent.bind("<Return>", addvol); vent.bind("<KP_Enter>", addvol)
        vscroll = ScrollableFrame(volbox, height=350); vscroll.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.hist_volume_vars = {}
        for r, volume in enumerate(self.volumes):
            var = tk.BooleanVar(value=self.histogram_volume_selection.get(volume, False))
            self.hist_volume_vars[volume] = var
            ttk.Checkbutton(vscroll.inner, text=volume, variable=var).grid(row=r, column=0, sticky="w", pady=3)
            ttk.Button(vscroll.inner, text="Delete", command=lambda n=volume: self._delete_shared_volume(n)).grid(row=r, column=1, sticky="e", padx=(8, 0), pady=2)
        ttk.Label(volbox, text="This master volume list is shared with the Average Table panel.", wraplength=310, foreground="#666666").grid(row=2, column=0, sticky="w", pady=(6, 0))

        varbox = ttk.LabelFrame(frame, text="Histogram variables", padding=10, style="Section.TLabelframe")
        varbox.grid(row=0, column=2, sticky="nsew", padx=(6, 0)); varbox.columnconfigure(0, weight=1); varbox.rowconfigure(0, weight=1)
        scroll = ScrollableFrame(varbox, height=340); scroll.grid(row=0, column=0, sticky="nsew")
        ttk.Label(scroll.inner, text="Variable", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", padx=3)
        ttk.Label(scroll.inner, text="Surface", font=("Segoe UI", 9, "bold")).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(scroll.inner, text="Volume", font=("Segoe UI", 9, "bold")).grid(row=0, column=2, sticky="w", padx=6)
        self.hist_variable_vars = {}; self.volume_hist_variable_vars = {}
        manual_set = set(self.manual_variables)
        for r, (label, name) in enumerate(self._surface_variable_rows(), start=1):
            ttk.Label(scroll.inner, text=label).grid(row=r, column=0, sticky="w", pady=3)
            svar = tk.BooleanVar(value=self.histogram_variable_selection.get(name, False))
            self.hist_variable_vars[name] = svar
            ttk.Checkbutton(scroll.inner, variable=svar).grid(row=r, column=1, padx=6)
            if not self._is_calculated_variable(name):
                vvar = tk.BooleanVar(value=self.volume_variable_selection.get(name, False))
                self.volume_hist_variable_vars[name] = vvar
                ttk.Checkbutton(scroll.inner, variable=vvar).grid(row=r, column=2, padx=6)
            else:
                ttk.Label(scroll.inner, text="surface only", foreground="#777777").grid(row=r, column=2, sticky="w", padx=6)
            if name in manual_set:
                ttk.Button(scroll.inner, text="Delete", command=lambda n=name: self._delete_shared_manual_variable(n)).grid(row=r, column=3, padx=(8, 0), pady=2)

        manualrow = ttk.Frame(varbox); manualrow.grid(row=1, column=0, sticky="ew", pady=(8, 0)); manualrow.columnconfigure(0, weight=1)
        ment = ttk.Entry(manualrow); ment.grid(row=0, column=0, sticky="ew")
        def addmanual(event=None):
            self._add_shared_manual_variable(ment, "histogram")
            return "break"
        ttk.Button(manualrow, text="Add manual variable", command=addmanual).grid(row=0, column=1, padx=(6, 0)); ment.bind("<Return>", addmanual); ment.bind("<KP_Enter>", addmanual)
        ttk.Label(varbox, text="Surface and volume variable selections are independent. Histogram bounds/divisions are shared per variable. Thermal-comfort calculated variables are surface-only.", wraplength=360, foreground="#666666").grid(row=2, column=0, sticky="w", pady=(6, 0))

    def _capture_histograms(self):
        for n, v in getattr(self, "hist_surface_vars", {}).items(): self.histogram_surface_selection[n] = bool(v.get())
        for n, v in getattr(self, "hist_volume_vars", {}).items(): self.histogram_volume_selection[n] = bool(v.get())
        for n, v in getattr(self, "hist_variable_vars", {}).items(): self.histogram_variable_selection[n] = bool(v.get())
        for n, v in getattr(self, "volume_hist_variable_vars", {}).items(): self.volume_variable_selection[n] = bool(v.get())

    def _selected_hist_surfaces(self):
        return [s for s in self.surfaces if self.histogram_surface_selection.get(s, False)]

    def _selected_hist_volumes(self):
        return [v for v in self.volumes if self.histogram_volume_selection.get(v, False)]

    def _selected_hist_vars(self):
        return [n for n in self._all_surface_variable_names() if self.histogram_variable_selection.get(n, False)]

    def _selected_volume_vars(self):
        return [n for n in self._all_native_variable_names() if self.volume_variable_selection.get(n, False)]

    # ------------------------------------------------------------------
    # Combined surface/volume average table panel
    # ------------------------------------------------------------------
    def _build_table_page(self):
        frame = ttk.Frame(self.content, padding=12)
        frame.grid(sticky="nsew")
        for c in range(3): frame.columnconfigure(c, weight=1)
        frame.rowconfigure(0, weight=1)

        surfbox = ttk.LabelFrame(frame, text="Surface averages", padding=10, style="Section.TLabelframe")
        surfbox.grid(row=0, column=0, sticky="nsew", padx=(0, 6)); surfbox.columnconfigure(0, weight=1); surfbox.rowconfigure(0, weight=1)
        sscroll = ScrollableFrame(surfbox, height=400); sscroll.grid(row=0, column=0, sticky="nsew")
        self.table_surface_vars = {}
        for r, surface in enumerate(self.surfaces):
            var = tk.BooleanVar(value=self.table_surface_selection.get(surface, True))
            self.table_surface_vars[surface] = var
            ttk.Checkbutton(sscroll.inner, text=surface, variable=var).grid(row=r, column=0, sticky="w", pady=3)
        ttk.Label(surfbox, text="Surface choices come from the master normal/top-view list.", wraplength=310, foreground="#666666").grid(row=1, column=0, sticky="w", pady=(6, 0))

        volbox = ttk.LabelFrame(frame, text="Volume averages", padding=10, style="Section.TLabelframe")
        volbox.grid(row=0, column=1, sticky="nsew", padx=6); volbox.columnconfigure(0, weight=1); volbox.rowconfigure(1, weight=1)
        add = ttk.Frame(volbox); add.grid(row=0, column=0, sticky="ew"); add.columnconfigure(0, weight=1)
        vent = ttk.Entry(add); vent.grid(row=0, column=0, sticky="ew")
        def addvol(event=None):
            self._add_shared_volume(vent, "table")
            return "break"
        ttk.Button(add, text="Add", command=addvol).grid(row=0, column=1, padx=(6, 0)); vent.bind("<Return>", addvol); vent.bind("<KP_Enter>", addvol)
        vscroll = ScrollableFrame(volbox, height=350); vscroll.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.table_volume_vars = {}
        for r, volume in enumerate(self.volumes):
            var = tk.BooleanVar(value=self.table_volume_selection.get(volume, False))
            self.table_volume_vars[volume] = var
            ttk.Checkbutton(vscroll.inner, text=volume, variable=var).grid(row=r, column=0, sticky="w", pady=3)
            ttk.Button(vscroll.inner, text="Delete", command=lambda n=volume: self._delete_shared_volume(n)).grid(row=r, column=1, sticky="e", padx=(8, 0), pady=2)
        ttk.Label(volbox, text="This master volume list is shared with Histograms; table checkboxes are independent.", wraplength=310, foreground="#666666").grid(row=2, column=0, sticky="w", pady=(6, 0))

        varbox = ttk.LabelFrame(frame, text="Table variables", padding=10, style="Section.TLabelframe")
        varbox.grid(row=0, column=2, sticky="nsew", padx=(6, 0)); varbox.columnconfigure(0, weight=1); varbox.rowconfigure(0, weight=1)
        scroll = ScrollableFrame(varbox, height=340); scroll.grid(row=0, column=0, sticky="nsew")
        self.table_variable_vars = {}
        manual_set = set(self.manual_variables)
        for r, (label, name) in enumerate(self._surface_variable_rows()):
            default = name in {"Temperature", "Relative Humidity", "Velocity", "Radiation Temperature", "PMV", "PPD", "Operative_Temperature"}
            var = tk.BooleanVar(value=self.table_variable_selection.get(name, default))
            self.table_variable_vars[name] = var
            text = label + ("  (surface averages only)" if self._is_calculated_variable(name) else "")
            ttk.Checkbutton(scroll.inner, text=text, variable=var).grid(row=r, column=0, sticky="w", pady=3)
            if name in manual_set:
                ttk.Button(scroll.inner, text="Delete", command=lambda n=name: self._delete_shared_manual_variable(n)).grid(row=r, column=1, padx=(8, 0), pady=2)

        manualrow = ttk.Frame(varbox); manualrow.grid(row=1, column=0, sticky="ew", pady=(8, 0)); manualrow.columnconfigure(0, weight=1)
        ment = ttk.Entry(manualrow); ment.grid(row=0, column=0, sticky="ew")
        def addmanual(event=None):
            self._add_shared_manual_variable(ment, "table")
            return "break"
        ttk.Button(manualrow, text="Add manual variable", command=addmanual).grid(row=0, column=1, padx=(6, 0)); ment.bind("<Return>", addmanual); ment.bind("<KP_Enter>", addmanual)
        ttk.Label(varbox, text="Selected variables are used in both table blocks where possible. Thermal-comfort calculated variables are included only in Surface Averages and are automatically omitted from Volume Averages.", wraplength=370, foreground="#666666").grid(row=2, column=0, sticky="w", pady=(6, 0))

    def _capture_table(self):
        for n, v in getattr(self, "table_surface_vars", {}).items(): self.table_surface_selection[n] = bool(v.get())
        for n, v in getattr(self, "table_volume_vars", {}).items(): self.table_volume_selection[n] = bool(v.get())
        for n, v in getattr(self, "table_variable_vars", {}).items(): self.table_variable_selection[n] = bool(v.get())

    def _selected_table_surfaces(self):
        return [s for s in self.surfaces if self.table_surface_selection.get(s, False)]

    def _selected_table_volumes(self):
        return [v for v in self.volumes if self.table_volume_selection.get(v, False)]

    def _selected_table_vars(self):
        return [n for n in self._all_surface_variable_names() if self.table_variable_selection.get(n, False)]

    # ------------------------------------------------------------------
    # Variable ranges / controls
    # ------------------------------------------------------------------
    def _all_setting_vars(self):
        out = []
        groups = []
        if self.visual_plan.get(): groups.append(self._selected_normal_vars())
        if self.visual_hist.get():
            groups.append(self._selected_hist_vars())
            groups.append(self._selected_volume_vars())
        if self.visual_sections.get(): groups.append(self._selected_section_vars())
        for group in groups:
            for name in group:
                if name not in out: out.append(name)
        return out

    def _build_variable_settings_page(self):
        frame = ttk.Frame(self.content, padding=12)
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        ttk.Label(
            frame,
            text=("Blank normal bounds use 5th/95th percentiles except in figures-only mode, where all non-section bounds "
                  "are mandatory. Blank contour count = 21; blank histogram divisions = 20. Section blanks inherit "
                  "normal values when available, otherwise use section 5th/95th percentiles and 21 contours."),
            wraplength=1040,
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))
        scroll = ScrollableFrame(frame, height=430)
        scroll.grid(row=1, column=0, sticky="nsew")
        inner = scroll.inner
        normal = set(self._selected_normal_vars()) if self.visual_plan.get() else set()
        hist = (set(self._selected_hist_vars()) | set(self._selected_volume_vars())) if self.visual_hist.get() else set()
        sections = set(self._selected_section_vars()) if self.visual_sections.get() else set()
        show_hist = bool(hist)
        show_sections = bool(sections)
        cols = [("Variable", "var")]
        if normal or hist: cols += [("Lower", "lower"), ("Upper", "upper")]
        if normal: cols += [("Contours", "contours")]
        if show_hist: cols += [("Histogram divisions", "hist_divisions")]
        if show_sections: cols += [("Section lower", "section_lower"), ("Section upper", "section_upper"), ("Section contours", "section_contours")]
        idx = {key: i for i, (_, key) in enumerate(cols)}
        for c, (label, _) in enumerate(cols):
            ttk.Label(inner, text=label, font=("Segoe UI", 9, "bold")).grid(row=0, column=c, padx=4, pady=(0, 6))
        self.settings_entry_vars = {}
        for r, name in enumerate(self._all_setting_vars(), start=1):
            saved = self.variable_settings.get(name, {})
            ttk.Label(inner, text=self._display_variable(name)).grid(row=r, column=0, sticky="w", padx=4, pady=3)
            fields = {k: tk.StringVar(value=saved.get(k, "")) for k in ["lower", "upper", "contours", "hist_divisions", "section_lower", "section_upper", "section_contours"]}
            self.settings_entry_vars[name] = fields
            if normal or hist:
                for key in ("lower", "upper"):
                    e = ttk.Entry(inner, textvariable=fields[key], width=12); e.grid(row=r, column=idx[key], padx=4, pady=3)
                    if name not in normal and name not in hist: e.configure(state="disabled")
            if normal:
                e = ttk.Entry(inner, textvariable=fields["contours"], width=12); e.grid(row=r, column=idx["contours"], padx=4, pady=3)
                if name not in normal: e.configure(state="disabled")
            if show_hist:
                e = ttk.Entry(inner, textvariable=fields["hist_divisions"], width=18); e.grid(row=r, column=idx["hist_divisions"], padx=4, pady=3)
                if name not in hist: e.configure(state="disabled")
            if show_sections:
                for key in ("section_lower", "section_upper", "section_contours"):
                    e = ttk.Entry(inner, textvariable=fields[key], width=14); e.grid(row=r, column=idx[key], padx=4, pady=3)
                    if name not in sections: e.configure(state="disabled")

        controls = ttk.Frame(frame); controls.grid(row=2, column=0, sticky="w", pady=(10, 0))
        if self.visual_sections.get() and any(self.section_vector_selection.get(n, False) for n in sections):
            ttk.Label(controls, text="Velocity vector samples").grid(row=0, column=0, sticky="w")
            ttk.Entry(controls, textvariable=self.velocity_vector_samples, width=10).grid(row=0, column=1, sticky="w", padx=(8, 22))
        if (self.visual_plan.get() and self.plan_streamlines.get()) or (self.visual_sections.get() and self.section_streamlines.get()):
            ttk.Label(controls, text="Streamline samples").grid(row=0, column=2, sticky="w")
            ttk.Entry(controls, textvariable=self.streamline_samples, width=10).grid(row=0, column=3, sticky="w", padx=(8, 0))

    def _capture_variable_settings(self):
        for name, fields in getattr(self, "settings_entry_vars", {}).items():
            self.variable_settings[name] = {key: var.get().strip() for key, var in fields.items()}

    def _build_controls_page(self):
        frame = ttk.Frame(self.content, padding=12)
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1); frame.columnconfigure(1, weight=1)
        a = ttk.LabelFrame(frame, text="Figures / camera", padding=12, style="Section.TLabelframe")
        a.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self._labeled_entry(a, 0, "First figure number", self.first_figure_number)
        self._labeled_entry(a, 1, "Camera scale factor", self.camera_scale_factor)
        self._labeled_entry(a, 2, "Camera margin [m]", self.camera_margin)
        self._labeled_entry(a, 3, "Clip-plane offset [m]", self.clip_plane_z_offset)
        b = ttk.LabelFrame(frame, text="Output", padding=12, style="Section.TLabelframe")
        b.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self._labeled_entry(b, 0, "Image width [px]", self.image_width)
        self._labeled_entry(b, 1, "Image height [px]", self.image_height)
        if self.mode.get() == MODE_FULL:
            self._labeled_entry(b, 2, "Maximum cleaning distance [m]", self.max_cleaning_distance)
        ttk.Checkbutton(b, text="Execute figures / charts / table printing session automatically", variable=self.execute_print_session).grid(row=4, column=0, columnspan=2, sticky="w", pady=(14, 4))
        ttk.Label(b, text="If disabled, print_figures_session.cse is still created for manual execution.", wraplength=410, foreground="#666666").grid(row=5, column=0, columnspan=2, sticky="w")

    def _labeled_entry(self, parent, row, label, var):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=5)
        ttk.Entry(parent, textvariable=var, width=14).grid(row=row, column=1, sticky="w", pady=5)

    # ------------------------------------------------------------------
    # Navigation + validation
    # ------------------------------------------------------------------
    def go_back(self):
        if not self.page_history:
            return
        page = self.page_history.pop()
        self.show_page(page, push_history=False)

    def _next_after(self, page):
        if page == "mode": return "thermal"
        if page == "thermal": return "directories"
        if page == "directories": return None if self.mode.get() == MODE_THERMAL else "visuals"
        if page == "visuals":
            if self._need_normal_surfaces(): return "surfaces"
            if self.visual_sections.get(): return "sections"
            if self.visual_hist.get(): return "histograms"
            if self.visual_table.get(): return "table"
            return "variable_settings"
        if page == "surfaces":
            if self.visual_sections.get(): return "sections"
            if self.visual_hist.get(): return "histograms"
            if self.visual_table.get(): return "table"
            return "variable_settings"
        if page == "sections":
            if self.visual_hist.get(): return "histograms"
            if self.visual_table.get(): return "table"
            return "variable_settings"
        if page == "histograms":
            return "table" if self.visual_table.get() else "variable_settings"
        if page == "table": return "variable_settings"
        if page == "variable_settings": return "controls"
        return None

    def go_next(self):
        if not self._validate_current_page():
            return
        page = self.current_page
        if page == "thermal": self._capture_created_variables()
        elif page == "surfaces": self._capture_normal_vars()
        elif page == "sections": self._capture_sections()
        elif page == "histograms": self._capture_histograms()
        elif page == "table": self._capture_table()
        elif page == "variable_settings": self._capture_variable_settings()
        nxt = self._next_after(page)
        if nxt:
            self.show_page(nxt)

    def _validate_current_page(self):
        try:
            page = self.current_page
            if page == "thermal":
                if self.mode.get() in (MODE_FULL, MODE_THERMAL):
                    met = self._preset_value(self.met_choice, MET_PRESETS, self.met_other)
                    clo = self._preset_value(self.clo_choice, CLO_PRESETS, self.clo_other)
                    if met <= 0 or clo < 0:
                        raise ValueError("MET must be > 0 and clo must be >= 0.")
                if self.mode.get() in (MODE_FULL, MODE_VISUALIZATION):
                    self._capture_created_variables()
                    names = set()
                    expressions = set()
                    for item in self.created_variables:
                        name_key = item["name"].casefold()
                        expr_key = item["expression_name"].casefold()
                        if name_key in names: raise ValueError(f"Duplicate created variable name: {item['name']}")
                        if expr_key in expressions or expr_key == name_key: raise ValueError(f"Internal expression name conflict for {item['name']}.")
                        names.add(name_key); expressions.add(expr_key)
                        if item.get("enabled", True) and not item.get("expression", "").strip():
                            raise ValueError(f"Enter a CEL expression for enabled variable '{item['name']}'.")
            elif page == "directories":
                if self.mode.get() == MODE_THERMAL:
                    if not Path(self.export_directory.get().strip()).is_dir(): raise ValueError("Choose an existing export CSV directory.")
                    if not self.import_directory.get().strip(): raise ValueError("Choose an import output directory.")
                elif not self.main_directory.get().strip():
                    raise ValueError("Choose the project/output directory.")
            elif page == "visuals":
                if self.mode.get() == MODE_FULL: self.visual_plan.set(True)
                if not any(v.get() for v in (self.visual_plan, self.visual_sections, self.visual_hist, self.visual_table)):
                    raise ValueError("Select at least one visual output type.")
                if self.visual_table.get() and not self.average_table_name.get().strip():
                    raise ValueError("Enter a table name.")
            elif page == "surfaces":
                self._capture_normal_vars()
                if self.visual_plan.get() and not self.surfaces: raise ValueError("Add at least one normal/top-view surface for top-view contours.")
                if self.visual_plan.get() and not self._selected_normal_vars(): raise ValueError("Select at least one top-view contour variable.")
                if self.visual_plan.get() and self.plan_streamlines.get() and "Velocity" not in self._selected_normal_vars():
                    raise ValueError("Top-view streamlines require Velocity to be selected.")
            elif page == "sections":
                self._capture_sections()
                if not self.section_surfaces: raise ValueError("Add at least one section surface.")
                if not self._selected_section_vars(): raise ValueError("Select at least one section variable.")
                if self.section_streamlines.get() and "Velocity" not in self._selected_section_vars():
                    raise ValueError("Section streamlines require Velocity to be selected.")
            elif page == "histograms":
                self._capture_histograms()
                surfaces, volumes = self._selected_hist_surfaces(), self._selected_hist_volumes()
                svars, vvars = self._selected_hist_vars(), self._selected_volume_vars()
                if not surfaces and not volumes: raise ValueError("Select at least one surface or volume for histograms.")
                if surfaces and not svars: raise ValueError("Select at least one surface-histogram variable.")
                if volumes and not vvars: raise ValueError("Select at least one volume-histogram variable.")
            elif page == "table":
                self._capture_table()
                surfaces, volumes = self._selected_table_surfaces(), self._selected_table_volumes()
                variables = self._selected_table_vars()
                if not surfaces and not volumes: raise ValueError("Select at least one surface or volume for the averages table.")
                if not variables: raise ValueError("Select at least one table variable.")
                if volumes and not surfaces and all(self._is_calculated_variable(n) for n in variables):
                    raise ValueError("Volume averages cannot use thermal-comfort calculated variables. Select at least one native or created variable.")
            elif page == "variable_settings":
                self._capture_variable_settings()
                non_section = set(self._selected_normal_vars() if self.visual_plan.get() else [])
                if self.visual_hist.get(): non_section |= set(self._selected_hist_vars()) | set(self._selected_volume_vars())
                sections = set(self._selected_section_vars() if self.visual_sections.get() else [])
                for name in non_section:
                    data = self.variable_settings.get(name, {})
                    lo, hi = data.get("lower", ""), data.get("upper", "")
                    if self.mode.get() == MODE_VISUALIZATION and (not lo or not hi):
                        raise ValueError(f"{self._display_variable(name)}: lower and upper bounds are mandatory in figures-only mode.")
                    if lo and hi and float(lo) >= float(hi): raise ValueError(f"{self._display_variable(name)}: lower must be smaller than upper.")
                    if data.get("contours", "") and int(data["contours"]) < 2: raise ValueError(f"{name}: contours must be >= 2.")
                    if data.get("hist_divisions", "") and int(data["hist_divisions"]) < 1: raise ValueError(f"{name}: histogram divisions must be >= 1.")
                for name in sections:
                    data = self.variable_settings.get(name, {})
                    lo, hi = data.get("section_lower", ""), data.get("section_upper", "")
                    if lo and hi and float(lo) >= float(hi): raise ValueError(f"{name} sections: lower must be smaller than upper.")
                    if data.get("section_contours", "") and int(data["section_contours"]) < 2: raise ValueError(f"{name} sections: contours must be >= 2.")
                if int(self.velocity_vector_samples.get()) < 1 or int(self.streamline_samples.get()) < 1:
                    raise ValueError("Vector/streamline samples must be >= 1.")
            elif page == "controls":
                if int(self.first_figure_number.get()) < 1 or float(self.camera_scale_factor.get()) <= 0 or float(self.camera_margin.get()) < 0:
                    raise ValueError("Check figure/camera settings.")
                if int(self.image_width.get()) <= 0 or int(self.image_height.get()) <= 0:
                    raise ValueError("Image dimensions must be positive.")
        except Exception as exc:
            messagebox.showerror("Check input", str(exc))
            return False
        return True

    # ------------------------------------------------------------------
    # Config builders / execution
    # ------------------------------------------------------------------
    def _thermal_config(self):
        return ThermalComfortConfig(
            met=self._preset_value(self.met_choice, MET_PRESETS, self.met_other),
            clo=self._preset_value(self.clo_choice, CLO_PRESETS, self.clo_other),
            max_cleaning_distance=float(self.max_cleaning_distance.get()),
            calculate_utci=self.calculate_utci.get(),
            calculate_psychrometrics=self.calculate_psychrometrics.get(),
            calculate_draft_rate=self.calculate_draft_rate.get(),
            calculate_clothing_temperature=self.calculate_clothing_temperature.get(),
            calculate_set=self.calculate_set.get(),
            calculate_pmv_ppd=self.calculate_pmv_ppd.get(),
            calculate_operative_temperature=self.calculate_operative_temperature.get(),
        )

    @staticmethod
    def _optional_float(value): return float(value) if str(value).strip() else None
    @staticmethod
    def _optional_int(value): return int(value) if str(value).strip() else None

    def _entry(self, name, countkey):
        data = self.variable_settings.get(name, {})
        lo, hi, count = data.get("lower", ""), data.get("upper", ""), data.get(countkey, "")
        if not lo and not hi and not count: return name
        return f"{name}, {lo}, {hi}, {count}"

    def _created_variable_configs(self):
        self._capture_created_variables()
        return [
            CreatedVariableConfig(
                name=item["name"], expression=item.get("expression", "").strip(),
                expression_name=item["expression_name"], enabled=bool(item.get("enabled", True)),
            )
            for item in self.created_variables
        ]

    def _visualization_config(self):
        normal = self._selected_normal_vars() if self.visual_plan.get() else []
        surface_hist = self._selected_hist_vars() if self.visual_hist.get() else []
        volume_hist = self._selected_volume_vars() if self.visual_hist.get() else []
        hist_surfaces = self._selected_hist_surfaces() if self.visual_hist.get() else []
        hist_volumes = self._selected_hist_volumes() if self.visual_hist.get() else []
        table_vars = self._selected_table_vars() if self.visual_table.get() else []
        sections = []
        for name in (self._selected_section_vars() if self.visual_sections.get() else []):
            data = self.variable_settings.get(name, {})
            sections.append(SectionVariableConfig(
                name=name,
                lower=self._optional_float(data.get("section_lower", "")),
                upper=self._optional_float(data.get("section_upper", "")),
                number_of_contours=self._optional_int(data.get("section_contours", "")),
                add_velocity_vectors=self.section_vector_selection.get(name, False),
                create_streamlines=(name == "Velocity" and self.section_streamlines.get()),
            ))
        return VisualizationConfig(
            create_plan_contours=self.visual_plan.get(),
            create_section_contours=self.visual_sections.get(),
            create_surface_histograms=bool(self.visual_hist.get() and hist_surfaces and surface_hist),
            create_volume_histograms=bool(self.visual_hist.get() and hist_volumes and volume_hist),
            create_average_table=self.visual_table.get(),
            figure_variables=[self._entry(name, "contours") for name in normal],
            create_plan_velocity_streamlines=(self.visual_plan.get() and self.plan_streamlines.get()),
            histogram_surfaces=hist_surfaces,
            histogram_variables=[self._entry(name, "hist_divisions") for name in surface_hist],
            table_surfaces=self._selected_table_surfaces() if self.visual_table.get() else [],
            table_volumes=self._selected_table_volumes() if self.visual_table.get() else [],
            table_variables=table_vars,
            created_variables=self._created_variable_configs() if self.mode.get() in (MODE_FULL, MODE_VISUALIZATION) else [],
            section_surfaces=list(self.section_surfaces) if self.visual_sections.get() else [],
            section_variables=sections,
            volume_histogram_volumes=hist_volumes,
            volume_histogram_variables=[self._entry(name, "hist_divisions") for name in volume_hist],
            velocity_vector_samples=int(self.velocity_vector_samples.get()),
            streamline_samples=int(self.streamline_samples.get()),
            average_table_name=self.average_table_name.get().strip() or "Average conditions",
            first_figure_number=int(self.first_figure_number.get()),
            camera_margin=float(self.camera_margin.get()),
            camera_scale_factor=float(self.camera_scale_factor.get()),
            clip_plane_z_offset=float(self.clip_plane_z_offset.get()),
            image_width=int(self.image_width.get()),
            image_height=int(self.image_height.get()),
            execute_print_session=self.execute_print_session.get(),
            require_explicit_plan_bounds=(self.mode.get() == MODE_VISUALIZATION),
        )

    def _toolkit_config(self):
        return ToolkitConfig(
            project=ProjectConfig(
                main_directory=Path(self.main_directory.get().strip()),
                surfaces=list(self.surfaces),
                direct_visualization_output=(self.mode.get() == MODE_VISUALIZATION),
            ),
            thermal_comfort=self._thermal_config(),
            visualization=self._visualization_config(),
        )

    def run_workflow(self):
        if not self._validate_current_page():
            return
        progress = ProgressWindow(self)
        mode = self.mode.get()
        def worker():
            try:
                if mode == MODE_FULL:
                    result = run_full_workflow(self._toolkit_config(), progress_callback=progress.enqueue_progress)
                elif mode == MODE_THERMAL:
                    result = run_thermal_comfort_directory_workflow(
                        self.export_directory.get().strip(), self.import_directory.get().strip(), self._thermal_config(),
                        execute_import=self.execute_thermal_import.get(), progress_callback=progress.enqueue_progress,
                    )
                else:
                    result = run_visualization_workflow(self._toolkit_config(), execute_creation=True, progress_callback=progress.enqueue_progress)
                progress.enqueue_done(result)
            except Exception as exc:
                progress.enqueue_error(exc, traceback.format_exc())
        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _display_variable(name):
        return str(name).replace("_", " ")

class ProgressWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master); self.title("CFX-Post Toolkit — Progress"); self.geometry("760x500"); self.minsize(650,420); self.transient(master); self.protocol("WM_DELETE_WINDOW",self._try_close); self.events=queue.Queue(); self.finished=False
        frame=ttk.Frame(self,padding=16);frame.pack(fill="both",expand=True);frame.columnconfigure(0,weight=1);frame.rowconfigure(3,weight=1)
        self.stage_label=ttk.Label(frame,text="Starting…",font=("Segoe UI",12,"bold"));self.stage_label.grid(row=0,column=0,sticky="w")
        self.detail_label=ttk.Label(frame,text="");self.detail_label.grid(row=1,column=0,sticky="w",pady=(4,8));self.progress=ttk.Progressbar(frame,mode="indeterminate");self.progress.grid(row=2,column=0,sticky="ew",pady=(0,10));self.progress.start(12)
        self.log=tk.Text(frame,height=18,wrap="word",state="disabled");self.log.grid(row=3,column=0,sticky="nsew");scroll=ttk.Scrollbar(frame,orient="vertical",command=self.log.yview);scroll.grid(row=3,column=1,sticky="ns");self.log.configure(yscrollcommand=scroll.set)
        self.close_button=ttk.Button(frame,text="Close",command=self.destroy,state="disabled");self.close_button.grid(row=4,column=0,sticky="e",pady=(10,0));self.after(100,self._poll)
    def enqueue_progress(self,e):self.events.put(("progress",e))
    def enqueue_done(self,r):self.events.put(("done",r))
    def enqueue_error(self,e,t):self.events.put(("error",e,t))
    def _poll(self):
        try:
            while True:
                item=self.events.get_nowait();kind=item[0]
                if kind=="progress":self._show_event(item[1])
                elif kind=="done":self._finish_success(item[1])
                else:self._finish_error(item[1],item[2])
        except queue.Empty:pass
        if not self.finished:self.after(100,self._poll)
    def _show_event(self,e):
        stage=e.stage.replace("_"," ").title();self.stage_label.configure(text=stage)
        detail=f"{e.current}/{e.total} — {e.message}" if e.current is not None and e.total is not None else e.message;self.detail_label.configure(text=detail);self._append_log(f"[{stage}] {detail}\n")
    def _finish_success(self,r):
        self.finished=True;self.progress.stop();self.stage_label.configure(text="Completed successfully");self.detail_label.configure(text="The selected workflow finished.");self._append_log("\nWorkflow completed successfully.\n");self.close_button.configure(state="normal")
        if isinstance(r,dict):
            for k,v in r.items():
                if k!="statistics":self._append_log(f"{k}: {v}\n")
    def _finish_error(self,e,t):
        self.finished=True;self.progress.stop();self.stage_label.configure(text="Workflow failed");self.detail_label.configure(text=str(e));self._append_log("\nERROR:\n"+t+"\n");self.close_button.configure(state="normal");messagebox.showerror("Workflow failed",str(e),parent=self)
    def _append_log(self,t):self.log.configure(state="normal");self.log.insert("end",t);self.log.see("end");self.log.configure(state="disabled")
    def _try_close(self):
        if self.finished:self.destroy()
        else:messagebox.showinfo("Workflow running","The workflow is still running.",parent=self)


def launch_gui():
    ToolkitWizard().mainloop()

if __name__ == "__main__": launch_gui()
