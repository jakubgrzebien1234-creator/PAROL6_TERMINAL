import flet
import threading
import time

class JogView(flet.Container):
    """
    Widok JOG (Joint Mode) zintegrowany z UART.
    Układ wzorowany na image_2e83d7.png:
    [ Kolumna 1-2: Silniki (Szeroka) ] [ Kolumna 3: HOME + Kafle Chwytaków ] [ Kolumna 4: Pozycje (Wąska) ]
    """

    def __init__(self, uart_communicator, on_status_update=None):
        super().__init__()
        
        self.uart = uart_communicator
        self.on_status_update = on_status_update 
        
        # --- ZMIENNE STANU ---
        self.is_jogging = False
        
        # Przechowujemy stan chwytaków (False = Wyłączony/Otwarty, True = Włączony/Zamknięty)
        self.gripper_states = {
            "pneumatic": False,
            "electric": False
        }
        
        self.current_joint_values = {
            "J1": 0.0, "J2": 0.0, "J3": 0.0, 
            "J4": 0.0, "J5": 0.0, "J6": 0.0
        }

        self.padding = 10 
        
        # Rozdzielamy listy na silniki i chwytaki
        self.motors_list = [
            "Silnik 1 (J1)", "Silnik 2 (J2)",
            "Silnik 3 (J3)", "Silnik 4 (J4)",
            "Silnik 5 (J5)", "Silnik 6 (J6)"
        ]
        
        self.grippers_list = [
            "Chwytak elektryczny", 
            "Chwytak pneumatyczny"
        ]
        
        # ============================================================
        # SEKCJA 1: SILNIKI (J1-J6) - Lewa strona
        # ============================================================
        # Zmniejszamy spacing do minimum (2), żeby przyciski były maksymalnie duże
        motors_column = flet.Column(spacing=2, expand=True)
        
        # Pętla tworząca wiersze po 2 silniki
        for i in range(0, len(self.motors_list), 2):
            if i+1 < len(self.motors_list):
                name1 = self.motors_list[i]
                name2 = self.motors_list[i+1]
                
                panel1 = self._create_joint_control(name1)
                panel2 = self._create_joint_control(name2)
                
                # Wiersz ma expand=True, żeby rozpychać się w pionie
                row = flet.Row(
                    controls=[panel1, panel2],
                    spacing=5, # Mniejszy odstęp poziomy
                    expand=True 
                )
                motors_column.controls.append(row)

        motors_container = flet.Container(
            content=motors_column,
            expand=20  # ZWIĘKSZONE (skala x2) - Silniki zajmują teraz lwią część ekranu
        )
        
        # ============================================================
        # SEKCJA 2: NARZĘDZIA (HOME + Chwytaki) - Środek
        # ============================================================
        tools_column = flet.Column(spacing=10, expand=True)
        
        # 1. PRZYCISK HOME
        home_btn_style = flet.ButtonStyle(
            bgcolor=flet.Colors.BLUE_GREY_700,
            shape=flet.RoundedRectangleBorder(radius=5), # Bardziej prostokątny
            padding=20,
            color="white"
        )
        
        btn_home = flet.Container(
            content=flet.ElevatedButton(
                "HOME",
                icon=flet.Icons.HOME,
                style=home_btn_style,
                on_click=self.on_home_click,
                expand=True
            ),
            height=60, # Stała wysokość dla HOME
            expand=False
        )
        
        tools_column.controls.append(btn_home)
        
        # 2. CHWYTAKI (POD SPODEM - KOMPAKTOWE)
        for gripper_name in self.grippers_list:
            # Tworzymy panel chwytaka
            gripper_panel = self._create_joint_control(gripper_name)
            
            # WAŻNE: USUNĄŁEM gripper_panel.expand = True
            tools_column.controls.append(gripper_panel)

        tools_container = flet.Container(
            content=tools_column,
            expand=4, # ZWIĘKSZONE (skala x2) - proporcjonalnie
            # PADDING POZIOMY kolumny (wpływa na szerokość ramki chwytaka)
            padding=flet.padding.symmetric(horizontal=5) 
        )

        # ============================================================
        # SEKCJA 3: POZYCJE - Prawa strona (WĄSKA)
        # ============================================================
        position_frame_style = {
            "bgcolor": "#2D2D2D",
            "border_radius": 10,
            "border": flet.border.all(1, "#555555"), 
            "padding": 10 # Mniejszy padding
        }
        
        # Zmniejszamy czcionkę w nagłówku, żeby się mieściło w wąskiej kolumnie
        position_rows = [
            flet.Text("POZYCJE OSI", size=16, weight="bold", color="white", text_align="center")
        ]
        
        joint_names_short = ["J1", "J2", "J3", "J4", "J5", "J6"]
        gripper_names_short = ["Chwytak E.", "Chwytak P."]
        
        self.position_value_labels = {} 
        
        # Pozycje silników
        for name in joint_names_short:
            value_label = flet.Text("0.00°", size=14, color="white", text_align="right", expand=True)
            self.position_value_labels[name] = value_label
            position_rows.append(
                flet.Row(
                    controls=[
                        flet.Text(f"{name}:", size=14, weight="bold", color="white"),
                        value_label
                    ],
                    alignment=flet.MainAxisAlignment.SPACE_BETWEEN 
                )
            )
        
        position_rows.append(flet.Divider(height=10, color="#555555"))
        
        # Pozycje chwytaków (tekstowe)
        for name in gripper_names_short:
            default_state = "OTWARTY" if "E." in name else "WYŁĄCZONY"
            value_label = flet.Text(default_state, size=14, color="white")
            self.position_value_labels[name] = value_label
            
            gripper_block = flet.Column(
                controls=[
                    flet.Text(f"{name}:", size=14, weight="bold", color="white"),
                    value_label
                ],
                spacing=2,
                horizontal_alignment=flet.CrossAxisAlignment.START 
            )
            position_rows.append(gripper_block)

        position_frame = flet.Container(
            content=flet.Column(
                controls=position_rows,
                spacing=8,
                horizontal_alignment=flet.CrossAxisAlignment.STRETCH
            ),
            **position_frame_style,
            expand=3 # ZMNIEJSZONE RELATYWNIE (wcześniej ekwiwalent 4, teraz 3) -> węższa kolumna
        )
        
        # ============================================================
        # GŁÓWNY UKŁAD (ROW)
        # ============================================================
        self.content = flet.Row(
            controls=[
                motors_container,
                tools_container,
                position_frame
            ],
            spacing=10,
            vertical_alignment=flet.CrossAxisAlignment.STRETCH # Rozciąganie do dołu
        )

    # --- LOGIKA JOG I UART ---

    def _jog_thread(self, joint_code, direction):
        step = 0.5 
        if direction == "minus":
            step = -step
            
        while self.is_jogging:
            if joint_code in self.current_joint_values:
                self.current_joint_values[joint_code] += step
                new_val = self.current_joint_values[joint_code]
                self.position_value_labels[joint_code].value = f"{new_val:.2f}°"
                
                if self.page:
                    self.page.update()
                
                if self.uart and self.uart.is_open():
                    try:
                        motor_index = int(joint_code[1]) 
                        cmd = f"J{motor_index}_{new_val:.2f}"
                        self.uart.send_message(cmd)
                    except Exception as e:
                        print(f"Błąd wysyłania JOG: {e}")

            time.sleep(0.05)

    def on_jog_start(self, e, joint_code: str, direction: str, btn):
        btn.style.bgcolor = "#666666" 
        btn.update()
        
        if not self.is_jogging:
            self.is_jogging = True
            t = threading.Thread(target=self._jog_thread, args=(joint_code, direction), daemon=True)
            t.start()

    def on_jog_stop(self, e, joint_code: str, direction: str, btn):
        self.is_jogging = False
        btn.style.bgcolor = "#444444"
        btn.update()

    def on_home_click(self, e):
        print("HOME clicked")
        if self.uart and self.uart.is_open():
            self.uart.send_message("HOME")
            
        for joint in self.current_joint_values:
            self.current_joint_values[joint] = 0.0
            if joint in self.position_value_labels:
                self.position_value_labels[joint].value = "0.00°"
        
        if self.page:
            self.page.update()

    # --- LOGIKA CHWYTAKÓW (TOGGLE) ---
    def on_gripper_click(self, e):
        # Pobieramy typ z data (Button lub Container -> content -> data)
        control = e.control
        if control.data is None and control.content is not None:
             # Czasami kliknięcie łapie kontener, czasem wnętrze
             pass 
        
        gripper_type = control.data.get('type')
        
        # Pobierz aktualny stan i go odwróć
        current_state = self.gripper_states.get(gripper_type, False)
        new_state = not current_state
        self.gripper_states[gripper_type] = new_state
        
        command_to_send = ""
        
        # Ustalanie tekstów i kolorów (dla dużego kafelka)
        # Szukamy wewnątrz kontenera tekstu do zmiany
        # e.control to Button
        
        status_text = ""
        bg_color = ""
        
        if gripper_type == 'pneumatic':
            status_text = "WŁĄCZONY" if new_state else "WYŁĄCZONY"
            if new_state: # ON
                command_to_send = "VGripON"
                bg_color = flet.Colors.GREEN_600
                if self.on_status_update:
                    import flet as ft
                    self.on_status_update("Pompa", "WŁĄCZONA", ft.Colors.GREEN_400)
                    self.on_status_update("Zawór", "ZAMKNIĘTY", ft.Colors.GREEN_400)
            else: # OFF
                command_to_send = "VGripOFF"
                bg_color = flet.Colors.RED_600
                if self.on_status_update:
                    import flet as ft
                    self.on_status_update("Pompa", "WYŁĄCZONA", ft.Colors.RED_400)
                    self.on_status_update("Zawór", "OTWARTY", ft.Colors.ORANGE_400)
            
            self.position_value_labels["Chwytak P."].value = status_text

        elif gripper_type == 'electric':
            status_text = "ZAMKNIĘTY" if new_state else "OTWARTY"
            if new_state: # CLOSE
                command_to_send = "VALVEON" 
                bg_color = flet.Colors.GREEN_600
                if self.on_status_update:
                    import flet as ft
                    self.on_status_update("Zawór", "OTWARTY", ft.Colors.ORANGE_400)
            else: # OPEN
                command_to_send = "VALVEOFF"
                bg_color = flet.Colors.RED_600
                if self.on_status_update:
                    import flet as ft
                    self.on_status_update("Zawór", "ZAMKNIĘTY", ft.Colors.GREEN_400)
            
            self.position_value_labels["Chwytak E."].value = status_text

        # Aktualizacja wyglądu przycisku
        control.style.bgcolor = bg_color
        control.content.value = status_text # Aktualizujemy tekst wewnątrz przycisku
        control.update()

        if self.page: self.page.update()
        if self.uart and self.uart.is_open() and command_to_send:
            self.uart.send_message(command_to_send)

    def _create_joint_control(self, display_name: str) -> flet.Container:
        """Tworzy panel sterowania."""
        
        # Styl dla przycisków silników (+/-)
        def get_motor_style():
            return flet.ButtonStyle(
                bgcolor="#444444", 
                shape=flet.RoundedRectangleBorder(radius=8),
                padding=0, # ZERO paddingu, żeby max wykorzystać miejsce
                color="white"
            )

        # STYL CHWYTAKÓW - DUŻY KAFEL
        if "pneumatyczny" in display_name.lower() or "elektryczny" in display_name.lower():
            BUTTON_HEIGHT = 60      # Wysokość (np. 60, 80, 100)
            BUTTON_WIDTH = None     # Szerokość (np. 150) lub None (rozciągnij na szerokość)

            is_pneumatic = "pneumatyczny" in display_name.lower()
            g_type = 'pneumatic' if is_pneumatic else 'electric'
            
            state = self.gripper_states[g_type]
            
            if is_pneumatic:
                txt = "WŁĄCZONY" if state else "WYŁĄCZONY"
            else:
                txt = "ZAMKNIĘTY" if state else "OTWARTY"
                
            color = flet.Colors.GREEN_600 if state else flet.Colors.RED_600
            
            btn = flet.ElevatedButton(
                content=flet.Text(txt, size=16, weight="bold"), # Tekst w środku
                style=flet.ButtonStyle(
                    bgcolor=color,
                    shape=flet.RoundedRectangleBorder(radius=8),
                    color="white",
                ),
                data={'type': g_type},
                on_click=self.on_gripper_click,
                height=BUTTON_HEIGHT, # Użycie Twojej zmiennej
                width=BUTTON_WIDTH    # Użycie Twojej zmiennej
            )
            
            align_mode = flet.CrossAxisAlignment.CENTER if BUTTON_WIDTH else flet.CrossAxisAlignment.STRETCH

            # Kontener z tytułem i przyciskiem
            return flet.Container(
                content=flet.Column(
                    controls=[
                        # --- text_align=CENTER wycentruje napis ---
                        flet.Text(display_name, size=15, weight="bold", color="white", text_align=flet.TextAlign.CENTER),
                        btn
                    ],
                    spacing=10,
                    horizontal_alignment=align_mode 
                ),
                bgcolor="#2D2D2D",
                border_radius=10,
                border=flet.border.all(1, "#555555"),
                padding=flet.padding.only(left=15, top=15, right=15, bottom=10),
            )

        # SILNIKI (J1 - J6)
        else:
            # ==========================================================
            # >>> KONFIGURACJA WYMIARÓW PRZYCISKU SILNIKA <<<
            # ==========================================================
            MOTOR_BTN_HEIGHT = 80  # Wpisz np. 80. Jeśli None -> auto/max
            MOTOR_BTN_WIDTH = None   # Wpisz np. 100. Jeśli None -> auto/max
            # ==========================================================

            start_idx = display_name.find("(")
            end_idx = display_name.find(")")
            if start_idx != -1 and end_idx != -1:
                joint_code = display_name[start_idx+1:end_idx] # "J1"
            else:
                joint_code = "UNK"

            t1, t2 = "-", "+"
            dir1, dir2 = "minus", "plus"
            
            # Logika expand: Jeśli user podał szerokość, wyłączamy automatyczne rozciąganie (expand)
            should_expand = True if MOTOR_BTN_WIDTH is None else False
            
            # ZWIĘKSZONA CZCIONKA (+/-) do 40
            v1 = flet.ElevatedButton(
                t1, 
                style=get_motor_style(), 
                expand=should_expand, 
                disabled=True, 
                content=flet.Text(t1, size=40, weight="bold"),
                height=MOTOR_BTN_HEIGHT,
                width=MOTOR_BTN_WIDTH
            )
            v2 = flet.ElevatedButton(
                t2, 
                style=get_motor_style(), 
                expand=should_expand, 
                disabled=True, 
                content=flet.Text(t2, size=40, weight="bold"),
                height=MOTOR_BTN_HEIGHT,
                width=MOTOR_BTN_WIDTH
            )
            
            # Używamy GestureDetector dla ciągłego ruchu
            btn1 = flet.GestureDetector(
                content=v1, 
                expand=should_expand,
                on_tap_down=lambda e, j=joint_code, d=dir1, v=v1: self.on_jog_start(e, j, d, v),
                on_tap_up=lambda e, j=joint_code, d=dir1, v=v1: self.on_jog_stop(e, j, d, v)
            )
            btn2 = flet.GestureDetector(
                content=v2, 
                expand=should_expand,
                on_tap_down=lambda e, j=joint_code, d=dir2, v=v2: self.on_jog_start(e, j, d, v),
                on_tap_up=lambda e, j=joint_code, d=dir2, v=v2: self.on_jog_stop(e, j, d, v)
            )
            
            # Jeśli user podał szerokość, centrujemy przyciski w ramce. Jeśli nie, rozciągamy.
            align_buttons = flet.MainAxisAlignment.CENTER if MOTOR_BTN_WIDTH else flet.MainAxisAlignment.SPACE_BETWEEN

            return flet.Container(
                content=flet.Column(
                    controls=[
                        flet.Text(display_name, size=16, weight="bold", color="white"),
                        flet.Row(
                            controls=[btn1, btn2],
                            spacing=5, # Minimalny odstęp między + i -
                            expand=True, # Rząd nadal się rozciąga w pionie
                            alignment=align_buttons # Centrowanie jeśli stała szerokość
                        )
                    ],
                    spacing=2, # Zmniejszony spacing wewnątrz ramki silnika
                    horizontal_alignment=flet.CrossAxisAlignment.CENTER 
                ),
                bgcolor="#2D2D2D",
                border_radius=10,
                border=flet.border.all(1, "#555555"),
                # ZMIANA: Mniejszy padding na dole (było 5)
                padding=flet.padding.only(left=5, top=5, right=5, bottom=2),
                expand=True 
            )