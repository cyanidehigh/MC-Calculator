import json
import math
import re
import sys
import heapq
import tkinter as tk
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk


ROOT = Path(__file__).resolve().parent
PROFILE_ROOT = ROOT / "profile"
APP_VERSION = "0.5.3"
LOGO_PATHS = [
    ROOT / "assets" / "logo.png",
    ROOT / "logo.png",
    ROOT / "assets" / "logo.gif",
    ROOT / "logo.gif",
]

COLORS = {
    "bg": "#101317",
    "panel": "#181d22",
    "panel_2": "#202731",
    "field": "#0c0f12",
    "line": "#4b5665",
    "text": "#eef3f7",
    "muted": "#aab5c0",
    "accent": "#4fb7a2",
    "accent_dark": "#233c3a",
    "gold": "#e0b457",
    "green": "#69d181",
    "red": "#f06c75",
    "danger": "#8d3f46",
    "select": "#2b5e57",
    "system_field_text": "#eef3f7",
    "system_field_bg": "#0c0f12",
}

UNIT_OPTIONS = ("item", "B", "mB")
FLUID_UNITS = {"B", "mB"}


def make_id(prefix):
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"


def safe_name(value):
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", str(value or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).rstrip(".")
    return (cleaned or "unnamed")[:80]


def amount_text(value):
    rounded = round(float(value), 4)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:g}"


def compact_amount_text(value):
    number = float(value)
    absolute = abs(number)
    units = [
        (1_000_000_000_000, "T"),
        (1_000_000_000, "B"),
        (1_000_000, "M"),
        (1_000, "k"),
    ]

    for threshold, suffix in units:
        if absolute >= threshold:
            scaled = number / threshold
            return f"{scaled:.3f}".rstrip("0").rstrip(".") + suffix

    return amount_text(number)


def normalize_unit(unit):
    return unit if unit in UNIT_OPTIONS else "item"


def unit_multiplier(unit):
    return {"B": 1000, "mB": 1}.get(normalize_unit(unit), 1)


def unit_kind(unit):
    return "fluid" if normalize_unit(unit) in FLUID_UNITS else "item"


def to_base_amount(amount, unit):
    return float(amount) * unit_multiplier(unit)


def format_amount_with_unit(amount, unit):
    unit = normalize_unit(unit)
    if unit == "item":
        return compact_amount_text(amount)
    if unit in FLUID_UNITS:
        base = float(amount)
        if abs(base) >= 1000:
            return f"{compact_amount_text(base / 1000)}B"
        return f"{amount_text(base)}mB"
    return compact_amount_text(amount)


def recipe_amount_text(amount, unit):
    unit = normalize_unit(unit)
    if unit == "item":
        return amount_text(amount)
    return f"{amount_text(amount)}{unit}"


def format_ticks(ticks):
    ticks = int(math.ceil(float(ticks)))
    seconds = ticks / 20
    if seconds < 60:
        return f"{amount_text(seconds)}s"
    minutes = int(seconds // 60)
    remaining_seconds = int(seconds % 60)
    if minutes < 60:
        return f"{minutes}m {remaining_seconds}s"
    hours = minutes // 60
    remaining_minutes = minutes % 60
    return f"{hours}h {remaining_minutes}m {remaining_seconds}s"


@dataclass
class Recipe:
    id: str
    output: str
    output_amount: float
    output_unit: str = "item"
    machine: str = ""
    inputs: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=str(data.get("id") or make_id("recipe")),
            output=str(data.get("output") or "").strip(),
            output_amount=float(data.get("outputAmount") or data.get("output_amount") or 1),
            output_unit=normalize_unit(data.get("outputUnit") or data.get("output_unit") or "item"),
            machine=str(data.get("machine") or "").strip(),
            inputs=[
                {
                    "item": str(item.get("item") or "").strip(),
                    "amount": float(item.get("amount") or 0),
                    "unit": normalize_unit(item.get("unit") or "item"),
                    "consumed": item.get("consumed", True) is not False,
                }
                for item in data.get("inputs", [])
                if item.get("item") and float(item.get("amount") or 0) > 0
            ],
        )

    def to_dict(self):
        return {
            "id": self.id,
            "output": self.output,
            "outputAmount": self.output_amount,
            "outputUnit": self.output_unit,
            "machine": self.machine,
            "inputs": self.inputs,
        }

    def label(self):
        machine = self.machine or "Recipe"
        inputs = ", ".join(
            f"{recipe_amount_text(item['amount'], item.get('unit', 'item'))} {item['item']}{' (kept)' if item.get('consumed', True) is False else ''}"
            for item in self.inputs
        )
        return f"{machine}: {self.output} x{recipe_amount_text(self.output_amount, self.output_unit)} from {inputs or 'nothing'}"

    def output_base_amount(self):
        return to_base_amount(self.output_amount, self.output_unit)


@dataclass
class Profile:
    id: str
    name: str
    recipes: list = field(default_factory=list)
    preferred_routes: dict = field(default_factory=dict)
    base_materials: list = field(default_factory=list)
    machines: dict = field(default_factory=dict)


def material_key(item, unit="item"):
    return f"{item.lower()}::{unit_kind(unit)}"


def material_label(key):
    item, _sep, kind = key.partition("::")
    return f"{item} ({kind or 'item'})"


def read_json_file(path):
    data = path.read_bytes()
    last_error = None
    for encoding in ("utf-8", "utf-8-sig", "utf-16", "cp1252"):
        try:
            return json.loads(data.decode(encoding))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            last_error = error
        try:
            text = data.decode(encoding, errors="ignore")
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            last_error = error
    raise ValueError(f"Could not read JSON from {path}: {last_error}")


def load_profiles():
    PROFILE_ROOT.mkdir(exist_ok=True)
    profiles = []

    for directory in sorted(PROFILE_ROOT.iterdir()):
        if not directory.is_dir():
            continue

        profile = Profile(id=make_id("profile"), name=directory.name)
        metadata_path = directory / "profile.json"
        if metadata_path.exists():
            try:
                metadata = read_json_file(metadata_path)
                profile.id = metadata.get("id") or profile.id
                profile.name = metadata.get("name") or profile.name
                profile.preferred_routes = metadata.get("preferredRoutes") or {}
                profile.base_materials = metadata.get("baseMaterials") or []
                profile.machines = metadata.get("machines") or {}
            except (OSError, ValueError):
                pass

        for path in sorted(directory.glob("*.json")):
            if path.name == "profile.json":
                continue
            try:
                recipe = Recipe.from_dict(read_json_file(path))
            except (OSError, ValueError):
                continue
            if recipe.output and recipe.output_amount > 0:
                profile.recipes.append(recipe)

        if profile.recipes or metadata_path.exists():
            profiles.append(profile)

    if profiles:
        return profiles

    return [Profile(id=make_id("profile"), name="Default Modpack")]


