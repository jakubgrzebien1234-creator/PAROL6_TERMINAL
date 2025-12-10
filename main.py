import flet as ft
import time
import os
import threading
import serial.tools.list_ports 

# --- Import widoków ---
try:
    from gui.cartesian import CartesianView
    from gui.jog import JogView
    from gui.settings import SettingsView 
    from gui.status import StatusView 
    from gui.errors import ErrorsView
    from gui.communication import UARTCommunicator
except ImportError as e:
    print(f"Błąd importu modułów GUI: {e}")
    # Fallback dla testów
    CartesianView = JogView = SettingsView = StatusView = ErrorsView = UARTCommunicator = None

from PIL import Image

def main(page: ft.Page):
    # --- Ustawienia strony ---
    page.title = "PAROL6 Operator Panel by Jakub Grzebień"
    page.theme_mode = ft.ThemeMode.DARK 
    
    # Ustawienia rozmiaru okna
    page.window_width = 1024
    page.window_height = 600
    page.window_resizable = False 
    page.window_maximizable = False 
    
    # Inicjalizacja komunikatora
    if UARTCommunicator:
        communicator = UARTCommunicator()
    else:
        class DummyComm:
            def is_open(self): return False
            def connect(self, port): return False
            def disconnect(self): pass
            def send_message(self, msg): print(f"Dummy send: {msg}")
            on_data_received = None
        communicator = DummyComm()
    
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

    # Słownik widoków (deklarujemy wcześniej, żeby był widoczny w toggle_connection)
    views = {}

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
            
            if "STATUS" in views and views["STATUS"]:
                views["STATUS"].update_status("Stan połączenia", "Rozłączono", ft.Colors.GREY_400)
                
        else:
            selected_port = dd_ports.value
            if selected_port:
                if communicator.connect(port=selected_port):
                    btn_connect.icon = ft.Icons.LINK
                    btn_connect.icon_color = "green"
                    btn_connect.tooltip = f"Połączony z {selected_port}"
                    dd_ports.disabled = True
                    
                    if "STATUS" in views and views["STATUS"]:
                        views["STATUS"].update_status("Stan połączenia", "Połączono", ft.Colors.GREEN_400)

                    # >>> POPRAWKA: Synchronizacja w wątku z opóźnieniem <<<
                    def delayed_sync():
                        # Czekamy 2 sekundy, aż STM32 wstanie po resecie DTR
                        print("Czekam na start STM32...")
                        time.sleep(2.0) 
                        
                        # Teraz wysyłamy konfigurację
                        if "SETTINGS" in views and views["SETTINGS"]:
                            print("Uruchamiam synchronizację...")
                            # Musimy użyć page z głównego wątku, ale wywołujemy to z tła
                            # Flet jest thread-safe przy page.update, ale lepiej robić to ostrożnie
                            views["SETTINGS"].upload_configuration(page)

                    # Uruchamiamy wątek w tle, żeby nie zawiesić GUI
                    threading.Thread(target=delayed_sync, daemon=True).start()
                    # >>> KONIEC POPRAWKI <<<

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
    
    # --- INICJALIZACJA WIDOKÓW ---
    
    def global_status_updater(key, value, color=None):
        if "STATUS" in views and views["STATUS"]:
            views["STATUS"].update_status(key, value, color)

    # Inicjalizujemy widoki (views zadeklarowane wyżej)
    if JogView:
        views["JOG"] = JogView(uart_communicator=communicator, on_status_update=global_status_updater)
    if CartesianView:
        views["CARTESIAN"] = CartesianView(
            urdf_path="resources/PAROL6.urdf",
            active_links_mask=[False, True, True, True, True, True, True],
            uart_communicator=communicator
        )
    if SettingsView:
        views["SETTINGS"] = SettingsView(uart_communicator=communicator)
    if StatusView:
        views["STATUS"] = StatusView()  
    if ErrorsView:
        views["ERRORS"] = ErrorsView()

    def handle_uart_data(data_string):
        """
        Główna funkcja parsująca dane z UART w main.py
        """
        # --- DEBUG: Odkomentuj, jeśli chcesz widzieć surowe dane w konsoli ---
        # print(f"[RAW]: {repr(data_string)}")

        # 1. Czyszczenie danych
        data_string = data_string.strip()
        if not data_string:
            return

        # ==========================================================
        # 2. HOMING I ODBLOKOWANIE
        # ==========================================================
        if "HOMING_COMPLETE_OK" in data_string:
            if "SETTINGS" in views and views["SETTINGS"]:
                views["SETTINGS"].on_homing_complete_signal()
        
            # --- ODBLOKUJ JOG ---
            if "JOG" in views and views["JOG"]:
                views["JOG"].set_homed_status(True)
                
            return

        # ==========================================================
        # 3. DEBUGOWANIE SILNIKÓW (J1_DBG...)
        # ==========================================================
        if "_DBG" in data_string:
            if "SETTINGS" in views and views["SETTINGS"]:
                try:
                    # Przekazujemy do SettingsView (do okna tuningu silników)
                    views["SETTINGS"].handle_stall_alert(data_string)
                except: pass
            return 

        # ==========================================================
        # 4. TUNING CHWYTAKA (EGRIPSGRESLUT...) - NOWOŚĆ
        # ==========================================================
        # To jest konieczne dla przycisku TUNNING w zakładce SGGRIP
        if "EGRIPSGRESULT" in data_string:
            if "SETTINGS" in views and views["SETTINGS"]:
                try:
                    views["SETTINGS"].handle_stall_alert(data_string)
                except: pass
            return

        # ==========================================================
        # 5. WYKRYCIE UTYKU (STALL)
        # ==========================================================
        if "STALL" in data_string:
            # 1. Przekazujemy do widoku ustawień (czerwony alert)
            if "SETTINGS" in views and views["SETTINGS"]:
                try:
                    views["SETTINGS"].handle_stall_alert(data_string)
                except: pass

            # 2. Logowanie do zakładki błędów
            if "ERRORS" in views and views["ERRORS"]:
                views["ERRORS"].add_log("WARNING", f"Wykryto utyk: {data_string}")
            
            return

        # ==========================================================
        # 6. STARA OBSŁUGA SG (Kompatybilność)
        # ==========================================================
        if data_string.startswith("SG"):
            parts = data_string.split('_')
            if len(parts) == 2:
                klucz = parts[0]   # np. SG1
                wartosc = parts[1] # np. 120
                
                kolor = ft.Colors.GREEN_400
                try:
                    if int(wartosc) < 50: kolor = ft.Colors.RED_400
                except: pass

                if "STATUS" in views and views["STATUS"]:
                    views["STATUS"].update_status(klucz, wartosc, kolor)
                
                if "SETTINGS" in views and views["SETTINGS"]:
                    try:
                        # Jeśli masz starą metodę update_stall_display, w przeciwnym razie to pominie
                        if hasattr(views["SETTINGS"], 'update_stall_display'):
                            views["SETTINGS"].update_stall_display(klucz, wartosc)
                    except: pass
            return

        # ==========================================================
        # 7. POMPY / ZAWORY
        # ==========================================================
        if "VAC_ON" in data_string:
            if "STATUS" in views and views["STATUS"]:
                views["STATUS"].update_status("Pompa", "WŁĄCZONA", ft.Colors.GREEN_400)
            return

        if "VAC_OFF" in data_string:
            if "STATUS" in views and views["STATUS"]:
                views["STATUS"].update_status("Pompa", "WYŁĄCZONA", ft.Colors.RED_400)
            return

        if "VALVEON" in data_string:
            if "STATUS" in views and views["STATUS"]:
                views["STATUS"].update_status("Zawór", "ZAMKNIĘTY", ft.Colors.ORANGE_400)
            return

        if "VALVEOFF" in data_string:
            if "STATUS" in views and views["STATUS"]:
                views["STATUS"].update_status("Zawór", "OTWARTY", ft.Colors.GREEN_400)
            return

        # ==========================================================
        # 8. CIŚNIENIE
        # ==========================================================
        # Próba 1: Sama liczba
        if data_string.replace('.','',1).isdigit():
            try:
                pressure_val = float(data_string)
                if "STATUS" in views and views["STATUS"]:
                    views["STATUS"].update_status("Ciśnienie", f"{pressure_val:.2f} kPa", ft.Colors.CYAN_400)
                return
            except ValueError: pass

        # Próba 2: Format P:
        if data_string.startswith("P:"):
            try:
                val = data_string.split(":")[1].strip()
                if "STATUS" in views and views["STATUS"]:
                    views["STATUS"].update_status("Ciśnienie", val + " kPa") 
            except: pass
            return

        # ==========================================================
        # 9. BŁĘDY OGÓLNE
        # ==========================================================
        if data_string.startswith("ERROR_"):
            tresc_bledu = data_string[6:].strip() 
            if "ERRORS" in views and views["ERRORS"]:
                views["ERRORS"].add_log("ERROR", tresc_bledu)
            return 

        # ==========================================================
        # 10. POZYCJE OSI (JOG & CARTESIAN)
        # ==========================================================
        if data_string.startswith("A_"):
            try:
                # Format: A_val1_val2...
                content = data_string[2:]
                parts = [p for p in content.split('_') if p.strip()]
                
                if len(parts) == 6:
                    joint_values = {
                        "J1": float(parts[0]),
                        "J2": float(parts[1]),
                        "J3": float(parts[2]),
                        "J4": float(parts[3]),
                        "J5": float(parts[4]),
                        "J6": float(parts[5])
                    }

                    # Aktualizacja JOG (FK)
                    if "JOG" in views and views["JOG"]:
                        views["JOG"].update_joints_and_fk(joint_values)
                    
                    # Aktualizacja Cartesian (jeśli jest potrzebna)
                    if "CARTESIAN" in views and views["CARTESIAN"]:
                        if hasattr(views["CARTESIAN"], '_on_uart_data'):
                            views["CARTESIAN"]._on_uart_data(data_string)

            except Exception as e:
                # print(f"Błąd ramki A_: {e}")
                pass
            return

        # ==========================================================
        # 11. KRAŃCÓWKI (LIMIT SWITCHES)
        # ==========================================================
        if data_string.startswith("LIMITSWITCH_"):
            if "STATUS" in views and views["STATUS"]:
                try:
                    # Format: LIMITSWITCH_0,0,1,0,0,0
                    raw_vals = data_string.replace("LIMITSWITCH_", "")
                    parts = raw_vals.split(',')
                    
                    if len(parts) >= 6:
                        for i in range(6):
                            val = parts[i].strip()
                            key = f"LS{i+1}" 
                            
                            if val == "1":
                                views["STATUS"].update_status(key, "PRESSED", ft.Colors.RED_400)
                            else:
                                views["STATUS"].update_status(key, "RELEASED", ft.Colors.GREEN_400)
                except Exception as e:
                    print(f"Błąd parsowania krańcówek: {e}")
            return

        # ==========================================================
        # 12. PROTOKÓŁ STATUSU (PROT_)
        # ==========================================================
        if data_string.startswith("PROT_"):
            if "STATUS" in views and views["STATUS"]:
                try:
                    raw_vals = data_string.replace("PROT_", "")
                    parts = raw_vals.split(',')
                    
                    if len(parts) >= 8:
                        # --- 1. Zasilanie (0/1) ---
                        def get_flag_status(val_str):
                            return ("OK", ft.Colors.GREEN_400) if val_str.strip() == "1" else ("BŁĄD", ft.Colors.RED_400)

                        txt, col = get_flag_status(parts[0])
                        views["STATUS"].update_status("PWR3V3", txt, col)
                        
                        txt, col = get_flag_status(parts[1])
                        views["STATUS"].update_status("PWR5V", txt, col)

                        txt, col = get_flag_status(parts[2])
                        views["STATUS"].update_status("PWROK", txt, col)

                        txt, col = get_flag_status(parts[3])
                        views["STATUS"].update_status("PWRSTAT", txt, col)

                        # --- 2. Temperatury ---
                        def format_temp(val_str):
                            try:
                                temp_val = float(val_str)
                                if temp_val <= -99.0:
                                    return "NOT CONN.", ft.Colors.GREY_500
                                else:
                                    return f"{temp_val:.2f} °C", ft.Colors.ORANGE_300
                            except ValueError:
                                return "ERR", ft.Colors.RED_400

                        views["STATUS"].update_status("TEMP1", format_temp(parts[4])[0], format_temp(parts[4])[1])
                        views["STATUS"].update_status("TEMP2", format_temp(parts[5])[0], format_temp(parts[5])[1])
                        views["STATUS"].update_status("TEMP3", format_temp(parts[6])[0], format_temp(parts[6])[1])
                        views["STATUS"].update_status("TEMP4", format_temp(parts[7])[0], format_temp(parts[7])[1])

                except Exception as e:
                    print(f"Błąd parsowania PROT_: {e}")
            return


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
            frame_middle.content = ft.Text(f"Brak widoku: {mode_name}", size=30, color="red")
            
        if mode_name == "SETTINGS" and "SETTINGS" in views:
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
                try:
                    page.update()
                except:
                    pass 
            time.sleep(1)

    t = threading.Thread(target=clock_updater, daemon=True)
    t.start()
    
    # Ustawienie domyślnego widoku
    current_mode_text.value = "JOG"
    if "JOG" in views:
        frame_middle.content = views["JOG"]
    else:
        frame_middle.content = ft.Text("Widok JOG niedostępny", color="red")
        
    frame_middle.alignment = ft.alignment.center

    page.update()

