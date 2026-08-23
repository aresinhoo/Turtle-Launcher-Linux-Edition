import os
import re
import sys
import json
import time
import shutil
import threading
import subprocess
import customtkinter as ctk
from tkinter import filedialog
from PIL import Image

def get_app_dir():
    """Directory of the running script, or the .exe itself when frozen with PyInstaller.
    NOT used for data storage: with --onefile this is a throwaway temp folder at runtime."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_persistent_data_dir():
    """A writable folder that survives restarts, app updates, and PyInstaller's
    --onefile temp-extraction (sys._MEIPASS gets deleted when the process exits)."""
    app_name = "TurtleLauncher"
    if sys.platform == "win32":
        base = os.getenv("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.getenv("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    path = os.path.join(base, app_name)
    os.makedirs(path, exist_ok=True)
    return path


def get_resource_path(relative_path):
    """Path to a bundled read-only resource (e.g. assets/icon.png). Works both
    running from source and frozen, where PyInstaller unpacks bundled files to
    sys._MEIPASS at runtime."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)


BASE_DIR = get_app_dir()
DATA_DIR = get_persistent_data_dir()
ICONS_DIR = os.path.join(DATA_DIR, "icons")
GAMES_DIR = os.path.join(DATA_DIR, "games")
GAMES_FILE = os.path.join(DATA_DIR, "games.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
ASSETS_DIR = get_resource_path("assets")
APP_ICON_PNG = os.path.join(ASSETS_DIR, "icon.png")

os.makedirs(ICONS_DIR, exist_ok=True)
os.makedirs(GAMES_DIR, exist_ok=True)

DEFAULT_SETTINGS = {"appearance_mode": "Dark", "color_theme": "green"}
THEME_OPTIONS = {"Blue": "blue", "Green": "green", "Dark Blue": "dark-blue"}
REVERSE_THEME_OPTIONS = {v: k for k, v in THEME_OPTIONS.items()}

games = []
settings = {}
current_view = "home"
games_list_frame = None
search_var = None


def load_settings():
    global settings
    try:
        with open(SETTINGS_FILE, "r") as file:
            settings = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        settings = {}
    for key, value in DEFAULT_SETTINGS.items():
        settings.setdefault(key, value)

    if settings.get("color_theme") not in THEME_OPTIONS.values():
        settings["color_theme"] = DEFAULT_SETTINGS["color_theme"]
    if settings.get("appearance_mode") not in ("Light", "Dark", "System"):
        settings["appearance_mode"] = DEFAULT_SETTINGS["appearance_mode"]


def save_settings():
    with open(SETTINGS_FILE, "w") as file:
        json.dump(settings, file, indent=4)


def save_games():
    with open(GAMES_FILE, "w") as file:
        json.dump(games, file, indent=4)


def load_games():
    global games
    try:
        with open(GAMES_FILE, "r") as file:
            games = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        games = []
    for game in games:
        game.setdefault("icon", "")
        game.setdefault("favourite", False)
        game.setdefault("playtime", 0)
        game.setdefault("install_dir", "")


def sanitize_filename(name):
    return re.sub(r"[^A-Za-z0-9_-]", "_", name) or "icon"


def show_error(message):
    popup = ctk.CTkToplevel(app)
    popup.title("Error")
    popup.geometry("350x160")
    popup.grab_set()

    label = ctk.CTkLabel(popup, text=message, wraplength=300)
    label.pack(pady=30, padx=20)

    ok_button = ctk.CTkButton(popup, text="OK", command=popup.destroy)
    ok_button.pack(pady=10)


def confirm_dialog(message, on_confirm):
    popup = ctk.CTkToplevel(app)
    popup.title("Confirm")
    popup.geometry("350x160")
    popup.grab_set()

    label = ctk.CTkLabel(popup, text=message, wraplength=300)
    label.pack(pady=20, padx=20)

    button_frame = ctk.CTkFrame(popup, fg_color="transparent")
    button_frame.pack(pady=10)

    def confirm():
        popup.destroy()
        on_confirm()

    yes_button = ctk.CTkButton(
        button_frame, text="Yes", fg_color="#a83232", hover_color="#7a2424", command=confirm
    )
    yes_button.pack(side="left", padx=10)

    cancel_button = ctk.CTkButton(button_frame, text="Cancel", command=popup.destroy)
    cancel_button.pack(side="left", padx=10)


def copy_game_locally(source_exe_path, game_name):
    """Copy the folder containing the selected .exe into the local GAMES_DIR
    so the launcher owns a persistent local copy of the game."""
    source_dir = os.path.dirname(source_exe_path)
    folder_name = f"{sanitize_filename(game_name)}_{os.urandom(4).hex()}"
    dest_dir = os.path.join(GAMES_DIR, folder_name)

    shutil.copytree(source_dir, dest_dir)

    rel_exe_path = os.path.relpath(source_exe_path, source_dir)
    dest_exe_path = os.path.join(dest_dir, rel_exe_path)
    return dest_dir, dest_exe_path


def addgame():
    file_path = filedialog.askopenfilename(
        title="Select a Game",
        filetypes=[("Executable Files", "*.exe")]
    )

    if not file_path:
        return

    game_name = os.path.splitext(os.path.basename(file_path))[0]

    try:
        install_dir, local_exe_path = copy_game_locally(file_path, game_name)
    except Exception as e:
        show_error(f"Could not copy game into local storage:\n{e}")
        return

    games.append({
        "name": game_name,
        "path": local_exe_path,
        "install_dir": install_dir,
        "icon": "",
        "favourite": False,
        "playtime": 0
    })

    save_games()
    show_library()


def play_game(game):
    def run():
        start_time = time.time()
        try:
            process = subprocess.Popen(game["path"], cwd=os.path.dirname(game["path"]))
        except Exception as e:
            app.after(0, lambda: show_error(f"Could not launch {game['name']}:\n{e}"))
            return

        process.wait()
        elapsed = time.time() - start_time
        game["playtime"] = game.get("playtime", 0) + elapsed
        save_games()
        app.after(0, refresh_current_view)

    threading.Thread(target=run, daemon=True).start()


def favourite_game(game):
    game["favourite"] = not game.get("favourite", False)
    save_games()
    refresh_current_view()


def edit_game(game):
    popup = ctk.CTkToplevel(app)
    popup.title("Edit Game")
    popup.geometry("400x340")
    popup.grab_set()

    title = ctk.CTkLabel(popup, text="Edit Game", font=("Segoe UI", 22, "bold"))
    title.pack(pady=15)

    def load_preview_image():
        icon_path = game.get("icon")
        if icon_path and os.path.exists(icon_path):
            try:
                return ctk.CTkImage(
                    light_image=Image.open(icon_path),
                    dark_image=Image.open(icon_path),
                    size=(64, 64)
                )
            except Exception as e:
                print(f"Could not load icon preview: {e}")
        return None

    preview_label = ctk.CTkLabel(popup, text="No Icon", image=None)
    preview_label.pack(pady=(0, 10))

    def refresh_preview():
        img = load_preview_image()
        if img:
            preview_label.configure(image=img, text="")
            preview_label.image = img
        else:
            preview_label.configure(image=None, text="No Icon")
            preview_label.image = None

    refresh_preview()

    name_entry = ctk.CTkEntry(popup, width=250)
    name_entry.pack(pady=10)
    name_entry.insert(0, game["name"])

    def change_icon():
        icon_path = filedialog.askopenfilename(
            title="Choose an Icon",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.ico")]
        )

        if not icon_path:
            return

        try:
            ext = os.path.splitext(icon_path)[1]
            dest_name = f"{sanitize_filename(game['name'])}_{os.urandom(4).hex()}{ext}"
            dest_path = os.path.join(ICONS_DIR, dest_name)

            with Image.open(icon_path) as img:
                img.save(dest_path)

            game["icon"] = dest_path
            save_games()
            refresh_preview()
        except Exception as e:
            show_error(f"Could not set icon:\n{e}")

    def remove_icon():
        game["icon"] = ""
        save_games()
        refresh_preview()

    def save_changes():
        new_name = name_entry.get().strip()
        if new_name:
            game["name"] = new_name

        save_games()
        popup.destroy()
        refresh_current_view()

    def cancel_edit():
        popup.destroy()

    def delete_game():
        popup.destroy()

        def do_delete():
            install_dir = game.get("install_dir")
            if install_dir and os.path.commonpath([os.path.abspath(install_dir), GAMES_DIR]) == GAMES_DIR:
                try:
                    shutil.rmtree(install_dir, ignore_errors=True)
                except Exception as e:
                    print(f"Could not remove local game files: {e}")

            if game in games:
                games.remove(game)
            save_games()
            refresh_current_view()

        confirm_dialog(f"Delete \"{game['name']}\" from your library?", do_delete)

    icon_button_frame = ctk.CTkFrame(popup, fg_color="transparent")
    icon_button_frame.pack(pady=(0, 15))

    icon_button = ctk.CTkButton(icon_button_frame, text="🖼️ Change Icon", command=change_icon)
    icon_button.pack(side="left", padx=5)

    remove_icon_button = ctk.CTkButton(
        icon_button_frame, text="✖ Remove Icon", fg_color="gray30", hover_color="gray20", command=remove_icon
    )
    remove_icon_button.pack(side="left", padx=5)

    button_frame = ctk.CTkFrame(popup, fg_color="transparent")
    button_frame.pack(pady=15)

    save_button = ctk.CTkButton(button_frame, text="Save Changes", command=save_changes)
    save_button.pack(pady=5, side="left", padx=5)

    cancel_button = ctk.CTkButton(button_frame, text="Cancel", command=cancel_edit)
    cancel_button.pack(pady=5, side="left", padx=5)

    delete_button = ctk.CTkButton(
        button_frame, text="Delete", fg_color="#a83232", hover_color="#7a2424", command=delete_game
    )
    delete_button.pack(pady=5, side="left", padx=5)


def create_game_card(parent, game, show_favourite=True):
    card = ctk.CTkFrame(parent, corner_radius=12)
    card.pack(fill="x", padx=25, pady=12, ipady=12)

    hours = game.get("playtime", 0) / 3600
    playtime_label = ctk.CTkLabel(card, text=f"⏱️ Playtime: {hours:.1f}h", font=("Segoe UI", 14))
    playtime_label.pack(anchor="w", padx=15)

    title_text = game["name"]
    if game.get("favourite", False):
        title_text = "⭐ " + title_text

    top_frame = ctk.CTkFrame(card, fg_color="transparent")
    top_frame.pack(fill="x", padx=15, pady=10)

    icon_path = game.get("icon")
    if icon_path and os.path.exists(icon_path):
        try:
            icon_image = ctk.CTkImage(
                light_image=Image.open(icon_path),
                dark_image=Image.open(icon_path),
                size=(48, 48)
            )
            icon_label = ctk.CTkLabel(top_frame, image=icon_image, text="")
            icon_label.image = icon_image
            icon_label.pack(side="left", padx=(0, 15))
        except Exception as e:
            print(f"Could not load icon for {game['name']}: {e}")

    label = ctk.CTkLabel(top_frame, text=title_text, font=("Segoe UI", 20, "bold"))
    label.pack(side="left", pady=15, padx=15, anchor="w")

    button_frame = ctk.CTkFrame(card, fg_color="transparent")
    button_frame.pack(pady=(5, 15))

    play_button = ctk.CTkButton(button_frame, text="▶ Play", width=90, command=lambda g=game: play_game(g))
    play_button.pack(side="left", padx=5)

    edit_button = ctk.CTkButton(button_frame, text="🖊️ Edit", width=90, command=lambda g=game: edit_game(g))
    edit_button.pack(side="left", padx=5)

    if show_favourite:
        favourite_button = ctk.CTkButton(
            button_frame, text="⭐ Favourite", width=90, command=lambda g=game: favourite_game(g)
        )
        favourite_button.pack(side="left", padx=5)

    return card


def clearMain():
    for widget in main_frame.winfo_children():
        widget.destroy()


def refresh_current_view():
    if current_view == "home":
        show_home()
    elif current_view == "library":
        show_library()
    elif current_view == "settings":
        show_settings()


def show_home():
    global current_view
    current_view = "home"
    clearMain()

    title = ctk.CTkLabel(main_frame, text="🏠 Home", font=("Segoe UI", 28, "bold"))
    title.pack(pady=20)

    welcome = ctk.CTkLabel(main_frame, text="Welcome to Turtle Launcher!", font=("Segoe UI", 18))
    welcome.pack()

    games_count = len(games)
    games_label = ctk.CTkLabel(main_frame, text=f"🎮 Games: {games_count}", font=("Segoe UI", 18, "bold"))
    games_label.pack(pady=10)

    favourites_count = sum(1 for game in games if game.get("favourite", False))
    favourite_label = ctk.CTkLabel(
        main_frame, text=f"⭐ Favourites: {favourites_count}", font=("Segoe UI", 18, "bold")
    )
    favourite_label.pack(pady=10)

    total_playtime = sum(game.get("playtime", 0) for game in games)
    total_hours = total_playtime / 3600
    playtime_label = ctk.CTkLabel(
        main_frame, text=f"⏱️ Total Playtime: {total_hours:.1f} hours", font=("Segoe UI", 18, "bold")
    )
    playtime_label.pack(pady=10)

    leaderboard_title = ctk.CTkLabel(main_frame, text="🏆 Most Played Games", font=("Segoe UI", 22, "bold"))
    leaderboard_title.pack(pady=(30, 10))

    most_played = sorted(games, key=lambda g: g.get("playtime", 0), reverse=True)
    top_games = [g for g in most_played if g.get("playtime", 0) > 0][:5]

    if not top_games:
        empty_label = ctk.CTkLabel(main_frame, text="No playtime recorded yet. Go play something!")
        empty_label.pack(pady=10)
    else:
        for game in top_games:
            create_game_card(main_frame, game, show_favourite=False)


def show_library():
    global current_view, games_list_frame
    current_view = "library"
    clearMain()

    title = ctk.CTkLabel(main_frame, text="🎮 Library", font=("Segoe UI", 28, "bold"))
    title.pack(pady=20)

    addgame_button = ctk.CTkButton(main_frame, text="Add Game", command=addgame)
    addgame_button.pack(pady=25)

    search_entry = ctk.CTkEntry(
        main_frame, textvariable=search_var, placeholder_text="🔍 Search Games", width=350
    )
    search_entry.pack(pady=(0, 20))

    games_list_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
    games_list_frame.pack(fill="both", expand=True)

    render_game_list()


def render_game_list(*_args):
    if games_list_frame is None:
        return

    for widget in games_list_frame.winfo_children():
        widget.destroy()

    search_text = search_var.get().lower()

    sorted_games = sorted(games, key=lambda game: game.get("favourite", False), reverse=True)
    filtered_games = [g for g in sorted_games if search_text in g["name"].lower()]

    if not games:
        empty = ctk.CTkLabel(games_list_frame, text="No games in your library.")
        empty.pack(pady=20)
    elif not filtered_games:
        empty = ctk.CTkLabel(games_list_frame, text="No games match your search.")
        empty.pack(pady=20)
    else:
        for game in filtered_games:
            create_game_card(games_list_frame, game, show_favourite=True)


def open_data_folder():
    try:
        if sys.platform == "win32":
            os.startfile(DATA_DIR)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", DATA_DIR])
        else:
            subprocess.Popen(["xdg-open", DATA_DIR])
    except Exception as e:
        show_error(f"Could not open data folder:\n{e}")


def confirm_reset_playtime():
    def do_reset():
        for game in games:
            game["playtime"] = 0
        save_games()
        refresh_current_view()

    confirm_dialog("Reset playtime for all games?", do_reset)


def confirm_clear_library():
    def do_clear():
        for game in games:
            install_dir = game.get("install_dir")
            if install_dir and os.path.commonpath([os.path.abspath(install_dir), GAMES_DIR]) == GAMES_DIR:
                shutil.rmtree(install_dir, ignore_errors=True)
        games.clear()
        save_games()
        refresh_current_view()

    confirm_dialog("Delete all games from your library? This cannot be undone.", do_clear)


def restart_app():
    save_settings()
    save_games()
    try:
        if getattr(sys, "frozen", False):
            # Frozen build: sys.executable IS the .exe, there's no separate
            # script to hand it — launch it directly.
            subprocess.Popen([sys.executable])
        else:
            subprocess.Popen([sys.executable, os.path.abspath(__file__)])
    except Exception as e:
        show_error(f"Could not restart the launcher:\n{e}")
        return
    app.destroy()
    sys.exit(0)


def show_settings():
    global current_view
    current_view = "settings"
    clearMain()

    title = ctk.CTkLabel(main_frame, text="⚙️ Settings", font=("Segoe UI", 28, "bold"))
    title.pack(pady=20)

    appearance_label = ctk.CTkLabel(main_frame, text="Appearance Mode", font=("Segoe UI", 16, "bold"))
    appearance_label.pack(pady=(20, 5))

    def on_appearance_change(value):
        ctk.set_appearance_mode(value)
        settings["appearance_mode"] = value
        save_settings()

    appearance_switch = ctk.CTkSegmentedButton(
        main_frame, values=["Light", "Dark", "System"], command=on_appearance_change
    )
    appearance_switch.set(settings["appearance_mode"])
    appearance_switch.pack(pady=5)

    theme_label = ctk.CTkLabel(
        main_frame, text="Accent Color (restart required)", font=("Segoe UI", 16, "bold")
    )
    theme_label.pack(pady=(25, 5))

    def on_theme_change(value):
        settings["color_theme"] = THEME_OPTIONS[value]
        save_settings()
        restart_prompt_label.configure(text="Restart the launcher to apply the new accent color.")

    theme_menu = ctk.CTkOptionMenu(main_frame, values=list(THEME_OPTIONS.keys()), command=on_theme_change)
    theme_menu.set(REVERSE_THEME_OPTIONS.get(settings["color_theme"], "Green"))
    theme_menu.pack(pady=5)

    restart_prompt_label = ctk.CTkLabel(main_frame, text="", text_color="gray60")
    restart_prompt_label.pack(pady=5)

    restart_button = ctk.CTkButton(main_frame, text="Restart Launcher", command=restart_app)
    restart_button.pack(pady=10)

    data_label = ctk.CTkLabel(main_frame, text="Library Data", font=("Segoe UI", 16, "bold"))
    data_label.pack(pady=(30, 5))

    open_folder_button = ctk.CTkButton(main_frame, text="Open Data Folder", command=open_data_folder)
    open_folder_button.pack(pady=5)

    reset_playtime_button = ctk.CTkButton(
        main_frame, text="Reset All Playtime", fg_color="gray30", hover_color="gray20",
        command=confirm_reset_playtime
    )
    reset_playtime_button.pack(pady=5)

    clear_library_button = ctk.CTkButton(
        main_frame, text="Clear Library", fg_color="#a83232", hover_color="#7a2424",
        command=confirm_clear_library
    )
    clear_library_button.pack(pady=5)


load_settings()
ctk.set_appearance_mode(settings["appearance_mode"])
ctk.set_default_color_theme(settings["color_theme"])

def set_app_icon(window):
    if not os.path.exists(APP_ICON_PNG):
        return
    try:
        source_image = Image.open(APP_ICON_PNG).convert("RGBA")
    except Exception as e:
        print(f"Could not open app icon: {e}")
        return

    if sys.platform == "win32":
        try:
            generated_ico = os.path.join(DATA_DIR, "_app_icon.ico")
            source_image.save(
                generated_ico,
                format="ICO",
                sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
            )
            window.iconbitmap(generated_ico)
            return
        except Exception as e:
            print(f"Could not set .ico app icon, falling back: {e}")

    try:
        from PIL import ImageTk
        preview_image = source_image.copy()
        preview_image.thumbnail((256, 256), Image.LANCZOS)
        icon_image = ImageTk.PhotoImage(preview_image)
        window.iconphoto(True, icon_image)
        window._icon_image_ref = icon_image
    except Exception as e:
        print(f"Could not set app icon: {e}")


def center_window(window, width, height):
    window.update_idletasks()
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    x = (screen_width - width) // 2
    y = (screen_height - height) // 2
    window.geometry(f"{width}x{height}+{x}+{y}")


WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 700

app = ctk.CTk()
app.title("Turtle Launcher")
app.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
app.minsize(900, 600)
set_app_icon(app)

title = ctk.CTkLabel(app, text="🐢 Turtle Launcher", font=ctk.CTkFont(size=30, weight="bold"))
title.pack(pady=20)

sidebar = ctk.CTkFrame(app, width=200, corner_radius=0)
sidebar.pack(side="left", fill="y")

main_frame = ctk.CTkScrollableFrame(app)
main_frame.pack(side="right", fill="both", expand=True)

sidebar_title = ctk.CTkLabel(sidebar, text="🐢 Turtle Launcher", font=("Segoe UI", 22, "bold"))
sidebar_title.pack(pady=(20, 30))

search_var = ctk.StringVar()
search_var.trace_add("write", render_game_list)

home_button = ctk.CTkButton(sidebar, text="🏠 Home", command=lambda: show_home())
home_button.pack(padx=15, pady=5, fill="x")

library_button = ctk.CTkButton(sidebar, text="🎮 Library", command=lambda: show_library())
library_button.pack(padx=15, pady=5, fill="x")

settings_button = ctk.CTkButton(sidebar, text="⚙️ Settings", command=lambda: show_settings())
settings_button.pack(padx=15, pady=5, fill="x")

load_games()
show_home()

center_window(app, WINDOW_WIDTH, WINDOW_HEIGHT)

app.mainloop()