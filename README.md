# MCCalculator

MCCalculator is a portable desktop production-chain calculator for modded Minecraft.

It is built for packs where recipes, machines, passive resource generation, alternate routes, and reusable crafting items can make spreadsheet planning painful. The app lets you enter recipes by hand, group them by modpack profile, and calculate what is needed to make a chosen amount of an item.

## Requirements

- Windows
- Python 3.10 or newer
- No third-party Python packages

## Running The App

Double-click:

```text
launch.bat
```

The launcher tries `py` first, then `python`.

You can also run it manually:

```text
python desktop_app.py
```

## Portable Storage

The app stores all profile and recipe data inside the project folder:

```text
profile/
  <profile name>/
    profile.json
    <recipe files>.json
```

This means the whole folder can be moved to another drive or computer. Keep these together:

- `desktop_app.py`
- `launch.bat`
- `profile/`
- `assets/` if you want the logo

## Core Workflow

1. Create or select a profile for your modpack.
2. Add recipes in **Add or edit recipe**.
3. Set the output item, output amount, machine/process, and inputs.
4. Save the recipe.
5. Choose a desired item and amount in **Calculate production**.
6. Press **Calculate**.

The result shows:

- raw/base requirements
- crafting workload
- time estimate
- route choices and supply-chain summary

## Recipes

Each recipe has:

- output item
- output amount
- output unit
- machine/process
- input items
- input amounts
- input units

Supported units:

- `item`
- `B`
- `mB`

Fluid conversion:

```text
1B = 1000mB
```

## Reusable Inputs

Some recipes use an item without consuming it, such as molds, casts, tools, or crafting catalysts.

Use the **Doesn't use** checkbox on an input row for these items. The calculator will treat that input as required, but not consumed per craft.

## Alternate Routes

You can add multiple recipes with the same output item.

By default, the calculator compares available routes and picks the route with the lowest expanded raw/base material count. This is useful, but still basic: it does not yet understand rarity, EMC, energy, passive buffers, or global resource value.

For routes you know should always be used, tick:

```text
Desired route for this output
```

Desired routes override automatic route choice for that output.

## Base Materials

Sometimes you want the calculator to stop expanding an item, even if a recipe exists for it. For example, passive farm outputs, buffered materials, or anything you simply want counted as a requirement.

Tick:

```text
Treat output as base material
```

That item will then appear as a raw/base requirement instead of being recursively crafted.

## Machine Settings And Time

Machine/process settings are stored per profile from the **Machines** button.

Each machine/process can have:

- `Ticks per craft`
- `Simultaneous crafts`

Minecraft runs at:

```text
20 ticks = 1 second
```

The time estimate uses the calculated craft workload, recipe dependencies, and machine settings. A craft can only begin once its required crafted inputs are ready and a slot is free on its machine/process.

If a machine/process does not have ticks per craft set, the time estimate will show that timing is unknown for that process.

## Current Limitations

- Recipes are entered manually.
- Automatic route choice is based on expanded raw/base quantity, not custom material value.
- Route choice is not yet a full global optimizer.
- Chance-based outputs should be entered as guaranteed recipes only, or handled manually.
- Time estimates are a planning aid and may not match every mod's internal automation behavior.
