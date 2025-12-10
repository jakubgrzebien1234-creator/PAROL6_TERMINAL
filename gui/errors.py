import flet
from flet import Column, Row, Container, Text, Icon, Colors, ElevatedButton, ListView, padding, border
from flet import Icons
from datetime import datetime

class ErrorsView(flet.Container):
    def __init__(self):
        super().__init__()
        # --- MAIN SETTINGS ---
        self.expand = True
        self.padding = 5
        self.bgcolor = "#2D2D2D" 
        
        # ======================================================================
        # === 1. STATUS HEADER (Monitor) ===
        # ======================================================================
        self.status_icon = Icon(name=Icons.CHECK_CIRCLE, size=40, color=Colors.GREEN_400)
        self.status_text = Text("SYSTEM OK", size=20, weight="bold", color=Colors.GREEN_400)
        
        self.header_panel = Container(
            content=Row(
                controls=[self.status_icon, self.status_text],
                alignment=flet.MainAxisAlignment.CENTER,
            ),
            bgcolor="#2D2D2D",
            border_radius=10,
            border=border.all(1, Colors.GREEN_900),
            padding=15,
        )

        # ======================================================================
        # === 2. LOG LIST (Scrollable) ===
        # ======================================================================
        self.logs_list_view = ListView(
            expand=True, spacing=5, padding=10, auto_scroll=True
        )

        logs_container = Container(
            content=self.logs_list_view,
            bgcolor="#2D2D2D",
            border_radius=10,
            border=border.all(1, "#444444"),
            expand=True, 
        )

        # ======================================================================
        # === 3. BUTTON BAR (Bottom) ===
        # ======================================================================
        clear_btn = ElevatedButton(
            text="Clear History",
            icon=Icons.DELETE_SWEEP,
            style=flet.ButtonStyle(
                bgcolor=Colors.RED_900, color=Colors.WHITE,
                shape=flet.RoundedRectangleBorder(radius=8),
            ),
            on_click=self._clear_logs
        )

        # Test Button
        test_error_btn = ElevatedButton(
            text="Test Error",
            icon=Icons.BUG_REPORT,
            on_click=lambda e: self.add_log("ERROR", "Test collision error")
        )
        
        buttons_row = Row(
            controls=[clear_btn, Container(expand=True), test_error_btn],
            alignment=flet.MainAxisAlignment.SPACE_BETWEEN
        )

        # ======================================================================
        # === MAIN LAYOUT ===
        # ======================================================================
        self.content = Column(
            controls=[
                self.header_panel,
                Text("Event Log:", size=14, color=Colors.GREY_500),
                logs_container,
                buttons_row
            ],
            expand=True,
            spacing=10
        )

    # ======================================================================
    # === ADD LOG FUNCTION ===
    # ======================================================================
    def add_log(self, level, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Color configuration based on error level
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

        # 1. Add entry to list
        self.logs_list_view.controls.append(log_row)
        
        # 2. Update view only if visible
        if self.logs_list_view.page:
            self.logs_list_view.update()

    def _clear_logs(self, e):
        self.logs_list_view.controls.clear()
        
        if self.logs_list_view.page:
            self.logs_list_view.update()
            
        self._set_system_status(True)
        self.add_log("INFO", "Log cleared.")

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
            self.status_text.value = "ERRORS DETECTED"
            self.status_text.color = Colors.RED_500
            self.header_panel.border = border.all(1, Colors.RED_500)
        
        if self.header_panel.page:
            self.header_panel.update()