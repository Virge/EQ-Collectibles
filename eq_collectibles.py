#!/usr/bin/env python3
"""EverQuest Achievement Collectibles Tracker"""

import os
import json
import glob
import sys
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus

def clear():
    os.system("cls" if os.name == "nt" else "clear")


CONFIG_DIR = Path.home() / ".config" / "eq_collectibles"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def save_config(config):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def find_files(folder, suffix):
    pattern = os.path.join(folder, f"*{suffix}")
    return sorted(glob.glob(pattern))


def prompt_folder(prompt_text="Enter folder path: "):
    while True:
        raw = input(prompt_text).strip()
        folder = os.path.expanduser(raw)
        if os.path.isdir(folder):
            return folder
        print(f"  Directory not found: {folder}")


def prompt_file(folder, suffix, label):
    files = find_files(folder, suffix)
    if not files:
        print(f"  No {suffix} files found in: {folder}")
        return None

    print(f"\nAvailable {label} files:")
    for i, f in enumerate(files, 1):
        print(f"  {i}. {os.path.basename(f)}")

    while True:
        raw = input("\nSelect file number (or Enter to cancel): ").strip()
        if raw == "":
            return None
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(files):
                return files[idx]
        except ValueError:
            pass
        print("  Invalid selection, try again.")


# ---------------------------------------------------------------------------
# Achievements parser
# ---------------------------------------------------------------------------

def parse_achievements(filepath):
    """
    Returns {expansion: {group_name: [missing_item_name, ...]}}

    File format (tab-separated, Windows line endings):
      Section header : "Expansion Name: Category"   (no leading status char)
      Depth-0 item   : "STATUS\\tName"
      Depth-1 item   : "STATUS\\t\\tName[\\tprogress]"

    In a Collections section depth-0 items are collection group headers;
    depth-1 items are individual collectibles. Missing ones have status "I"
    and progress "0/N".
    """
    expansions = {}
    in_collections = False
    current_expansion = None
    current_group = None

    with open(filepath, encoding="latin-1") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if not line:
                continue

            if not (line.startswith("I\t") or line.startswith("C\t")):
                if ": " in line:
                    expansion, category = line.split(": ", 1)
                    current_expansion = expansion.strip()
                    in_collections = category.strip() == "Collections"
                    current_group = None
                    if in_collections and current_expansion not in expansions:
                        expansions[current_expansion] = {}
                continue

            if not in_collections:
                continue

            parts = line.split("\t")
            status = parts[0]

            depth = 0
            name_idx = 1
            while name_idx < len(parts) and parts[name_idx] == "":
                depth += 1
                name_idx += 1

            if name_idx >= len(parts):
                continue

            name = parts[name_idx]
            progress = parts[name_idx + 1] if name_idx + 1 < len(parts) else None

            if depth == 0:
                current_group = name
            elif depth == 1 and current_group and status == "I" and progress:
                p = progress.split("/")
                if len(p) == 2:
                    try:
                        if int(p[0]) < int(p[1]):
                            expansions[current_expansion].setdefault(current_group, []).append(name)
                    except ValueError:
                        pass

    return expansions


# ---------------------------------------------------------------------------
# House storage parser
# ---------------------------------------------------------------------------

def parse_house(filepath):
    """
    Returns a set of item names (lowercased for case-insensitive matching).

    House file format: one item name per line, plain text.
    Example filename: 108BrimmingWay_House.txt
    """
    names = set()
    with open(filepath, encoding="latin-1") as f:
        for line in f:
            name = line.rstrip("\r\n").strip()
            if name:
                names.add(name.lower())
    return names


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def prompt_expansion(expansions):
    names = sorted(expansions.keys())
    print("\nAvailable expansions with collection data:")
    for i, name in enumerate(names, 1):
        missing = sum(len(v) for v in expansions[name].values())
        marker = f"  ({missing} missing)" if missing else "  (complete)"
        print(f"  {i}. {name}{marker}")

    while True:
        raw = input("\nSelect expansion number: ").strip()
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(names):
                return names[idx]
        except ValueError:
            pass
        print("  Invalid selection, try again.")


def open_allakhazam(item_name):
    url = "https://everquest.allakhazam.com/search.html?q=" + quote_plus(item_name)
    webbrowser.open(url)


def prompt_item_lookup(items):
    """Prompt user to pick an item number to look up on Allakhazam."""
    while True:
        raw = input("  Enter item number to look up on Allakhazam, or Enter to continue: ").strip()
        if not raw:
            break
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(items):
                open_allakhazam(items[idx])
            else:
                print(f"  Enter a number between 1 and {len(items)}.")
        except ValueError:
            print("  Enter a number or press Enter to skip.")


