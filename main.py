import flet as ft
import time
import os
import threading
import serial.tools.list_ports 

# --- Import widoków ---
from gui.cartesian import CartesianView
from gui.jog import JogView
from gui.settings import SettingsView 
from gui.status import StatusView 
from gui.errors import ErrorsView
from PIL import Image
from gui.communication import UARTCommunicator

def main(page: ft.Page):
    # --- Ustawienia strony ---
    page.title = "PAROL6 Operator Panel by Jakub Grzebień"
    page.theme_mode = ft.ThemeMode.DARK 
    
    # Inicjalizacja komunikatora
    communicator = UARTCommunicator()
    
    page.bgcolor = "#1C1C1C"
    page.padding = 10 
    
    # Ustawienie folderu assets
    assets_dir = os.path.join(os.getcwd(), "resources")
    page.assets_dir = assets_dir
    
    # --- DEFINICJE KOLORÓW I STYLÓW ---
    COLOR_RAMKA_GLOWNA = "#2D2D2D" 
    COLOR_OBRYSOW = "#555555" 
    
    STYL_RAMKI = {
        "bgcolor": COLOR_RAMKA_GLOWNA,
        "border_radius": 10,
        "border": ft.border.all(2, COLOR_OBRYSOW),
        "alignment": ft.alignment.center,
        "padding": 10
    }

    # --- 1. LOGIKA I UI DLA PORTU SZEREGOWEGO ---
    
    dd_ports = ft.Dropdown(
        width=120,           
        text_size=14,
        content_padding=10,
        color="white",
        bgcolor="#333333",
        border_color="#555555",
        hint_text="COM",
    )

    btn_connect = ft.IconButton(
        icon=ft.Icons.LINK_OFF,
        icon_color="red",
        tooltip="Połącz"
    )

    def refresh_ports(e=None):
        """Skanuje dostępne porty COM i aktualizuje listę."""
        ports = serial.tools.list_ports.comports()
        port_names = [p.device for p in ports]
        dd_ports.options = [ft.dropdown.Option(p) for p in port_names]
        if port_names and not dd_ports.value:
            dd_ports.value = port_names[0]
        page.update()

    def toggle_connection(e):
        """Obsługa przycisku połącz/rozłącz."""
        if communicator.is_open():
            communicator.disconnect()
            btn_connect.icon = ft.Icons.LINK_OFF
            btn_connect.icon_color = "red"
            btn_connect.tooltip = "Rozłączony"
            dd_ports.disabled = False
            
            # Aktualizacja statusu w widoku STATUS (jeśli istnieje)
            if "STATUS" in views:
                views["STATUS"].update_status("Stan połączenia", "Rozłączono", ft.Colors.GREY_400)
                
        else:
            selected_port = dd_ports.value
            if selected_port:
                if communicator.connect(port=selected_port):
                    btn_connect.icon = ft.Icons.LINK
                    btn_connect.icon_color = "green"
                    btn_connect.tooltip = f"Połączony z {selected_port}"
                    dd_ports.disabled = True
                    
                    # Aktualizacja statusu w widoku STATUS
                    if "STATUS" in views:
                        views["STATUS"].update_status("Stan połączenia", "Połączono", ft.Colors.GREEN_400)
            else:
                print("Nie wybrano portu!")
        page.update()

    btn_connect.on_click = toggle_connection
    
    btn_refresh = ft.IconButton(
        icon=ft.Icons.REFRESH,
        icon_color="white",
        tooltip="Odśwież porty",
        on_click=refresh_ports
    )

    refresh_ports()

    connection_block = ft.Row(
        controls=[dd_ports, btn_refresh, btn_connect],
        spacing=0,
        alignment=ft.MainAxisAlignment.CENTER
    )

    # --- 2. KONTROLKI ZEGARA I DATY ---
    clock_text = ft.Text(value="00:00:00", size=20, weight=ft.FontWeight.BOLD, color="white")
    date_text = ft.Text(value="DD.MM.RRRR", size=20, weight=ft.FontWeight.NORMAL, color="white")
    
    # --- 3. KONTROLKI TRYBU ---
    mode_label = ft.Text(value="MODE:", size=22, weight=ft.FontWeight.NORMAL, color="white")
    current_mode_text = ft.Text(value="JOG", size=22, weight=ft.FontWeight.BOLD, color="white")

    at_logo = ft.Image(src="AT.png", height=60, error_content=ft.Text("AT", size=30, color="yellow"))
    powered_by_logo = ft.Image(src="poweredby.png", height=60, error_content=ft.Text("PBY", size=14, color="red"))
    
    parol_label = ft.Text("PAROL6", color="white", size=40, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)
    
    mode_block = ft.Column(
        controls=[mode_label, current_mode_text],
        spacing=0,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER 
    )
    
    clock_block = ft.Column(
        controls=[clock_text, date_text, ft.Container(height=2)],
        horizontal_alignment=ft.CrossAxisAlignment.END, 
        spacing=0
    )
    
    # --- GŁÓWNY HEADER ---
    header_content = ft.Row(
        controls=[
            ft.Container(
                content=ft.Row(
                    controls=[at_logo, powered_by_logo],
                    spacing=80,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER
                ),
                alignment=ft.alignment.center_left,
                expand=1 
            ),
            
            ft.Container(
                content=parol_label,
                alignment=ft.alignment.center,
                expand=2, 
            ),

            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Container(
                            content=connection_block,
                            alignment=ft.alignment.center,
                            padding=ft.padding.only(right=15)
                        ),
                        
                        ft.Container(
                            content=mode_block,
                            alignment=ft.alignment.center,
                        ),
                        
                        ft.Container(
                            content=clock_block,
                            alignment=ft.alignment.center_right,
                            padding=ft.padding.only(left=15)
                        )
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=10,
                    alignment=ft.MainAxisAlignment.END 
                ),
                alignment=ft.alignment.center_right, 
                padding=ft.padding.only(right=20),
                expand=2 
            )
        ],
        vertical_alignment=ft.CrossAxisAlignment.CENTER 
    )
    
    STYL_RAMKI_TOP = STYL_RAMKI.copy()
    STYL_RAMKI_TOP.pop("alignment", None)

    frame_top = ft.Container(
        content=header_content, 
        height=80, 
        **STYL_RAMKI_TOP 
    )
    
