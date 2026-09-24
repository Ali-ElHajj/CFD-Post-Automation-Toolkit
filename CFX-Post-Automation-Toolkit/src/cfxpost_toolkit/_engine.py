# ============================================================
# AUTOMATED CFX-POST THERMAL COMFORT WORKFLOW
# CFX-Post 23.2
#
# Workflow:
# 1. User settings
# 2. Create export_session.cse
# 3. Execute it in already-open CFX-Post
# 4. Wait for all exports
# 5. Thermal comfort calculations
# 6. Create import_session.cse
# 7. Execute it in the same CFX-Post
# 8. Create create_figures_session.cse
# 9. Execute create_figures_session.cse
# 10. Create print_figures_session.cse (not executed automatically)
# ============================================================

import sys
import time
import ctypes
import io
import re
from pathlib import Path

# Dependencies are resolved from the active Python environment.

import pandas as pd
import numpy as np
import win32gui
import win32clipboard

from pythermalcomfort.models import (
    pmv_ppd_ashrae,
    set_tmp,
    utci
)
from pythermalcomfort.utilities import (
    v_relative,
    clo_dynamic_ashrae
)
from scipy.spatial import cKDTree
import psychrolib
psychrolib.SetUnitSystem(
    psychrolib.SI
)


# ============================================================
# 1. USER SETTINGS
# ============================================================

# Main project directory. Subfolders export/, import/, and figures/ are
# created automatically when the script starts.
MAIN_DIRECTORY = Path("runs/default")
INPUT_DIRECTORY = MAIN_DIRECTORY / "export"
OUTPUT_DIRECTORY = MAIN_DIRECTORY / "import"
FIGURES_DIRECTORY = MAIN_DIRECTORY / "figures"

# CFX-Post surfaces to process.
SURFACES = ["Occupied Plane"]

# Native CFX variables exported for the thermal-comfort calculations.
CFX_VARIABLES = (
    "Radiation Temperature, Relative Humidity Percentage, Temperature, "
    "Turbulence Kinetic Energy, Velocity"
)

# ------------------------------------------------------------
# CONTOURS AND HISTOGRAMS
# ------------------------------------------------------------
# Entry format for both FIGURE_VARIABLES and HISTOGRAM_VARIABLES:
#   "Variable"                       -> automatic 5th/95th-percentile bounds
#                                       + the corresponding default count.
#   "Variable, lower, upper, count"  -> each numeric field may be blank.
#                                       Blank bounds use 5th/95th percentiles;
#                                       blank count uses the corresponding default.
#
# For contours, count = number of contours; bounds are written through CEL.
# For histograms, count = number of divisions; bounds/divisions are numeric.
# Histograms are optional: leave HISTOGRAM_SURFACES or HISTOGRAM_VARIABLES empty.
# Relative humidity handling is fixed and consistent:
#   CFX native "Relative Humidity" is a 0-1 fraction. The export session creates
#   "Relative Humidity Percentage" = Relative Humidity*100 and exports that variable.
#   For figures/histograms/tables, the user selects "Relative Humidity" and the
#   toolkit automatically uses the percentage variable created in CFX-Post.
# Calculated variables can be selected only when their calculation is enabled.
#
# Native variables supported here:
#   Temperature, Radiation Temperature, Relative Humidity, Velocity,
#   Turbulence Kinetic Energy
# Calculated variables:
#   Relative_Air_Speed, PMV, PPD, SET, UTCI, Turbulence_Intensity, Draft_Rate,
#   Clothing_Surface_Temperature, Convective_HTC, Radiative_HTC,
#   Operative_Temperature, Wet_Bulb_Temperature, Dew_Point_Temperature,
#   Humidity_Ratio

FIGURE_VARIABLES = [
    "Temperature, 18, 28, 21",
    "Velocity, 0, 1, 21",
    "Relative Humidity, 40, 70, 31",
    "PMV, -2, 2, 21",
    "PPD, 0, 80, 81",
    "Radiation Temperature, 18, 48, 31",
    "Operative_Temperature, 18, 48, 31",
]

HISTOGRAM_SURFACES = ["Occupied Plane"]

HISTOGRAM_VARIABLES = [
    "Temperature, 18, 28, 20",
    "Radiation Temperature, 18, 48, 30",
    "Operative_Temperature, 18, 48, 30",
    "PMV, -2, 2, 20",
]

DEFAULT_NUMBER_OF_CONTOURS = 21
DEFAULT_NUMBER_OF_HISTOGRAM_DIVISIONS = 20

AVERAGE_TABLE_NAME = "Average conditions"
FIRST_FIGURE_NUMBER = 3

# Common contour-view camera and clip-plane settings.
CAMERA_MARGIN = 0.5  # m
CAMERA_SCALE_FACTOR = 2.5
CLIP_PLANE_Z_OFFSET = 0.1  # m

# PNG dimensions for contour figures and histograms.
FIGURE_IMAGE_WIDTH = 2400
FIGURE_IMAGE_HEIGHT = 1600

# ------------------------------------------------------------
# THERMAL COMFORT CALCULATIONS
# ------------------------------------------------------------
calculate_utci = False
calculate_psychrometrics = False
calculate_draft_rate = False
calculate_clothing_temperature = False
calculate_set = False
calculate_pmv_ppd = True
calculate_operative_temperature = True

met = 1.7
clo = 0.57
minimum_velocity = 0.05
pressure = 101325
emissivity = 0.95

# ------------------------------------------------------------
# CLEANING / CFX AUTOMATION
# ------------------------------------------------------------
MAX_CLEANING_DISTANCE = 1.0  # m

CFD_VARIABLES = ["MRT", "RH", "Temperature", "TKE", "Velocity"]

COMMAND_EDITOR_TITLE = "Command Editor"
PROCESS_BUTTON_X_RATIO = 0.145
PROCESS_BUTTON_Y_FROM_BOTTOM_RATIO = 0.05
EDITOR_FOCUS_X_RATIO = 0.50
EDITOR_FOCUS_Y_RATIO = 0.50



# ============================================================
# 2. CFX-POST AUTOMATION
# ============================================================

VK_CONTROL = 0x11
VK_END = 0x23
VK_RETURN = 0x0D
VK_V = 0x56
VK_BACK = 0x08

KEYEVENTF_KEYUP = 0x0002

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


def find_command_editor():
    windows = []

    def callback(hwnd, extra):
        if not win32gui.IsWindowVisible(hwnd):
            return

        if win32gui.GetWindowText(hwnd) == COMMAND_EDITOR_TITLE:
            windows.append(hwnd)

    win32gui.EnumWindows(callback, None)

    if not windows:
        raise RuntimeError(
            "CFX-Post Command Editor was not found. "
            "Please make sure CFX-Post is open and the Command Editor is visible."
        )

    return windows[0]


def key_down(key):
    ctypes.windll.user32.keybd_event(key, 0, 0, 0)


def key_up(key):
    ctypes.windll.user32.keybd_event(
        key, 0, KEYEVENTF_KEYUP, 0
    )


def press_key(key):
    key_down(key)
    key_up(key)


def hotkey(key1, key2):
    key_down(key1)
    key_down(key2)
    key_up(key2)
    key_up(key1)


def left_click(x, y):
    ctypes.windll.user32.SetCursorPos(int(x), int(y))

    time.sleep(0.15)

    ctypes.windll.user32.mouse_event(
        MOUSEEVENTF_LEFTDOWN,
        0, 0, 0, 0
    )

    time.sleep(0.05)

    ctypes.windll.user32.mouse_event(
        MOUSEEVENTF_LEFTUP,
        0, 0, 0, 0
    )


def bring_command_editor_to_front(hwnd):
    win32gui.ShowWindow(hwnd, 9)
    win32gui.SetForegroundWindow(hwnd)

    time.sleep(0.5)

    if win32gui.GetForegroundWindow() != hwnd:
        raise RuntimeError(
            "Could not bring CFX-Post Command Editor to foreground."
        )


def click_process_button(hwnd):
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)

    width = right - left
    height = bottom - top

    x = left + int(width * PROCESS_BUTTON_X_RATIO)
    y = bottom - int(height * PROCESS_BUTTON_Y_FROM_BOTTOM_RATIO)

    print(f"  Process click: ({x}, {y})")

    left_click(x, y)


def focus_editor(hwnd):
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)

    width = right - left
    height = bottom - top

    x = left + int(width * EDITOR_FOCUS_X_RATIO)
    y = top + int(height * EDITOR_FOCUS_Y_RATIO)

    left_click(x, y)
    time.sleep(0.2)


def paste_text(text):
    win32clipboard.OpenClipboard()

    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(
            13,
            text
        )
    finally:
        win32clipboard.CloseClipboard()

    hotkey(VK_CONTROL, VK_V)
    

def remove_last_command(hwnd, command):

    bring_command_editor_to_front(hwnd)

    # Put keyboard focus back inside the Command Editor
    focus_editor(hwnd)

    # Go to the very end of the document
    hotkey(VK_CONTROL, VK_END)

    time.sleep(0.2)

    # Delete exactly the number of characters that were pasted
    print(
        f"Removing readsession command "
        f"({len(command)} characters)..."
    )

    for _ in range(len(command)):
        press_key(VK_BACK)

    # Delete the newline that was inserted before the command
    press_key(VK_BACK)

    time.sleep(0.5)

    print("Readsession command removed.")


def wait_for_completion_file(
        completion_file,
        timeout=600.0,
        expected_text="Import is successful",
        description="CFX-Post session"
):

    print(
        f"Waiting for CFX-Post completion marker..."
    )

    start_time = time.time()

    while True:

        if completion_file.exists():

            try:

                content = completion_file.read_text(
                    encoding="utf-8"
                ).strip()

                if content == expected_text:

                    print(
                        f"{description} completed successfully."
                    )

                    return

            except PermissionError:
                # CFX may still be writing the file
                pass

        if time.time() - start_time > timeout:

            raise TimeoutError(
                f"Timed out waiting for {description} "
                "completion marker."
            )

        time.sleep(0.2)

def execute_cfx_session(
        session_file,
        completion_file,
        completion_text="Import is successful",
        completion_description="CFX-Post session"
):
    """
    Execute a CFX-Post session in the already-open Command Editor.

    The inserted readsession command is removed after execution,
    so a later Process click cannot execute it again.
    """

    session_file = Path(session_file)

    if not session_file.exists():
        raise FileNotFoundError(
            f"Session file not found: {session_file}"
        )

    hwnd = find_command_editor()

    print("\n============================================================")
    print("EXECUTING CFX-POST SESSION")
    print("============================================================")
    print(f"Session: {session_file}")

    bring_command_editor_to_front(hwnd)

    # Explicitly restore keyboard focus to the editor text area before
    # navigating/pasting.  After a previous Process click, Qt often leaves
    # focus on the Process button even though the Command Editor window is
    # foreground; in that state Ctrl+End/Ctrl+V do not reach the command text.
    focus_editor(hwnd)

    # Add readsession at the end
    hotkey(VK_CONTROL, VK_END)
    time.sleep(0.2)

    press_key(VK_RETURN)
    time.sleep(0.2)

    session_path = str(session_file).replace("\\", "/")
    command = f">readsession filename={session_path}"

    print("Adding readsession command...")
    print(command)

    paste_text(command)

    time.sleep(0.5)

    # Remove an old completion marker from a previous run.
    if completion_file.exists():
        completion_file.unlink()
        print("Old completion marker removed.")

    # Execute and wait until CFX explicitly confirms completion.
    click_process_button(hwnd)

    wait_for_completion_file(
        completion_file,
        expected_text=completion_text,
        description=completion_description
    )

    completion_file.unlink()
    print("Completion marker removed.")

    # Remove the command after execution
    print("Removing executed readsession command...")
    remove_last_command(hwnd, command)

    print("CFX-Post session completed.")
    print("Command Editor restored.")




def _created_variable_field(item, field, default=""):
    if isinstance(item, dict):
        return item.get(field, default)
    return getattr(item, field, default)


def write_created_variable_definitions(f, created_variables=None, *, include_relative_humidity=True):
    """Write CEL expressions and USER SCALAR VARIABLE objects.

    Relative Humidity Percentage remains the fixed built-in mapping. Optional
    user variables must already have distinct expression/object names.
    """
    items = [item for item in (created_variables or []) if bool(_created_variable_field(item, "enabled", True))]
    if include_relative_humidity or items:
        f.write("LIBRARY:\n  CEL:\n    EXPRESSIONS:\n")
        if include_relative_humidity:
            f.write("      Relative Humidity percentage = Relative Humidity*100\n")
        for item in items:
            expr_name = str(_created_variable_field(item, "expression_name")).strip()
            expression = str(_created_variable_field(item, "expression")).strip()
            if not expr_name or not expression:
                continue
            f.write(f"      {expr_name} = {expression}\n")
        f.write("    END\n  END\nEND\n\n")

    if include_relative_humidity:
        f.write("USER SCALAR VARIABLE: Relative Humidity Percentage\n")
        f.write("  Boundary Values = Conservative\n")
        f.write("  Calculate Global Range = On\n")
        f.write("  Component Index = 1\n")
        f.write("  Expression = Relative Humidity percentage\n")
        f.write("  Recipe = Expression\n")
        f.write("  Variable to Copy = Pressure\n")
        f.write("  Variable to Gradient = Pressure\n")
        f.write("END\n\n")

    for item in items:
        name = str(_created_variable_field(item, "name")).strip()
        expr_name = str(_created_variable_field(item, "expression_name")).strip()
        expression = str(_created_variable_field(item, "expression")).strip()
        if not name or not expr_name or not expression:
            continue
        f.write(f"USER SCALAR VARIABLE: {name}\n")
        f.write("  Boundary Values = Conservative\n")
        f.write("  Calculate Global Range = On\n")
        f.write("  Component Index = 1\n")
        f.write(f"  Expression = {expr_name}\n")
        f.write("  Recipe = Expression\n")
        f.write("  Variable to Copy = Pressure\n")
        f.write("  Variable to Gradient = Pressure\n")
        f.write("END\n\n")

# ============================================================
# 3. CREATE EXPORT SESSION
# ============================================================