def show_missing(expansions, expansion, bag_items=None):
    """
    Print missing collectibles for an expansion.

    If bag_items (set of lowercased names) is provided, items found in the
    bag are marked with [IN BAG] so the player knows they can turn them in.
    """
    groups = expansions.get(expansion, {})
    missing_groups = {g: items for g, items in groups.items() if items}

    if not missing_groups:
        print(f"\n  All collectibles complete for: {expansion}")
        return

    total = sum(len(v) for v in missing_groups.values())
    in_bag_total = 0

    # Build output lines first so we can show the in-bag count in the header
    all_items = []
    output = []
    for group, items in sorted(missing_groups.items()):
        lines = []
        in_bag_count = 0
        for item in items:
            num = len(all_items) + 1
            all_items.append(item)
            if bag_items and item.lower() in bag_items:
                lines.append(f"  {num:3}. >>> {item}  [IN BAG]")
                in_bag_count += 1
                in_bag_total += 1
            else:
                lines.append(f"  {num:3}. -   {item}")
        group_header = f"  {group}  [{len(items)} missing"
        if in_bag_count:
            group_header += f", {in_bag_count} in bag"
        group_header += "]"
        output.append((group_header, lines))

    print(f"\nMissing collectibles for: {expansion}")
    print("=" * 60)
    header = f"Total missing: {total}"
    if bag_items is not None:
        header += f"  |  In bag: {in_bag_total}"
    print(header)

    if bag_items is not None and in_bag_total == 0:
        print("  (none of your missing collectibles are currently in your bag)")

    for group_header, lines in output:
        print()
        print(group_header)
        for line in lines:
            print(line)
    print()
    prompt_item_lookup(all_items)


def print_columns(rows, headers, numbered=False):
    """Print a list of equal-length tuples as padded columns with a header."""
    if numbered:
        headers = ("#",) + tuple(headers)
        rows = [(str(i + 1),) + tuple(row) for i, row in enumerate(rows)]

    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    fmt = "  " + "  ".join(f"{{:<{w}}}" for w in widths)
    separator = "  " + "  ".join("-" * w for w in widths)

    print(fmt.format(*headers))
    print(separator)
    for row in rows:
        print(fmt.format(*row))


def show_compare(expansions, expansion, bag_items):
    groups = expansions.get(expansion, {})
    matches = sorted(
        (item, group)
        for group, items in groups.items()
        for item in items
        if item.lower() in bag_items
    )

    print(f"\nHouse matches for: {expansion}")
    print("=" * 60)

    if not matches:
        print("  No missing collectibles from this expansion are in your house.")
        return

    print(f"Total: {len(matches)}\n")
    print_columns(matches, ["Item", "Collection"], numbered=True)
    print()
    prompt_item_lookup([m[0] for m in matches])


def show_all_expansions_vs_house(expansions, bag_items):
    matches = sorted(
        (item, group, expansion)
        for expansion, groups in expansions.items()
        for group, items in groups.items()
        for item in items
        if item.lower() in bag_items
    )

    if not matches:
        print("\n  No missing collectibles from any expansion are in your house.")
        return

    print(f"\nHouse matches — all expansions")
    print("=" * 60)
    print(f"Total: {len(matches)}\n")
    print_columns(matches, ["Item", "Collection", "Expansion"], numbered=True)
    print()
    prompt_item_lookup([m[0] for m in matches])


def show_all_houses_vs_all_expansions(expansions, folder):
    """
    Load every *_House.txt in folder, combine them, and show all missing
    collectibles found across all expansions as a flat sorted column list.
    Includes a House File column so you know where each item was found.
    """
    house_files = find_files(folder, "_House.txt")
    if not house_files:
        print(f"\n  No *_House.txt files found in: {folder}")
        return

    # Build a mapping: lowercased item name -> house file basename
    # If an item appears in multiple houses, keep the first file found.
    item_source = {}
    for path in house_files:
        label = os.path.basename(path)
        for name in parse_house(path):
            item_source.setdefault(name, label)

    print(f"\n  Loaded {len(house_files)} house file(s), {len(item_source)} unique item(s).")

    matches = sorted(
        (item, group, expansion, item_source[item.lower()])
        for expansion, groups in expansions.items()
        for group, items in groups.items()
        for item in items
        if item.lower() in item_source
    )

    if not matches:
        print("\n  No missing collectibles from any expansion were found in any house file.")
        return

    print(f"\nAll house files vs. all expansions")
    print("=" * 60)
    print(f"Total: {len(matches)}\n")
    print_columns(matches, ["Item", "Collection", "Expansion", "House File"], numbered=True)
    print()
    prompt_item_lookup([m[0] for m in matches])


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