# 1. Definiujemy funkcję pomocniczą (Mostek)
    def global_status_updater(key, value, color=None):
        if "STATUS" in views:
            views["STATUS"].update_status(key, value, color)

    # 2. Tworzymy widoki i przekazujemy im ten mostek
    views = {
        # PRZEKAZUJEMY FUNKCJĘ DO JOGVIEW:
        "JOG": JogView(uart_communicator=communicator, on_status_update=global_status_updater),
        
        "CARTESIAN": CartesianView(
            urdf_path="resources/PAROL6.urdf",
            active_links_mask=[False, True, True, True, True, True, True],
            uart_communicator=communicator
        ),
        "SETTINGS": SettingsView(uart_communicator=communicator), 
        "STATUS": StatusView(uart_communicator=communicator),
        "ERRORS": ErrorsView()
    }

    def handle_uart_data(data_string):
        # 1. Czyszczenie danych (usuwamy spacje i znaki nowej linii)
        data_string = data_string.strip()
        if not data_string:
            return

        # Opcjonalnie: Zobacz co przychodzi (jeśli nic nie działa, odkomentuj to)
        # print(f"DEBUG: '{data_string}'")

        # ==========================================================
        # 2. NAJPIERW SPRAWDZAMY KOMENDY TEKSTOWE (POMPA / ZAWÓR)
        # ==========================================================
        if "VAC_ON" in data_string:
            if "STATUS" in views:
                views["STATUS"].update_status("Pompa", "WŁĄCZONA", ft.Colors.GREEN_400)
            return  # Kończymy, bo to była komenda, a nie ciśnienie

        if "VAC_OFF" in data_string:
            if "STATUS" in views:
                views["STATUS"].update_status("Pompa", "WYŁĄCZONA", ft.Colors.RED_400)
            return

        if "VALVEON" in data_string:
            if "STATUS" in views:
                views["STATUS"].update_status("Zawór", "ZAMKNIĘTY", ft.Colors.ORANGE_400)
            return

        if "VALVEOFF" in data_string:
            if "STATUS" in views:
                views["STATUS"].update_status("Zawór", "OTWARTY", ft.Colors.GREEN_400)
            return

        # ==========================================================
        # 3. JEŚLI TO NIE KOMENDA, TO MOŻE CIŚNIENIE (LICZBA)?
        # ==========================================================
        try:
            # Próbujemy zamienić tekst na liczbę (np. "-12.50")
            pressure_val = float(data_string)
            
            # Jeśli się udało -> Aktualizujemy STATUS
            if "STATUS" in views:
                # WAŻNE: Upewnij się, że w status.py masz wiersz o nazwie "Ciśnienie"
                views["STATUS"].update_status("Ciśnienie", f"{pressure_val:.2f} kPa", ft.Colors.CYAN_400)
            return

        except ValueError:
            # To nie była ani znana komenda, ani liczba
            pass

        # ==========================================================
        # 4. OBSŁUGA STARYCH FORMATÓW ("P:...") LUB INNYCH DANYCH
        # ==========================================================
        if data_string.startswith("P:"):
            try:
                val = data_string.split(":")[1].strip()
                if "STATUS" in views:
                    views["STATUS"].update_status("Ciśnienie", val)
            except: pass

    communicator.on_data_received = handle_uart_data

    # 2. ŚRODEK
    frame_middle = ft.Container(
        content=None, 
        expand=1,
        **STYL_RAMKI 
    )

    # --- 3. DÓŁ (Stopka) ---
    def change_mode_clicked(e):
        mode_name = e.control.data
        current_mode_text.value = mode_name
        
        if mode_name in views:
            frame_middle.content = views[mode_name]
        else:
            frame_middle.content = ft.Text("Nieznany widok", size=50, color="red")
            
        if mode_name == "SETTINGS":
            views["SETTINGS"].reset_view()
        
        frame_middle.alignment = ft.alignment.center
        page.update()
    
    buttons_data = [
        ("JOG", "JOG.png"),
        ("CARTESIAN", "CARTESIAN.png"),
        ("SETTINGS", "SETTINGS.png"),
        ("STATUS", "STATUS.png"),
        ("ERRORS", "ERRORS.png")
    ]
    
    footer_buttons = []
    for name, img_file in buttons_data:
        footer_buttons.append(
            ft.ElevatedButton(
                data=name, 
                content=ft.Image(
                    src=img_file,
                    height=70,
                    fit=ft.ImageFit.CONTAIN,
                    error_content=ft.Text(name, size=16, weight="bold", color="white") 
                ),
                style=ft.ButtonStyle(
                    bgcolor="#444444",
                    shape=ft.RoundedRectangleBorder(radius=8)
                ),
                height=90, 
                expand=True, 
                on_click=change_mode_clicked 
            )
        )

    frame_bottom = ft.Container(
        content=ft.Row(controls=footer_buttons, spacing=10), 
        height=100,
        **STYL_RAMKI 
    )

    page.add(frame_top, frame_middle, frame_bottom)
    
    # --- Wątek zegara ---
    def clock_updater():
        while True:
            now_time = time.strftime("%H:%M:%S")
            now_date = time.strftime("%d.%m.%Y")
            needs_update = False
            
            if clock_text.value != now_time:
                clock_text.value = now_time
                needs_update = True
            if date_text.value != now_date:
                date_text.value = now_date
                needs_update = True
            
            if needs_update:
                page.update() 
            time.sleep(1)

    t = threading.Thread(target=clock_updater, daemon=True)
    t.start()
    
    # Ustawienie domyślnego widoku
    current_mode_text.value = "JOG"
    frame_middle.content = views["JOG"]
    frame_middle.alignment = ft.alignment.center

    page.update()