def create_export_session_file(input_directory, surfaces, extra_variables=None, metadata_volume_names=None, created_variables=None):
    """Create the standard surface export session plus case/location metadata."""
    input_directory.mkdir(parents=True, exist_ok=True)
    session_file = input_directory / "export_session.cse"
    completion_file = input_directory / "export_complete.txt"
    metadata_file = input_directory / "visualization_metadata.txt"

    export_variables = [v.strip() for v in CFX_VARIABLES.split(",") if v.strip()]
    for variable in extra_variables or []:
        variable = str(variable).strip()
        if variable and variable not in export_variables:
            export_variables.append(variable)

    volume_names = []
    seen = set()
    for volume in metadata_volume_names or []:
        volume = str(volume).strip()
        if volume and volume not in seen:
            seen.add(volume)
            volume_names.append(volume)

    file_path = str(input_directory).replace("\\", "/")
    with open(session_file, "w", newline="") as f:
        f.write("# ================================================================\n")
        f.write("# AUTOMATIC SURFACE DATA EXPORT\n")
        f.write("# CFX-Post 23.2\n")
        f.write("# ================================================================\n\n")
        f.write("COMMAND FILE:\n  CFX Post Version = 23.2\nEND\n\n")

        write_created_variable_definitions(f, created_variables, include_relative_humidity=True)

        f.write(f'!$file_path = "{file_path}";\n')
        f.write(f'!$metadata_file = "{metadata_file.as_posix()}";\n')
        f.write(f'!$variables = "{", ".join(export_variables)}";\n')
        f.write(f'!$no_surfaces = {len(surfaces)};\n')
        for i, surface in enumerate(surfaces, 1):
            f.write(f'!$surface[{i}] = "{surface}";\n')
        f.write(f'!$no_volumes = {len(volume_names)};\n')
        for i, volume in enumerate(volume_names, 1):
            f.write(f'!$volume[{i}] = "{volume}";\n')
        f.write("\n")

        f.write('!$all_surface_objects = getChildrenByCategory("/", "surface");\n')
        f.write('!@surface_objects = split(",", $all_surface_objects);\n')
        f.write('!$all_volume_objects = getChildren("/", "VOLUME");\n')
        f.write('!@volume_objects = split(",", $all_volume_objects);\n')
        # DATA READER is the authoritative source for the currently active
        # CFD-Post case name.  Root CASE discovery is not reliable in all
        # loaded-result layouts.
        f.write('!$case_name = getValue("DATA READER", "Active Case Name");\n')
        f.write('!open(META, ">$metadata_file") or die "Cannot create metadata: $!";\n')
        f.write('!print META "CASE|$case_name\\n";\n')

        f.write("!for($i=1;$i<=$no_surfaces;$i++){\n")
        f.write('  !$location = "";\n')
        f.write("  !for($j=0;$j<scalar(@surface_objects);$j++){\n")
        f.write("    !$object = $surface_objects[$j];\n")
        f.write("    !$object_name = getObjectName($object);\n")
        f.write("    !if($object_name eq $surface[$i]){\n")
        f.write("      !$location = $object;\n")
        f.write("    !}\n")
        f.write("  !}\n")
        f.write('  !if($location eq \"\"){\n')
        f.write('    !die \"Export surface not found: $surface[$i]\\n\";\n')
        f.write('  !}\n')
        f.write('  !print META "SURFACE|$surface[$i]|$location\\n";\n')
        f.write("  EXPORT:\n")
        f.write("    CSV Type = CSV\n")
        f.write("    Export Connectivity = On\n")
        f.write("    Export Coord Frame = Global\n")
        f.write("    Export File = $file_path/export_$surface[$i].csv\n")
        f.write("    Export Geometry = On\n")
        f.write("    Export Node Numbers = Off\n")
        f.write("    Export Null Data = On\n")
        f.write("    Export Type = Generic\n")
        f.write("    Include File Information = Off\n")
        f.write("    Include Header = On\n")
        f.write("    Location List = $surface[$i]\n")
        f.write("    Null Token = null\n")
        f.write("    Overwrite = On\n")
        f.write("    Precision = 8\n")
        f.write('    Separator = ", "\n')
        f.write("    Spatial Variables = X,Y,Z\n")
        f.write("    Variable List = $variables\n")
        f.write("    Vector Brackets = ()\n")
        f.write("    Vector Display = Scalar\n")
        f.write("  END\n")
        f.write("  >export\n")
        f.write("!}\n\n")

        # Resolve user-created CFX-Post volumes versus mesh/case locations.
        f.write("!for($i=1;$i<=$no_volumes;$i++){\n")
        f.write("  !$location = $volume[$i];\n")
        f.write("  !for($j=0;$j<scalar(@volume_objects);$j++){\n")
        f.write("    !$object = $volume_objects[$j];\n")
        f.write("    !$object_name = getObjectName($object);\n")
        f.write("    !if($object_name eq $volume[$i]){\n")
        f.write("      !$location = $object;\n")
        f.write("    !}\n")
        f.write("  !}\n")
        f.write('  !print META "VOLUME|$volume[$i]|$location\\n";\n')
        f.write("!}\n")
        f.write("!close(META);\n\n")

        f.write(f'!open(MARKER, ">{completion_file.as_posix()}") or die "Cannot create export completion marker: $!";\n')
        f.write('!print MARKER "Export is successful\\n";\n')
        f.write("!close(MARKER);\n")

    print("Export session created:", session_file)
    return session_file


def clean_null_data(
        data,
        input_file,
        original_lines,
        faces_start
):

    null_mask = data[
        CFD_VARIABLES
    ].isna().any(axis=1)

    null_count = null_mask.sum()

    if null_count == 0:
        return data

    print(
        f"\nNull CFD data detected: "
        f"{null_count} points"
    )

    valid_mask = ~null_mask

    valid_coordinates = data.loc[
        valid_mask,
        ["X", "Y", "Z"]
    ].to_numpy()

    valid_data = data.loc[
        valid_mask,
        CFD_VARIABLES
    ].to_numpy()

    invalid_coordinates = data.loc[
        null_mask,
        ["X", "Y", "Z"]
    ].to_numpy()

    if len(valid_coordinates) == 0:
        raise ValueError(
            f"No valid CFD points available "
            f"to repair {input_file.name}"
        )

    tree = cKDTree(
        valid_coordinates
    )

    distances, nearest_indices = tree.query(
        invalid_coordinates
    )

    maximum_distance = distances.max()

    print(
        f"Maximum distance to nearest valid point: "
        f"{maximum_distance:.4f} m"
    )

    if maximum_distance > MAX_CLEANING_DISTANCE:

        raise ValueError(
            f"Maximum cleaning distance "
            f"({maximum_distance:.3f} m) exceeds "
            f"the allowed limit of "
            f"{MAX_CLEANING_DISTANCE:.3f} m."
        )

    invalid_indices = data.index[
        null_mask
    ]

    for i, row_index in enumerate(
        invalid_indices
    ):

        nearest_data = valid_data[
            nearest_indices[i]
        ]

        data.loc[
            row_index,
            CFD_VARIABLES
        ] = nearest_data

    cleaned_file = (
        input_file.parent /
        f"{input_file.stem}_cleaned.csv"
    )

    with open(
        cleaned_file,
        "w",
        newline=""
    ) as f:

        f.write("[Name]\n")

        f.write(
            f"Cleaned CFD Data - "
            f"{input_file.name}\n\n"
        )

        f.write("[Data]\n")

        data.to_csv(
            f,
            index=False,
            lineterminator="\n"
        )

        f.write("\n[Faces]\n")

        for line in original_lines[
            faces_start + 1:
        ]:

            f.write(line)

    print(
        f"Cleaned file created: "
        f"{cleaned_file.name}"
    )

    return data


# ============================================================
# 5. CLOTHING TEMPERATURE
# ============================================================

def clothing_temperature_ashrae(
        ta,
        tr,
        vr,
        met,
        clo_dynamic
):

    M = met * 58.15
    Icl = clo_dynamic * 0.155

    if Icl <= 0.078:
        fcl = 1 + 1.29 * Icl
    else:
        fcl = 1.05 + 0.645 * Icl

    tcl = 35.7 - 0.028 * M

    for _ in range(150):

        hc_forced = (
            12.1 * np.sqrt(
                max(vr, 0.01)
            )
        )

        hc_natural = (
            2.38 *
            abs(tcl - ta) ** 0.25
        )

        hc = max(
            hc_forced,
            hc_natural
        )

        hr = (
            4
            * emissivity
            * 5.670374e-8
            * (
                (tcl + 273.15) ** 2
                +
                (tr + 273.15) ** 2
            )
            * (
                (tcl + 273.15)
                +
                (tr + 273.15)
            )
        )

        tcl_new = (
            35.7
            - 0.028 * M
            +
            Icl * fcl
            * (
                hc * ta
                +
                hr * tr
            )
        ) / (
            1
            +
            Icl * fcl * (
                hc + hr
            )
        )

        if abs(
            tcl_new - tcl
        ) < 0.001:

            tcl = tcl_new
            break

        tcl = tcl_new

    return tcl, hc, hr


# ============================================================
# 6. THERMAL COMFORT CALCULATIONS
# ============================================================

def validate_relative_humidity_percentage_header(header_text):
    """Require the CFX-created percentage humidity variable in export CSVs."""
    variable_name = str(header_text).split("[", 1)[0].strip()
    if variable_name != "Relative Humidity Percentage":
        raise ValueError(
            "Expected exported humidity variable 'Relative Humidity Percentage', "
            f"but found '{variable_name}'. Generate the export with this toolkit so "
            "the percentage variable is created before export."
        )


def detect_temperature_unit(header_text, variable_name):
    """
    Detect temperature unit from a CFX-Post CSV header.

    Returns:
        "K" if Kelvin
        "C" if Celsius
    """

    pattern = rf"{re.escape(variable_name)}\s*\[\s*([^\]]+)\s*\]"

    match = re.search(
        pattern,
        header_text,
        re.IGNORECASE
    )

    if not match:
        raise ValueError(
            f"Could not detect unit for "
            f"'{variable_name}' from the CFX header."
        )

    unit = match.group(1).strip().lower()

    if unit in ("k", "kelvin"):
        return "K"

    if unit in ("c", "°c", "deg c", "degc", "celsius"):
        return "C"

    raise ValueError(
        f"Unsupported temperature unit "
        f"'{unit}' for '{variable_name}'."
    )

def _split_cfx_header(header_text):
    """Return (variable name, unit) from a CFX Generic CSV header."""
    header_text = str(header_text).strip()
    match = re.match(r"^(.*?)\s*\[\s*([^\]]+)\s*\]\s*$", header_text)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return header_text, ""


def load_export_dataframe(export_file):
    """Read a CFX Generic surface export while preserving extra variables.

    Core thermal-comfort variables are renamed to the toolkit's internal names;
    any additional CFX variables keep their original CFX name.
    """
    export_file = Path(export_file)
    with open(export_file, "r") as f:
        lines = f.readlines()

    faces_index = next(
        (i for i, line in enumerate(lines) if "[Faces]" in line),
        None
    )
    if faces_index is None:
        raise ValueError(f"No [Faces] section found in {export_file}")

    header_index = next(
        (i for i, line in enumerate(lines) if "X [ m ]" in line),
        None
    )
    if header_index is None:
        raise ValueError(f"Could not find data header in {export_file}")

    data = pd.read_csv(
        io.StringIO("".join(lines[header_index:faces_index])),
        header=0,
        sep=",",
        skipinitialspace=True,
    )
    data.columns = data.columns.str.strip()

    headers = list(data.columns)
    header_by_name = {}
    unit_by_name = {}
    for header in headers:
        name, unit = _split_cfx_header(header)
        header_by_name.setdefault(name, header)
        unit_by_name.setdefault(name, unit)

    required = [
        "X",
        "Y",
        "Z",
        "Radiation Temperature",
        "Relative Humidity Percentage",
        "Temperature",
        "Turbulence Kinetic Energy",
        "Velocity",
    ]
    missing = [name for name in required if name not in header_by_name]
    if missing:
        raise ValueError(
            "Missing required CFX export variable(s): " + ", ".join(missing)
        )

    validate_relative_humidity_percentage_header(
        header_by_name["Relative Humidity Percentage"]
    )
    temperature_unit = detect_temperature_unit(
        header_by_name["Temperature"],
        "Temperature"
    )
    mrt_unit = detect_temperature_unit(
        header_by_name["Radiation Temperature"],
        "Radiation Temperature"
    )

    internal_names = {
        "X": "X",
        "Y": "Y",
        "Z": "Z",
        "Radiation Temperature": "MRT",
        "Relative Humidity Percentage": "RH",
        "Temperature": "Temperature",
        "Turbulence Kinetic Energy": "TKE",
        "Velocity": "Velocity",
    }

    renamed_columns = []
    for header in headers:
        name, _ = _split_cfx_header(header)
        renamed_columns.append(internal_names.get(name, name))
    data.columns = renamed_columns

    # Metadata used by visualization helpers for project-specific native CFX variables.
    units = dict(unit_by_name)
    units["Temperature"] = "C" if temperature_unit in ("K", "C") else temperature_unit
    units["Radiation Temperature"] = "C" if mrt_unit in ("K", "C") else mrt_unit
    units["Relative Humidity"] = ""
    data.attrs["cfx_units"] = units

    return data, lines, faces_index, header_index, temperature_unit, mrt_unit