HELP_TEXT = """
EverQuest Collectibles Tracker — How It Works
=============================================

OVERVIEW
  This tool reads your EverQuest character achievement export and shows you
  which collectible items you are still missing, organized by expansion.
  You can also load a house storage file to see which of those missing items
  you already have stashed away and are ready to turn in.

FILES USED
  Achievements file  (*-Achievements.txt)
    Exported directly from EverQuest. Contains your full achievement progress
    including collection completion status. The file is named after your
    character and server, e.g.:
      Pixelhero_firiona-Achievements.txt

  House storage file  (*_House.txt)
    A plain text list of items stored in your in-game house, one item name
    per line. Because EverQuest has no built-in house export, these files are
    created manually:
      1. Take screenshots of your house inventory in-game.
      2. Paste the screenshots into ChatGPT and ask it to extract the item
         names into a clean list.
      3. Save that list as a text file named with the _House.txt suffix, e.g.:
           108BrimmingWay_House.txt
    Place the file in the same folder as your achievements file so the app
    can find it automatically.

MENU OPTIONS
   1. Select achievements file
        Pick which character's achievement file to load. The selection is
        remembered and auto-loaded on the next run.

   2. Reload achievements file
        Re-parse the currently loaded achievements file without changing which
        file is selected. Use this after exporting a fresh copy from EverQuest
        so the app picks up newly completed collectibles.

   3. Select house storage file
        Pick a single house storage file to use for comparisons in options 6
        and 7.

   4. Reload house storage file
        Re-parse the currently selected house file. Use this after you have
        updated the file with a new ChatGPT export.

   5. Browse missing collectibles by expansion
        Select an expansion and see the full list of collectibles you have not
        yet obtained, grouped by collection set.

   6. Compare missing collectibles against house file (one expansion)
        Select an expansion and see which of your missing collectibles for that
        expansion are in the selected house file, ready to be turned in.
        Output is a sorted column list: Item | Collection.

   7. Compare missing collectibles against house file (all expansions)
        Same as option 6 but scans every expansion at once and shows a single
        sorted list across all of them.
        Output is a sorted column list: Item | Collection | Expansion.

   8. Compare all house files against achievement list
        Automatically loads every *_House.txt file in the folder, combines
        them, and shows all missing collectibles found across all expansions.
        Output is a sorted column list: Item | Collection | Expansion | House File.
        Useful when your collectibles are spread across multiple storage houses.

   9. Change folder
        Set a different folder to look for achievement and house files.
        Clears the remembered achievements file so you can pick a new one.

  10. How to use this app
        Display these instructions.

  11. Exit

TIPS
  - Re-export your achievements file from EverQuest after a play session, then
    use option 2 (Reload) to refresh the app without restarting.
  - When you update a house file with a new ChatGPT export, use option 4
    (Reload) to pick up the changes without re-selecting the file.
  - Option 8 is the quickest way to see everything across all your houses at
    once — it finds all *_House.txt files automatically.
  - The app saves your folder and last-used achievements file to:
      ~/.config/eq_collectibles/config.json
"""