# --- Uruchomienie aplikacji ---
if __name__ == "__main__":
    # Obsługa folderów i placeholderów
    resources_dir = "resources"
    os.makedirs(resources_dir, exist_ok=True)
    
    gui_dir = os.path.join(os.getcwd(), "gui")
    os.makedirs(gui_dir, exist_ok=True)
    init_py = os.path.join(gui_dir, "__init__.py")
    if not os.path.exists(init_py): open(init_py, 'a').close()
    
    at_img_path = os.path.join(resources_dir, "AT.png")
    if not os.path.exists(at_img_path) and Image:
        img = Image.new('RGB', (100, 100), color="#0055A4")
        img_draw = Image.new('RGB', (50, 50), color="#FFD700")
        img.paste(img_draw, (25, 25))
        img.save(at_img_path)
        
    poweredby_img_path = os.path.join(resources_dir, "poweredby.png")
    if not os.path.exists(poweredby_img_path) and Image:
        Image.new('RGB', (200, 80), color="purple").save(poweredby_img_path)

    button_image_files = ["JOG.png", "CARTESIAN.png", "SETTINGS.png", "STATUS.png", "ERRORS.png"]
    button_colors = ["#FF6347", "#1E90FF", "#32CD32", "#FFD700", "#DC143C"]
    for img_file, color in zip(button_image_files, button_colors):
        img_path = os.path.join(resources_dir, img_file)
        if not os.path.exists(img_path) and Image:
            Image.new('RGB', (150, 70), color=color).save(img_path)

    ft.app(target=main, assets_dir="resources")