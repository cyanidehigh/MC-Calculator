# MCCalculator Handoff

## Purpose

MCCalculator is a native Python/Tkinter desktop app for planning modded Minecraft production chains. It lets the user define profiles per modpack, add arbitrary recipes, calculate requirements for a desired output, and choose the cheapest available alternate route by raw material cost.

## Active Working Copy

The active project the user works from is:

```text
H:\projects\MCCalculator\MC Calculator
```

There may also be older workspace copies at:

```text
F:\MCCalculator
H:\projects\MCCalculator
C:\Users\tarad\Documents\DATA SET\MCCalculator
```

Future edits, tests, and launches should target `H:\projects\MCCalculator\MC Calculator` directly. The nested `H:` copy is the one the user runs and where current recipe data lives.

The app is designed to be portable. Storage is rooted from the folder containing `desktop_app.py`:

```python
ROOT = Path(__file__).resolve().parent
PROFILE_ROOT = ROOT / "profile"
```

That means the whole project folder can be moved to another drive/computer as long as `desktop_app.py`, `launch.bat`, `profile/`, and any desired `assets/` files move together.

## Entry Points

- `launch.bat`: Windows launcher. Uses `py` first, then `python`.
- `desktop_app.py`: Current native desktop app.
- `profile/`: Persistent recipe storage.

The original HTML/CSS/JavaScript prototype was removed after the project moved to the native Tkinter app. The active application is now only `desktop_app.py`.

## Runtime Requirements

- Python 3.10+ recommended.
- No third-party packages.
- Uses only Python standard library modules, mainly `tkinter`, `json`, `pathlib`, and `dataclasses`.

## Data Layout

Recipes are stored on disk under:

```text
profile/
  <profile name>/
    profile.json
    <recipe output>-<recipe id>.json
```

Example recipe file:

```json
{
  "id": "recipe-20260530123013581207",
  "output": "Molten Iron",
  "outputAmount": 1,
  "outputUnit": "B",
  "machine": "Smeltery",
  "inputs": [
    {
      "item": "Iron Ingot",
      "amount": 1,
      "unit": "item",
      "consumed": true
    },
    {
      "item": "Cast",
      "amount": 1,
      "unit": "item",
      "consumed": false
    }
  ]
}
```

Profile metadata can also store desired routes and base materials:

```json
{
  "id": "profile-...",
  "name": "Gears and Gardens",
  "recipeCount": 42,
  "preferredRoutes": {
    "redstone dust": "recipe-20260603123456000000"
  },
  "baseMaterials": [
    "ender pearl::item",
    "molten iron::fluid"
  ],
  "machines": {
    "Extended Molecular Assembler": {
      "simultaneousCrafts": 8,
      "ticksPerCraft": 100
    }
  }
}
```

Supported units:

- `item`
- `B`
- `mB`

Fluid conversion:

```text
1B = 1000mB
```

Missing legacy fields are tolerated:

- Missing `outputUnit` defaults to `item`.
- Missing input `unit` defaults to `item`.
- Missing input `consumed` defaults to `true`.

## Calculation Model

The planner is in these functions:

- `group_recipes(recipes)`
- `build_best_plan(item, amount, recipes_by_output, stack=None, depth=0, unit="item")`
- `build_recipe_plan(recipe, amount, recipes_by_output, stack, depth)`
- `merge_plan(target, source)`

Important behavior:

- Recipe outputs are grouped by output item name, case-insensitive.
- If multiple recipes produce the same item, every route is evaluated.
- If a desired route is set for an output, that route is used directly.
- If no desired route is set, the cheapest route is selected by total raw material quantity.
- Base materials are treated as raw inputs even if recipes exist for them.
- Fluids are converted to base `mB` internally.
- Non-consumed inputs are treated as reusable catalysts: required once for that recipe path, not multiplied by craft count.
- Circular chains are detected and counted as raw inputs with a warning.
- The planner also emits a task graph for crafted recipe work. Each task knows its recipe, craft count, machine/process, and crafted-input dependencies.
- Time estimates use that task graph. A task can start when its dependency tasks are finished and a slot is free on its machine/process.
- Task duration is `crafts * ticksPerCraft`.
- `simultaneousCrafts` controls how many separate material/process jobs can run on that machine/process at once.
- Missing `ticksPerCraft` makes that process time unknown rather than guessing.

