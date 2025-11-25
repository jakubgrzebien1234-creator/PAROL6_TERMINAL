import flet
# 1. Prawidłowe importy
from flet import Column, Row, Container, Text, Icon, Colors, FloatingActionButton, ElevatedButton, ListView, padding, border, alignment
# 2. Ikony osobno
from flet import Icons
from datetime import datetime

class ErrorsView(flet.Container):
    def __init__(self):
        super().__init__()
        # --- USTAWIENIA GŁÓWNE ---
        self.expand = True
        self.padding = 5
        # Jeśli w SettingsView nie masz tła, usuń tę linię poniżej. 
        # Jeśli masz tam ciemny szary, zostaw #232323.
        self.bgcolor = "#2D2D2D" 
        
        self.log_controls = []

        # ======================================================================
        # === 1. NAGŁÓWEK STATUSU (Monitor) ===
        # ======================================================================
        self.status_icon = Icon(name=Icons.CHECK_CIRCLE, size=40, color=Colors.GREEN_400)
        self.status_text = Text("SYSTEM OK", size=20, weight="bold", color=Colors.GREEN_400)
        
        self.header_panel = Container(
            content=Row(
                controls=[self.status_icon, self.status_text],
                alignment=flet.MainAxisAlignment.CENTER,
            ),
            bgcolor="#2D2D2D", # Spójny kolor panelu
            border_radius=10,
            border=border.all(1, Colors.GREEN_900),
            padding=15,
        )

        # ======================================================================
        # === 2. LISTA LOGÓW (Scrollowana) ===
        # ======================================================================
        self.logs_list_view = ListView(
            expand=True, spacing=5, padding=10, auto_scroll=True
        )

        # --- ZMIANA TUTAJ: ---
        # Zmieniłem bgcolor z "#111111" na "#2D2D2D", żeby pasował do reszty aplikacji
        logs_container = Container(
            content=self.logs_list_view,
            bgcolor="#2D2D2D", # Teraz jest taki sam jak ramki w StatusView
            border_radius=10,
            border=border.all(1, "#444444"), # Obramowanie też spójne
            expand=True, 
        )

        # ======================================================================
        # === 3. PASEK PRZYCISKÓW (Na dole) ===
        # ======================================================================
        clear_btn = ElevatedButton(
            text="Wyczyść historię",
            icon=Icons.DELETE_SWEEP,
            style=flet.ButtonStyle(
                bgcolor=Colors.RED_900, color=Colors.WHITE,
                shape=flet.RoundedRectangleBorder(radius=8),
            ),
            on_click=self._clear_logs
        )

        # Przycisk Testowy 1
        test_error_btn = ElevatedButton(
            text="Generuj Błąd (Test)",
            icon=Icons.BUG_REPORT,
            on_click=lambda e: self.add_log("ERROR", "Wykryto kolizję w osi J2!")
        )
        
        # Przycisk Testowy 2
        test_warn_btn = ElevatedButton(
            text="Generuj Ostrzeżenie",
            icon=Icons.WARNING_AMBER,
            on_click=lambda e: self.add_log("WARNING", "Wysoka temperatura silnika J1")
        )

        buttons_row = Row(
            controls=[clear_btn, Container(expand=True), test_warn_btn, test_error_btn],
            alignment=flet.MainAxisAlignment.SPACE_BETWEEN
        )

        # ======================================================================
        # === UKŁAD CAŁOŚCI ===
        # ======================================================================
        self.content = Column(
            controls=[
                self.header_panel,
                Text("Dziennik zdarzeń:", size=14, color=Colors.GREY_500),
                logs_container,
                buttons_row
            ],
            expand=True,
            spacing=10
        )

    def add_log(self, level, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        if level == "ERROR":
            icon_name = Icons.ERROR_OUTLINE
            icon_color = Colors.RED_400
            text_color = Colors.RED_200
            bg_color = Colors.RED_900
            self._set_system_status(False)
        elif level == "WARNING":
            icon_name = Icons.WARNING_AMBER
            icon_color = Colors.AMBER_400
            text_color = Colors.AMBER_200
            bg_color = "#4d3b00"
        else: # INFO
            icon_name = Icons.INFO_OUTLINE
            icon_color = Colors.BLUE_400
            text_color = Colors.BLUE_200
            bg_color = "#0d1f33"

        log_row = Container(
            content=Row(
                controls=[
                    Text(f"[{timestamp}]", color=Colors.GREY_500, size=12, weight="bold"),
                    Icon(name=icon_name, color=icon_color, size=16),
                    # Zwiększona szerokość dla "WARNING"
                    Text(level, color=icon_color, weight="bold", width=85), 
                    Text(message, color=text_color, size=14, expand=True, no_wrap=False),
                ],
                alignment=flet.MainAxisAlignment.START,
                vertical_alignment=flet.CrossAxisAlignment.CENTER
            ),
            bgcolor=bg_color,
            border_radius=5,
            padding=5,
            border=border.only(left=border.BorderSide(4, icon_color))
        )

        self.logs_list_view.controls.append(log_row)
        self.logs_list_view.update()

    def _clear_logs(self, e):
        self.logs_list_view.controls.clear()
        self.logs_list_view.update()
        self._set_system_status(True)
        self.add_log("INFO", "Dziennik został wyczyszczony ręcznie.")

    def _set_system_status(self, is_ok):
        if is_ok:
            self.status_icon.name = Icons.CHECK_CIRCLE
            self.status_icon.color = Colors.GREEN_400
            self.status_text.value = "SYSTEM OK"
            self.status_text.color = Colors.GREEN_400
            self.header_panel.border = border.all(1, Colors.GREEN_900)
        else:
            self.status_icon.name = Icons.DANGEROUS
            self.status_icon.color = Colors.RED_500
            self.status_text.value = "WYKRYTO BŁĘDY"
            self.status_text.color = Colors.RED_500
            self.header_panel.border = border.all(1, Colors.RED_500)
        
        self.header_panel.update()