def process_file(
        input_file,
        output_file
):

    print("\n============================================================")
    print(
        f"Processing: {input_file.name}"
    )
    print("============================================================")

    t_0 = time.time()

    (
        data,
        lines,
        faces_index,
        header_line,
        temperature_unit,
        mrt_unit,
    ) = load_export_dataframe(input_file)

    print(
        f"Temperature units detected: "
        f"Temperature = {temperature_unit}, "
        f"Radiation Temperature = {mrt_unit}"
    )

    print(
        f"Found "
        f"{faces_index - header_line - 2} "
        f"data points"
    )

    # --------------------------------------------------------
    # Conditional null cleaning
    # --------------------------------------------------------

    null_mask = data[
        CFD_VARIABLES
    ].isna().any(axis=1)

    if null_mask.any():

        data = clean_null_data(
            data,
            input_file,
            lines,
            faces_index
        )

    # --------------------------------------------------------
    # Required columns
    # --------------------------------------------------------

    required_columns = [
        "X",
        "Y",
        "Z",
        "Temperature",
        "Velocity",
        "RH",
        "MRT",
        "TKE"
    ]

    for col in required_columns:

        if col not in data.columns:

            raise ValueError(
                f"Missing column: {col}"
            )

    Ta = data[
        "Temperature"
    ]

    Tr = data[
        "MRT"
    ]

    # --------------------------------------------------------
    # Convert temperatures to Celsius when required
    # --------------------------------------------------------

    if temperature_unit == "K":
        Ta = Ta - 273.15

    if mrt_unit == "K":
        Tr = Tr - 273.15

    data["Temperature"] = Ta
    data["MRT"] = Tr

    Vel = data[
        "Velocity"
    ]

    RH = data[
        "RH"
    ]

    TKE = data[
        "TKE"
    ]

    # --------------------------------------------------------
    # Correct zero velocity
    # --------------------------------------------------------

    Vel = Vel.clip(
        lower=minimum_velocity
    )

    data[
        "Velocity"
    ] = Vel

    # Relative Humidity Percentage is created in CFX-Post before export,
    # so RH is already in percent here. No fraction/percentage detection is needed.
    data[
        "RH"
    ] = RH

    # --------------------------------------------------------
    # [1/8] Psychrometrics
    # --------------------------------------------------------

    t0 = time.time()

    print(
        "\n[1/8] Calculating "
        "psychrometric properties..."
    )

    if calculate_psychrometrics:

        wet_bulb = []
        dew_point = []
        humidity_ratio = []

        for t, rh in zip(
            Ta,
            RH
        ):

            dp = (
                psychrolib
                .GetTDewPointFromRelHum(
                    t,
                    rh / 100
                )
            )

            wb = (
                psychrolib
                .GetTWetBulbFromRelHum(
                    t,
                    rh / 100,
                    pressure
                )
            )

            w = (
                psychrolib
                .GetHumRatioFromRelHum(
                    t,
                    rh / 100,
                    pressure
                )
            )

            dew_point.append(dp)
            wet_bulb.append(wb)
            humidity_ratio.append(w)

        data[
            "Wet_Bulb_Temperature"
        ] = wet_bulb

        data[
            "Dew_Point_Temperature"
        ] = dew_point

        data[
            "Humidity_Ratio"
        ] = humidity_ratio

        elapsed = time.time() - t0

        if elapsed >= 0.1:
            print(f"      ✓ Completed ({elapsed:.1f} s)")
        else:
            print(f"      ✓ Completed ({elapsed:.1e} s)")

    else:

        print(
            "      Skipped (disabled)"
        )

    # --------------------------------------------------------
    # [2/8] Relative air speed
    # --------------------------------------------------------

    t0 = time.time()

    print(
        "\n[2/8] Calculating "
        "relative air speed..."
    )

    vr = v_relative(
        v=Vel,
        met=met
    )

    clo_dynamic = (
        clo_dynamic_ashrae(
            clo=clo,
            met=met
        )
    )

    data[
        "Relative_Air_Speed"
    ] = vr

    elapsed = time.time() - t0

    if elapsed >= 0.1:
        print(f"      ✓ Completed ({elapsed:.1f} s)")
    else:
        print(f"      ✓ Completed ({elapsed:.1e} s)")

    # --------------------------------------------------------
    # [3/8] PMV / PPD
    # --------------------------------------------------------

    t0 = time.time()

    print(
        "\n[3/8] Calculating PMV / PPD..."
    )

    if calculate_pmv_ppd:
        pmv_result = pmv_ppd_ashrae(
            tdb=Ta.values,
            tr=Tr.values,
            vr=vr,
            rh=RH.values,
            met=met,
            clo=clo_dynamic,
            limit_inputs=False,
            round_output=False
        )

        data[
            "PMV"
        ] = pmv_result["pmv"]

        data[
            "PPD"
        ] = pmv_result["ppd"]

        elapsed = time.time() - t0

        if elapsed >= 0.1:
            print(f"      ✓ Completed ({elapsed:.1f} s)")
        else:
            print(f"      ✓ Completed ({elapsed:.1e} s)")
    else:

        print("      Skipped (disabled)")

    # --------------------------------------------------------
    # [4/8] SET
    # --------------------------------------------------------

    t0 = time.time()

    print(
        "\n[4/8] Calculating SET..."
    )

    if calculate_set:
        SET = set_tmp(
            tdb=Ta.values,
            tr=Tr.values,
            v=Vel.values,
            rh=RH.values,
            met=met,
            clo=clo_dynamic,
            limit_inputs=False,
            round_output=False
        )

        data[
            "SET"
        ] = SET.set

        elapsed = time.time() - t0

        if elapsed >= 0.1:
            print(f"      ✓ Completed ({elapsed:.1f} s)")
        else:
            print(f"      ✓ Completed ({elapsed:.1e} s)")
    else:

        print("      Skipped (disabled)")
    # --------------------------------------------------------
    # [5/8] UTCI
    # --------------------------------------------------------

    t0 = time.time()

    print(
        "\n[5/8] Calculating UTCI..."
    )

    if calculate_utci:

        UTCI_values = []

        for ta, tr, vel, rh in zip(
            Ta,
            Tr,
            Vel,
            RH
        ):

            result = utci(
                tdb=float(ta),
                tr=float(tr),
                v=float(vel),
                rh=float(rh),
                limit_inputs=False,
                round_output=False
            )

            UTCI_values.append(
                result.utci
            )

        data[
            "UTCI"
        ] = UTCI_values

        elapsed = time.time() - t0

        if elapsed >= 0.1:
            print(f"      ✓ Completed ({elapsed:.1f} s)")
        else:
            print(f"      ✓ Completed ({elapsed:.1e} s)")

    else:

        print(
            "      Skipped (disabled)"
        )

    # --------------------------------------------------------
    # [6/8] Draft rate
    # --------------------------------------------------------

    t0 = time.time()

    print(
        "\n[6/8] Calculating draft rate..."
    )

    if calculate_draft_rate:

        Turbulence_Intensity = (
            np.sqrt(
                (2 / 3) * TKE
            )
            / Vel
        )

        Turbulence_Intensity = (
            Turbulence_Intensity * 100
        )

        Draft_Rate = (
            (34 - Ta)
            *
            np.maximum(
                Vel - 0.05,
                0
            ) ** 0.62
            *
            (
                0.37
                * Vel
                * Turbulence_Intensity
                + 3.14
            )
        )

        Draft_Rate = np.clip(
            Draft_Rate,
            0,
            100
        )

        data[
            "Turbulence_Intensity"
        ] = Turbulence_Intensity

        data[
            "Draft_Rate"
        ] = Draft_Rate

        elapsed = time.time() - t0

        if elapsed >= 0.1:
            print(f"      ✓ Completed ({elapsed:.1f} s)")
        else:
            print(f"      ✓ Completed ({elapsed:.1e} s)")

    else:

        print(
            "      Skipped (disabled)"
        )

    # --------------------------------------------------------
    # [7/8] Clothing surface
    # --------------------------------------------------------

    t0 = time.time()

    print(
        "\n[7/8] Calculating "
        "clothing surface temperature..."
    )

    need_clothing_model = (
        calculate_clothing_temperature
        or calculate_operative_temperature
    )
    if need_clothing_model:
        Tcl = []
        HC = []
        HR = []

        for t_air, t_rad, v_r in zip(
            Ta,
            Tr,
            vr
        ):

            tcl, hc, hr = (
                clothing_temperature_ashrae(
                    t_air,
                    t_rad,
                    v_r,
                    met,
                    clo_dynamic
                )
            )

            Tcl.append(tcl)
            HC.append(hc)
            HR.append(hr)

            if abs(tcl) > 100:
                print(
                    "Warning: unrealistic Tcl:",
                    tcl
                )

        data[
            "Clothing_Surface_Temperature"
        ] = Tcl

        data[
            "Convective_HTC"
        ] = HC

        data[
            "Radiative_HTC"
        ] = HR

        elapsed = time.time() - t0

        if elapsed >= 0.1:
            print(f"      ✓ Completed ({elapsed:.1f} s)")
        else:
            print(f"      ✓ Completed ({elapsed:.1e} s)")

    else:

        print("      Skipped (disabled)")
    
    # --------------------------------------------------------
    # [8/8] Operative temperature
    # --------------------------------------------------------

    t0 = time.time()

    print(
        "\n[8/8] Calculating "
        "operative temperature..."
    )

    if calculate_operative_temperature:
        data[
            "Operative_Temperature"
        ] = (
            (
                np.array(HR) * Tr
                +
                np.array(HC) * Ta
            )
            /
            (
                np.array(HR)
                +
                np.array(HC)
            )
        )

        elapsed = time.time() - t0

        if elapsed >= 0.1:
            print(f"      ✓ Completed ({elapsed:.1f} s)")
        else:
            print(f"      ✓ Completed ({elapsed:.1e} s)")

    else:

        print("      Skipped (disabled)")

    # --------------------------------------------------------
    # Export results + original topology
    # --------------------------------------------------------

    print(
        "\nExporting results..."
    )

    original_project_name = "Unknown"

    for i, line in enumerate(lines):

        if "[Name]" in line:

            if i + 1 < len(lines):
                original_project_name = (
                    lines[i + 1].strip()
                )

            break

    with open(
        output_file,
        "w",
        newline=""
    ) as f:

        f.write("[Name]\n")

        f.write(
            "Thermal Comfort Results - "
            f"{original_project_name}\n\n"
        )

        f.write("[Data]\n")

        data.to_csv(
            f,
            index=False,
            lineterminator="\n"
        )

        f.write("\n[Faces]\n")

        for line in lines[
            faces_index + 1:
        ]:

            f.write(line)

    print(
        "      ✓ Results exported with topology"
    )

    print(
        f"\nSaved:\n{output_file}"
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    summary_variables = [
        "Relative_Air_Speed"
    ]

    if calculate_pmv_ppd:
        summary_variables.extend([
            "PMV",
            "PPD"
        ])

    if calculate_set:
        summary_variables.append(
            "SET"
        )

    if calculate_operative_temperature:
        summary_variables.append(
            "Operative_Temperature"
        )

    if calculate_utci:
        summary_variables.append(
            "UTCI"
        )

    if calculate_draft_rate:
        summary_variables.append(
            "Draft_Rate"
        )

    if calculate_clothing_temperature:
        summary_variables.extend([
            "Clothing_Surface_Temperature",
            "Convective_HTC",
            "Radiative_HTC"
        ])

    if calculate_psychrometrics:
        summary_variables.extend([
            "Wet_Bulb_Temperature",
            "Dew_Point_Temperature",
            "Humidity_Ratio"
        ])

    pd.set_option(
        "display.max_columns",
        None
    )

    pd.set_option(
        "display.width",
        None
    )

    print(
        data[
            summary_variables
        ].describe()
    )

    print(
        f"\nFinished processing "
        f"{input_file.name}"
    )

    print(
        f"Execution time: "
        f"{time.time() - t_0:.1f} s"
    )


# ============================================================
# 7. CREATE IMPORT SESSION
# ============================================================

def create_update_import_session_file(
        output_directory,
        import_files
):
    """Create a thermal-comfort-only session that updates existing imports.

    This mode is intended for an already-prepared .cst file where the Generic
    Data USER SURFACEs already exist.  Re-defining those USER SURFACEs with a
    new Input File refreshes the data in place and avoids duplicate imported
    objects such as ``Imported ... 1``.
    """
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    import_files = sorted(Path(f) for f in import_files)

    if not import_files:
        raise RuntimeError(
            "No import CSV files found. "
            "Import update session cannot be created."
        )

    session_file = output_directory / "import_session.cse"
    completion_file = output_directory / "import_complete.txt"

    with open(session_file, "w", newline="") as f:
        f.write("# Session file started\n")
        f.write("# Automatically generated by Python\n")
        f.write("# CFX-Post 23.2\n\n")
        f.write("COMMAND FILE:\n")
        f.write("  CFX Post Version = 23.2\n")
        f.write("END\n\n")

        for import_file in import_files:
            stem = import_file.stem
            surface = stem[len("import_"):] if stem.lower().startswith("import_") else stem
            if not surface:
                raise ValueError(f"Could not determine surface name from import file: {import_file.name}")

            file_path = str(import_file).replace("\\", "/")
            imported_surface = f"Imported Thermal Comfort Results {surface}"
            section_name = f"Thermal Comfort Results - {surface}"

            f.write(f"USER SURFACE: {imported_surface}\n\n")
            f.write(f"  Input File = {file_path}\n\n")
            f.write("  Option = From File\n\n")
            f.write(f"  Section Name = {section_name}\n\n")
            f.write("  Visibility = Off\n\n")
            f.write("END\n\n")

        f.write("# Import-update completion marker\n")
        f.write(
            f'!open(MARKER, ">{completion_file.as_posix()}") '
            'or die "Cannot create import completion marker: $!";\n'
        )
        f.write('!print MARKER "Import is successful\\n";\n')
        f.write('!close(MARKER);\n')

    print("\n============================================================")
    print("CFX-POST IMPORT UPDATE SESSION CREATED")
    print("============================================================")
    print(f"Session file : {session_file}")
    print(f"Import files : {len(import_files)}")
    return session_file


def create_import_session_file(
        output_directory,
        import_files
):

    import_files = sorted(
        Path(f) for f in import_files
    )

    if not import_files:
        raise RuntimeError(
            "No import CSV files found. "
            "Import session cannot be created."
        )

    session_file = (
        output_directory /
        "import_session.cse"
    )
    
    completion_file = (
        output_directory /
        "import_complete.txt"
    )
    
    with open(
        session_file,
        "w",
        newline=""
    ) as f:

        f.write(
            "# Session file started\n"
        )

        f.write(
            "# Automatically generated by Python\n"
        )

        f.write(
            "# CFX-Post 23.2\n\n"
        )

        f.write(
            "COMMAND FILE:\n"
        )

        f.write(
            "  CFX Post Version = 23.2\n"
        )

        f.write(
            "END\n\n"
        )

        for import_file in import_files:

            file_path = str(
                import_file
            ).replace("\\", "/")

            f.write(
                f">import filename={file_path}, "
                f"type=Generic, visibility=Off\n"
            )
            
        f.write("\n")
        f.write("# Import completion marker\n")
        f.write(
            f'!open(MARKER, ">{completion_file.as_posix()}") '
            'or die "Cannot create import completion marker: $!";\n'
        )
        f.write(
            '!print MARKER "Import is successful\\n";\n'
        )
        f.write(
            '!close(MARKER);\n'
        )

    print("\n============================================================")
    print("CFX-POST IMPORT SESSION CREATED")
    print("============================================================")

    print(
        f"Session file : {session_file}"
    )

    print(
        f"Import files : {len(import_files)}"
    )

    return session_file



# ============================================================
# 8. FIGURE / CONTOUR HELPERS
# ============================================================

ORIGINAL_FIGURE_VARIABLES = {
    "Temperature": {
        "cfx_variable": "Temperature",
        "data_column": "Temperature",
        "unit": "C",
        "legend_title": "Temperature [C]",
        "legend_format": "%3.0f",
    },
    "Radiation Temperature": {
        "cfx_variable": "Radiation Temperature",
        "data_column": "MRT",
        "unit": "C",
        "legend_title": "Radiation Temperature [C]",
        "legend_format": "%3.0f",
    },
    "Relative Humidity": {
        "cfx_variable": "Relative Humidity Percentage",
        "data_column": "RH",
        "unit": "",
        "legend_title": "Relative Humidity [%]",
        "legend_format": "%3.0f",
    },
    "Velocity": {
        "cfx_variable": "Velocity",
        "data_column": "Velocity",
        "unit": "m s^-1",
        "legend_title": "Velocity [m/s]",
        "legend_format": "%4.1f",
    },
    "Turbulence Kinetic Energy": {
        "cfx_variable": "Turbulence Kinetic Energy",
        "data_column": "TKE",
        "unit": "m^2 s^-2",
        "legend_title": "Turbulence Kinetic Energy [m^2/s^2]",
        "legend_format": "%4.2f",
    },
}

MANUAL_FIGURE_VARIABLES = {}

CALCULATED_FIGURE_VARIABLES = {
    "Relative_Air_Speed": {
        "unit": "m s^-1",
        "legend_title": "Relative Air Speed [m/s]",
        "legend_format": "%4.1f",
    },
    "PMV": {
        "unit": "",
        "legend_title": "PMV",
        "legend_format": "%4.1f",
    },
    "PPD": {
        "unit": "",
        "legend_title": "PPD [%]",
        "legend_format": "%3.0f",
    },
    "SET": {
        "unit": "C",
        "legend_title": "SET [C]",
        "legend_format": "%3.0f",
    },
    "UTCI": {
        "unit": "C",
        "legend_title": "UTCI [C]",
        "legend_format": "%3.0f",
    },
    "Turbulence_Intensity": {
        "unit": "",
        "legend_title": "Turbulence Intensity [%]",
        "legend_format": "%3.0f",
    },
    "Draft_Rate": {
        "unit": "",
        "legend_title": "Draft Rate [%]",
        "legend_format": "%3.0f",
    },
    "Clothing_Surface_Temperature": {
        "unit": "C",
        "legend_title": "Clothing Surface Temperature [C]",
        "legend_format": "%3.0f",
    },
    "Convective_HTC": {
        "unit": "W m^-2 K^-1",
        "legend_title": "Convective HTC [W/m^2-K]",
        "legend_format": "%4.1f",
    },
    "Radiative_HTC": {
        "unit": "W m^-2 K^-1",
        "legend_title": "Radiative HTC [W/m^2-K]",
        "legend_format": "%4.1f",
    },
    "Operative_Temperature": {
        "unit": "C",
        "legend_title": "Operative Temperature [C]",
        "legend_format": "%3.0f",
    },
    "Wet_Bulb_Temperature": {
        "unit": "C",
        "legend_title": "Wet Bulb Temperature [C]",
        "legend_format": "%3.0f",
    },
    "Dew_Point_Temperature": {
        "unit": "C",
        "legend_title": "Dew Point Temperature [C]",
        "legend_format": "%3.0f",
    },
    "Humidity_Ratio": {
        "unit": "",
        "legend_title": "Humidity Ratio",
        "legend_format": "%5.4f",
    },
}


def sanitize_expression_name(variable_name):

    # CFX CEL expression names do not accept underscores.
    # Convert underscores and other separators to spaces.

    name = re.sub(
        r"[^A-Za-z0-9 ]+",
        " ",
        variable_name.strip()
    )

    name = " ".join(
        name.split()
    )

    return name


def table_column_letter(index):
    """
    Convert zero-based column index to CFX table column letters.

    0  -> A
    1  -> B
    ...
    25 -> Z
    26 -> AA
    """

    index += 1
    result = ""

    while index > 0:

        index, remainder = divmod(
            index - 1,
            26
        )

        result = (
            chr(65 + remainder)
            + result
        )

    return result


def figure_display_name(variable_name):
    return variable_name.replace("_", " ")


def read_export_dataframe(export_file):
    data, _, _, _, temperature_unit, mrt_unit = load_export_dataframe(export_file)

    # Statistics used for contour/histogram limits are expressed in C for the
    # two native temperature variables, matching CFX display/CEL ranges.
    if temperature_unit == "K":
        data["Temperature"] = data["Temperature"] - 273.15

    if mrt_unit == "K":
        data["MRT"] = data["MRT"] - 273.15

    return data


def read_visualization_export_dataframe(export_file):
    """Read a lightweight CFX Generic export used for visualization geometry.

    Unlike the thermal-comfort export reader, this does not require a [Faces]
    section or the full thermal variable set. CFX headers are normalized to the
    same internal names used by the visualization engine.
    """
    export_file = Path(export_file)
    with open(export_file, "r") as f:
        lines = f.readlines()

    data_header = next(
        (i for i, line in enumerate(lines) if line.strip() == "[Data]"),
        None,
    )
    if data_header is None:
        raise ValueError(f"No [Data] section found in {export_file}")

    end_index = next(
        (i for i in range(data_header + 1, len(lines)) if lines[i].strip() == "[Faces]"),
        len(lines),
    )

    payload = "".join(lines[data_header + 1:end_index]).strip()
    if not payload:
        raise ValueError(f"No visualization data found in {export_file}")

    data = pd.read_csv(
        io.StringIO(payload),
        header=0,
        sep=",",
        skipinitialspace=True,
    )
    data.columns = data.columns.str.strip()

    renamed = []
    units = {}
    temperature_units = {}
    for header in data.columns:
        name, unit = _split_cfx_header(header)
        units[name] = unit
        if name == "Radiation Temperature":
            renamed.append("MRT")
            temperature_units["MRT"] = unit
        elif name == "Relative Humidity Percentage":
            renamed.append("RH")
        elif name == "Turbulence Kinetic Energy":
            renamed.append("TKE")
        else:
            renamed.append(name)
            if name == "Temperature":
                temperature_units["Temperature"] = unit

    data.columns = renamed

    # Keep statistics in Celsius, matching the normal contour CEL limits.
    for column in ("Temperature", "MRT"):
        unit = str(temperature_units.get(column, "")).strip().lower()
        if unit in ("k", "kelvin") and column in data.columns:
            data[column] = pd.to_numeric(data[column], errors="coerce") - 273.15

    units["Temperature"] = "C" if "Temperature" in data.columns else units.get("Temperature", "")
    units["Radiation Temperature"] = "C" if "MRT" in data.columns else units.get("Radiation Temperature", "")
    units["Relative Humidity"] = ""
    data.attrs["cfx_units"] = units
    return data


def _normalize_vector(vector, label="vector"):
    vector = np.asarray(vector, dtype=float)
    norm = float(np.linalg.norm(vector))
    if not np.isfinite(norm) or norm <= 1.0e-12:
        raise ValueError(f"Cannot normalize degenerate {label}.")
    return vector / norm


def _rotation_matrix_to_quaternion(matrix):
    """Return CFX-style x,y,z,w quaternion for a 3x3 rotation matrix."""
    m = np.asarray(matrix, dtype=float)
    trace = float(np.trace(m))
    if trace > 0.0:
        s = np.sqrt(trace + 1.0) * 2.0
        qw = 0.25 * s
        qx = (m[2, 1] - m[1, 2]) / s
        qy = (m[0, 2] - m[2, 0]) / s
        qz = (m[1, 0] - m[0, 1]) / s
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2.0
        qw = (m[2, 1] - m[1, 2]) / s
        qx = 0.25 * s
        qy = (m[0, 1] + m[1, 0]) / s
        qz = (m[0, 2] + m[2, 0]) / s
    elif m[1, 1] > m[2, 2]:
        s = np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2.0
        qw = (m[0, 2] - m[2, 0]) / s
        qx = (m[0, 1] + m[1, 0]) / s
        qy = 0.25 * s
        qz = (m[1, 2] + m[2, 1]) / s
    else:
        s = np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2.0
        qw = (m[1, 0] - m[0, 1]) / s
        qx = (m[0, 2] + m[2, 0]) / s
        qy = (m[1, 2] + m[2, 1]) / s
        qz = 0.25 * s

    q = _normalize_vector([qx, qy, qz, qw], "camera quaternion")
    # q and -q are equivalent. Keep a deterministic sign.
    if q[3] < 0:
        q = -q
    return tuple(float(v) for v in q)


def calculate_section_camera(section_data):
    """Determine section normal, in-plane axes, pivot, scale, and quaternion.

    PCA/SVD is used because the section can have any orientation. The smallest
    singular-vector direction is the plane normal. Global Z is projected into
    the plane to give a stable screen-up direction whenever possible.
    """
    required = ["X", "Y", "Z"]
    missing = [name for name in required if name not in section_data.columns]
    if missing:
        raise ValueError("Section geometry is missing: " + ", ".join(missing))

    points = section_data[required].apply(pd.to_numeric, errors="coerce").dropna().to_numpy(float)
    if len(points) < 3:
        raise ValueError("At least three valid points are required to orient a section camera.")

    centroid = points.mean(axis=0)
    centered = points - centroid
    _, singular_values, vh = np.linalg.svd(centered, full_matrices=False)
    if len(singular_values) < 3 or singular_values[1] <= 1.0e-10:
        raise ValueError("Section geometry is degenerate and does not define a 2D plane.")

    normal = _normalize_vector(vh[-1], "section normal")
    # Deterministic side: make the largest absolute component positive.
    major = int(np.argmax(np.abs(normal)))
    if normal[major] < 0:
        normal = -normal

    global_up = np.array([0.0, 0.0, 1.0])
    up = global_up - np.dot(global_up, normal) * normal
    if np.linalg.norm(up) <= 1.0e-8:
        fallback = np.array([0.0, 1.0, 0.0])
        up = fallback - np.dot(fallback, normal) * normal
    up = _normalize_vector(up, "section up direction")
    right = _normalize_vector(np.cross(up, normal), "section right direction")
    up = _normalize_vector(np.cross(normal, right), "section up direction")

    local_x = centered @ right
    local_y = centered @ up
    width = float(local_x.max() - local_x.min()) + 2.0 * CAMERA_MARGIN
    height = float(local_y.max() - local_y.min()) + 2.0 * CAMERA_MARGIN
    if width <= 0 or height <= 0:
        raise ValueError("Invalid section extent for camera calculation.")

    image_aspect = FIGURE_IMAGE_WIDTH / FIGURE_IMAGE_HEIGHT
    effective_span = max(width, height * image_aspect)
    scale = CAMERA_SCALE_FACTOR / effective_span

    # ``right``, ``up`` and ``normal`` are expressed in world coordinates.
    # Stacking them as columns gives the camera-to-world basis transform.
    # CFD-Post's ``Rotation Quaternion`` uses the inverse convention
    # (world-to-camera), so transpose the orthonormal basis before converting.
    # This distinction is invisible for some symmetric principal views (for
    # example a Y=constant section) but is essential for X=constant and
    # arbitrary oblique sections.
    camera_to_world = np.column_stack((right, up, normal))
    world_to_camera = camera_to_world.T
    quaternion = _rotation_matrix_to_quaternion(world_to_camera)
    clip_point = centroid + CLIP_PLANE_Z_OFFSET * normal

    return {
        "pivot": tuple(float(v) for v in centroid),
        "normal": tuple(float(v) for v in normal),
        "right": tuple(float(v) for v in right),
        "up": tuple(float(v) for v in up),
        "quaternion": quaternion,
        "scale": float(scale),
        "clip_point": tuple(float(v) for v in clip_point),
    }


def read_import_dataframe(import_file):
    with open(import_file, "r") as f:
        lines = f.readlines()

    faces_index = next(
        (
            i for i, line in enumerate(lines)
            if "[Faces]" in line
        ),
        None
    )

    if faces_index is None:
        raise ValueError(
            f"No [Faces] section found in {import_file}"
        )

    data_header = next(
        (
            i for i, line in enumerate(lines)
            if line.strip() == "[Data]"
        ),
        None
    )

    if data_header is None:
        raise ValueError(
            f"No [Data] section found in {import_file}"
        )

    data = pd.read_csv(
        io.StringIO(
            "".join(lines[data_header + 1:faces_index])
        ),
        header=0,
        sep=",",
        skipinitialspace=True
    )

    data.columns = data.columns.str.strip()

    return data


def parse_variable_entries(
        entries,
        settings_name,
        count_key,
        default_count,
        minimum_count
):
    """Parse variable settings.

    Accepted forms:
        "Variable"
        "Variable, lower, upper, count"

    In the four-field form, lower, upper, and count may each be left blank.
    Blank bounds use the automatic 5th/95th percentile value; a blank count
    uses the supplied default count.
    """
    parsed = []
    seen = set()

    for entry in entries:
        parts = [part.strip() for part in str(entry).split(",")]

        if len(parts) not in (1, 4):
            raise ValueError(
                f"Invalid {settings_name} entry: '{entry}'. "
                "Use 'Variable' or 'Variable, lower, upper, count'."
            )

        variable_name = parts[0]
        if not variable_name:
            raise ValueError(f"Empty variable name in {settings_name}.")
        if variable_name in seen:
            raise ValueError(
                f"Duplicate variable '{variable_name}' in {settings_name}."
            )
        seen.add(variable_name)

        lower = None
        upper = None
        count = default_count

        if len(parts) == 4:
            try:
                lower = float(parts[1]) if parts[1] else None
                upper = float(parts[2]) if parts[2] else None
                count = int(parts[3]) if parts[3] else default_count
            except ValueError as exc:
                raise ValueError(
                    f"Invalid numeric settings in {settings_name}: '{entry}'."
                ) from exc

        if lower is not None and upper is not None and lower >= upper:
            raise ValueError(
                f"Lower bound must be smaller than upper bound: '{entry}'."
            )
        if count < minimum_count:
            raise ValueError(
                f"Count must be at least {minimum_count}: '{entry}'."
            )

        parsed.append({
            "name": variable_name,
            "lower": lower,
            "upper": upper,
            count_key: count,
            "user_lower": lower is not None,
            "user_upper": upper is not None,
        })

    return parsed

def get_source_data_and_column(
        variable_name,
        surface,
        export_data,
        import_data
):
    definition = get_variable_definition(variable_name)

    if definition["source"] == "original":
        return export_data[surface], definition["data_column"]

    return import_data[surface], definition["import_variable"]


def calculate_5th_95th_percentile_bounds(
        variable_name,
        surfaces,
        export_data,
        import_data
):
    values_q05 = []
    values_q95 = []

    for surface in surfaces:
        source_data, source_column = get_source_data_and_column(
            variable_name,
            surface,
            export_data,
            import_data
        )

        if source_column not in source_data.columns:
            raise ValueError(
                f"Variable '{variable_name}' is not available for surface "
                f"'{surface}'. Check the corresponding calculation switch "
                "or the variable name."
            )

        values = pd.to_numeric(
            source_data[source_column],
            errors="coerce"
        ).dropna()

        if values.empty:
            raise ValueError(
                f"No valid values found for '{variable_name}' "
                f"on surface '{surface}'."
            )

        values_q05.append(float(values.quantile(0.05)))
        values_q95.append(float(values.quantile(0.95)))

    return min(values_q05), max(values_q95)


def histogram_divisions(lower, upper, count):
    if count < 1:
        raise ValueError("Number of histogram divisions must be at least 1.")

    values = np.linspace(lower, upper, count + 1)
    epsilon = max(abs(upper - lower) * 1.0e-6, 1.0e-6)
    values[0] -= epsilon
    values[-1] += epsilon
    return ",".join(f"{value:.12g}" for value in values)


def collect_variable_statistics(
        configs,
        target_surfaces,
        export_data,
        import_data,
        count_key
):
    statistics = {}

    for config in configs:
        variable_name = config["name"]
        lower = config["lower"]
        upper = config["upper"]

        if lower is None or upper is None:
            automatic_lower, automatic_upper = calculate_5th_95th_percentile_bounds(
                variable_name,
                target_surfaces,
                export_data,
                import_data
            )
            if lower is None:
                lower = automatic_lower
            if upper is None:
                upper = automatic_upper

        if lower >= upper:
            raise ValueError(
                f"Final lower bound must be smaller than upper bound for '{variable_name}'."
            )

        statistics[variable_name] = {
            "lower": lower,
            "upper": upper,
            count_key: config[count_key],
            "user_lower": config.get("user_lower", False),
            "user_upper": config.get("user_upper", False),
        }

    return statistics

def collect_plot_statistics(
        surfaces,
        export_files,
        import_files,
        figure_configs,
        histogram_surfaces,
        histogram_configs,
        section_surfaces=None,
        section_export_files=None,
        section_configs=None,
        *,
        volume_histogram_volumes=None,
        volume_export_files=None,
        volume_histogram_configs=None,
):
    """Collect unified plan/section/surface+volume histogram statistics."""
    section_surfaces = list(section_surfaces or [])
    section_export_files = list(section_export_files or [])
    section_configs = list(section_configs or [])
    volume_histogram_volumes = list(volume_histogram_volumes or [])
    volume_export_files = list(volume_export_files or [])
    volume_histogram_configs = list(volume_histogram_configs or [])

    if len(export_files) != len(surfaces):
        raise ValueError("Number of export files does not match normal surfaces.")
    if len(import_files) != len(surfaces):
        raise ValueError("Number of import files does not match normal surfaces.")
    if len(section_export_files) != len(section_surfaces):
        raise ValueError("Number of section export files does not match section surfaces.")
    # Volume point-data exports are optional when all volume histogram bounds
    # are explicit. They are validated below only if an automatic percentile
    # calculation actually needs the volume distribution.

    export_data, import_data, section_data, volume_data = {}, {}, {}, {}
    global_x_min, global_x_max = np.inf, -np.inf
    global_y_min, global_y_max = np.inf, -np.inf
    global_z_min, global_z_max = np.inf, -np.inf
    clip_plane_z = {}

    for surface, export_file, import_file in zip(surfaces, export_files, import_files):
        exp = read_visualization_export_dataframe(export_file)
        imp = read_import_dataframe(import_file) if import_file is not None else pd.DataFrame()
        export_data[surface] = exp
        import_data[surface] = imp
        for coord in ("X", "Y", "Z"):
            if coord not in exp.columns:
                raise ValueError(f"Missing {coord} geometry in {export_file}")
        x = pd.to_numeric(exp["X"], errors="coerce").dropna()
        y = pd.to_numeric(exp["Y"], errors="coerce").dropna()
        z = pd.to_numeric(exp["Z"], errors="coerce").dropna()
        if x.empty or y.empty or z.empty:
            raise ValueError(f"No valid geometry found in {export_file}")
        global_x_min = min(global_x_min, float(x.min())); global_x_max = max(global_x_max, float(x.max()))
        global_y_min = min(global_y_min, float(y.min())); global_y_max = max(global_y_max, float(y.max()))
        global_z_min = min(global_z_min, float(z.min())); global_z_max = max(global_z_max, float(z.max()))
        clip_plane_z[surface] = float(z.max()) + CLIP_PLANE_Z_OFFSET

    section_camera = {}
    for surface, export_file in zip(section_surfaces, section_export_files):
        data = read_visualization_export_dataframe(export_file)
        section_data[surface] = data
        section_camera[surface] = calculate_section_camera(data)

    for volume, export_file in zip(volume_histogram_volumes, volume_export_files):
        volume_data[volume] = read_visualization_export_dataframe(export_file)

    requested = [cfg["name"] for cfg in figure_configs]
    requested += [cfg["name"] for cfg in histogram_configs]
    requested += [cfg["name"] for cfg in section_configs]
    requested += [cfg["name"] for cfg in volume_histogram_configs]
    combined_native_data = {
        **export_data,
        **{f"section::{k}": v for k, v in section_data.items()},
        **{f"volume::{k}": v for k, v in volume_data.items()},
    }
    register_manual_variable_definitions(requested, combined_native_data)

    if surfaces:
        x_range = (global_x_max - global_x_min) + 2.0 * CAMERA_MARGIN
        y_range = (global_y_max - global_y_min) + 2.0 * CAMERA_MARGIN
        if x_range <= 0 or y_range <= 0:
            raise ValueError("Invalid global X-Y extent for camera calculation.")
        image_aspect = FIGURE_IMAGE_WIDTH / FIGURE_IMAGE_HEIGHT
        camera_scale = CAMERA_SCALE_FACTOR / max(x_range, y_range * image_aspect)
        camera_pivot = (
            0.5 * (global_x_min + global_x_max),
            0.5 * (global_y_min + global_y_max),
            0.5 * (global_z_min + global_z_max),
        )
    else:
        camera_scale, camera_pivot = 1.0, (0.0, 0.0, 0.0)

    variable_statistics = collect_variable_statistics(
        figure_configs, surfaces, export_data, import_data, "number_of_contours"
    ) if figure_configs and surfaces else {}

    # One histogram range per variable, shared by surface and volumetric charts.
    surface_cfg = {c["name"]: c for c in histogram_configs}
    volume_cfg = {c["name"]: c for c in volume_histogram_configs}
    histogram_statistics = {}
    ordered_names = []
    for cfg in [*histogram_configs, *volume_histogram_configs]:
        if cfg["name"] not in ordered_names:
            ordered_names.append(cfg["name"])

    for variable_name in ordered_names:
        cfg = surface_cfg.get(variable_name) or volume_cfg[variable_name]
        lower, upper = cfg.get("lower"), cfg.get("upper")
        count = int(cfg.get("divisions", DEFAULT_NUMBER_OF_HISTOGRAM_DIVISIONS))
        q05, q95 = [], []

        if variable_name in surface_cfg:
            for surface in histogram_surfaces:
                source, column = get_source_data_and_column(variable_name, surface, export_data, import_data)
                if column not in source.columns:
                    raise ValueError(f"Variable '{variable_name}' is unavailable on surface '{surface}'.")
                vals = pd.to_numeric(source[column], errors="coerce").dropna()
                if not vals.empty:
                    q05.append(float(vals.quantile(0.05))); q95.append(float(vals.quantile(0.95)))

        if variable_name in volume_cfg and (lower is None or upper is None):
            definition = get_variable_definition(variable_name)
            if definition["source"] != "original":
                raise ValueError(f"Volumetric histogram variable '{variable_name}' must be a native CFX variable.")
            if len(volume_export_files) != len(volume_histogram_volumes):
                raise ValueError(
                    "Volume data exports are required for automatic histogram bounds "
                    f"for '{variable_name}'."
                )
            column = definition["data_column"]
            for volume in volume_histogram_volumes:
                source = volume_data[volume]
                if column not in source.columns:
                    raise ValueError(f"Variable '{variable_name}' is unavailable in volume '{volume}'.")
                vals = pd.to_numeric(source[column], errors="coerce").dropna()
                if not vals.empty:
                    q05.append(float(vals.quantile(0.05))); q95.append(float(vals.quantile(0.95)))

        if lower is None:
            if not q05: raise ValueError(f"Cannot calculate automatic histogram lower bound for '{variable_name}'.")
            lower = min(q05)
        if upper is None:
            if not q95: raise ValueError(f"Cannot calculate automatic histogram upper bound for '{variable_name}'.")
            upper = max(q95)
        if lower >= upper:
            raise ValueError(f"Final histogram lower bound must be smaller than upper bound for '{variable_name}'.")
        histogram_statistics[variable_name] = {"lower": float(lower), "upper": float(upper), "divisions": count}

    section_variable_statistics = {}
    empty_import = {surface: pd.DataFrame() for surface in section_surfaces}
    for config in section_configs:
        name = config["name"]
        definition = get_variable_definition(name)
        if definition["source"] != "original":
            raise ValueError(f"Section variable '{name}' must be native CFX data.")
        lower, upper, count = config.get("lower"), config.get("upper"), config.get("number_of_contours")
        inherited = variable_statistics.get(name)
        if lower is None and inherited is not None: lower = inherited["lower"]
        if upper is None and inherited is not None: upper = inherited["upper"]
        if count is None and inherited is not None: count = inherited["number_of_contours"]
        if lower is None or upper is None:
            auto_lo, auto_hi = calculate_5th_95th_percentile_bounds(name, section_surfaces, section_data, empty_import)
            if lower is None: lower = auto_lo
            if upper is None: upper = auto_hi
        if count is None: count = DEFAULT_NUMBER_OF_CONTOURS
        if lower >= upper: raise ValueError(f"Invalid section bounds for '{name}'.")
        section_variable_statistics[name] = {
            "lower": float(lower), "upper": float(upper), "number_of_contours": int(count),
            "add_velocity_vectors": bool(config.get("add_velocity_vectors", False)),
            "create_streamlines": bool(config.get("create_streamlines", False)),
        }

    return {
        "clip_plane_z": clip_plane_z,
        "camera_pivot": camera_pivot,
        "camera_scale": camera_scale,
        "variable_statistics": variable_statistics,
        "histogram_statistics": histogram_statistics,
        "section_camera": section_camera,
        "section_variable_statistics": section_variable_statistics,
    }


def register_manual_variable_definitions(variable_names, export_data):
    """Register user-entered native CFX variables using export metadata when available."""
    for variable_name in variable_names:
        if (
            variable_name in ORIGINAL_FIGURE_VARIABLES
            or variable_name in CALCULATED_FIGURE_VARIABLES
        ):
            continue

        unit = ""
        for data in export_data.values():
            units = data.attrs.get("cfx_units", {})
            if variable_name in units:
                unit = units[variable_name]
                break

        legend_title = figure_display_name(variable_name)
        if unit:
            legend_title += f" [{unit}]"

        MANUAL_FIGURE_VARIABLES[variable_name] = {
            "cfx_variable": variable_name,
            "data_column": variable_name,
            "unit": unit,
            "legend_title": legend_title,
            "legend_format": "%4.1f",
        }


def get_variable_definition(variable_name):
    # Public/user-facing name -> CFX percentage variable created before export.
    if variable_name in ORIGINAL_FIGURE_VARIABLES:
        definition = dict(ORIGINAL_FIGURE_VARIABLES[variable_name])
        definition["source"] = "original"
        return definition

    if variable_name in CALCULATED_FIGURE_VARIABLES:
        definition = dict(CALCULATED_FIGURE_VARIABLES[variable_name])
        definition["source"] = "imported"
        definition["import_variable"] = variable_name
        return definition

    if variable_name in MANUAL_FIGURE_VARIABLES:
        definition = dict(MANUAL_FIGURE_VARIABLES[variable_name])
        definition["source"] = "original"
        definition["manual"] = True
        return definition

    # Any other user-entered variable is treated as an existing native
    # CFX-Post variable. This keeps the GUI flexible for project-specific
    # variables. Automatic bounds require that the variable is also present
    # in the corresponding export CSV.
    return {
        "source": "original",
        "cfx_variable": variable_name,
        "data_column": variable_name,
        "unit": "",
        "legend_title": figure_display_name(variable_name),
        "legend_format": "%4.1f",
        "manual": True,
    }


def format_cel_value(value, unit):
    if unit:
        return f"{value:.8g} [{unit}]"
    return f"{value:.8g}"


def _write_object_view_transform(f):
    f.write("  OBJECT VIEW TRANSFORM:\n")
    f.write("    Apply Reflection = Off\n")
    f.write("    Apply Rotation = Off\n")
    f.write("    Apply Scale = Off\n")
    f.write("    Apply Translation = Off\n")
    f.write("    Principal Axis = Z\n")
    f.write("    Reflection Plane Option = XY Plane\n")
    f.write("    Rotation Angle = 0.0 [degree]\n")
    f.write("    Rotation Axis From = 0 [m], 0 [m], 0 [m]\n")
    f.write("    Rotation Axis To = 0 [m], 0 [m], 0 [m]\n")
    f.write("    Rotation Axis Type = Principal Axis\n")
    f.write("    Scale Vector = 1 , 1 , 1\n")
    f.write("    Translation Vector = 0 [m], 0 [m], 0 [m]\n")
    f.write("    X = 0.0 [m]\n")
    f.write("    Y = 0.0 [m]\n")
    f.write("    Z = 0.0 [m]\n")
    f.write("  END\n")


def _write_contour_block(
        f,
        contour_name,
        colour_variable,
        location,
        lower_expression,
        upper_expression,
        number_of_contours,
):
    f.write(f"CONTOUR: {contour_name}\n")
    f.write("  Apply Instancing Transform = On\n")
    f.write("  Clip Contour = Off\n")
    f.write("  Colour Map = Default Colour Map\n")
    f.write("  Colour Scale = Linear\n")
    f.write(f"  Colour Variable = {colour_variable}\n")
    f.write("  Colour Variable Boundary Values = Conservative\n")
    f.write("  Constant Contour Colour = Off\n")
    f.write("  Contour Range = User Specified\n")
    f.write("  Culling Mode = No Culling\n")
    f.write("  Domain List = /DOMAIN GROUP:All Domains\n")
    f.write("  Draw Contours = On\n")
    f.write("  Font = Sans Serif\n")
    f.write("  Fringe Fill = On\n")
    f.write("  Instancing Transform = /DEFAULT INSTANCE TRANSFORM:Default Transform\n")
    f.write("  Lighting = On\n")
    f.write("  Line Colour = 0, 0, 0\n")
    f.write("  Line Colour Mode = Default\n")
    f.write("  Line Width = 1\n")
    f.write(f"  Location List = {location}\n")
    f.write(f"  Max = {upper_expression}\n")
    f.write(f"  Min = {lower_expression}\n")
    f.write(f"  Number of Contours = {number_of_contours}\n")
    f.write("  Show Numbers = Off\n")
    f.write("  Specular Lighting = On\n")
    f.write("  Surface Drawing = Smooth Shading\n")
    f.write("  Text Colour = 0, 0, 0\n")
    f.write("  Text Colour Mode = Default\n")
    f.write("  Text Height = 0.024\n")
    f.write("  Transparency = 0.0\n")
    f.write("  Use Face Values = Off\n")
    f.write("  Value List = 0,1\n")
    f.write("  Visibility = Off\n")
    _write_object_view_transform(f)
    f.write("END\n\n")


def _write_legend_block(f, legend_name, contour_name, definition):
    f.write(f"LEGEND: {legend_name}\n")
    f.write("  Colour = 0, 0, 0\n")
    f.write("  Font = Sans Serif\n")
    f.write("  Legend Aspect = 0.07\n")
    f.write(f"  Legend Format = {definition['legend_format']}\n")
    f.write("  Legend Orientation = Vertical\n")
    f.write(f"  Legend Plot = /CONTOUR:{contour_name}\n")
    f.write("  Legend Position = 0.02 , 0.15\n")
    f.write("  Legend Resolution = 256\n")
    f.write("  Legend Shading = Smooth\n")
    f.write("  Legend Size = 0.6\n")
    f.write("  Legend Ticks = 5\n")
    f.write(f"  Legend Title = {definition['legend_title']}\n")
    f.write("  Legend Title Mode = User Specified\n")
    f.write("  Legend X Justification = Left\n")
    f.write("  Legend Y Justification = Top\n")
    f.write("  Show Legend Units = Off\n")
    f.write("  Text Colour Mode = Default\n")
    f.write("  Text Height = 0.024\n")
    f.write("  Text Rotation = 0\n")
    f.write("  Visibility = Off\n")
    f.write("END\n\n")


def _write_view_block(
        f,
        figure_name,
        clip_name,
        contour_name,
        legend_name,
        pivot,
        scale,
        quaternion=(0.0, 0.0, 0.0, 1.0),
        extra_objects=None,
        visibility_objects=None,
):
    if visibility_objects is None:
        object_list = []
        if contour_name:
            object_list.append(f"/CONTOUR:{contour_name}")
        if legend_name:
            object_list.append(f"/LEGEND:{legend_name}")
        object_list.extend(extra_objects or [])
    else:
        object_list = list(visibility_objects)
        if legend_name:
            object_list.append(f"/LEGEND:{legend_name}")
    object_list.append("/WIREFRAME:Wireframe")
    visibility = ",".join(object_list)
    px, py, pz = pivot
    qx, qy, qz, qw = quaternion

    f.write(f"VIEW: {figure_name}\n")
    f.write("  Angular Coord Shift = 0.0\n")
    f.write("  Auto Center = false\n")
    f.write("  Axis Visibility = Off\n")
    f.write("  Border Visibility = false\n")
    f.write("  Camera Mode = User Specified\n")
    f.write(f"  Clip Plane = {clip_name}\n")
    f.write("  Clip Scene = 1\n")
    f.write("  Coord Transform = Cartesian\n")
    f.write("  Hide Difference Case = false\n")
    f.write("  Highlight Type = Surface Mesh\n")
    f.write("  Is A Figure = true\n")
    f.write("  Light Angle = 50, 110\n")
    f.write(f"  Object Visibility List = {visibility}\n")
    f.write("  Projection = Orthographic\n")
    f.write("  Ruler Visibility = Off\n")
    f.write("  Standard View = Isometric Y\n")
    f.write("  Valid Case = All Cases\n")
    f.write("  CAMERA:\n")
    f.write("    Option = Pivot Point and Quaternion\n")
    f.write("    Pan = 0,0\n")
    f.write(f"    Pivot Point = {px:.8g},{py:.8g},{pz:.8g}\n")
    f.write("    Rotation = -90, 0, 0\n")
    f.write(f"    Rotation Quaternion = {qx:.12g},{qy:.12g},{qz:.12g},{qw:.12g}\n")
    f.write(f"    Scale = {scale:.8g}\n")
    f.write("    Send To Viewer = True\n")
    f.write("  END\n")
    f.write("END\n\n")


def _write_velocity_vector_block(f, vector_name, location, samples):
    f.write(f"VECTOR: {vector_name}\n")
    f.write("  Apply Instancing Transform = On\n")
    f.write("  Colour = 0, 0, 0\n  Colour Map = Default Colour Map\n  Colour Mode = Constant\n")
    f.write("  Colour Scale = Linear\n  Colour Variable = Velocity\n  Colour Variable Boundary Values = Conservative\n")
    f.write("  Coord Frame = Global\n  Culling Mode = No Culling\n  Direction = X\n")
    f.write("  Domain List = /DOMAIN GROUP:All Domains\n  Draw Faces = On\n  Draw Lines = Off\n")
    f.write("  Instancing Transform = /DEFAULT INSTANCE TRANSFORM:Default Transform\n")
    f.write("  Lighting = On\n  Line Width = 1\n")
    f.write(f"  Location List = {location}\n")
    f.write("  Locator Sampling Method = Equally Spaced\n")
    f.write("  Max = 0.0 [m s^-1]\n")
    f.write(f"  Maximum Number of Items = {int(samples)}\n")
    f.write("  Min = 0.0 [m s^-1]\n  Normalized = On\n")
    f.write(f"  Number of Samples = {int(samples)}\n")
    f.write("  Projection Type = Tangential\n  Random Seed = 1\n  Range = Global\n")
    f.write("  Reduction Factor = 1.0\n  Reduction or Max Number = Max Number\n  Sample Spacing = 0.1\n")
    f.write("  Sampling Aspect Ratio = 1\n  Sampling Grid Angle = 0 [degree]\n")
    f.write("  Specular Lighting = On\n  Surface Drawing = Smooth Shading\n  Symbol = Arrow2D\n")
    f.write("  Symbol Size = 0.5\n  Transparency = 0.0\n  Variable = Velocity\n")
    f.write("  Variable Boundary Values = Conservative\n  Visibility = On\n")
    _write_object_view_transform(f)
    f.write("END\n\n")


def _write_streamline_block(f, name, location, lower_expression, upper_expression, contour_count, samples):
    f.write(f"STREAMLINE: {name}\n")
    f.write("  Absolute Tolerance = 0.0 [m]\n  Apply Instancing Transform = On\n")
    f.write("  Colour = 0.75, 0.75, 0.75\n  Colour Map = Default Colour Map\n")
    f.write("  Colour Mode = Use Plot Variable\n  Colour Scale = Linear\n")
    f.write("  Colour Variable = Velocity\n  Colour Variable Boundary Values = Conservative\n")
    f.write("  Cross Periodics = On\n  Culling Mode = No Culling\n  Domain List = All Domains\n")
    f.write("  Draw Contours = Off\n  Draw Faces = On\n  Draw Lines = Off\n  Draw Streams = On\n  Draw Symbols = Off\n")
    f.write("  Grid Tolerance = 0.01\n  Instancing Transform = /DEFAULT INSTANCE TRANSFORM:Default Transform\n")
    f.write("  Lighting = On\n  Line Width = 1\n")
    f.write(f"  Location List = {location}\n")
    f.write("  Locator Sampling Method = Equally Spaced\n")
    f.write(f"  Max = {upper_expression}\n")
    f.write(f"  Maximum Number of Items = {int(samples)}\n")
    f.write(f"  Min = {lower_expression}\n")
    f.write(f"  Number of Contours = {int(contour_count)}\n")
    f.write(f"  Number of Samples = {int(samples)}\n")
    f.write("  Number of Sides = 8\n  Range = User Specified\n  Reduction Factor = 1.0\n")
    f.write("  Reduction or Max Number = Max Number\n  Sample Spacing = 0.1\n  Sampling Aspect Ratio = 1\n")
    f.write("  Sampling Grid Angle = 0 [degree]\n  Seed Point Type = Equally Spaced Samples\n")
    f.write("  Simplify Geometry = On\n  Specular Lighting = On\n  Stream Drawing Mode = Line\n")
    f.write("  Stream Initial Direction = 0 , 0 , 0\n  Stream Size = 1.0\n  Stream Symbol = Ball\n")
    f.write("  Streamline Direction = Forward\n  Streamline Maximum Periods = 20\n")
    f.write("  Streamline Maximum Segments = 10000\n  Streamline Maximum Time = 0.0 [s]\n")
    f.write("  Streamline Periodic Time Interval = -1 [s]\n  Streamline Type = Surface Streamline\n")
    f.write("  Streamline Width = 2\n  Surface Drawing = Smooth Shading\n")
    f.write("  Surface Streamline Direction = Forward and Backward\n  Symbol Size = 1.0\n")
    f.write("  Symbol Start Time = 10.0 [s]\n  Symbol Stop Time = -10.0 [s]\n  Symbol Time Interval = 1.0 [s]\n")
    f.write("  Tolerance Mode = Grid Relative\n  Transparency = 0.0\n  Variable = Velocity\n")
    f.write("  Variable Boundary Values = Conservative\n  Visibility = On\n")
    _write_object_view_transform(f)
    f.write("END\n\n")


def _write_histogram_block(f, location_name, variable_name, statistics, *, location_reference, case_name="", is_volume=False):
    display_name = figure_display_name(variable_name)
    kind = "volume" if is_volume else "surface"
    chart_name = f"{display_name} histogram in {location_name}" if is_volume else f"{display_name} histogram at {location_name}"
    definition = get_variable_definition(variable_name)

    if definition["source"] == "original":
        histogram_variable = definition["cfx_variable"]
    else:
        imported_surface = f"Imported Thermal Comfort Results {location_name}"
        histogram_variable = f"{definition['import_variable']} on {imported_surface}"
        location_reference = f"/USER SURFACE:{imported_surface}"

    hs = statistics["histogram_statistics"][variable_name]
    lower, upper, division_count = hs["lower"], hs["upper"], hs["divisions"]
    divisions = histogram_divisions(lower, upper, division_count)

    f.write(f"CHART: {chart_name}\n")
    f.write("  Chart Axes Font = Tahoma, 10, False, False, False, False\n")
    f.write("  Chart Axes Titles Font = Tahoma, 10, True, False, False, False\n")
    f.write("  Chart Grid Line Width = 1\n  Chart Horizontal Grid = On\n  Chart Legend = On\n")
    f.write("  Chart Legend Font = Tahoma, 8, False, False, False, False\n")
    f.write("  Chart Legend Inside = Outside Chart\n  Chart Legend Justification = Center\n  Chart Legend Position = Bottom\n")
    f.write("  Chart Legend Width Height = 0.2 , 0.4\n  Chart Legend X Justification = Right\n")
    f.write("  Chart Legend XY Position = 0.73 , 0.275\n  Chart Legend Y Justification = Center\n")
    f.write("  Chart Line Width = 2\n  Chart Lines Order = Series 1,Chart Line 1\n")
    f.write("  Chart Minor Grid = Off\n  Chart Minor Grid Line Width = 1\n  Chart Symbol Size = 4\n")
    f.write(f"  Chart Title = {display_name} Histogram in {location_name}\n")
    f.write("  Chart Title Font = Tahoma, 12, True, False, False, False\n  Chart Title Visibility = On\n")
    f.write("  Chart Type = Histogram\n  Chart Vertical Grid = On\n")
    f.write("  Chart X Axis Automatic Number Formatting = Off\n  Chart X Axis Label = X Axis <units>\n")
    f.write(f"  Chart X Axis Number Format = {definition['legend_format']}\n")
    f.write("  Chart Y Axis Automatic Number Formatting = On\n  Chart Y Axis Label = Y Axis <units>\n")
    f.write("  Chart Y Axis Number Format = %10.3e\n")
    f.write(f"  Default Chart X Variable = {histogram_variable}\n")
    f.write("  Default Chart Y Variable = Pressure\n  Default Difference Line Calculation = From Points\n")
    f.write("  Default Histogram Y Axis Weighting = Geometrical\n  Default Time Chart Variable = Pressure\n")
    f.write("  Default Time Chart X Expression = Time\n  Default Time Variable Absolute Value = Off\n")
    f.write("  Default Time Variable Boundary Values = Conservative\n  Default X Variable Absolute Value = Off\n")
    f.write("  Default X Variable Boundary Values = Conservative\n  Default Y Variable Absolute Value = Off\n")
    f.write("  Default Y Variable Boundary Values = Conservative\n  FFT Full Input Range = On\n")
    f.write("  FFT Max = 0.0\n  FFT Min = 0.0\n  FFT Subtract Mean = Off\n  FFT Window Type = Hanning\n")
    f.write("  FFT X Function = Frequency\n  FFT Y Function = Power Spectral Density\n")
    f.write("  Histogram Automatic Divisions = Automatic\n")
    f.write(f"  Histogram Divisions = {divisions}\n  Histogram Divisions Count = {division_count}\n")
    f.write("  Histogram Y Axis Value = Percentage\n  Is FFT Chart = Off\n")
    f.write(f"  Max X = {upper:.12g}\n  Max Y = 1.0\n  Min X = {lower:.12g}\n  Min Y = -1.0\n")
    f.write("  Use Data For X Axis Labels = On\n  Use Data For Y Axis Labels = On\n  X Axis Automatic Range = Off\n")
    f.write("  X Axis Inverted = Off\n  X Axis Logarithmic Scaling = Off\n  Y Axis Automatic Range = On\n")
    f.write("  Y Axis Inverted = Off\n  Y Axis Logarithmic Scaling = Off\n")
    f.write("  CHART SERIES: Series 1\n")
    f.write("    Chart Line Custom Data Selection = Off\n    Chart Line Filename = \n    Chart Series Type = Regular\n")
    f.write("    Chart X Variable = Air.Mass Fraction\n    Chart Y Variable = Air.Mass Fraction\n")
    f.write("    Histogram Y Axis Weighting = None\n")
    f.write(f"    Location = {location_reference}\n")
    f.write("    Monitor Data Filename = \n    Monitor Data Source = Case\n")
    f.write("    Monitor Data X Variable Absolute Value = Off\n    Monitor Data Y Variable Absolute Value = Off\n")
    if case_name:
        f.write(f"    Operating Point Data Case = {case_name}\n")
    f.write("    Operating Point Data Filename = \n    Operating Point Data Source = File\n")
    f.write("    Series Name = Series 1\n    Time Chart Expression = Time\n    Time Chart Type = Point\n")
    f.write("    Time Chart Variable = Air.Mass Fraction\n    Time Chart X Expression = Time\n")
    f.write("    Time Variable Absolute Value = Off\n    Time Variable Boundary Values = Conservative\n")
    f.write("    X Variable Absolute Value = Off\n    X Variable Boundary Values = Conservative\n")
    f.write("    Y Variable Absolute Value = Off\n    Y Variable Boundary Values = Conservative\n")
    f.write("    CHART LINE: Chart Line 1\n")
    f.write("      Auto Chart Line Colour = On\n      Auto Chart Symbol Colour = On\n      Chart FFT Line Type = Bars\n")
    f.write("      Chart Line Colour = 1.0, 0.0, 0.0\n      Chart Line Style = Automatic\n")
    f.write("      Chart Line Type = Lines\n      Chart Line Visibility = On\n")
    f.write("      Chart Symbol Colour = 0.0, 1.0, 0.0\n      Chart Symbol Style = Automatic\n")
    f.write("      Fill Area = On\n      Fill Area Options = Automatic\n      Is Valid = True\n")
    if case_name:
        f.write(f"      Case Name = {case_name}\n")
    f.write("      Line Name = Series 1\n      Use Automatic Line Naming = On\n    END\n  END\n")
    f.write("  OBJECT REPORT OPTIONS:\n    Report Caption = \n  END\nEND\n\n")


def _write_average_table(f, surfaces, volumes, figure_variables, table_name="Average conditions"):
    """Write one CFX table containing optional surface and volume average blocks."""
    surfaces = list(surfaces or [])
    volumes = list(volumes or [])
    figure_variables = list(figure_variables or [])
    f.write(f"TABLE: {table_name}\n")
    f.write("  Export Table Only = True\n")
    f.write("  Table Exists = True\n")
    f.write("  Table Export Format = State\n")
    f.write("  Table Export HTML Border Width = 1\n")
    f.write("  Table Export HTML Caption = \n")
    f.write("  Table Export HTML Caption Position = Bottom\n")
    f.write("  Table Export HTML Cell Padding = 5\n")
    f.write("  Table Export HTML Cell Spacing = 1\n")
    f.write("  Table Export HTML Title = \n")
    f.write("  Table Export Lines = All\n")
    f.write("  Table Export Separator = Tab\n")
    f.write("  Table Export Trailing Separators = True\n")
    f.write("  TABLE CELLS: \n")

    def write_text_cell(column, row, text, fmt="%10.3e", bold=True):
        f.write(
            f'    {column}{row} = "{text}", False, False, False, Left, True, 0, '
            f'Font Name, 1|1, {fmt}, {"True" if bold else "False"}, ffffff, 000000, True\n'
        )

    def write_value_cell(column, row, expression):
        f.write(
            f'    {column}{row} = "{expression}", False, False, False, Left, True, 0, '
            'Font Name, 1|1, %4.1f, False, ffffff, 000000, True\n'
        )

    next_row = 1
    if surfaces:
        write_text_cell("A", next_row, "Surface Averages")
        header_row = next_row + 1
        data_start = header_row + 1
        for row_offset, surface in enumerate(surfaces):
            write_text_cell("A", data_start + row_offset, surface)
        for variable_index, variable_name in enumerate(figure_variables, start=1):
            column = table_column_letter(variable_index)
            definition = get_variable_definition(variable_name)
            write_text_cell(column, header_row, definition["legend_title"])
            for row_offset, surface in enumerate(surfaces):
                row = data_start + row_offset
                if definition["source"] == "original":
                    expression = f"=areaAve({definition['cfx_variable']})@{surface}"
                    if variable_name in ("Temperature", "Radiation Temperature"):
                        expression += " -273.15[K]"
                else:
                    imported_surface = f"Imported Thermal Comfort Results {surface}"
                    qualified = f"{definition['import_variable']} on {imported_surface}"
                    expression = f"=areaAve({qualified})@{imported_surface}"
                write_value_cell(column, row, expression)
        next_row = data_start + len(surfaces) + 1  # one blank row between blocks

    if volumes:
        volume_variables = [
            name for name in figure_variables
            if get_variable_definition(name)["source"] == "original"
        ]
        if volume_variables:
            write_text_cell("A", next_row, "Volume Averages")
            header_row = next_row + 1
            data_start = header_row + 1
            for row_offset, volume in enumerate(volumes):
                write_text_cell("A", data_start + row_offset, volume)
            for variable_index, variable_name in enumerate(volume_variables, start=1):
                column = table_column_letter(variable_index)
                definition = get_variable_definition(variable_name)
                write_text_cell(column, header_row, definition["legend_title"])
                for row_offset, volume in enumerate(volumes):
                    row = data_start + row_offset
                    expression = f"=volumeAve({definition['cfx_variable']})@{volume}"
                    if variable_name in ("Temperature", "Radiation Temperature"):
                        expression += " -273.15[K]"
                    write_value_cell(column, row, expression)

    f.write("  END\n")
    f.write("END\n\n")


def create_figures_session_file(
        figures_directory,
        surfaces,
        figure_variables,
        histogram_surfaces,
        histogram_variables,
        statistics,
        section_surfaces=None,
        section_variables=None,
        create_average_table=True,
        table_surfaces=None,
        table_volumes=None,
        table_variables=None,
        average_table_name="Average conditions",
        created_variables=None,
        create_plan_contours=True,
        create_plan_streamlines=False,
        vector_samples=100,
        streamline_samples=100,
        volume_histogram_volumes=None,
        volume_histogram_variables=None,
        surface_locations=None,
        volume_locations=None,
        case_name="",
):
    section_surfaces = list(section_surfaces or [])
    section_variables = list(section_variables or [])
    table_surfaces = list(table_surfaces or [])
    table_volumes = list(table_volumes or [])
    table_variables = list(table_variables or [])
    volume_histogram_volumes = list(volume_histogram_volumes or [])
    volume_histogram_variables = list(volume_histogram_variables or [])
    created_variables = [item for item in (created_variables or []) if bool(_created_variable_field(item, "enabled", True))]
    surface_locations = dict(surface_locations or {})
    volume_locations = dict(volume_locations or {})

    session_file = figures_directory / "create_figures_session.cse"
    completion_file = figures_directory / "figures_creation_complete.txt"
    pivot = statistics["camera_pivot"]
    camera_scale = statistics["camera_scale"]

    with open(session_file, "w", newline="") as f:
        f.write("# ================================================================\n")
        f.write("# AUTOMATIC CONTOUR / SECTION / HISTOGRAM CREATION\n")
        f.write("# CFX-Post 23.2\n")
        f.write("# ================================================================\n\n")
        f.write("COMMAND FILE:\n  CFX Post Version = 23.2\nEND\n\n")

        f.write("LIBRARY:\n  CEL:\n    EXPRESSIONS:\n")
        f.write("      Relative Humidity percentage = Relative Humidity*100\n")
        for item in created_variables:
            expr_name = str(_created_variable_field(item, "expression_name")).strip()
            expr = str(_created_variable_field(item, "expression")).strip()
            if expr_name and expr:
                f.write(f"      {expr_name} = {expr}\n")
        for variable_name in figure_variables:
            if variable_name not in statistics["variable_statistics"]:
                continue
            expression = sanitize_expression_name(variable_name)
            definition = get_variable_definition(variable_name)
            unit = definition["unit"] if definition["source"] == "original" else ""
            stats = statistics["variable_statistics"][variable_name]
            f.write(f"      {expression} lower bound = {format_cel_value(stats['lower'], unit)}\n")
            f.write(f"      {expression} upper bound = {format_cel_value(stats['upper'], unit)}\n")
        for item in section_variables:
            variable_name = item["name"]
            expression = sanitize_expression_name(variable_name)
            definition = get_variable_definition(variable_name)
            stats = statistics["section_variable_statistics"][variable_name]
            f.write(f"      {expression} Sections lower bound = {format_cel_value(stats['lower'], definition['unit'])}\n")
            f.write(f"      {expression} Sections upper bound = {format_cel_value(stats['upper'], definition['unit'])}\n")
        f.write("    END\n  END\nEND\n\n")

        f.write("USER SCALAR VARIABLE: Relative Humidity Percentage\n")
        f.write("  Boundary Values = Conservative\n  Calculate Global Range = On\n  Component Index = 1\n")
        f.write("  Expression = Relative Humidity percentage\n  Recipe = Expression\n")
        f.write("  Variable to Copy = Pressure\n  Variable to Gradient = Pressure\nEND\n\n")
        for item in created_variables:
            name = str(_created_variable_field(item, "name")).strip()
            expr_name = str(_created_variable_field(item, "expression_name")).strip()
            expr = str(_created_variable_field(item, "expression")).strip()
            if not name or not expr_name or not expr:
                continue
            f.write(f"USER SCALAR VARIABLE: {name}\n")
            f.write("  Boundary Values = Conservative\n  Calculate Global Range = On\n  Component Index = 1\n")
            f.write(f"  Expression = {expr_name}\n  Recipe = Expression\n")
            f.write("  Variable to Copy = Pressure\n  Variable to Gradient = Pressure\nEND\n\n")

        # Clip planes for normal/top surfaces are needed only by top-view
        # contour/streamline figures.  Histogram/table-only surfaces should
        # not create unrelated clip planes.
        if create_plan_contours:
            for surface in surfaces:
                if surface not in statistics["clip_plane_z"]:
                    continue
                clip_z = statistics["clip_plane_z"][surface]
                f.write(f"CLIP PLANE: Clip Plane {surface}\n")
                f.write("  Flip Normal = Off\n  Normal = 1 , 0 , 0\n  Option = XY Plane\n")
                f.write("  Point = 0 [m], 0 [m], 0 [m]\n  Point 1 = 0 [m], 0 [m], 0 [m]\n")
                f.write("  Point 2 = 1 [m], 0 [m], 0 [m]\n  Point 3 = 0 [m], 1 [m], 0 [m]\n")
                f.write(f"  X = 0.0 [m]\n  Y = 0.0 [m]\n  Z = {clip_z:.8g} [m]\nEND\n\n")

        # Per-section clip planes and cameras.
        for section in section_surfaces:
            camera = statistics["section_camera"][section]
            nx, ny, nz = camera["normal"]
            px, py, pz = camera["clip_point"]
            rx, ry, rz = camera["right"]
            ux, uy, uz = camera["up"]
            f.write(f"CLIP PLANE: Clip Plane Section {section}\n")
            f.write("  Flip Normal = Off\n")
            f.write(f"  Normal = {nx:.12g} , {ny:.12g} , {nz:.12g}\n")
            f.write("  Option = Point and Normal\n")
            f.write(f"  Point = {px:.12g} [m], {py:.12g} [m], {pz:.12g} [m]\n")
            f.write(f"  Point 1 = {px:.12g} [m], {py:.12g} [m], {pz:.12g} [m]\n")
            f.write(f"  Point 2 = {px+rx:.12g} [m], {py+ry:.12g} [m], {pz+rz:.12g} [m]\n")
            f.write(f"  Point 3 = {px+ux:.12g} [m], {py+uy:.12g} [m], {pz+uz:.12g} [m]\n")
            f.write(f"  X = {px:.12g} [m]\n  Y = {py:.12g} [m]\n  Z = {pz:.12g} [m]\nEND\n\n")

        # Normal/top-view contour figures and optional independent velocity streamlines.
        if create_plan_contours:
            for surface_offset, surface in enumerate(surfaces):
                figure_number = FIRST_FIGURE_NUMBER + surface_offset
                imported_surface = f"Imported Thermal Comfort Results {surface}"
                suffix_index = 0
                velocity_contour_name = None
                velocity_legend_name = "Legend Velocity"
                for variable_name in figure_variables:
                    if suffix_index >= 26:
                        raise ValueError("A maximum of 26 top-view figures per surface is supported.")
                    letter = chr(ord("a") + suffix_index); suffix_index += 1
                    display_name = figure_display_name(variable_name)
                    figure_name = f"Figure {figure_number:02d}{letter} {display_name} contours at {surface}"
                    contour_name = f"{display_name} at {surface}"
                    legend_name = f"Legend {display_name}"
                    definition = get_variable_definition(variable_name)
                    expression = sanitize_expression_name(variable_name)
                    if definition["source"] == "original":
                        location = surface
                        colour_variable = definition["cfx_variable"]
                    else:
                        location = imported_surface
                        colour_variable = f"{definition['import_variable']} on {imported_surface}"
                    count = statistics["variable_statistics"][variable_name]["number_of_contours"]
                    _write_contour_block(f, contour_name, colour_variable, location,
                                         f"{expression} lower bound", f"{expression} upper bound", count)
                    if surface_offset == 0:
                        _write_legend_block(f, legend_name, contour_name, definition)
                    if variable_name == "Velocity":
                        velocity_contour_name = contour_name
                    _write_view_block(f, figure_name, f"Clip Plane {surface}", contour_name, legend_name,
                                      pivot, camera_scale)

                if create_plan_streamlines and "Velocity" in figure_variables:
                    if suffix_index >= 26:
                        raise ValueError("A maximum of 26 top-view figures per surface is supported.")
                    letter = chr(ord("a") + suffix_index)
                    stream_name = f"Velocity Streamlines {surface}"
                    velocity_stats = statistics["variable_statistics"]["Velocity"]
                    velocity_expr = sanitize_expression_name("Velocity")
                    location = surface_locations.get(surface, surface)
                    _write_streamline_block(f, stream_name, location,
                                            f"{velocity_expr} lower bound", f"{velocity_expr} upper bound",
                                            velocity_stats["number_of_contours"], streamline_samples)
                    figure_name = f"Figure {figure_number:02d}{letter} Velocity streamlines at {surface}"
                    _write_view_block(
                        f, figure_name, f"Clip Plane {surface}", None, velocity_legend_name,
                        pivot, camera_scale,
                        visibility_objects=[f"/STREAMLINE:{stream_name}"],
                    )

        # Section contours, one vector object per section, optional independent streamlines.
        section_base_number = FIRST_FIGURE_NUMBER + (len(surfaces) if create_plan_contours else 0)
        for section_offset, section in enumerate(section_surfaces):
            figure_number = section_base_number + section_offset
            camera = statistics["section_camera"][section]
            section_location = surface_locations.get(section, section)
            needs_vectors = any(
                statistics["section_variable_statistics"][item["name"]]["add_velocity_vectors"]
                for item in section_variables
            )
            vector_name = None
            if needs_vectors:
                vector_name = f"Velocity vectors on {section}"
                _write_velocity_vector_block(f, vector_name, section_location, vector_samples)

            suffix_index = 0
            for item in section_variables:
                if suffix_index >= 26:
                    raise ValueError("A maximum of 26 section figures per section is supported.")
                variable_name = item["name"]
                letter = chr(ord("a") + suffix_index); suffix_index += 1
                display_name = figure_display_name(variable_name)
                contour_name = f"{display_name} Section at {section}"
                legend_name = f"Legend {display_name} Sections"
                figure_name = f"Figure {figure_number:02d}{letter} {display_name} section contours at {section}"
                definition = get_variable_definition(variable_name)
                expression = sanitize_expression_name(variable_name)
                stats = statistics["section_variable_statistics"][variable_name]
                _write_contour_block(f, contour_name, definition["cfx_variable"], section,
                                     f"{expression} Sections lower bound", f"{expression} Sections upper bound",
                                     stats["number_of_contours"])
                if section_offset == 0:
                    _write_legend_block(f, legend_name, contour_name, definition)
                extras = [f"/VECTOR:{vector_name}"] if stats["add_velocity_vectors"] and vector_name else []
                _write_view_block(f, figure_name, f"Clip Plane Section {section}", contour_name, legend_name,
                                  camera["pivot"], camera["scale"], quaternion=camera["quaternion"], extra_objects=extras)

            velocity_cfg = next((i for i in section_variables if i["name"] == "Velocity"), None)
            if velocity_cfg and statistics["section_variable_statistics"]["Velocity"].get("create_streamlines"):
                if suffix_index >= 26:
                    raise ValueError("A maximum of 26 section figures per section is supported.")
                letter = chr(ord("a") + suffix_index)
                stream_name = f"Velocity Streamlines {section}"
                stats = statistics["section_variable_statistics"]["Velocity"]
                expr = sanitize_expression_name("Velocity")
                _write_streamline_block(f, stream_name, section_location,
                                        f"{expr} Sections lower bound", f"{expr} Sections upper bound",
                                        stats["number_of_contours"], streamline_samples)
                figure_name = f"Figure {figure_number:02d}{letter} Velocity section streamlines at {section}"
                _write_view_block(
                    f, figure_name, f"Clip Plane Section {section}", None, "Legend Velocity Sections",
                    camera["pivot"], camera["scale"], quaternion=camera["quaternion"],
                    visibility_objects=[f"/STREAMLINE:{stream_name}"],
                )

        # Surface histograms.
        for surface in histogram_surfaces:
            for variable_name in histogram_variables:
                definition = get_variable_definition(variable_name)
                if definition["source"] == "original":
                    location_ref = surface_locations.get(surface, f"/SURFACE GROUP:{surface}")
                else:
                    location_ref = f"/USER SURFACE:Imported Thermal Comfort Results {surface}"
                _write_histogram_block(f, surface, variable_name, statistics,
                                       location_reference=location_ref, case_name=case_name, is_volume=False)

        # Volumetric histograms.
        for volume in volume_histogram_volumes:
            location_ref = volume_locations.get(volume, volume)
            for variable_name in volume_histogram_variables:
                _write_histogram_block(f, volume, variable_name, statistics,
                                       location_reference=location_ref, case_name=case_name, is_volume=True)

        if create_average_table and (table_surfaces or table_volumes) and table_variables:
            _write_average_table(
                f, table_surfaces, table_volumes, table_variables, average_table_name
            )

        f.write("# Figure-creation completion marker\n")
        f.write(f'!open(MARKER, ">{completion_file.as_posix()}") or die "Cannot create figure completion marker: $!";\n')
        f.write('!print MARKER "Figure creation is successful\\n";\n!close(MARKER);\n')

    return session_file


def create_print_figures_session_file(
        figures_directory,
        surfaces,
        figure_variables,
        histogram_surfaces,
        histogram_variables,
        section_surfaces=None,
        section_variables=None,
        *,
        create_plan_streamlines=False,
        volume_histogram_volumes=None,
        volume_histogram_variables=None,
        create_average_table=False,
        average_table_name="Average conditions",
):
    section_surfaces = list(section_surfaces or [])
    section_variables = list(section_variables or [])
    volume_histogram_volumes = list(volume_histogram_volumes or [])
    volume_histogram_variables = list(volume_histogram_variables or [])
    session_file = figures_directory / "print_figures_session.cse"
    completion_file = figures_directory / "figures_printing_complete.txt"

    figure_names = []
    for surface_offset, surface in enumerate(surfaces):
        figure_number = FIRST_FIGURE_NUMBER + surface_offset
        suffix = 0
        for variable_name in figure_variables:
            letter = chr(ord("a") + suffix); suffix += 1
            figure_names.append(f"Figure {figure_number:02d}{letter} {figure_display_name(variable_name)} contours at {surface}")
        if create_plan_streamlines and "Velocity" in figure_variables:
            letter = chr(ord("a") + suffix)
            figure_names.append(f"Figure {figure_number:02d}{letter} Velocity streamlines at {surface}")

    section_base = FIRST_FIGURE_NUMBER + len(surfaces)
    for section_offset, section in enumerate(section_surfaces):
        figure_number = section_base + section_offset
        suffix = 0
        for item in section_variables:
            letter = chr(ord("a") + suffix); suffix += 1
            figure_names.append(f"Figure {figure_number:02d}{letter} {figure_display_name(item['name'])} section contours at {section}")
        velocity_cfg = next((i for i in section_variables if i["name"] == "Velocity"), None)
        if velocity_cfg and velocity_cfg.get("create_streamlines"):
            letter = chr(ord("a") + suffix)
            figure_names.append(f"Figure {figure_number:02d}{letter} Velocity section streamlines at {section}")

    histogram_names = [
        f"{figure_display_name(v)} histogram at {s}"
        for s in histogram_surfaces for v in histogram_variables
    ]
    volume_histogram_names = [
        f"{figure_display_name(v)} histogram in {vol}"
        for vol in volume_histogram_volumes for v in volume_histogram_variables
    ]
    all_histograms = histogram_names + volume_histogram_names

    with open(session_file, "w", newline="") as f:
        f.write("# ================================================================\n")
        f.write("# FIGURE / HISTOGRAM PRINT SESSION - CREATED ONLY, NOT AUTO-EXECUTED\n")
        f.write("# CFX-Post 23.2\n# ================================================================\n\n")
        f.write("COMMAND FILE:\n  CFX Post Version = 23.2\nEND\n\n")
        figure_path = str(figures_directory).replace("\\", "/")
        f.write(f'!$file_path = "{figure_path}";\n\n')
        f.write(f"!$no_figures = {len(figure_names)};\n")
        for i, name in enumerate(figure_names, 1):
            f.write(f'!$figure[{i}] = "{name}";\n')
        f.write("\n")
        if figure_names:
            f.write("!for($a=1;$a<=$no_figures;$a++){\n")
            f.write(">setViewportView cmd=set, view=/VIEW:$figure[$a], viewport=1\n")
            f.write("HARDCOPY:\n")
            f.write("  Antialiasing = On\n")
            f.write("  Hardcopy Filename = $file_path/$figure[$a].png\n")
            f.write("  Hardcopy Format = png\n")
            f.write("  Hardcopy Tolerance = 0.0001\n")
            f.write(f"  Image Height = {FIGURE_IMAGE_HEIGHT}\n")
            f.write("  Image Scale = 100\n")
            f.write(f"  Image Width = {FIGURE_IMAGE_WIDTH}\n")
            f.write("  JPEG Image Quality = 80\n")
            f.write("  Use Screen Size = Off\n")
            f.write("  White Background = On\n")
            f.write("END\n")
            f.write(">print\n!}\n\n")

        f.write(f"!$no_charts = {len(all_histograms)};\n")
        for i, name in enumerate(all_histograms, 1):
            f.write(f'!$chart[{i}] = "{name}";\n')
        f.write("\n")
        if all_histograms:
            f.write("!for($a=1;$a<=$no_charts;$a++){\n")
            f.write(f'>chart print, Chart Name = /CHART:$chart[$a], filename = $file_path/$chart[$a].png, x size={FIGURE_IMAGE_WIDTH}, y size={FIGURE_IMAGE_HEIGHT}, format=png, factor=1.95319\n')
            f.write("!}\n\n")

        if create_average_table:
            safe_table = re.sub(r"[^A-Za-z0-9]+", "_", str(average_table_name).strip()).strip("_").lower() or "average_conditions"
            table_file = f"{figure_path}/table_{safe_table}.csv"
            f.write(f"TABLE:{average_table_name}\n")
            f.write("  Export Table Only = True\n")
            f.write("  Table Export HTML Title =\n")
            f.write("  Table Export HTML Caption Position = Bottom\n")
            f.write("  Table Export HTML Caption =\n")
            f.write("  Table Export HTML Border Width = 1\n")
            f.write("  Table Export HTML Cell Padding = 5\n")
            f.write("  Table Export HTML Cell Spacing = 1\n")
            f.write("  Table Export Lines = All\n")
            f.write("  Table Export Trailing Separators = True\n")
            f.write("  Table Export Separator = Tab\n")
            f.write("END\n")
            f.write(f">table save={table_file}, name={average_table_name}\n\n")

        f.write("# Printing completion marker\n")
        f.write(f'!open(MARKER, ">{completion_file.as_posix()}") or die "Cannot create printing completion marker: $!";\n')
        f.write('!print MARKER "Figure printing is successful\\n";\n!close(MARKER);\n')
    return session_file


def main():

    total_start = time.time()

    print("\n")
    print("=" * 70)
    print("AUTOMATED CFX-POST THERMAL COMFORT WORKFLOW")
    print("=" * 70)

    for directory in (
        INPUT_DIRECTORY,
        OUTPUT_DIRECTORY,
        FIGURES_DIRECTORY
    ):
        directory.mkdir(parents=True, exist_ok=True)

    if not SURFACES:
        raise ValueError(
            "SURFACES list is empty."
        )

    # --------------------------------------------------------
    # Validate duplicate surfaces
    # --------------------------------------------------------

    duplicates = sorted({
        s for s in SURFACES
        if SURFACES.count(s) > 1
    })

    if duplicates:

        raise ValueError(
            "Duplicate surface names detected:\n"
            + "\n".join(
                f"  - {s}"
                for s in duplicates
            )
        )

    # --------------------------------------------------------
    # Find existing Command Editor
    # --------------------------------------------------------

    command_editor = find_command_editor()

    print(
        f"\nCFX-Post Command Editor found: "
        f"HWND {command_editor}"
    )

    # --------------------------------------------------------
    # STEP 3
    # Create export session
    # --------------------------------------------------------

    export_session = (
        create_export_session_file(
            INPUT_DIRECTORY,
            SURFACES
        )
    )

    expected_exports = [
        INPUT_DIRECTORY /
        f"export_{surface}.csv"
        for surface in SURFACES
    ]

    # --------------------------------------------------------
    # STEP 4
    # Execute export session
    # --------------------------------------------------------

    export_completion_file = (
        INPUT_DIRECTORY /
        "export_complete.txt"
    )

    execute_cfx_session(
        export_session,
        completion_file=export_completion_file,
        completion_text="Export is successful",
        completion_description="CFX-Post export"
    )

    # --------------------------------------------------------
    # STEP 5
    # Thermal comfort calculations
    # --------------------------------------------------------

    # Process exactly the files requested in SURFACES; old exports are ignored.
    csv_files = expected_exports
    missing = [file_path for file_path in csv_files if not file_path.exists()]

    if missing:
        raise RuntimeError(
            "Some expected CFX-Post export files are missing:\n"
            + "\n".join(str(file_path) for file_path in missing)
        )

    print("\n")
    print("=" * 70)
    print("THERMAL COMFORT CALCULATIONS")
    print("=" * 70)

    print(
        f"Found {len(csv_files)} CSV files."
    )

    successful_outputs = []

    for input_file in csv_files:

        output_filename = re.sub(
            "export",
            "import",
            input_file.name,
            flags=re.IGNORECASE
        )

        output_file = (
            OUTPUT_DIRECTORY /
            output_filename
        )

        try:

            process_file(
                input_file,
                output_file
            )

            successful_outputs.append(
                output_file
            )

        except Exception as e:

            print(
                f"\nERROR processing "
                f"{input_file.name}: {e}"
            )

            raise

    print("\n")
    print("=" * 70)
    print("ALL THERMAL COMFORT CALCULATIONS FINISHED")
    print("=" * 70)

    # --------------------------------------------------------
    # STEP 6
    # Create import session
    # --------------------------------------------------------

    import_session = (
        create_import_session_file(
            OUTPUT_DIRECTORY,
            successful_outputs
        )
    )

    # --------------------------------------------------------
    # STEP 7
    # Execute import session
    # --------------------------------------------------------
    
    import_completion_file = (
        OUTPUT_DIRECTORY /
        "import_complete.txt"
    )
    
    execute_cfx_session(
        import_session,
        completion_file=import_completion_file
    )

    # --------------------------------------------------------
    # STEP 8
    # Create contour / histogram session
    # --------------------------------------------------------

    figure_configs = parse_variable_entries(
        FIGURE_VARIABLES,
        "FIGURE_VARIABLES",
        "number_of_contours",
        DEFAULT_NUMBER_OF_CONTOURS,
        2
    )
    histogram_configs = parse_variable_entries(
        HISTOGRAM_VARIABLES,
        "HISTOGRAM_VARIABLES",
        "divisions",
        DEFAULT_NUMBER_OF_HISTOGRAM_DIVISIONS,
        1
    )

    figure_variable_names = [item["name"] for item in figure_configs]
    histogram_variable_names = [item["name"] for item in histogram_configs]

    if not figure_variable_names:
        raise ValueError("FIGURE_VARIABLES list is empty.")

    if FIRST_FIGURE_NUMBER < 1:
        raise ValueError("FIRST_FIGURE_NUMBER must be at least 1.")

    if len(figure_variable_names) > 26:
        raise ValueError(
            "A maximum of 26 figure variables is supported "
            "because figure suffixes use a-z."
        )

    unknown_histogram_surfaces = [
        surface for surface in HISTOGRAM_SURFACES
        if surface not in SURFACES
    ]
    if unknown_histogram_surfaces:
        raise ValueError(
            "HISTOGRAM_SURFACES contains surfaces not present in SURFACES:\n"
            + "\n".join(f"  - {s}" for s in unknown_histogram_surfaces)
        )

    # Histograms are optional. If either list is empty, none are created.
    active_histogram_surfaces = (
        HISTOGRAM_SURFACES if histogram_variable_names else []
    )
    if not active_histogram_surfaces:
        histogram_variable_names = []
        histogram_configs = []

    figure_statistics = collect_plot_statistics(
        SURFACES,
        expected_exports,
        successful_outputs,
        figure_configs,
        active_histogram_surfaces,
        histogram_configs
    )

    create_figures_session = (
        create_figures_session_file(
            FIGURES_DIRECTORY,
            SURFACES,
            figure_variable_names,
            active_histogram_surfaces,
            histogram_variable_names,
            figure_statistics
        )
    )

    # --------------------------------------------------------
    # STEP 9
    # Execute contour / histogram session
    # --------------------------------------------------------

    figures_completion_file = (
        FIGURES_DIRECTORY /
        "figures_creation_complete.txt"
    )

    execute_cfx_session(
        create_figures_session,
        completion_file=figures_completion_file,
        completion_text="Figure creation is successful",
        completion_description="CFX-Post figure creation"
    )

    # --------------------------------------------------------
    # STEP 10
    # Create print session - DO NOT EXECUTE
    # --------------------------------------------------------

    print_figures_session = (
        create_print_figures_session_file(
            FIGURES_DIRECTORY,
            SURFACES,
            figure_variable_names,
            active_histogram_surfaces,
            histogram_variable_names
        )
    )

    # --------------------------------------------------------
    # FINISHED
    # --------------------------------------------------------

    print("\n")
    print("=" * 70)
    print("FULL AUTOMATED WORKFLOW FINISHED")
    print("=" * 70)

    print(
        f"Total execution time: "
        f"{time.time() - total_start:.1f} s"
    )

    print(
        "\nCFX-Post remains open with the imported "
        "thermal comfort results."
    )


