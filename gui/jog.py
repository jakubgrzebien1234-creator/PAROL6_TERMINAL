import flet
import threading
import time

class JogView(flet.Container):
    """
    Widok JOG (Joint Mode) zintegrowany z UART.
    Wysyła komendy w formacie zrozumiałym dla STM32:
    - Silniki: "J{nr}_{wartość}" np. "J1_90.5"
    - Chwytaki: "VAC_ON", "VAC_OFF", "VALVEON", "VALVEOFF"
    """

    def __init__(self, uart_communicator, on_status_update=None):
        """
        :param uart_communicator: Instancja klasy UARTCommunicator
        :param on_status_update: Funkcja wywoływana, gdy chcemy zmienić status w głównej aplikacji
        """
        super().__init__()
        
        # Przechowujemy referencję do komunikatora
        self.uart = uart_communicator
        
        # --- ZMIANA TUTAJ: Zapisujemy funkcję aktualizującą ---
        self.on_status_update = on_status_update 
        
        # --- ZMIENNE STANU ---
        self.is_jogging = False
        self.is_jogging = False
        
        # Symulacja wartości kątów (teoretycznie powinieneś je też odczytywać z robota)
        self.current_joint_values = {
            "J1": 0.0, "J2": 0.0, "J3": 0.0, 
            "J4": 0.0, "J5": 0.0, "J6": 0.0
        }

        self.padding = 10 
        
        joints_list_display = [
            "Silnik 1 (J1)", "Silnik 2 (J2)",
            "Silnik 3 (J3)", "Silnik 4 (J4)",
            "Silnik 5 (J5)", "Silnik 6 (J6)",
            "Chwytak elektryczny", "Chwytak pneumatyczny"
        ]
        
        # --- SEKCJA 1: Budowa siatki przycisków (LEWA STRONA) ---
        jog_grid_layout = flet.Column(spacing=10, expand=True)
        
        for i in range(0, len(joints_list_display), 2):
            if i+1 < len(joints_list_display):
                name1 = joints_list_display[i]
                name2 = joints_list_display[i+1]
                
                panel1 = self._create_joint_control(name1)
                panel2 = self._create_joint_control(name2)
                
                row = flet.Row(
                    controls=[panel1, panel2],
                    spacing=10,
                    expand=True 
                )
                jog_grid_layout.controls.append(row)

        jog_buttons_container = flet.Container(
            content=jog_grid_layout,
            expand=8 
        )
        
        # --- SEKCJA 2: Budowa ramki pozycji (PRAWA STRONA) ---
        position_frame_style = {
            "bgcolor": "#2D2D2D",
            "border_radius": 10,
            "border": flet.border.all(1, "#555555"), 
            "padding": 15 
        }
        
        position_rows = [
            flet.Text("POZYCJE OSI", size=18, weight="bold", color="white", text_align="center")
        ]
        
        joint_names_short = ["J1", "J2", "J3", "J4", "J5", "J6"]
        gripper_names_short = ["Chwytak E.", "Chwytak P."]
        
        self.position_value_labels = {} 
        
        for name in joint_names_short:
            value_label = flet.Text("0.00°", size=16, color="white", text_align="right", expand=True)
            self.position_value_labels[name] = value_label
            position_rows.append(
                flet.Row(
                    controls=[
                        flet.Text(f"{name}:", size=16, weight="bold", color="white"),
                        value_label
                    ],
                    alignment=flet.MainAxisAlignment.SPACE_BETWEEN 
                )
            )
        
        position_rows.append(flet.Divider(height=10, color="#555555"))
        
        for name in gripper_names_short:
            default_state = "OTWARTY" if "E." in name else "WYŁĄCZONY"
            value_label = flet.Text(default_state, size=16, color="white")
            self.position_value_labels[name] = value_label
            
            gripper_block = flet.Column(
                controls=[
                    flet.Text(f"{name}:", size=16, weight="bold", color="white"),
                    value_label
                ],
                spacing=5,
                horizontal_alignment=flet.CrossAxisAlignment.START 
            )
            
            centered_gripper_block = flet.Container(
                content=gripper_block,
                alignment=flet.alignment.center
            )
            position_rows.append(centered_gripper_block)

        position_frame = flet.Container(
            content=flet.Column(
                controls=position_rows,
                spacing=10,
                horizontal_alignment=flet.CrossAxisAlignment.CENTER
            ),
            **position_frame_style,
            expand=1
        )
        
        self.content = flet.Row(
            controls=[jog_buttons_container, position_frame],
            spacing=10
        )

    # --- LOGIKA JOG I UART ---

    def _jog_thread(self, joint_code, direction):
        """Pętla działająca w tle przy trzymaniu przycisku."""
        # Krok zmiany (w stopniach)
        step = 0.5 
        if direction == "minus":
            step = -step
            
        while self.is_jogging:
            # 1. Aktualizacja wartości w GUI
            if joint_code in self.current_joint_values:
                self.current_joint_values[joint_code] += step
                
                new_val = self.current_joint_values[joint_code]
                self.position_value_labels[joint_code].value = f"{new_val:.2f}°"
                
                if self.page:
                    self.page.update()
                
                # 2. WYSYŁANIE KOMENDY DO STM32
                if self.uart and self.uart.is_open():
                    # Wyciągamy numer silnika z "J1" -> 1
                    try:
                        motor_index = int(joint_code[1]) 
                        # Formatowanie zgodne z Twoim sscanf: "J%d_%lf" -> "J1_45.50"
                        cmd = f"J{motor_index}_{new_val:.2f}"
                        self.uart.send_message(cmd)
                    except Exception as e:
                        print(f"Błąd wysyłania JOG: {e}")

            # Częstotliwość wysyłania (0.05s = 20Hz). 
            # Jeśli STM nie wyrabia z buforem, zwiększ to np. do 0.1
            time.sleep(0.05)

    def on_jog_start(self, e, joint_code: str, direction: str, btn):
        """Start po wciśnięciu."""
        # Podświetlenie tylko tego przycisku
        btn.style.bgcolor = "#666666" 
        btn.update()
        
        if not self.is_jogging:
            self.is_jogging = True
            t = threading.Thread(target=self._jog_thread, args=(joint_code, direction), daemon=True)
            t.start()

    def on_jog_stop(self, e, joint_code: str, direction: str, btn):
        """Stop po puszczeniu."""
        self.is_jogging = False
        btn.style.bgcolor = "#444444"
        btn.update()

    # --- LOGIKA CHWYTAKÓW ---
    def on_gripper_click(self, e):
            """Obsługa kliknięć chwytaków + wysyłanie UART."""
            gripper_type = e.control.data.get('type') 
            action = e.control.data.get('action')     
            
            command_to_send = ""

            # --- SEKCJA PNEUMATYCZNA ---
            if gripper_type == 'pneumatic':
                new_txt = "WŁĄCZONY" if action == "ON" else "WYŁĄCZONY"
                self.position_value_labels["Chwytak P."].value = new_txt
                
                # 1. Logika komend
                if action == "ON":
                    command_to_send = "VGripON"
                    # >>> NOWOŚĆ: Aktualizacja STATUSU GLOBALNEGO <<<
                    if self.on_status_update:
                        # Przekazujemy kolor zielony ("green") dla ON
                        import flet as ft # upewnij się że masz import
                        self.on_status_update("Pompa", "WŁĄCZONA", ft.Colors.GREEN_400)
                        self.on_status_update("Zawór", "ZAMKNIĘTY", ft.Colors.GREEN_400)
                else:
                    command_to_send = "VGripOFF"
                    # >>> NOWOŚĆ: Aktualizacja STATUSU GLOBALNEGO <<<
                    if self.on_status_update:
                        import flet as ft
                        self.on_status_update("Pompa", "WYŁĄCZONA", ft.Colors.RED_400)
                        self.on_status_update("Zawór", "OTWARTY", ft.Colors.ORANGE_400)
            # --- SEKCJA ELEKTRYCZNA (ZAWÓR) ---
            elif gripper_type == 'electric':
                new_txt = "ZAMKNIĘTY" if action == "CLOSE" else "OTWARTY"
                self.position_value_labels["Chwytak E."].value = new_txt
                
                if action == "CLOSE":
                    command_to_send = "VALVEON" # Zakładam że to zamykanie
                    # >>> NOWOŚĆ <<<
                    if self.on_status_update:
                        import flet as ft
                        self.on_status_update("Zawór", "OTWARTY", ft.Colors.ORANGE_400)
                else:
                    command_to_send = "VALVEOFF"
                    # >>> NOWOŚĆ <<<
                    if self.on_status_update:
                        import flet as ft
                        self.on_status_update("Zawór", "ZAMKNIĘTY", ft.Colors.GREEN_400)

            # Reszta funkcji bez zmian (wysyłanie UART itp.)
            if self.page: self.page.update()
            if self.uart and self.uart.is_open() and command_to_send:
                self.uart.send_message(command_to_send)

    def _create_joint_control(self, display_name: str) -> flet.Container:
        """Tworzy panel sterowania z unikalnymi stylami."""
        
        # Funkcja generująca NOWY styl dla każdego przycisku
        def get_style():
            return flet.ButtonStyle(
                bgcolor="#444444", 
                shape=flet.RoundedRectangleBorder(radius=8),
                padding=15,
                color="white"
            )
        
        control_content = None
        
        # CHWYTAK PNEUMATYCZNY
        if "pneumatyczny" in display_name.lower():
            btn1 = flet.ElevatedButton("WYŁĄCZ", style=get_style(), expand=True,
                                     data={'type': 'pneumatic', 'action': 'OFF'}, on_click=self.on_gripper_click)
            btn2 = flet.ElevatedButton("WŁĄCZ", style=get_style(), expand=True,
                                     data={'type': 'pneumatic', 'action': 'ON'}, on_click=self.on_gripper_click)
            
        # CHWYTAK ELEKTRYCZNY
        elif "elektryczny" in display_name.lower():
            btn1 = flet.ElevatedButton("OTWÓRZ", style=get_style(), expand=True,
                                     data={'type': 'electric', 'action': 'OPEN'}, on_click=self.on_gripper_click)
            btn2 = flet.ElevatedButton("ZAMKNIJ", style=get_style(), expand=True,
                                     data={'type': 'electric', 'action': 'CLOSE'}, on_click=self.on_gripper_click)
            
        # SILNIKI (J1 - J6)
        else:
            start_idx = display_name.find("(")
            end_idx = display_name.find(")")
            if start_idx != -1 and end_idx != -1:
                joint_code = display_name[start_idx+1:end_idx] # "J1"
            else:
                joint_code = "UNK"

            t1, t2 = "-", "+"
            dir1, dir2 = "minus", "plus"
            
            v1 = flet.ElevatedButton(t1, style=get_style(), expand=True, disabled=True, content=flet.Text(t1, size=20, weight="bold"))
            v2 = flet.ElevatedButton(t2, style=get_style(), expand=True, disabled=True, content=flet.Text(t2, size=20, weight="bold"))
            
            btn1 = flet.GestureDetector(
                content=v1, expand=True,
                on_tap_down=lambda e, j=joint_code, d=dir1, v=v1: self.on_jog_start(e, j, d, v),
                on_tap_up=lambda e, j=joint_code, d=dir1, v=v1: self.on_jog_stop(e, j, d, v)
            )
            btn2 = flet.GestureDetector(
                content=v2, expand=True,
                on_tap_down=lambda e, j=joint_code, d=dir2, v=v2: self.on_jog_start(e, j, d, v),
                on_tap_up=lambda e, j=joint_code, d=dir2, v=v2: self.on_jog_stop(e, j, d, v)
            )

        return flet.Container(
            content=flet.Column(
                controls=[
                    flet.Text(display_name, size=16, weight="bold", color="white"),
                    flet.Row(
                        controls=[btn1, btn2],
                        spacing=10
                    )
                ],
                spacing=10,
                horizontal_alignment=flet.CrossAxisAlignment.CENTER 
            ),
            bgcolor="#2D2D2D",
            border_radius=10,
            border=flet.border.all(1, "#555555"),
            padding=10,
            expand=True 
        )