def show_help():
    print(HELP_TEXT)
    input("  Press Enter to return to the menu...")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    config = load_config()
    clear()

    # First-run folder setup
    folder = config.get("folder")
    if not folder or not os.path.isdir(folder):
        print("\nNo folder configured. Please set one up.")
        folder = prompt_folder("Enter folder path containing EQ character files: ")
        config["folder"] = folder
        save_config(config)

    # Auto-load previously used achievements file
    current_ach_file = config.get("achievements_file")
    if current_ach_file and os.path.isfile(current_ach_file):
        print(f"\n  Auto-loading {os.path.basename(current_ach_file)} ...")
        expansions = parse_achievements(current_ach_file)
        print(f"  Found {len(expansions)} expansion(s) with collection data.")
    else:
        current_ach_file = None
        expansions = {}

    current_inv_file = None
    bag_items = None

    while True:
        clear()
        ach_label = os.path.basename(current_ach_file) if current_ach_file else "(none)"
        inv_label = os.path.basename(current_inv_file) if current_inv_file else "(none)"

        print("=" * 50)
        print("  EverQuest Collectibles Tracker")
        print("=" * 50)
        print(f"\nFolder       : {folder}")
        print(f"Achievements : {ach_label}")
        print(f"House storage: {inv_label}")
        print()
        print("  1. Select achievements file")
        print("  2. Reload achievements file")
        print("  3. Select house storage file")
        print("  4. Reload house storage file")
        print("  5. Browse missing collectibles by expansion")
        print("  6. Compare missing collectibles against house file (one expansion)")
        print("  7. Compare missing collectibles against house file (all expansions)")
        print("  8. Compare all house files against achievement list")
        print("  9. Change folder")
        print(" 10. How to use this app")
        print(" 11. Exit")

        choice = input("\nChoice: ").strip()
        clear()

        if choice == "1":
            path = prompt_file(folder, "-Achievements.txt", "achievements")
            if path:
                current_ach_file = path
                config["achievements_file"] = current_ach_file
                save_config(config)
                print(f"\n  Parsing {os.path.basename(current_ach_file)} ...")
                expansions = parse_achievements(current_ach_file)
                print(f"  Found {len(expansions)} expansion(s) with collection data.")
            input("\n  Press Enter to continue...")

        elif choice == "2":
            if not current_ach_file:
                print("\n  No achievements file loaded to reload (use option 1 first).")
            else:
                print(f"\n  Reloading {os.path.basename(current_ach_file)} ...")
                expansions = parse_achievements(current_ach_file)
                print(f"  Found {len(expansions)} expansion(s) with collection data.")
            input("\n  Press Enter to continue...")

        elif choice == "3":
            path = prompt_file(folder, "_House.txt", "house storage")
            if path:
                current_inv_file = path
                print(f"\n  Parsing {os.path.basename(current_inv_file)} ...")
                bag_items = parse_house(current_inv_file)
                print(f"  Loaded {len(bag_items)} item(s) from house storage.")
            else:
                answer = input("  Clear current house file? (y/n): ").strip().lower()
                if answer == "y":
                    current_inv_file = None
                    bag_items = None
                    print("  House file cleared.")
            input("\n  Press Enter to continue...")

        elif choice == "4":
            if not current_inv_file:
                print("\n  No house file loaded to reload (use option 3 first).")
            else:
                print(f"\n  Reloading {os.path.basename(current_inv_file)} ...")
                bag_items = parse_house(current_inv_file)
                print(f"  Loaded {len(bag_items)} item(s) from house storage.")
            input("\n  Press Enter to continue...")

        elif choice == "5":
            if not expansions:
                print("\n  Please select an achievements file first (option 1).")
                input("\n  Press Enter to continue...")
                continue
            while True:
                clear()
                expansion = prompt_expansion(expansions)
                clear()
                show_missing(expansions, expansion)
                again = input("Check another expansion? (y/n): ").strip().lower()
                if again != "y":
                    break

        elif choice == "6":
            if not expansions:
                print("\n  Please select an achievements file first (option 1).")
                input("\n  Press Enter to continue...")
                continue
            if not bag_items:
                print("\n  Please select a house storage file first (option 3).")
                input("\n  Press Enter to continue...")
                continue
            while True:
                clear()
                expansion = prompt_expansion(expansions)
                clear()
                print(f"  Comparing against: {os.path.basename(current_inv_file)}")
                show_compare(expansions, expansion, bag_items)
                again = input("Check another expansion? (y/n): ").strip().lower()
                if again != "y":
                    break

        elif choice == "7":
            if not expansions:
                print("\n  Please select an achievements file first (option 1).")
                input("\n  Press Enter to continue...")
                continue
            if not bag_items:
                print("\n  Please select a house storage file first (option 3).")
                input("\n  Press Enter to continue...")
                continue
            print(f"  Comparing all expansions against: {os.path.basename(current_inv_file)}")
            show_all_expansions_vs_house(expansions, bag_items)
            input("\n  Press Enter to continue...")

        elif choice == "8":
            if not expansions:
                print("\n  Please select an achievements file first (option 1).")
                input("\n  Press Enter to continue...")
                continue
            show_all_houses_vs_all_expansions(expansions, folder)
            input("\n  Press Enter to continue...")

        elif choice == "9":
            folder = prompt_folder("Enter folder path containing EQ character files: ")
            config["folder"] = folder
            config.pop("achievements_file", None)
            save_config(config)
            current_ach_file = None
            current_inv_file = None
            expansions = {}
            bag_items = None
            input("\n  Press Enter to continue...")

        elif choice == "10":
            show_help()

        elif choice == "11":
            clear()
            print("Goodbye!")
            break

        else:
            print("  Invalid choice.")
            input("\n  Press Enter to continue...")


if __name__ == "__main__":
    main()