def save_profile(profile):
    PROFILE_ROOT.mkdir(exist_ok=True)
    directory = PROFILE_ROOT / safe_name(profile.name)
    directory.mkdir(exist_ok=True)

    for path in directory.glob("*.json"):
        path.unlink()

    metadata = {
        "id": profile.id,
        "name": profile.name,
        "recipeCount": len(profile.recipes),
        "preferredRoutes": profile.preferred_routes,
        "baseMaterials": profile.base_materials,
        "machines": profile.machines,
        "savedAt": datetime.now(timezone.utc).isoformat(),
    }
    (directory / "profile.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    for recipe in profile.recipes:
        file_name = f"{safe_name(recipe.output)}-{safe_name(recipe.id)}.json"
        (directory / file_name).write_text(json.dumps(recipe.to_dict(), indent=2), encoding="utf-8")


def group_recipes(recipes):
    grouped = {}
    for recipe in recipes:
        grouped.setdefault(recipe.output.lower(), []).append(recipe)
    return grouped


def empty_plan():
    return {
        "raw": {},
        "crafts": {},
        "tasks": [],
        "root_tasks": [],
        "warnings": [],
        "choices": [],
        "chain": [],
        "cost": 0,
    }


def add_raw(plan, item, amount, unit="item"):
    unit = normalize_unit(unit)
    key = f"{item.lower()}::{unit_kind(unit)}"
    existing = plan["raw"].setdefault(key, {"item": item, "amount": 0, "unit": unit})
    existing["amount"] += amount
    if unit_kind(unit) == "fluid":
        existing["unit"] = "mB"


def add_craft(plan, recipe, crafts):
    existing = plan["crafts"].setdefault(recipe.id, {
        "item": recipe.output,
        "machine": recipe.machine,
        "recipe": recipe.label(),
        "amount": 0,
    })
    existing["amount"] += crafts


def merge_plan(target, source):
    for raw in source["raw"].values():
        add_raw(target, raw["item"], raw["amount"], raw.get("unit", "item"))
    for key, craft in source["crafts"].items():
        existing = target["crafts"].setdefault(key, {**craft, "amount": 0})
        existing["amount"] += craft["amount"]
    target["tasks"].extend(source["tasks"])
    target["warnings"].extend(source["warnings"])
    target["choices"].extend(source["choices"])
    target["chain"].extend(source["chain"])


def total_raw_cost(raw):
    return sum(row["amount"] for row in raw.values())


def build_recipe_plan(recipe, amount, recipes_by_output, stack, depth, preferred_routes=None, base_materials=None, task_counter=None):
    plan = empty_plan()
    crafts = math.ceil(amount / recipe.output_base_amount())
    produced_amount = crafts * recipe.output_base_amount()
    task_counter = task_counter or [0]
    task_counter[0] += 1
    task_id = f"task-{task_counter[0]}"
    dependencies = []
    add_craft(plan, recipe, crafts)
    plan["chain"].append({
        "depth": depth,
        "item": recipe.output,
        "amount": produced_amount,
        "unit": recipe.output_unit,
        "type": "crafted",
        "crafts": crafts,
        "machine": recipe.machine,
    })

    for item in recipe.inputs:
        consumed = item.get("consumed", True) is not False
        input_unit = normalize_unit(item.get("unit", "item"))
        input_base_amount = to_base_amount(item["amount"], input_unit)
        needed_amount = input_base_amount * crafts if consumed else input_base_amount
        if not consumed:
            plan["chain"].append({
                "depth": depth + 1,
                "item": item["item"],
                "amount": needed_amount,
                "unit": input_unit,
                "type": "reusable",
            })
        input_plan = build_best_plan(
            item["item"],
            needed_amount,
            recipes_by_output,
            [*stack, recipe.output.lower()],
            depth + 1 if consumed else depth + 2,
            input_unit,
            preferred_routes,
            base_materials,
            task_counter,
        )
        dependencies.extend(input_plan["root_tasks"])
        merge_plan(plan, input_plan)

    plan["tasks"].append({
        "id": task_id,
        "recipe_id": recipe.id,
        "item": recipe.output,
        "machine": recipe.machine or "Recipe",
        "crafts": crafts,
        "depends_on": sorted(set(dependencies)),
    })
    plan["root_tasks"] = [task_id]
    plan["cost"] = total_raw_cost(plan["raw"])
    plan["recipe"] = recipe
    return plan


def build_best_plan(item, amount, recipes_by_output, stack=None, depth=0, unit="item", preferred_routes=None, base_materials=None, task_counter=None):
    stack = stack or []
    task_counter = task_counter or [0]
    preferred_routes = preferred_routes or {}
    base_materials = set(base_materials or [])
    key = item.lower()
    recipes = recipes_by_output.get(key, [])

    if material_key(item, unit) in base_materials:
        plan = empty_plan()
        add_raw(plan, item, amount, unit)
        plan["chain"].append({"depth": depth, "item": item, "amount": amount, "unit": unit, "type": "raw"})
        plan["cost"] = total_raw_cost(plan["raw"])
        return plan

    if not recipes:
        plan = empty_plan()
        add_raw(plan, item, amount, unit)
        plan["chain"].append({"depth": depth, "item": item, "amount": amount, "unit": unit, "type": "missing"})
        plan["cost"] = total_raw_cost(plan["raw"])
        return plan

    if key in stack:
        plan = empty_plan()
        plan["warnings"].append(f"Circular recipe chain detected at {item}. Counted it as raw.")
        add_raw(plan, item, amount, unit)
        plan["chain"].append({"depth": depth, "item": item, "amount": amount, "unit": unit, "type": "cycle"})
        plan["cost"] = total_raw_cost(plan["raw"])
        return plan

    preferred_recipe_id = preferred_routes.get(key)
    preferred_recipe = next((recipe for recipe in recipes if recipe.id == preferred_recipe_id), None)
    if preferred_recipe:
        best = build_recipe_plan(preferred_recipe, amount, recipes_by_output, stack, depth, preferred_routes, base_materials, task_counter)
        if len(recipes) > 1:
            best["choices"].insert(0, f"Using desired {item} route: {preferred_recipe.label()}.")
        best.pop("recipe", None)
        return best

    candidates = [build_recipe_plan(recipe, amount, recipes_by_output, stack, depth, preferred_routes, base_materials, task_counter) for recipe in recipes]
    candidates.sort(key=lambda plan: plan["cost"])
    best = candidates[0]

    if len(recipes) > 1:
        compared = "; ".join(
            f"{candidate['recipe'].label()} needs {compact_amount_text(candidate['cost'])} raw"
            for candidate in candidates
        )
        best["choices"].insert(0, f"Picked cheapest {item} route: {best['recipe'].label()}. Compared {compared}.")

    best.pop("recipe", None)
    return best


class CalculatorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Minecraft Production Calculator v{APP_VERSION}")
        self.geometry("1180x760")
        self.minsize(980, 620)

        self.profiles = load_profiles()
        self.active_profile = next((profile for profile in self.profiles if profile.recipes), self.profiles[0])
        self.active_recipe_id = None
        self.input_rows = []
        self.logo_image = None

        self.configure(bg=COLORS["bg"])
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self.configure_style()
        self.build_ui()
        self.refresh_all()

    def configure_style(self):
        self.style.configure(".", background=COLORS["panel"], foreground=COLORS["text"], fieldbackground=COLORS["field"])
        self.style.configure("TFrame", background=COLORS["bg"])
        self.style.configure("Panel.TFrame", background=COLORS["panel"], relief="solid", borderwidth=1)
        self.style.configure("Logo.TFrame", background=COLORS["panel_2"], relief="solid", borderwidth=1)
        self.style.configure("TLabel", background=COLORS["panel"], foreground=COLORS["text"])
        self.style.configure("Muted.TLabel", background=COLORS["panel"], foreground=COLORS["muted"])
        self.style.configure("Logo.TLabel", background=COLORS["panel_2"], foreground=COLORS["text"])
        self.style.configure("LogoAccent.TLabel", background=COLORS["panel_2"], foreground=COLORS["accent"])
        self.style.configure("TButton", background=COLORS["accent_dark"], foreground=COLORS["text"], borderwidth=1)
        self.style.map("TButton", background=[("active", COLORS["select"])])
        self.style.configure(
            "TCombobox",
            background=COLORS["panel_2"],
            bordercolor=COLORS["line"],
            darkcolor=COLORS["line"],
            fieldbackground=COLORS["field"],
            foreground=COLORS["text"],
            lightcolor=COLORS["line"],
            selectbackground=COLORS["select"],
            selectforeground=COLORS["text"],
            arrowcolor=COLORS["text"],
        )
        self.style.configure(
            "Dark.TCombobox",
            background=COLORS["panel_2"],
            bordercolor=COLORS["line"],
            darkcolor=COLORS["line"],
            fieldbackground=COLORS["field"],
            foreground=COLORS["text"],
            lightcolor=COLORS["line"],
            selectbackground=COLORS["select"],
            selectforeground=COLORS["text"],
            arrowcolor=COLORS["text"],
        )
        self.style.map(
            "TCombobox",
            background=[("readonly", COLORS["panel_2"]), ("active", COLORS["select"])],
            fieldbackground=[("readonly", COLORS["field"]), ("disabled", COLORS["field"])],
            foreground=[("readonly", COLORS["system_field_text"]), ("disabled", COLORS["muted"])],
            selectbackground=[("readonly", COLORS["select"])],
            selectforeground=[("readonly", COLORS["system_field_text"])],
        )
        self.style.map(
            "Dark.TCombobox",
            background=[("readonly", COLORS["panel_2"]), ("active", COLORS["select"])],
            fieldbackground=[("readonly", COLORS["field"]), ("disabled", COLORS["field"])],
            foreground=[("readonly", COLORS["system_field_text"]), ("disabled", COLORS["muted"])],
            selectbackground=[("readonly", COLORS["select"])],
            selectforeground=[("readonly", COLORS["system_field_text"])],
        )
        self.option_add("*TCombobox*Listbox.background", COLORS["field"])
        self.option_add("*TCombobox*Listbox.foreground", COLORS["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", COLORS["select"])
        self.option_add("*TCombobox*Listbox.selectForeground", COLORS["text"])
        self.style.configure("Treeview", background=COLORS["field"], foreground=COLORS["text"], fieldbackground=COLORS["field"], bordercolor=COLORS["line"])
        self.style.configure("Treeview.Heading", background=COLORS["panel_2"], foreground=COLORS["text"])
        self.style.map("Treeview", background=[("selected", COLORS["select"])], foreground=[("selected", COLORS["text"])])

    def prepare_combobox(self, combo):
        combo.configure(style="Dark.TCombobox")
        combo.configure(postcommand=lambda widget=combo: self.style_combobox_popup(widget))
        self.style_combobox_popup(combo)

    def style_combobox_popup(self, combo):
        try:
            popdown = combo.tk.call("ttk::combobox::PopdownWindow", combo)
            listbox = f"{popdown}.f.l"
            combo.tk.call(listbox, "configure", "-background", COLORS["system_field_bg"])
            combo.tk.call(listbox, "configure", "-foreground", COLORS["system_field_text"])
            combo.tk.call(listbox, "configure", "-selectbackground", COLORS["system_field_bg"])
            combo.tk.call(listbox, "configure", "-selectforeground", COLORS["system_field_text"])
            combo.tk.call(listbox, "configure", "-highlightbackground", COLORS["line"])
        except tk.TclError:
            pass

    def build_ui(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=0, minsize=320)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        self.sidebar = ttk.Frame(root, style="Panel.TFrame", padding=12)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.sidebar.columnconfigure(0, weight=1)
        self.sidebar.rowconfigure(5, weight=1)

        self.main = ttk.Frame(root)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.columnconfigure(0, weight=1)
        self.main.rowconfigure(1, weight=1)

        self.build_sidebar()
        self.build_editor()
        self.build_calculator()

    def build_sidebar(self):
        ttk.Label(self.sidebar, text="Profile", font=("Segoe UI", 13, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Button(self.sidebar, text="New", command=self.new_profile).grid(row=0, column=1, sticky="e")

        ttk.Label(self.sidebar, text="Active modpack", style="Muted.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(14, 4))
        self.profile_var = tk.StringVar()
        self.profile_combo = ttk.Combobox(self.sidebar, textvariable=self.profile_var, state="readonly")
        self.prepare_combobox(self.profile_combo)
        self.profile_combo.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.profile_combo.bind("<<ComboboxSelected>>", self.select_profile)

        buttons = ttk.Frame(self.sidebar, style="Panel.TFrame")
        buttons.grid(row=3, column=0, columnspan=2, sticky="ew", pady=10)
        ttk.Button(buttons, text="Rename", command=self.rename_profile).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Delete", command=self.delete_profile).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Save", command=self.save_current_profile).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Machines", command=self.edit_machines).pack(side="left")

        ttk.Label(self.sidebar, text="Recipes", font=("Segoe UI", 13, "bold")).grid(row=4, column=0, columnspan=2, sticky="w", pady=(16, 6))
        self.recipe_tree = ttk.Treeview(self.sidebar, columns=("route",), show="tree headings", height=25)
        self.recipe_tree.heading("#0", text="Output")
        self.recipe_tree.heading("route", text="Route")
        self.recipe_tree.column("#0", width=190, stretch=True)
        self.recipe_tree.column("route", width=110, stretch=True)
        self.recipe_tree.tag_configure("desired", foreground=COLORS["green"])
        self.recipe_tree.tag_configure("base", foreground=COLORS["gold"])
        self.recipe_tree.grid(row=5, column=0, columnspan=2, sticky="nsew")
        self.recipe_tree.bind("<<TreeviewSelect>>", self.select_recipe)

        self.status = ttk.Label(self.sidebar, text="", style="Muted.TLabel", wraplength=280)
        self.status.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(10, 10))

        logo = ttk.Frame(self.sidebar, style="Logo.TFrame", padding=10)
        logo.grid(row=7, column=0, columnspan=2, sticky="ew")
        logo.columnconfigure(0, weight=1)
        loaded_logo = self.load_logo_image(max_width=260, max_height=150)
        if loaded_logo:
            ttk.Label(logo, image=loaded_logo, style="Logo.TLabel").grid(row=0, column=0, sticky="ew")
        else:
            mark = tk.Canvas(logo, width=42, height=42, bg=COLORS["panel_2"], highlightthickness=0)
            mark.grid(row=0, column=0, sticky="w")
            mark.create_rectangle(4, 4, 38, 38, fill=COLORS["accent_dark"], outline=COLORS["accent"], width=2)
            mark.create_text(21, 21, text="MC", fill=COLORS["text"], font=("Segoe UI", 11, "bold"))
        ttk.Label(logo, text="MCCalculator", style="LogoAccent.TLabel", font=("Segoe UI", 10, "bold")).grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Label(logo, text="Profile recipes on disk", style="Logo.TLabel").grid(row=2, column=0, sticky="w")

    def load_logo_image(self, max_width, max_height):
        for path in LOGO_PATHS:
            if not path.exists():
                continue
            try:
                image = tk.PhotoImage(file=str(path))
                scale = max(1, int(max(image.width() / max_width, image.height() / max_height)))
                self.logo_image = image.subsample(scale, scale)
                return self.logo_image
            except tk.TclError:
                continue
        return None

    def build_editor(self):
        editor = ttk.Frame(self.main, style="Panel.TFrame", padding=12)
        editor.grid(row=0, column=0, sticky="ew")
        editor.columnconfigure(1, weight=1)
        editor.columnconfigure(3, weight=1)

        ttk.Label(editor, text="Add or edit recipe", font=("Segoe UI", 13, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Button(editor, text="Clear", command=self.clear_recipe_form).grid(row=0, column=3, sticky="e")

        ttk.Label(editor, text="Output item").grid(row=1, column=0, sticky="w", pady=(12, 4))
        self.output_var = tk.StringVar()
        ttk.Entry(editor, textvariable=self.output_var).grid(row=1, column=1, sticky="ew", padx=(6, 14), pady=(12, 4))

        ttk.Label(editor, text="Output amount").grid(row=1, column=2, sticky="w", pady=(12, 4))
        self.output_amount_var = tk.StringVar(value="1")
        output_amount_frame = ttk.Frame(editor, style="Panel.TFrame")
        output_amount_frame.grid(row=1, column=3, sticky="ew", padx=(6, 0), pady=(12, 4))
        output_amount_frame.columnconfigure(0, weight=1)
        ttk.Entry(output_amount_frame, textvariable=self.output_amount_var, width=10).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.output_unit_var = tk.StringVar(value="item")
        self.output_unit_combo = ttk.Combobox(output_amount_frame, textvariable=self.output_unit_var, values=UNIT_OPTIONS, state="readonly", width=6)
        self.prepare_combobox(self.output_unit_combo)
        self.output_unit_combo.grid(row=0, column=1)

        ttk.Label(editor, text="Machine or process").grid(row=2, column=0, sticky="w", pady=4)
        self.machine_var = tk.StringVar()
        self.machine_combo = ttk.Combobox(editor, textvariable=self.machine_var)
        self.prepare_combobox(self.machine_combo)
        self.machine_combo.grid(row=2, column=1, sticky="ew", padx=(6, 14), pady=4)

        route_options = ttk.Frame(editor, style="Panel.TFrame")
        route_options.grid(row=3, column=0, columnspan=4, sticky="w", pady=(8, 0))
        self.desired_route_var = tk.BooleanVar(value=False)
        self.base_material_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(route_options, text="Desired route for this output", variable=self.desired_route_var).pack(side="left", padx=(0, 16))
        ttk.Checkbutton(route_options, text="Treat output as base material", variable=self.base_material_var).pack(side="left")

        ttk.Label(editor, text="Inputs").grid(row=4, column=0, sticky="w", pady=(14, 4))
        ttk.Button(editor, text="Add input", command=self.add_input_row).grid(row=4, column=3, sticky="e", pady=(14, 4))

        inputs_panel = ttk.Frame(editor, style="Panel.TFrame")
        inputs_panel.grid(row=5, column=0, columnspan=4, sticky="ew")
        inputs_panel.columnconfigure(0, weight=1)

        self.inputs_canvas = tk.Canvas(
            inputs_panel,
            height=150,
            bg=COLORS["panel"],
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=COLORS["line"],
        )
        self.inputs_canvas.grid(row=0, column=0, sticky="ew")
        inputs_scrollbar = ttk.Scrollbar(inputs_panel, orient="vertical", command=self.inputs_canvas.yview)
        inputs_scrollbar.grid(row=0, column=1, sticky="ns")
        self.inputs_canvas.configure(yscrollcommand=inputs_scrollbar.set)

        self.inputs_frame = ttk.Frame(self.inputs_canvas, style="Panel.TFrame")
        self.inputs_frame.columnconfigure(0, weight=1)
        self.inputs_canvas_window = self.inputs_canvas.create_window((0, 0), window=self.inputs_frame, anchor="nw")
        self.inputs_frame.bind("<Configure>", self.update_inputs_scrollregion)
        self.inputs_canvas.bind("<Configure>", self.resize_inputs_window)
        self.inputs_canvas.bind("<MouseWheel>", self.scroll_inputs)
        self.inputs_frame.bind("<MouseWheel>", self.scroll_inputs)

        actions = ttk.Frame(editor, style="Panel.TFrame")
        actions.grid(row=6, column=0, columnspan=4, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="Delete recipe", command=self.delete_recipe).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Save recipe", command=self.save_recipe).pack(side="left")

    def update_inputs_scrollregion(self, _event=None):
        self.inputs_canvas.configure(scrollregion=self.inputs_canvas.bbox("all"))

    def resize_inputs_window(self, event):
        self.inputs_canvas.itemconfigure(self.inputs_canvas_window, width=event.width)

    def scroll_inputs(self, event):
        self.inputs_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def build_calculator(self):
        calc = ttk.Frame(self.main, style="Panel.TFrame", padding=12)
        calc.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        calc.columnconfigure(0, weight=1)
        calc.rowconfigure(3, weight=1)

        ttk.Label(calc, text="Calculate production", font=("Segoe UI", 13, "bold")).grid(row=0, column=0, columnspan=4, sticky="w")

        ttk.Label(calc, text="Desired item").grid(row=1, column=0, sticky="w", pady=(12, 4))
        self.target_var = tk.StringVar()
        self.target_entry = ttk.Combobox(calc, textvariable=self.target_var)
        self.prepare_combobox(self.target_entry)
        self.target_entry.grid(row=2, column=0, sticky="ew", padx=(0, 10))
        self.target_entry.bind("<<ComboboxSelected>>", self.sync_target_unit)

        ttk.Label(calc, text="Amount").grid(row=1, column=1, sticky="w", pady=(12, 4))
        self.target_amount_var = tk.StringVar(value="1")
        target_amount_frame = ttk.Frame(calc, style="Panel.TFrame")
        target_amount_frame.grid(row=2, column=1, sticky="ew", padx=(0, 10))
        target_amount_frame.columnconfigure(0, weight=1)
        ttk.Entry(target_amount_frame, textvariable=self.target_amount_var, width=10).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.target_unit_var = tk.StringVar(value="item")
        self.target_unit_combo = ttk.Combobox(target_amount_frame, textvariable=self.target_unit_var, values=UNIT_OPTIONS, state="readonly", width=6)
        self.prepare_combobox(self.target_unit_combo)
        self.target_unit_combo.grid(row=0, column=1)
        ttk.Button(calc, text="Calculate", command=self.calculate).grid(row=2, column=2, sticky="ew")

        panes = ttk.PanedWindow(calc, orient="horizontal")
        panes.grid(row=3, column=0, columnspan=4, sticky="nsew", pady=(14, 0))

        left = ttk.Frame(panes, style="Panel.TFrame", padding=8)
        right = ttk.Frame(panes, style="Panel.TFrame", padding=8)
        panes.add(left, weight=1)
        panes.add(right, weight=2)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=3)
        left.rowconfigure(3, weight=3)
        left.rowconfigure(5, weight=2)

        ttk.Label(left, text="Raw requirements", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        self.raw_tree = ttk.Treeview(left, columns=("item", "amount"), show="headings", height=5)
        self.raw_tree.heading("item", text="Item")
        self.raw_tree.heading("amount", text="Amount")
        self.raw_tree.grid(row=1, column=0, sticky="nsew", pady=(6, 12))

        ttk.Label(left, text="Crafting workload", font=("Segoe UI", 11, "bold")).grid(row=2, column=0, sticky="w")
        self.craft_tree = ttk.Treeview(left, columns=("item", "crafts", "machine"), show="headings", height=5)
        self.craft_tree.heading("item", text="Item")
        self.craft_tree.heading("crafts", text="Crafts")
        self.craft_tree.heading("machine", text="Process")
        self.craft_tree.grid(row=3, column=0, sticky="nsew", pady=(6, 12))

        ttk.Label(left, text="Time estimate", font=("Segoe UI", 11, "bold")).grid(row=4, column=0, sticky="w")
        self.time_tree = ttk.Treeview(left, columns=("process", "crafts", "ticks", "time"), show="headings", height=4)
        self.time_tree.heading("process", text="Process")
        self.time_tree.heading("crafts", text="Crafts")
        self.time_tree.heading("ticks", text="Ticks")
        self.time_tree.heading("time", text="Time")
        self.time_tree.grid(row=5, column=0, sticky="nsew", pady=(6, 0))

        ttk.Label(right, text="Supply chain and choices", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.chain_text = tk.Text(right, bg=COLORS["field"], fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat", wrap="word")
        self.chain_text.tag_configure("raw_input", foreground=COLORS["gold"], font=("Segoe UI", 9, "bold"))
        self.chain_text.tag_configure("reusable_input", foreground=COLORS["accent"], font=("Segoe UI", 9, "bold"))
        self.chain_text.tag_configure("crafted_detail", foreground=COLORS["green"], font=("Segoe UI", 9, "bold"))
        self.chain_text.tag_configure("missing_recipe", foreground=COLORS["red"], font=("Segoe UI", 9, "bold"))
        self.chain_text.pack(fill="both", expand=True, pady=(6, 0))

    def refresh_all(self):
        self.profile_combo["values"] = [profile.name for profile in self.profiles]
        self.profile_var.set(self.active_profile.name)
        self.refresh_recipe_list()
        self.clear_recipe_form()
        self.set_status(f"Saving to {PROFILE_ROOT}")

    def refresh_recipe_list(self):
        self.recipe_tree.delete(*self.recipe_tree.get_children())
        recipes_by_output = group_recipes(self.active_profile.recipes)
        for output in sorted(recipes_by_output):
            recipes = sorted(recipes_by_output[output], key=lambda current: (current.machine.lower(), current.id))
            first_recipe = recipes[0]
            parent_id = self.recipe_parent_id(output)
            route_count = len(recipes)
            parent_tags = []
            if material_key(first_recipe.output, first_recipe.output_unit) in set(self.active_profile.base_materials):
                parent_tags.append("base")
            self.recipe_tree.insert(
                "",
                tk.END,
                iid=parent_id,
                text=first_recipe.output,
                values=(f"{route_count} route{'s' if route_count != 1 else ''}",),
                tags=tuple(parent_tags),
            )
            preferred_id = self.active_profile.preferred_routes.get(output)
            for recipe in recipes:
                route_name = recipe.machine or "Recipe"
                marker = "* " if recipe.id == preferred_id else ""
                tags = ("desired",) if recipe.id == preferred_id else ()
                self.recipe_tree.insert(
                    parent_id,
                    tk.END,
                    iid=recipe.id,
                    text=f"{marker}{route_name}",
                    values=(f"x{recipe_amount_text(recipe.output_amount, recipe.output_unit)}",),
                    tags=tags,
                )
        outputs = sorted({recipe.output for recipe in self.active_profile.recipes}, key=str.lower)
        if hasattr(self, "target_entry"):
            self.target_entry["values"] = outputs
        machines = sorted({recipe.machine for recipe in self.active_profile.recipes if recipe.machine}, key=str.lower)
        if hasattr(self, "machine_combo"):
            self.machine_combo["values"] = machines

    def set_status(self, text):
        self.status.config(text=text)

    def recipe_parent_id(self, output):
        return f"output::{output}"

    def sync_target_unit(self, _event=None):
        target = self.target_var.get().strip().lower()
        for recipe in self.active_profile.recipes:
            if recipe.output.lower() == target:
                self.target_unit_var.set(recipe.output_unit)
                return

    def new_profile(self):
        name = simpledialog.askstring("New profile", "Profile name?", parent=self)
        if not name:
            return
        profile = Profile(id=make_id("profile"), name=name.strip())
        self.profiles.append(profile)
        self.active_profile = profile
        save_profile(profile)
        self.refresh_all()

    def rename_profile(self):
        name = simpledialog.askstring("Rename profile", "Profile name?", initialvalue=self.active_profile.name, parent=self)
        if not name:
            return
        self.active_profile.name = name.strip()
        save_profile(self.active_profile)
        self.refresh_all()

    def delete_profile(self):
        if len(self.profiles) <= 1:
            messagebox.showinfo("Delete profile", "At least one profile is required.")
            return
        if not messagebox.askyesno("Delete profile", f"Remove {self.active_profile.name} from this app? Files on disk are left alone."):
            return
        self.profiles = [profile for profile in self.profiles if profile.id != self.active_profile.id]
        self.active_profile = self.profiles[0]
        self.refresh_all()

    def select_profile(self, _event=None):
        selected = self.profile_var.get()
        for profile in self.profiles:
            if profile.name == selected:
                self.active_profile = profile
                self.refresh_recipe_list()
                self.clear_recipe_form()
                return

    def save_current_profile(self):
        save_profile(self.active_profile)
        self.set_status(f"Saved {len(self.active_profile.recipes)} recipe file(s) to profile/{safe_name(self.active_profile.name)}")

    def machine_options(self):
        machines = {}
        for recipe in self.active_profile.recipes:
            machine = recipe.machine.strip()
            if not machine:
                continue
            key = machine.lower()
            entry = machines.setdefault(key, {"name": machine, "recipes": 0})
            entry["recipes"] += 1

        for machine in self.active_profile.machines:
            key = machine.lower()
            machines.setdefault(key, {"name": machine, "recipes": 0})

        return dict(sorted(machines.items(), key=lambda row: row[1]["name"].lower()))

    def edit_machines(self):
        window = tk.Toplevel(self)
        window.title(f"Machines - {self.active_profile.name}")
        window.geometry("760x520")
        window.configure(bg=COLORS["bg"])
        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)

        panel = ttk.Frame(window, style="Panel.TFrame", padding=12)
        panel.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)

        ttk.Label(
            panel,
            text="Machine settings are saved per profile for later tick-time and simultaneous-crafting calculations.",
            style="Muted.TLabel",
            wraplength=700,
        ).grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 8))

        tree = ttk.Treeview(panel, columns=("machine", "recipes", "simultaneous", "ticks"), show="headings", height=14)
        tree.heading("machine", text="Machine or process")
        tree.heading("recipes", text="Recipes")
        tree.heading("simultaneous", text="Simultaneous")
        tree.heading("ticks", text="Ticks/craft")
        tree.column("machine", width=360)
        tree.column("recipes", width=90, anchor="center")
        tree.column("simultaneous", width=110, anchor="center")
        tree.column("ticks", width=110, anchor="center")
        tree.grid(row=1, column=0, columnspan=4, sticky="nsew")

        scrollbar = ttk.Scrollbar(panel, orient="vertical", command=tree.yview)
        scrollbar.grid(row=1, column=4, sticky="ns")
        tree.configure(yscrollcommand=scrollbar.set)

        form = ttk.Frame(panel, style="Panel.TFrame")
        form.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(12, 0))
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        ttk.Label(form, text="Machine").grid(row=0, column=0, sticky="w", padx=(0, 6))
        machine_var = tk.StringVar()
        machine_combo = ttk.Combobox(form, textvariable=machine_var)
        self.prepare_combobox(machine_combo)
        machine_combo.grid(row=0, column=1, sticky="ew", padx=(0, 12))

        ttk.Label(form, text="Simultaneous crafts").grid(row=0, column=2, sticky="w", padx=(0, 6))
        simultaneous_var = tk.StringVar(value="1")
        ttk.Entry(form, textvariable=simultaneous_var, width=10).grid(row=0, column=3, sticky="w")

        ttk.Label(form, text="Ticks per craft").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=(8, 0))
        ticks_var = tk.StringVar(value="")
        ttk.Entry(form, textvariable=ticks_var, width=12).grid(row=1, column=1, sticky="w", pady=(8, 0))

        def setting_for(machine):
            return self.active_profile.machines.get(machine) or self.active_profile.machines.get(machine.lower()) or {}

        def populate():
            tree.delete(*tree.get_children())
            options = self.machine_options()
            machine_combo["values"] = [entry["name"] for entry in options.values()]
            for key, entry in options.items():
                setting = setting_for(entry["name"])
                simultaneous = setting.get("simultaneousCrafts", setting.get("count", ""))
                ticks = setting.get("ticksPerCraft", "")
                if ticks == "" and setting.get("secondsPerCraft", "") != "":
                    ticks = float(setting["secondsPerCraft"]) * 20
                tree.insert("", tk.END, iid=key, values=(entry["name"], entry["recipes"], simultaneous, amount_text(ticks) if ticks != "" else ""))

        def load_selection(_event=None):
            selection = tree.selection()
            if not selection:
                return
            values = tree.item(selection[0], "values")
            machine_var.set(values[0])
            simultaneous_var.set(str(values[2] or "1"))
            ticks_var.set(str(values[3] or ""))

        def save_machine():
            machine = machine_var.get().strip()
            if not machine:
                messagebox.showerror("Machine", "Machine or process is required.")
                return
            try:
                simultaneous = int(float(simultaneous_var.get() or 1))
                ticks_text = ticks_var.get().strip()
                ticks = float(ticks_text) if ticks_text else 0
            except ValueError:
                messagebox.showerror("Machine", "Simultaneous crafts and ticks must be numbers.")
                return
            if simultaneous < 1:
                messagebox.showerror("Machine", "Simultaneous crafts must be at least 1.")
                return
            if ticks < 0:
                messagebox.showerror("Machine", "Ticks per craft cannot be negative.")
                return

            for existing in list(self.active_profile.machines):
                if existing.lower() == machine.lower() and existing != machine:
                    self.active_profile.machines.pop(existing, None)
            self.active_profile.machines[machine] = {
                "simultaneousCrafts": simultaneous,
                "ticksPerCraft": ticks,
            }
            save_profile(self.active_profile)
            populate()
            self.set_status(f"Saved machine settings for {machine}")

        def clear_machine():
            machine = machine_var.get().strip()
            if not machine:
                return
            for existing in list(self.active_profile.machines):
                if existing.lower() == machine.lower():
                    self.active_profile.machines.pop(existing, None)
            save_profile(self.active_profile)
            simultaneous_var.set("1")
            ticks_var.set("")
            populate()
            self.set_status(f"Cleared machine settings for {machine}")

        controls = ttk.Frame(panel, style="Panel.TFrame")
        controls.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(12, 0))
        ttk.Button(controls, text="Save machine", command=save_machine).pack(side="left", padx=(0, 8))
        ttk.Button(controls, text="Clear settings", command=clear_machine).pack(side="left", padx=(0, 8))
        ttk.Button(controls, text="Close", command=window.destroy).pack(side="right")

        tree.bind("<<TreeviewSelect>>", load_selection)
        populate()

    def material_options(self):
        options = {}
        for recipe in self.active_profile.recipes:
            output_key = material_key(recipe.output, recipe.output_unit)
            options[output_key] = {
                "item": recipe.output,
                "unit": "mB" if unit_kind(recipe.output_unit) == "fluid" else "item",
                "source": "output",
            }
            for item in recipe.inputs:
                item_name = item.get("item", "").strip()
                if not item_name:
                    continue
                unit = normalize_unit(item.get("unit", "item"))
                key = material_key(item_name, unit)
                options.setdefault(key, {
                    "item": item_name,
                    "unit": "mB" if unit_kind(unit) == "fluid" else "item",
                    "source": "input",
                })

        for key in self.active_profile.base_materials:
            if key not in options:
                item_name, _sep, kind = key.partition("::")
                options[key] = {
                    "item": item_name,
                    "unit": "mB" if kind == "fluid" else "item",
                    "source": "saved",
                }

        return dict(sorted(options.items(), key=lambda row: row[1]["item"].lower()))

    def edit_base_materials(self):
        window = tk.Toplevel(self)
        window.title(f"Base materials - {self.active_profile.name}")
        window.geometry("680x520")
        window.configure(bg=COLORS["bg"])
        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)

        panel = ttk.Frame(window, style="Panel.TFrame", padding=12)
        panel.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)

        ttk.Label(
            panel,
            text="Base materials are treated as raw inputs even if recipes exist for them.",
            style="Muted.TLabel",
            wraplength=620,
        ).grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 8))

        tree = ttk.Treeview(panel, columns=("material", "unit", "base"), show="headings", height=16)
        tree.heading("material", text="Material")
        tree.heading("unit", text="Unit")
        tree.heading("base", text="Base")
        tree.column("material", width=360)
        tree.column("unit", width=80, anchor="center")
        tree.column("base", width=120, anchor="center")
        tree.grid(row=1, column=0, columnspan=3, sticky="nsew")

        scrollbar = ttk.Scrollbar(panel, orient="vertical", command=tree.yview)
        scrollbar.grid(row=1, column=3, sticky="ns")
        tree.configure(yscrollcommand=scrollbar.set)

        def populate():
            tree.delete(*tree.get_children())
            base_set = set(self.active_profile.base_materials)
            for key, material in self.material_options().items():
                tree.insert("", tk.END, iid=key, values=(material["item"], material["unit"], "Yes" if key in base_set else ""))

        def toggle_base():
            selection = tree.selection()
            if not selection:
                return
            key = selection[0]
            base_set = set(self.active_profile.base_materials)
            if key in base_set:
                base_set.remove(key)
            else:
                base_set.add(key)
            self.active_profile.base_materials = sorted(base_set)
            save_profile(self.active_profile)
            populate()
            self.set_status(f"Updated base material: {material_label(key)}")

        controls = ttk.Frame(panel, style="Panel.TFrame")
        controls.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        ttk.Button(controls, text="Toggle base material", command=toggle_base).pack(side="left", padx=(0, 8))
        ttk.Button(controls, text="Close", command=window.destroy).pack(side="right")

        tree.bind("<Double-1>", lambda _event: toggle_base())
        populate()

    def edit_desired_routes(self):
        window = tk.Toplevel(self)
        window.title(f"Desired routes - {self.active_profile.name}")
        window.geometry("860x540")
        window.configure(bg=COLORS["bg"])
        window.columnconfigure(0, weight=1)
        window.columnconfigure(1, weight=2)
        window.rowconfigure(0, weight=1)

        outputs_panel = ttk.Frame(window, style="Panel.TFrame", padding=12)
        outputs_panel.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        outputs_panel.rowconfigure(1, weight=1)
        outputs_panel.columnconfigure(0, weight=1)

        routes_panel = ttk.Frame(window, style="Panel.TFrame", padding=12)
        routes_panel.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        routes_panel.rowconfigure(1, weight=1)
        routes_panel.columnconfigure(0, weight=1)

        ttk.Label(outputs_panel, text="Outputs with alternate recipes", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        output_list = tk.Listbox(outputs_panel, bg=COLORS["field"], fg=COLORS["text"], selectbackground=COLORS["select"], selectforeground=COLORS["text"], relief="flat")
        output_list.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

        ttk.Label(routes_panel, text="Routes", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        route_list = tk.Listbox(routes_panel, bg=COLORS["field"], fg=COLORS["text"], selectbackground=COLORS["select"], selectforeground=COLORS["text"], relief="flat")
        route_list.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

        recipes_by_output = group_recipes(self.active_profile.recipes)
        alternate_outputs = sorted([output for output, recipes in recipes_by_output.items() if len(recipes) > 1])
        route_lookup = {}
        selected_output = tk.StringVar()

        for output in alternate_outputs:
            preferred = self.active_profile.preferred_routes.get(output)
            marker = " *" if preferred else ""
            output_list.insert(tk.END, f"{output}{marker}")

        def selected_output_key():
            selection = output_list.curselection()
            if not selection:
                return ""
            return alternate_outputs[selection[0]]

        def populate_routes(_event=None):
            output = selected_output_key()
            if not output:
                return
            selected_output.set(output)
            route_lookup.clear()
            route_list.delete(0, tk.END)
            preferred = self.active_profile.preferred_routes.get(output)
            for recipe in recipes_by_output[output]:
                marker = "* " if recipe.id == preferred else "  "
                label = f"{marker}{recipe.label()}"
                route_lookup[label] = recipe
                route_list.insert(tk.END, label)

        def set_route():
            selection = route_list.curselection()
            output = selected_output.get()
            if not selection or not output:
                return
            label = route_list.get(selection[0])
            recipe = route_lookup.get(label)
            if not recipe:
                return
            self.active_profile.preferred_routes[output] = recipe.id
            save_profile(self.active_profile)
            self.set_status(f"Desired route set for {output}: {recipe.machine or 'Recipe'}")
            window.destroy()

        def clear_route():
            output = selected_output.get()
            if not output:
                return
            self.active_profile.preferred_routes.pop(output, None)
            save_profile(self.active_profile)
            self.set_status(f"Cleared desired route for {output}")
            window.destroy()

        controls = ttk.Frame(routes_panel, style="Panel.TFrame")
        controls.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(controls, text="Use selected route", command=set_route).pack(side="left", padx=(0, 8))
        ttk.Button(controls, text="Clear desired route", command=clear_route).pack(side="left", padx=(0, 8))
        ttk.Button(controls, text="Close", command=window.destroy).pack(side="right")

        output_list.bind("<<ListboxSelect>>", populate_routes)
        route_list.bind("<Double-1>", lambda _event: set_route())

    def add_input_row(self, item="", amount="1", consumed=True, unit="item"):
        row = ttk.Frame(self.inputs_frame, style="Panel.TFrame")
        row.grid(sticky="ew", pady=3)
        row.columnconfigure(0, weight=1)
        item_var = tk.StringVar(value=item)
        amount_var = tk.StringVar(value=str(amount))
        unit_var = tk.StringVar(value=normalize_unit(unit))
        kept_var = tk.BooleanVar(value=not consumed)
        ttk.Entry(row, textvariable=item_var).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Entry(row, textvariable=amount_var, width=12).grid(row=0, column=1, padx=(0, 8))
        unit_combo = ttk.Combobox(row, textvariable=unit_var, values=UNIT_OPTIONS, state="readonly", width=6)
        self.prepare_combobox(unit_combo)
        unit_combo.grid(row=0, column=2, padx=(0, 8))
        ttk.Checkbutton(row, text="Doesn't use", variable=kept_var).grid(row=0, column=3, padx=(0, 8))
        ttk.Button(row, text="Remove", command=lambda: self.remove_input_row(row)).grid(row=0, column=4)
        self.input_rows.append((row, item_var, amount_var, unit_var, kept_var))
        row.bind("<MouseWheel>", self.scroll_inputs)
        for child in row.winfo_children():
            child.bind("<MouseWheel>", self.scroll_inputs)
        self.after_idle(lambda: self.inputs_canvas.yview_moveto(1.0))

    def remove_input_row(self, row):
        self.input_rows = [entry for entry in self.input_rows if entry[0] is not row]
        row.destroy()
        if not self.input_rows:
            self.add_input_row()

    def clear_recipe_form(self):
        self.active_recipe_id = None
        self.output_var.set("")
        self.output_amount_var.set("1")
        self.output_unit_var.set("item")
        self.machine_var.set("")
        self.desired_route_var.set(False)
        self.base_material_var.set(False)
        for row, _item, _amount, _unit, _kept in self.input_rows:
            row.destroy()
        self.input_rows = []
        self.add_input_row()

    def selected_recipe_from_tree(self):
        selection = self.recipe_tree.selection()
        if not selection:
            return None
        item_id = selection[0]
        if item_id.startswith("output::"):
            output = item_id.replace("output::", "", 1)
            recipes = group_recipes(self.active_profile.recipes).get(output, [])
            if recipes:
                self.target_var.set(recipes[0].output)
                self.target_unit_var.set(recipes[0].output_unit)
            self.recipe_tree.item(item_id, open=not self.recipe_tree.item(item_id, "open"))
            return None
        return next((recipe for recipe in self.active_profile.recipes if recipe.id == item_id), None)

    def select_recipe(self, _event=None):
        recipe = self.selected_recipe_from_tree()
        if not recipe:
            return
        self.active_recipe_id = recipe.id
        self.output_var.set(recipe.output)
        self.target_var.set(recipe.output)
        self.output_amount_var.set(amount_text(recipe.output_amount))
        self.output_unit_var.set(recipe.output_unit)
        self.target_unit_var.set(recipe.output_unit)
        self.machine_var.set(recipe.machine)
        self.desired_route_var.set(self.active_profile.preferred_routes.get(recipe.output.lower()) == recipe.id)
        self.base_material_var.set(material_key(recipe.output, recipe.output_unit) in set(self.active_profile.base_materials))
        for row, _item, _amount, _unit, _kept in self.input_rows:
            row.destroy()
        self.input_rows = []
        for item in recipe.inputs:
            self.add_input_row(item["item"], amount_text(item["amount"]), item.get("consumed", True), item.get("unit", "item"))
        if not self.input_rows:
            self.add_input_row()

    def read_recipe_form(self):
        output = self.output_var.get().strip()
        if not output:
            raise ValueError("Output item is required.")
        output_amount = float(self.output_amount_var.get())
        if output_amount <= 0:
            raise ValueError("Output amount must be greater than zero.")

        inputs = []
        for _row, item_var, amount_var, unit_var, kept_var in self.input_rows:
            item = item_var.get().strip()
            if not item:
                continue
            amount = float(amount_var.get())
            if amount <= 0:
                raise ValueError("Input amounts must be greater than zero.")
            inputs.append({
                "item": item,
                "amount": amount,
                "unit": normalize_unit(unit_var.get()),
                "consumed": not kept_var.get(),
            })

        return Recipe(
            id=self.active_recipe_id or make_id("recipe"),
            output=output,
            output_amount=output_amount,
            output_unit=normalize_unit(self.output_unit_var.get()),
            machine=self.machine_var.get().strip(),
            inputs=inputs,
        )

    def save_recipe(self):
        try:
            recipe = self.read_recipe_form()
        except ValueError as error:
            messagebox.showerror("Save recipe", str(error))
            return

        is_new_recipe = self.active_recipe_id is None
        for index, existing in enumerate(self.active_profile.recipes):
            if existing.id == recipe.id:
                self.active_profile.recipes[index] = recipe
                break
        else:
            self.active_profile.recipes.append(recipe)

        self.apply_recipe_profile_flags(recipe)
        save_profile(self.active_profile)
        self.refresh_recipe_list()
        self.set_status(f"Saved {recipe.output}")
        if is_new_recipe:
            self.clear_recipe_form()
        else:
            self.active_recipe_id = recipe.id

    def apply_recipe_profile_flags(self, recipe):
        output_key = recipe.output.lower()
        existing_route_for_output = self.active_profile.preferred_routes.get(output_key)
        if self.desired_route_var.get():
            self.active_profile.preferred_routes[output_key] = recipe.id
        elif existing_route_for_output == recipe.id:
            self.active_profile.preferred_routes.pop(output_key, None)

        for key, route_recipe_id in list(self.active_profile.preferred_routes.items()):
            if route_recipe_id == recipe.id and key != output_key:
                self.active_profile.preferred_routes.pop(key, None)

        base_set = set(self.active_profile.base_materials)
        current_base_key = material_key(recipe.output, recipe.output_unit)
        if self.base_material_var.get():
            base_set.add(current_base_key)
        else:
            base_set.discard(current_base_key)
        self.active_profile.base_materials = sorted(base_set)

    def delete_recipe(self):
        if not self.active_recipe_id:
            return
        self.active_profile.recipes = [recipe for recipe in self.active_profile.recipes if recipe.id != self.active_recipe_id]
        save_profile(self.active_profile)
        self.refresh_recipe_list()
        self.clear_recipe_form()

    def calculate(self):
        target = self.target_var.get().strip()
        if not target:
            selected = self.selected_recipe_from_tree()
            if selected:
                target = selected.output
                self.target_var.set(target)
                self.target_unit_var.set(selected.output_unit)
            else:
                messagebox.showinfo("Calculate", "Choose or type a desired item first.")
                return
        try:
            amount = float(self.target_amount_var.get())
        except ValueError:
            messagebox.showerror("Calculate", "Target amount must be a number.")
            return
        if amount <= 0:
            messagebox.showerror("Calculate", "Target amount must be greater than zero.")
            return

        target_unit = normalize_unit(self.target_unit_var.get())
        plan = build_best_plan(
            target,
            to_base_amount(amount, target_unit),
            group_recipes(self.active_profile.recipes),
            unit=target_unit,
            preferred_routes=self.active_profile.preferred_routes,
            base_materials=self.active_profile.base_materials,
        )
        self.show_plan(plan)
        self.set_status(f"Calculated {recipe_amount_text(amount, target_unit)} {target}")

    def machine_setting(self, machine):
        setting = self.active_profile.machines.get(machine) or self.active_profile.machines.get(machine.lower()) or {}
        simultaneous = int(float(setting.get("simultaneousCrafts", setting.get("count", 1)) or 1))
        ticks = setting.get("ticksPerCraft", "")
        if ticks == "" and setting.get("secondsPerCraft", "") != "":
            ticks = float(setting["secondsPerCraft"]) * 20
        ticks = float(ticks or 0)
        return max(1, simultaneous), max(0, ticks)

    def build_time_schedule(self, plan):
        task_lookup = {}
        task_ids_by_recipe = {}
        for task in plan.get("tasks", []):
            recipe_id = task["recipe_id"]
            if recipe_id not in task_lookup:
                task_lookup[recipe_id] = {
                    "id": recipe_id,
                    "item": task["item"],
                    "machine": task["machine"] or "Recipe",
                    "crafts": 0,
                    "depends_on": set(),
                }
            task_lookup[recipe_id]["crafts"] += task["crafts"]
            task_ids_by_recipe[task["id"]] = recipe_id

        for task in plan.get("tasks", []):
            recipe_id = task["recipe_id"]
            for dependency in task.get("depends_on", []):
                dependency_recipe = task_ids_by_recipe.get(dependency)
                if dependency_recipe and dependency_recipe != recipe_id:
                    task_lookup[recipe_id]["depends_on"].add(dependency_recipe)

        tasks = task_lookup
        dependents = {task_id: [] for task_id in tasks}
        remaining_dependencies = {task_id: len(task["depends_on"]) for task_id, task in tasks.items()}
        dependency_finish = {task_id: 0 for task_id in tasks}
        for task_id, task in tasks.items():
            for dependency in sorted(task["depends_on"]):
                if dependency in dependents:
                    dependents[dependency].append(task_id)
        for task_id in dependents:
            dependents[task_id].sort(key=lambda current: (tasks[current]["machine"].lower(), tasks[current]["item"].lower(), current))

        rows = []
        process_rows = []
        unknown = set()

        def ready_priority(task_id):
            task = tasks[task_id]
            machine = task["machine"] or "Recipe"
            simultaneous, ticks_per_craft = self.machine_setting(machine)
            duration = math.ceil(task["crafts"] / simultaneous) * ticks_per_craft
            return (
                dependency_finish[task_id],
                machine.lower(),
                -duration,
                task["item"].lower(),
                task_id,
            )

        ready = [ready_priority(task_id) for task_id, count in remaining_dependencies.items() if count == 0]
        heapq.heapify(ready)

        while ready:
            earliest, _machine_key, _duration_key, _item_key, task_id = heapq.heappop(ready)
            task = tasks[task_id]
            machine = task["machine"] or "Recipe"
            simultaneous, ticks_per_craft = self.machine_setting(machine)
            duration = math.ceil(task["crafts"] / simultaneous) * ticks_per_craft
            if ticks_per_craft <= 0:
                unknown.add(machine)
            start = earliest
            finish = start + duration

            rows.append({
                "item": task["item"],
                "machine": machine,
                "crafts": task["crafts"],
                "start": start,
                "finish": finish,
                "duration": duration,
                "unknown": ticks_per_craft <= 0,
            })
            process_rows.append({
                "process": f"{task['item']} ({machine})" if machine else task["item"],
                "crafts": task["crafts"],
                "ticks": finish,
                "unknown": ticks_per_craft <= 0,
            })

            for dependent in dependents.get(task_id, []):
                remaining_dependencies[dependent] -= 1
                dependency_finish[dependent] = max(dependency_finish[dependent], finish)
                if remaining_dependencies[dependent] == 0:
                    heapq.heappush(ready, ready_priority(dependent))

        if len(rows) != len(tasks):
            unknown.add("cycle or unresolved dependency")

        total_ticks = max((row["finish"] for row in rows), default=0)
        return {
            "rows": rows,
            "processes": sorted(process_rows, key=lambda row: (row["ticks"], row["process"].lower())),
            "total_ticks": total_ticks,
            "unknown": sorted(unknown),
        }

    def show_plan(self, plan):
        self.raw_tree.delete(*self.raw_tree.get_children())
        self.craft_tree.delete(*self.craft_tree.get_children())
        self.time_tree.delete(*self.time_tree.get_children())
        self.chain_text.delete("1.0", tk.END)

        for raw in sorted(plan["raw"].values(), key=lambda row: row["item"].lower()):
            self.raw_tree.insert("", tk.END, values=(raw["item"], format_amount_with_unit(raw["amount"], raw.get("unit", "item"))))

        for craft in sorted(plan["crafts"].values(), key=lambda row: row["item"].lower()):
            self.craft_tree.insert("", tk.END, values=(craft["item"], compact_amount_text(craft["amount"]), craft["machine"]))

        schedule = self.build_time_schedule(plan)
        for process in schedule["processes"]:
            ticks_text = "set ticks/craft" if process["unknown"] else compact_amount_text(process["ticks"])
            time_text = "unknown" if process["unknown"] else format_ticks(process["ticks"])
            self.time_tree.insert("", tk.END, values=(process["process"], compact_amount_text(process["crafts"]), ticks_text, time_text))

        if schedule["processes"]:
            total_text = "unknown" if schedule["unknown"] else format_ticks(schedule["total_ticks"])
            self.time_tree.insert("", tk.END, values=("Total estimate", len(schedule["rows"]), compact_amount_text(schedule["total_ticks"]), total_text))

        for choice in self.summarize_choices(plan["choices"]):
            self.chain_text.insert(tk.END, f"{choice}\n\n")
        for warning in plan["warnings"]:
            self.chain_text.insert(tk.END, f"Warning: {warning}\n\n")
        if schedule["unknown"]:
            self.chain_text.insert(tk.END, f"Time estimate needs ticks/craft for: {', '.join(schedule['unknown'])}\n\n", "missing_recipe")
        elif schedule["processes"]:
            self.chain_text.insert(tk.END, f"Estimated completion time: {compact_amount_text(schedule['total_ticks'])} ticks ({format_ticks(schedule['total_ticks'])})\n\n", "crafted_detail")

        self.insert_supply_chain_summary(plan)

    def insert_supply_chain_summary(self, plan):
        if plan["crafts"]:
            self.chain_text.insert(tk.END, "Crafted processes\n")
            for craft in sorted(plan["crafts"].values(), key=lambda row: (row["machine"].lower(), row["item"].lower())):
                detail = f"{compact_amount_text(craft['amount'])} craft(s)"
                if craft.get("machine"):
                    detail += f" in {craft['machine']}"
                self.chain_text.insert(tk.END, f"{craft['item']} - ")
                self.chain_text.insert(tk.END, detail, "crafted_detail")
                self.chain_text.insert(tk.END, "\n")
            self.chain_text.insert(tk.END, "\n")

        reusable = self.summarize_chain_nodes(plan["chain"], "reusable")
        if reusable:
            self.chain_text.insert(tk.END, "Reusable inputs\n")
            for node in reusable:
                self.chain_text.insert(tk.END, f"{node['item']} x{format_amount_with_unit(node['amount'], node.get('unit', 'item'))} - ")
                self.chain_text.insert(tk.END, "not consumed", "reusable_input")
                self.chain_text.insert(tk.END, "\n")
            self.chain_text.insert(tk.END, "\n")

        missing = self.summarize_chain_nodes(plan["chain"], "missing")
        if missing:
            self.chain_text.insert(tk.END, "No recipe\n")
            for node in missing:
                self.chain_text.insert(tk.END, f"{node['item']} x{format_amount_with_unit(node['amount'], node.get('unit', 'item'))} - ")
                self.chain_text.insert(tk.END, "no recipe", "missing_recipe")
                self.chain_text.insert(tk.END, "\n")
            self.chain_text.insert(tk.END, "\n")

        if plan["raw"]:
            self.chain_text.insert(tk.END, "Raw/base inputs\n")
            for raw in sorted(plan["raw"].values(), key=lambda row: row["item"].lower()):
                self.chain_text.insert(tk.END, f"{raw['item']} x{format_amount_with_unit(raw['amount'], raw.get('unit', 'item'))} - ")
                self.chain_text.insert(tk.END, "raw input", "raw_input")
                self.chain_text.insert(tk.END, "\n")

    def summarize_chain_nodes(self, nodes, node_type):
        summarized = {}
        for node in nodes:
            if node.get("type") != node_type:
                continue
            key = (node["item"].lower(), unit_kind(node.get("unit", "item")))
            current = summarized.setdefault(key, {"item": node["item"], "amount": 0, "unit": node.get("unit", "item")})
            current["amount"] += node.get("amount", 0)
            if unit_kind(node.get("unit", "item")) == "fluid":
                current["unit"] = "mB"
        return sorted(summarized.values(), key=lambda row: row["item"].lower())

    def summarize_choices(self, choices):
        counts = {}
        messages = {}
        ordered = []
        for choice in choices:
            key = self.choice_summary_key(choice)
            if key not in counts:
                ordered.append(key)
                counts[key] = 0
                messages[key] = choice
            counts[key] += 1
        summarized = []
        for key in ordered:
            suffix = f" (used {counts[key]} times)" if counts[key] > 1 else ""
            summarized.append(f"{messages[key]}{suffix}")
        return summarized

    def choice_summary_key(self, choice):
        if not choice.startswith("Picked cheapest "):
            return choice
        prefix, _compared, _rest = choice.partition(". Compared ")
        return prefix


def main():
    PROFILE_ROOT.mkdir(exist_ok=True)
    app = CalculatorApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
