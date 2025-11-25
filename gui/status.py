import flet
from flet import Column, Row, Container, Text, alignment, Colors, MainAxisAlignment, ScrollMode, padding, border

class StatusView(flet.Container):
    def __init__(self, uart_communicator=None): 
        super().__init__()
        
        self.uart = uart_communicator 
        
        # --- USTAWIENIA GŁÓWNE ---
        self.expand = True
        self.padding = 5
        self.bgcolor = "#2D2D2D"
        
        self.value_controls = {}

        # ======================================================================
        # === LEWA KOLUMNA (Z PNEUMATYKĄ) ===
        # ======================================================================
        self.left_column_content = Column(
            controls=[
                self._create_header("ZASILANIE"),
                self._create_status_row("Napięcie baterii", "12.4 V"),
                self._create_status_row("Pobór prądu", "1.2 A"),
                self._create_status_row("Temp. sterownika", "45°C"),
                
                # --- SEKCJA PNEUMATYKA ---
                self._create_header("PNEUMATYKA"),
                self._create_status_row("Ciśnienie", "0.00 kPa", color=Colors.CYAN_400),
                
                # NOWE ELEMENTY:
                self._create_status_row("Pompa", "WYŁĄCZONA", color=Colors.RED_400),
                self._create_status_row("Zawór", "OTWARTY", color=Colors.GREEN_400),
                # -------------------------

                self._create_header("STATUS SYSTEMU"),
                self._create_status_row("Stan połączenia", "Rozłączono", color=Colors.GREY_400),
                self._create_status_row("Tryb pracy", "Manualny", color=Colors.BLUE_400),
                self._create_status_row("Ostatni błąd", "Brak", color=Colors.GREY_400),
            ],
            scroll=ScrollMode.ADAPTIVE,
            spacing=5,
            expand=True
        )

        # ======================================================================
        # === PRAWA KOLUMNA (Bez zmian) ===
        # ======================================================================
        self.right_column_content = Column(
            controls=[
                self._create_header("POZYCJA ROBOTA (Kątowa)"),
                self._create_status_row("Oś J1", "0.00°"),
                self._create_status_row("Oś J2", "-45.50°"),
                self._create_status_row("Oś J3", "90.00°"),
                self._create_status_row("Oś J4", "0.00°"),
                self._create_status_row("Oś J5", "10.00°"),
                self._create_status_row("Oś J6", "0.00°"),

                self._create_header("POZYCJA XYZ"),
                self._create_status_row("X [mm]", "150.0"),
                self._create_status_row("Y [mm]", "200.5"),
                self._create_status_row("Z [mm]", "50.0"),
            ],
            scroll=ScrollMode.ADAPTIVE,
            spacing=5,
            expand=True
        )

        # --- STYL RAMEK ---
        frame_style = {
            "bgcolor": "#2D2D2D",
            "border_radius": 10,
            "padding": 15,
            "border": flet.border.all(1, "#444444"),
            "expand": True,
        }

        # ======================================================================
        # === GŁÓWNY UKŁAD ===
        # ======================================================================
        self.content = Row(
            controls=[
                Container(content=self.left_column_content, **frame_style),
                Container(content=self.right_column_content, **frame_style)
            ],
            spacing=5,
            expand=True,
            vertical_alignment=flet.CrossAxisAlignment.STRETCH
        )

    def _create_header(self, text):
        return Container(
            content=Text(text, color=Colors.BLUE_GREY_200, weight="bold", size=14),
            padding=padding.only(top=10, bottom=5)
        )

    def _create_status_row(self, label_text, start_value, color="white"):
        value_display = Text(
            value=start_value,
            color=color,
            weight="bold",
            size=16,
            text_align=flet.TextAlign.CENTER
        )
        self.value_controls[label_text] = value_display

        value_box = Container(
            content=value_display,
            bgcolor=Colors.BLUE_GREY_900,
            border=border.all(1, Colors.BLUE_GREY_700),
            border_radius=6,
            padding=padding.symmetric(horizontal=5, vertical=5),
            width=130, # Zwiększyłem lekko szerokość, żeby napisy się mieściły
            alignment=alignment.center
        )

        row = Row(
            controls=[
                Text(label_text, color="white", size=16, expand=True),
                value_box
            ],
            alignment=MainAxisAlignment.SPACE_BETWEEN,
        )

        return Container(
            content=row,
            padding=padding.symmetric(vertical=3),
            border=border.only(bottom=border.BorderSide(1, "#444444"))
        )

    def update_status(self, parameter_name, new_value, new_color=None):
        if parameter_name in self.value_controls:
            control = self.value_controls[parameter_name]
            
            control.value = str(new_value)
            
            if new_color:
                control.color = new_color
            
            if control.page:
                control.update()