## UI Structure

The main class is `CalculatorApp(tk.Tk)`.

Key UI builder methods:

- `build_ui()`
- `build_sidebar()`
- `build_editor()`
- `build_calculator()`

Important workflow methods:

- `refresh_all()`
- `refresh_recipe_list()`
- `select_recipe()`
- `read_recipe_form()`
- `save_recipe()`
- `delete_recipe()`
- `calculate()`
- `show_plan(plan)`

The recipe editor supports:

- Output item
- Output amount and unit
- Machine/process dropdown based on existing profile machines
- `Desired route for this output` checkbox, which stores the current recipe as the profile's preferred route for that output.
- `Treat output as base material` checkbox, which stops recursive expansion for that output.
- Multiple input rows
- Input amount and unit
- Per-input `Doesn't use` checkbox for catalysts/reusable ingredients

The calculator supports:

- Desired item dropdown based on known recipe outputs
- Desired amount and unit
- Per-profile desired routes via the recipe editor checkbox
- Per-profile base material stop-points via the recipe editor checkbox
- Per-profile machine/process settings via the `Machines` button
- Raw requirements table
- Crafting workload table
- Time estimate table
- Supply chain and choices text panel

## Styling

Colors are centralized in the `COLORS` dictionary near the top of `desktop_app.py`.

Logo loading checks these paths:

```text
assets/logo.png
logo.png
assets/logo.gif
logo.gif
```

Tkinter `PhotoImage` supports PNG and GIF on the current target environment.

## Known UX Decisions

- Saving a new recipe clears the editor afterward.
- Saving an existing recipe keeps it loaded.
- Selecting a recipe also sets it as the calculation target.
- Recipes are shown in an expandable tree: parent rows are output items, child rows are individual routes.
- Selecting an output parent sets the calculation target and expands/collapses that output; selecting a route child loads that recipe into the editor.
- Alternate-route choice messages are deduplicated by selected route, not exact full message text.
- Raw inputs are highlighted gold in the supply chain panel.
- Missing recipes are shown as `no recipe` and highlighted red in the supply chain panel.
- Crafted process details, such as `52.92k craft(s) in Matter Condenser`, are highlighted green.
- Reusable/non-consumed inputs are highlighted teal as `not consumed`.
- Large displayed item counts use compact suffixes: `k`, `M`, `B`, `T`.
- Fluid amounts display as `mB` below 1000 and `B` at or above 1000.
- Desired routes override automatic route choice.
- Base materials stop recursive recipe expansion for selected materials.
- Desired route and base material settings are changed directly from the recipe editor checkboxes.
- `Machines` opens a per-profile dialog for simultaneous crafts and ticks per craft. Minecraft runs at 20 ticks per second. These values feed the time estimate table.
- Time and simultaneous-crafting calculations live at the machine/process level rather than as material recipe fields.
- The supply-chain text panel summarizes repeated work by material/process instead of rendering every recursive occurrence.

## Likely Next Improvements

Good next features:

- Input item autocomplete from known outputs and raw inputs.
- Search/filter for recipe list.
- Explicit recipe categories or tags.
- More advanced route comparison, such as energy, time, rarity presets, or per-machine preferences.
- Per-profile settings, such as preferred machines or banned recipes.
- Use saved machine/process settings to estimate total time, parallel workload, and bottlenecks.
- Import from common mod recipe export formats, if available.
- Packaging into a standalone `.exe` with PyInstaller.

Riskier changes:

- Reworking the planner to optimize globally rather than locally per sub-route.
- Adding full fluid/item type separation by item ID rather than display name.
- Supporting ore dictionary/tags like `#forge:ingots/copper`.

## Packaging Notes

The app should package cleanly with PyInstaller later because it has no third-party dependencies.

Likely command:

```powershell
pyinstaller --onefile --windowed desktop_app.py
```

If packaged, make sure the app can still find or create its `profile/` directory. The current code roots storage at:

```python
ROOT = Path(__file__).resolve().parent
PROFILE_ROOT = ROOT / "profile"
```

For a one-file executable, this may need to change to use the executable directory or an app data folder.