# --- Uruchomienie aplikacji ---
if __name__ == "__main__":
    # Obsługa folderów i placeholderów (jak wcześniej)
    resources_dir = "resources"
    os.makedirs(resources_dir, exist_ok=True)
    
    gui_dir = os.path.join(os.getcwd(), "gui")
    os.makedirs(gui_dir, exist_ok=True)
    init_py = os.path.join(gui_dir, "__init__.py")
    if not os.path.exists(init_py): open(init_py, 'a').close()
    
    settings_py = os.path.join(gui_dir, "settings.py")
    if not os.path.exists(settings_py): open(settings_py, 'a').close()
    
    # Placeholder AT.png
    at_img_path = os.path.join(resources_dir, "AT.png")
    if not os.path.exists(at_img_path) and Image:
        img = Image.new('RGB', (100, 100), color="#0055A4")
        img_draw = Image.new('RGB', (50, 50), color="#FFD700")
        img.paste(img_draw, (25, 25))
        img.save(at_img_path)
        
    # Placeholder poweredby.png
    poweredby_img_path = os.path.join(resources_dir, "poweredby.png")
    if not os.path.exists(poweredby_img_path) and Image:
        Image.new('RGB', (200, 80), color="purple").save(poweredby_img_path)

    # Placeholdery przycisków
    button_image_files = ["JOG.png", "CARTESIAN.png", "SETTINGS.png", "STATUS.png", "ERRORS.png"]
    button_colors = ["#FF6347", "#1E90FF", "#32CD32", "#FFD700", "#DC143C"]
    for img_file, color in zip(button_image_files, button_colors):
        img_path = os.path.join(resources_dir, img_file)
        if not os.path.exists(img_path) and Image:
            Image.new('RGB', (150, 70), color=color).save(img_path)

    ft.app(target=main, assets_dir="resources")