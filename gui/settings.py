import flet
from flet import Column, Row, Container, ElevatedButton, Slider, Text, Image, alignment, ScrollMode, MainAxisAlignment, Colors
import json
import os
# Zmiana: Nie importujemy już UARTCommunicator, bo dostaniemy go z zewnątrz
# from gui.communication import UARTCommunicator 

class SettingsView(flet.Container):
    """
    Widok Ustawień (Settings) - WERSJA POPRAWIONA (FIX COM PORT).
    """
    
    VIEW_MAPPING = {
        "render1.png": "ROBOT GŁÓWNY",
        "render2.png": "CHWYTAK OBR.",
        "render3.png": "CHWYTAK PION."
    }

    # --- ZMIANA TUTAJ: Dodajemy argument uart_communicator ---
    def __init__(self, uart_communicator):
        super().__init__()
        self.padding = 10
        self.alignment = alignment.center
        
        # --- ZMIANA TUTAJ: Przypisujemy instancję z main.py ---
        self.comm = uart_communicator
        # USUNIĘTO: self.comm.connect() - bo połączenie już jest aktywne!
        
        # --- ZMIENNE STANU ---
        self.selected_motor_index = 1 
        self.active_slider_set_id = 1 
        self.active_view_name = "render1.png" 
        self.current_gripper_values = []      
        
        self.motor_names = ["SILNIK J1","SILNIK J2","SILNIK J3","SILNIK J4","SILNIK J5","SILNIK J6"]
        self.config_file_path = "motor_settings.json"

        # --- KONFIGURACJA SUWAKÓW ROBOTA ---
        self.slider_set_definitions = {
            1: [ ("A1", 200, 10000), ("V1", 500, 20000), ("AMAX", 1000, 30000), ("VMAX", 20000, 400000), ("D1", 500, 4000) ],
            2: [ ("IHOLD", 0, 31), ("IRUN", 0, 31), ("IHOLDDELAY", 0, 15) ],
            3: [ ("VMAX - HOMING", 5000, 500000), ("AMAX - HOMING", 1000, 8000), ("OFFSET[mm]", -50, 50) ],
            4: [ ("Czułość", -31, 31), ("STALL - IHOLD", 0, 31) ]
        }

        self.motor_settings_data = {} 
        self._load_settings() 
        
        # Zmienne wewnętrzne UI
        self.sliders_column_container = Column(controls=[], spacing=10, expand=True, scroll=ScrollMode.ADAPTIVE)
        self.sliders_labels = []        
        self.slider_controls = []       
        self.slider_value_displays = [] 

        self.content = self._create_main_view()

    # --- Konfiguracja Chwytaków ---
    def _get_gripper_config(self, image_name):
        if image_name == "render2.png":
            return {
                "title": "CHWYTAK OBROTOWY",
                "image": "Gripper1.png",
                "sliders": [
                    ("Siła podciśnienia", 0, 100, 50),
                    ("Czas załączenia pompy", 0, 30, 10)
                ]
            }
        elif image_name == "render3.png":
            return {
                "title": "CHWYTAK PIONOWY",
                "image": "Gripper2.png",
                "sliders": [
                    ("Offset Z [mm]", 0, 300, 0),
                    ("Prędkość zacisku", 10, 200, 50),
                    ("Zacisk siła", 0, 100, 80)
                ]
            }
        return None

    # --- Obsługa Danych ---
    def _get_default_settings(self):
        return {
            1: { 1: [1500, 2500, 10000, 100000, 1400], 2: [11, 11, 6], 3: [300000, 5000, 0], 4: [0, 11] },
            2: { 1: [1500, 2500, 20000, 200000, 1400], 2: [12, 12, 6], 3: [200000, 10000, 0], 4: [0, 12] },
            3: { 1: [1500, 2500, 20000, 200000, 1400], 2: [9, 9, 6], 3: [200000, 10000, 0], 4: [0, 9] },
            4: { 1: [1500, 2500, 10000, 100000, 1400], 2: [9, 9, 6], 3: [300000, 5000, 0], 4: [0, 9] },
            5: { 1: [1500, 2500, 10000, 100000, 1400], 2: [9, 9, 6], 3: [200000, 10000, 0], 4: [0, 9] },
            6: { 1: [1500, 2500, 20000, 200000, 1400], 2: [5, 5, 6], 3: [200000, 10000, 0], 4: [0, 5] }
        }

    def _load_settings(self):
        try:
            with open(self.config_file_path, "r") as f:
                loaded_data = json.load(f)
                self.motor_settings_data = {
                    int(m): {int(s): v for s, v in sett.items()} for m, sett in loaded_data.items()
                }
            print(f"Wczytano: {self.config_file_path}")
        except:
            print("Tworzenie domyślnych ustawień.")
            self.motor_settings_data = self._get_default_settings()
            self._save_settings()

    def _save_settings(self):
        try:
            with open(self.config_file_path, "w") as f:
                json.dump(self.motor_settings_data, f, indent=4)
        except Exception as e:
            print(f"Błąd zapisu JSON: {e}")

    def did_mount(self):
        if self.page: self.page.update()
            
    def reset_view(self):
        self.content = self._create_main_view()
        if self.page: self.page.update()
            
    def on_image_click(self, e, image_path: str):
        self.content = self._create_detail_view(image_path)
        if self.page: self.update()
    
    def _create_clickable_panel(self, image_name: str, map_key: str):
        panel_style = {
            "bgcolor": "#2D2D2D", "border_radius": 10,
            "border": flet.border.all(2, "#555555"),
            "clip_behavior": flet.ClipBehavior.ANTI_ALIAS, "expand": True
        }
        return flet.GestureDetector(
            on_tap=lambda e: self.on_image_click(e, image_name),
            content=Container(
                content=Image(src=image_name, fit=flet.ImageFit.COVER, expand=True),
                **panel_style
            ),
            expand=True
        )
    
    def _create_main_view(self):
        self.active_view_name = "MAIN"
        panel1 = self._create_clickable_panel("render1.png", "render1.png")
        panel2 = self._create_clickable_panel("render2.png", "render2.png")
        panel3 = self._create_clickable_panel("render3.png", "render3.png")
        prawa_kolumna = Column(controls=[panel2, panel3], spacing=10, expand=True)
        return Row(
            controls=[Container(content=panel1, expand=3), Container(content=prawa_kolumna, expand=1)],
            spacing=10, expand=True
        )
    
    def _create_detail_view(self, image_name: str):
        self.active_view_name = image_name 
        
        podramka_style = {
            "bgcolor": "#2D2D2D", "border_radius": 10,
            "border": flet.border.all(1, "#555555"),
            "padding": 10, "alignment": alignment.center 
        }
        podramka_obrazkowa_style = podramka_style.copy()
        podramka_obrazkowa_style.pop("padding", None)
        podramka_obrazkowa_style.pop("alignment", None)
        podramka_obrazkowa_style["clip_behavior"] = flet.ClipBehavior.ANTI_ALIAS

        value_display_box_style = {
            "width": 60, "height": 30, "bgcolor": Colors.BLUE_GREY_800, 
            "border_radius": 5, "border": flet.border.all(1, Colors.BLUE_GREY_600), 
            "alignment": alignment.center 
        }

        # ======================================================================
        # WIDOK 1: ROBOT GŁÓWNY (render1.png)
        # ======================================================================
        if image_name == "render1.png":
            btn_ctrls = []
            for idx, name in enumerate(self.motor_names, start=1):
                btn = ElevatedButton(
                    text=name, expand=True,
                    style=flet.ButtonStyle(bgcolor=Colors.BLUE_GREY_700, color=Colors.WHITE, shape=flet.RoundedRectangleBorder(radius=8)),
                    on_click=lambda e, i=idx: self._on_motor_select(i)
                )
                btn_ctrls.append(btn)
            
            przycisk_panel = Container(
                content=Column(controls=btn_ctrls, spacing=10, expand=True),
                **podramka_style, expand=1
            )
            
            top_btns = []
            names = ["Ustawienia rampy", "Ustawienia prądu", "Ustawienia bazowania", "Ustawienia kolizji"]
            for i, name in enumerate(names, start=1):
                btn = ElevatedButton(
                    text=name, height=45, expand=True,
                    style=flet.ButtonStyle(bgcolor=Colors.BLUE_GREY_600, color=Colors.WHITE, shape=flet.RoundedRectangleBorder(radius=8)),
                    on_click=lambda e, i=i: self._on_slider_set_select(i)
                )
                top_btns.append(btn)

            restore_btn = ElevatedButton(
                text="DEFAULT", height=45, width=80, expand=False,
                style=flet.ButtonStyle(bgcolor=Colors.RED_700, color=Colors.WHITE, shape=flet.RoundedRectangleBorder(radius=8)),
                on_click=self._restore_default_settings
            )
            top_btns.append(restore_btn)

            top_panel = Container(content=Row(controls=top_btns, spacing=10, expand=True), **podramka_style)
            
            self.sliders_column_container = Column(controls=[], spacing=10, expand=True, scroll=ScrollMode.ADAPTIVE)
            
            suwak_panel_style = podramka_style.copy()
            suwak_panel_style["alignment"] = alignment.top_center

            suwak_panel = Container(
                content=Column(controls=[top_panel, self.sliders_column_container], spacing=10, expand=True),
                **suwak_panel_style,
                expand=7
            )
            
            self.selected_motor_index = 1
            self.active_slider_set_id = 1
            self._build_slider_ui(
                self.slider_set_definitions.get(1, []),
                self.motor_settings_data.get(1, {}).get(1, [])
            )
            
            self.motor_display = Text("Silnik: J1", color="white", size=18, weight="bold")
            save_button = ElevatedButton(
                text="Zapisz", height=40, expand=True,
                style=flet.ButtonStyle(bgcolor=Colors.GREEN_700, color=Colors.WHITE, shape=flet.RoundedRectangleBorder(radius=8)),
                on_click=self._on_save_button_click
            )
            
            obrazek_panel = Column(
                controls=[
                    Container(content=self.motor_display, **podramka_style, height=50),
                    Container(content=Image(src="stepper60.png", fit=flet.ImageFit.CONTAIN, expand=True), **podramka_obrazkowa_style, expand=1),
                    Row(controls=[save_button])
                ],
                spacing=10, expand=2
            )
            
            return Row(controls=[przycisk_panel, suwak_panel, obrazek_panel], spacing=10, expand=True)

        # ======================================================================
        # WIDOK 2 i 3: CHWYTAKI
        # ======================================================================
        else:
            config = self._get_gripper_config(image_name)
            if not config: return Text("Błąd konfiguracji")

            self.current_gripper_values = [item[3] for item in config["sliders"]]
            sliders_list = []
            
            for index, (label, min_val, max_val, start_val) in enumerate(config["sliders"]):
                lbl = Text(label, color="white", size=14, weight="bold", width=120) 
                val_txt = Text(str(int(start_val)), color="white", size=14, weight="bold")
                val_box = Container(content=val_txt, **value_display_box_style)

                def on_change_local(e, v_txt=val_txt, idx=index):
                    val = int(e.control.value)
                    v_txt.value = str(val)
                    v_txt.update()
                    self.current_gripper_values[idx] = val 

                sld = Slider(
                    min=min_val, max=max_val, value=start_val, 
                    label="{value}", active_color=Colors.BLUE_ACCENT_400, 
                    expand=True, on_change=on_change_local
                )

                row_container = Container(
                    content=Row(
                        controls=[lbl, sld, val_box],
                        alignment=MainAxisAlignment.SPACE_BETWEEN, spacing=10
                    ),
                    padding=flet.padding.only(bottom=5)
                )
                sliders_list.append(row_container)

            # --- PRZYCISKI ---
            save_btn_gripper = ElevatedButton(
                text="Zapisz", height=40, width=120, 
                style=flet.ButtonStyle(bgcolor=Colors.GREEN_700, color=Colors.WHITE, shape=flet.RoundedRectangleBorder(radius=8)),
                on_click=self._on_save_button_click
            )

            default_btn_gripper = ElevatedButton(
                text="DEFAULT", height=40, width=120,
                style=flet.ButtonStyle(bgcolor=Colors.RED_700, color=Colors.WHITE, shape=flet.RoundedRectangleBorder(radius=8)),
                on_click=self._restore_default_settings
            )
            
            buttons_row = Row(
                controls=[default_btn_gripper, save_btn_gripper],
                alignment=MainAxisAlignment.END, 
                spacing=10
            )

            # --- UKŁAD ---
            lewy_panel = Container(
                content=Image(src=config["image"], fit=flet.ImageFit.CONTAIN),
                **podramka_obrazkowa_style,
                width=450, expand=False 
            )

            prawy_panel = Container(
                content=Column(
                    controls=[
                        Text(config["title"], size=20, weight="bold", color="white"),
                        Column(controls=sliders_list, scroll=ScrollMode.ADAPTIVE, expand=True),
                        buttons_row 
                    ],
                    spacing=15, expand=True
                ),
                **podramka_style, expand=True
            )

            return Row(controls=[lewy_panel, prawy_panel], spacing=10, expand=True)

  # --- Logika Suwaków ---
    def _build_slider_ui(self, structure_configs: list, value_configs: list):
        self.sliders_column_container.controls.clear()
        self.sliders_labels = []
        self.slider_controls = []
        self.slider_value_displays = []

        value_display_box_style = {
            "width": 60, "height": 30, "bgcolor": Colors.BLUE_GREY_800, 
            "border_radius": 5, "border": flet.border.all(1, Colors.BLUE_GREY_600), 
            "alignment": alignment.center 
        }

        # --- NOWA FUNKCJA AKTUALIZACJI (LIVE) ---
        # Uruchamiana przy każdym ruchu suwaka
        def on_live_change(e, txt_ctrl, idx):
            val = int(e.control.value)
            
            # 1. Aktualizacja wizualna (Text)
            txt_ctrl.value = str(val)
            txt_ctrl.update()
            
            # 2. Aktualizacja danych w pamięci (Słownik) OD RAZU
            try:
                self.motor_settings_data[self.selected_motor_index][self.active_slider_set_id][idx] = val
            except Exception as ex:
                print(f"Błąd aktualizacji danych suwaka: {ex}")

        # --- FUNKCJA ZAPISU DO PLIKU ---
        # Uruchamiana tylko po puszczeniu suwaka
        def on_release(e):
            self._save_settings()

        for i, (s_label, s_min, s_max) in enumerate(structure_configs):
            # Zabezpieczenie przed brakiem wartości w configu
            s_val = value_configs[i] if i < len(value_configs) else 0
            s_val = max(s_min, min(s_max, s_val))
            
            lbl = Text(s_label, color="white", size=14, weight="bold")
            val_txt = Text(str(int(s_val)), color="white", size=14, weight="bold")
            val_box = Container(content=val_txt, **value_display_box_style)
            
            sld = Slider(
                min=s_min, max=s_max, value=s_val, label="{value}", 
                active_color=Colors.BLUE_ACCENT_400, expand=True
            )

            # --- TUTAJ ZMIANA ---
            # on_change: Aktualizuje tekst ORAZ dane w zmiennej (gotowe do wysłania przyciskiem Zapisz)
            sld.on_change = lambda e, t=val_txt, idx=i: on_live_change(e, t, idx)
            
            # on_change_end: Zapisuje ustawienia do pliku JSON (żeby nie mulić podczas przesuwania)
            sld.on_change_end = lambda e: on_release(e)
            
            self.sliders_labels.append(lbl)
            self.slider_controls.append(sld)
            self.slider_value_displays.append(val_txt) 
            
            self.sliders_column_container.controls.append(Container(
                content=Row(controls=[lbl, sld, val_box], spacing=10),
                padding=flet.padding.only(top=5,bottom=5)
            ))
    def _on_slider_set_select(self, idx):
        self.active_slider_set_id = idx
        self._build_slider_ui(
            self.slider_set_definitions.get(idx, []),
            self.motor_settings_data.get(self.selected_motor_index, {}).get(idx, [])
        )
        if self.page: self.sliders_column_container.update() 
            
    def _on_motor_select(self, idx):
        self.selected_motor_index = idx
        self.motor_display.value = f"Silnik: J{idx}"
        struct = self.slider_set_definitions.get(self.active_slider_set_id, [])
        vals = self.motor_settings_data.get(idx, {}).get(self.active_slider_set_id, [])

        for i in range(min(len(self.slider_controls), len(struct))):
            _, s_min, s_max = struct[i]
            v = vals[i] if i < len(vals) else 0
            v = max(s_min, min(s_max, v))
            self.slider_controls[i].value = v
            self.slider_value_displays[i].value = str(int(v))
            self.slider_controls[i].update()
            self.slider_value_displays[i].update()

        if self.page: self.motor_display.update()
            
    # --- Logika Przycisków ---
    def _restore_default_settings(self, e):
        print(f"Przywracanie ustawień dla: {self.active_view_name}")
        if self.active_view_name == "render1.png":
            self.motor_settings_data = self._get_default_settings()
            self._save_settings()
            self._on_motor_select(self.selected_motor_index)
        elif self.active_view_name in ["render2.png", "render3.png"]:
            self.content = self._create_detail_view(self.active_view_name)
            if self.page: self.update()

    def _on_save_button_click(self, e):
        final_command = ""
        if self.active_view_name == "render1.png":
            option_map = { 1: "ramp", 2: "current", 3: "homing", 4: "stall" }
            opt = option_map.get(self.active_slider_set_id, "unknown")
            mot = f"J{self.selected_motor_index}"
            try:
                vals = self.motor_settings_data[self.selected_motor_index][self.active_slider_set_id]
                v_str = ",".join(map(str, vals))
                final_command = f"OT,{opt},{mot},{v_str}"
            except: pass
        elif self.active_view_name == "render2.png":
            v_str = ",".join(map(str, self.current_gripper_values))
            final_command = f"OT,VGrip,{v_str}"
        elif self.active_view_name == "render3.png":
            v_str = ",".join(map(str, self.current_gripper_values))
            final_command = f"OT,SGrip,{v_str}"

        if final_command:
            final_command += "\n\r"
            print(f"Wysyłanie ({self.active_view_name}): {final_command.strip()}")
            if self.comm and self.comm.is_open():
                if not self.comm.send_message(final_command):
                    print("BŁĄD: Nie udało się wysłać polecenia.")
            else:
                print("BŁĄD: Brak połączenia z portem.")
        else:
            print("BŁĄD: Puste polecenie.")


    def _update_text_only(self, e, txt):
        # Tylko aktualizacja wizualna tekstu (bez zapisu, bez logiki)
        txt.value = str(int(e.control.value))
        txt.update()