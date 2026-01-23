import flet as ft
import time
import os
import threading
import serial.tools.list_ports 

# --- View Imports ---
try:
    from gui.cartesian import CartesianView
    from gui.jog import JogView
    from gui.settings import SettingsView 
    from gui.status import StatusView 
    from gui.errors import ErrorsView
    from gui.communication import UARTCommunicator
except ImportError as e:
    CartesianView = JogView = SettingsView = StatusView = ErrorsView = UARTCommunicator = None

from PIL import Image

def main(page: ft.Page):
    # --- Page Settings ---
    page.title = "PAROL6 Operator Panel by Jakub Grzebień"
    page.theme_mode = ft.ThemeMode.DARK 
    
    # Window size settings
    #page.window_full_screen = True
    #page.window_frameless = True 
    
    # Communicator initialization
    if UARTCommunicator:
        communicator = UARTCommunicator()
    else:
        class DummyComm:
            def is_open(self): return False
            def connect(self, port): return False
            def disconnect(self): pass
            def send_message(self, msg): pass
            on_data_received = None
        communicator = DummyComm()
    
    page.bgcolor = "#1C1C1C"
    page.bgcolor = "#1C1C1C"
    page.padding = 0  
    
    # Assets folder setup
    assets_dir = os.path.join(os.getcwd(), "resources")
    page.assets_dir = assets_dir
    
    # --- COLOR AND STYLE DEFINITIONS ---
    COLOR_RAMKA_GLOWNA = "#2D2D2D" 
    COLOR_OBRYSOW = "#555555" 
    


 
    
    STYL_RAMKI = {
        "bgcolor": COLOR_RAMKA_GLOWNA,
        "border_radius": 10,
        "border": ft.border.all(2, COLOR_OBRYSOW),
        "alignment": ft.alignment.center,
        "padding": 10
    }

    # Views dictionary
    views = {}

    # --- ESTOP SCREEN (Overlay) ---
    estop_overlay = ft.Container(
        content=ft.Column(
            controls=[
                ft.Icon(name=ft.icons.WARNING_ROUNDED, color="white", size=80),
                ft.Text("EMERGENCY STOP ACTIVE", size=50, weight=ft.FontWeight.BOLD, color="white", text_align=ft.TextAlign.CENTER),
                ft.Image(src="ESTOP.png", width=250, height=250, fit=ft.ImageFit.CONTAIN, error_content=ft.Text("BRAK ZDJĘCIA ESTOP", color="white")),
                ft.Text("System Stopped. Release E-Stop button to resume.", size=20, color="white")
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=20
        ),
        bgcolor=ft.colors.with_opacity(0.95, "#B00020"), 
        alignment=ft.alignment.center,
        visible=False, 
        expand=True,
        padding=20,
        on_click=lambda e: None 
    )

    # --- 1. SERIAL PORT LOGIC AND UI ---
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
        icon=ft.icons.LINK_OFF,
        icon_color="red",
        tooltip="Połącz"
    )

    def refresh_ports(e=None):
        ports = serial.tools.list_ports.comports()
        port_names = [p.device for p in ports]
        dd_ports.options = [ft.dropdown.Option(p) for p in port_names]
        if port_names and not dd_ports.value:
            dd_ports.value = port_names[0]
        page.update()

    def toggle_connection(e):
        if communicator.is_open():
            communicator.disconnect()
            btn_connect.icon = ft.icons.LINK_OFF
            btn_connect.icon_color = "red"
            btn_connect.tooltip = "Rozłączony"
            dd_ports.disabled = False
            
            if "STATUS" in views and views["STATUS"]:
                views["STATUS"].update_status("CONN_STAT", "DISCONNECTED", ft.colors.GREY_400)
                views["STATUS"].update_status("PORT_NAME", "None", ft.colors.GREY_400)
            
            # Log disconnect to errors
            if "ERRORS" in views and views["ERRORS"]:
                views["ERRORS"].handle_error_code("DIS")
                
        else:
            selected_port = dd_ports.value
            if selected_port:
                if communicator.connect(port=selected_port):
                    btn_connect.icon = ft.icons.LINK
                    btn_connect.icon_color = "green"
                    btn_connect.tooltip = f"Połączony z {selected_port}"
                    dd_ports.disabled = True
                    
                    if "STATUS" in views and views["STATUS"]:
                        views["STATUS"].update_status("CONN_STAT", "CONNECTED", ft.colors.GREEN_400)
                        views["STATUS"].update_status("PORT_NAME", selected_port, ft.colors.BLUE_400)
                    
                    # Log connect to errors
                    if "ERRORS" in views and views["ERRORS"]:
                        views["ERRORS"].handle_error_code("CON")

                    def delayed_sync():
                        time.sleep(2.0) 
                        if "SETTINGS" in views and views["SETTINGS"]:
                            views["SETTINGS"].upload_configuration(page)
                        
                        # Show tool selection dialog after sync
                        time.sleep(0.5)
                        if "JOG" in views and views["JOG"]:
                            try:
                                # Call tool change dialog
                                views["JOG"].on_change_tool_click(None)
                            except Exception as ex:
                                pass

                    threading.Thread(target=delayed_sync, daemon=True).start()

            else:
                pass
        page.update()

    btn_connect.on_click = toggle_connection
    
    btn_refresh = ft.IconButton(
        icon=ft.icons.REFRESH,
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

    # --- 2. CLOCK AND DATE CONTROLS ---
    clock_text = ft.Text(value="00:00:00", size=20, weight=ft.FontWeight.BOLD, color="white")
    date_text = ft.Text(value="DD.MM.RRRR", size=20, weight=ft.FontWeight.NORMAL, color="white")

    at_logo = ft.Image(src="AT.png", height=60, error_content=ft.Text("AT", size=30, color="yellow"))
    powered_by_logo = ft.Image(src="poweredby.png", height=60, error_content=ft.Text("PBY", size=14, color="red"))
    
    parol_label = ft.Text("PAROL6", color="white", size=40, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)
    
    clock_block = ft.Column(
        controls=[clock_text, date_text, ft.Container(height=2)],
        horizontal_alignment=ft.CrossAxisAlignment.END, 
        spacing=0
    )
    
    # --- MAIN HEADER ---
    header_content = ft.Row(
        controls=[
            ft.Container(
                content=ft.Row(
                    controls=[at_logo, powered_by_logo],
                    spacing=20,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER
                ),
                alignment=ft.alignment.center_left,
                expand=1 
            ),
            
            ft.Container(
                content=ft.Column(
                    controls=[
                        parol_label,
                        ft.Text("MADE BY JAKUB GRZEBIEŃ", size=10, color="white", weight=ft.FontWeight.BOLD)
                    ],
                    spacing=-5, 
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER
                ),
                alignment=ft.alignment.center, 
                margin=ft.margin.only(top=-5), 
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
    
    # --- VIEW INITIALIZATION ---
    frame_middle = ft.Container(
        content=None, 
        expand=1,
        **STYL_RAMKI 
    )
    
    # Global variables for error handling
    footer_buttons_map = {} 
    current_alert_level = "NONE"

    # Global variables for animation
    animation_thread = None
    stop_animation = False

    def animate_button_loop():
        nonlocal stop_animation
        error_btn = footer_buttons_map.get("ERRORS")
        if not error_btn: return

        # Starting animation loop
        state_toggle = False
        
        while not stop_animation and current_alert_level != "NONE":
            # Base color selection
            if current_alert_level == "ERROR":
                color_on = ft.colors.RED_500
                color_off = ft.colors.RED_900 if page.theme_mode == ft.ThemeMode.DARK else ft.colors.RED_100
                width = 4
            elif current_alert_level == "WARNING":
                color_on = ft.colors.YELLOW_500
                color_off = ft.colors.YELLOW_900 if page.theme_mode == ft.ThemeMode.DARK else ft.colors.YELLOW_100
                width = 4
            else:
                break
            
            # Pulse animation (border color change)
            current_color = color_on if state_toggle else color_off
            
            error_btn.style.side = ft.BorderSide(width, current_color)
            
            try:
                error_btn.update()
            except:
                break 
                
            state_toggle = not state_toggle
            time.sleep(0.5) 
            
        error_btn.style.side = ft.BorderSide(0, ft.colors.TRANSPARENT)
        try:
            error_btn.update()
        except: pass

    def update_error_button_style(level):
        nonlocal animation_thread, stop_animation
        
        error_btn = footer_buttons_map.get("ERRORS")
        if not error_btn: 
            return

        if level == "NONE":

            stop_animation = True
            if animation_thread and animation_thread.is_alive():
                animation_thread.join(timeout=1.0)
            
            error_btn.style.side = ft.BorderSide(0, ft.colors.TRANSPARENT)
            error_btn.update()
            

            if animation_thread is None or not animation_thread.is_alive():
                stop_animation = False
                animation_thread = threading.Thread(target=animate_button_loop, daemon=True)
                animation_thread.start()
            else:
                pass

    def set_controls_locked(is_locked):
        """Locks/Unlocks control views"""
        if "JOG" in views:
            if hasattr(views["JOG"], "set_locked"):
                views["JOG"].set_locked(is_locked)
            else:
                views["JOG"].disabled = is_locked 
                
        if "CARTESIAN" in views:
            if hasattr(views["CARTESIAN"], "set_locked"):
                views["CARTESIAN"].set_locked(is_locked)
            else:
                views["CARTESIAN"].disabled = is_locked 
                
        # Force middle view update
        if frame_middle.page:
            frame_middle.update()


    def update_global_error_state(level):
        nonlocal current_alert_level
        
        if level == "ERROR":
            current_alert_level = "ERROR"
            set_controls_locked(True) 
        elif level == "WARNING":
            if current_alert_level != "ERROR":
                current_alert_level = "WARNING"
                set_controls_locked(False) 
        elif level == "NONE":
            current_alert_level = "NONE"
            set_controls_locked(False) 
            
            if "STATUS" in views and views["STATUS"]:
                for i in range(1, 7):
                    views["STATUS"].update_status(f"M{i}_CONN", "True", ft.colors.GREEN_400)
            
        update_error_button_style(current_alert_level)

    
    def global_status_updater(key, value, color=None):
        if "STATUS" in views and views["STATUS"]:
            views["STATUS"].update_status(key, value, color)

    def global_error_handler(error_code):
        """Function handling errors from JOG/CARTESIAN views"""
        if "ERRORS" in views and views["ERRORS"]:
            views["ERRORS"].send_error_code(error_code)

    # --- SHARED STATE CALLBACKS ---
    def global_set_homed(is_homed):
        """Set homing status for ALL views at once"""
        if "JOG" in views and views["JOG"]:
            views["JOG"].set_homed_status(is_homed)
        if "CARTESIAN" in views and views["CARTESIAN"]:
            views["CARTESIAN"].set_homed_status(is_homed)
        if "SETTINGS" in views and views["SETTINGS"]:
            views["SETTINGS"].set_homed_status(is_homed)

    def global_sync_joints():
        """Sync joint positions from JOG to CARTESIAN and vice versa"""
        # Get current joints from JOG (in degrees, internal_target_values)
        if "JOG" in views and views["JOG"] and "CARTESIAN" in views and views["CARTESIAN"]:
            jog_joints = views["JOG"].internal_target_values
            # Convert to radians and set to CARTESIAN
            import numpy as np
            cartesian_joints = [np.radians(jog_joints.get(f"J{i+1}", 0.0)) for i in range(6)]
            views["CARTESIAN"].commanded_joints = cartesian_joints

    def global_set_tool(tool_name):
        """Set tool for ALL views at once"""
        if "JOG" in views and views["JOG"] and views["JOG"].ik:
            views["JOG"].ik.set_tool(tool_name)
            views["JOG"]._calculate_forward_kinematics()
        if "CARTESIAN" in views and views["CARTESIAN"] and views["CARTESIAN"].ik:
            views["CARTESIAN"].ik.set_tool(tool_name)
            views["CARTESIAN"]._update_labels_logic()

    # Initialize views - ERRORS first to be available for others
    if ErrorsView:
        # Pass callback to ErrorsView
        views["ERRORS"] = ErrorsView(uart_communicator=communicator, on_status_change=update_global_error_state)
    if JogView:
        views["JOG"] = JogView(uart_communicator=communicator, on_status_update=global_status_updater, on_error=global_error_handler)
        views["JOG"].on_global_set_homed = global_set_homed  
        views["JOG"].on_global_set_tool = global_set_tool    
    if CartesianView:
        views["CARTESIAN"] = CartesianView(
            urdf_path="resources/PAROL6.urdf",
            active_links_mask=[False, True, True, True, True, True, True, False],
            uart_communicator=communicator,
            on_error=global_error_handler
        )
        views["CARTESIAN"].on_global_set_homed = global_set_homed  
        views["CARTESIAN"].on_global_set_tool = global_set_tool   
    if SettingsView:
        views["SETTINGS"] = SettingsView(uart_communicator=communicator)
    if StatusView:
        views["STATUS"] = StatusView()

    def handle_uart_data(data_string):
            """
            Main UART data parsing function in main.py
            """
            data_string = data_string.strip()
            if not data_string: return
            # ==========================================================
            # 0. ESTOP HANDLING
            # ==========================================================
            if "ESTOP_TRIGGER" in data_string:
                # 1. CLOSE HOMING WINDOW IN SETTINGS
                if "SETTINGS" in views and views["SETTINGS"]:
                    try:
                        views["SETTINGS"].close_homing_dialog()
                    except Exception:
                        pass

                # 2. CLOSE HOMING WINDOW IN JOG
                if "JOG" in views and views["JOG"]:
                    try:
                        views["JOG"].set_homed_status(False)
                    except Exception:
                        pass
                
                # 3. Reset for CARTESIAN
                if "CARTESIAN" in views and views["CARTESIAN"]:
                    try:
                        views["CARTESIAN"].set_homed_status(False)
                    except Exception:
                        pass

                # 3. Show red ESTOP overlay
                estop_overlay.visible = True
                page.update()
                
                # 4. Log E2 error for ESTOP
                if "ERRORS" in views and views["ERRORS"]:
                    views["ERRORS"].handle_error_code("E2")
                
                return
            
            if "ESTOP_RELEASE" in data_string or "ESTOP_OFF" in data_string:
                estop_overlay.visible = False
                page.update()
                return

            # ==========================================================
            # 2. HOMING AND UNLOCKING (WITH DIAGNOSTICS)
            # ==========================================================
            if "HOMING_COMPLETE_OK" in data_string:
                
                # Debugowanie SETTINGS
                if "SETTINGS" in views and views["SETTINGS"]:
                    views["SETTINGS"].set_homed_status(True)
                
                # Debugowanie JOG
                if "JOG" in views and views["JOG"]:
                    views["JOG"].set_homed_status(True)
                
                # Debugowanie CARTESIAN
                if "CARTESIAN" in views and views["CARTESIAN"]:
                    views["CARTESIAN"].set_homed_status(True)
                    
                    if hasattr(views["CARTESIAN"], 'ik') and views["CARTESIAN"].ik:
                        current_tool = getattr(views["CARTESIAN"].ik, 'current_tool', None)
                        if current_tool == "CHWYTAK_DUZY":
                            communicator.send_message("EGRIP_OPEN")
                
                # Log HMD info for homing complete
                if "ERRORS" in views and views["ERRORS"]:
                    views["ERRORS"].handle_error_code("HMD")
                
                return

            # ==========================================================
            # 3. MOTOR TUNING AND DIAGNOSTICS HANDLING
            # ==========================================================
            if "SGRESULT" in data_string or "COLLISION" in data_string:
                if "SETTINGS" in views and views["SETTINGS"]:
                    try: views["SETTINGS"].handle_stall_alert(data_string)
                    except: pass
                if "COLLISION" in data_string and "ERRORS" in views and views["ERRORS"]:
                    views["ERRORS"].add_log("WARNING", f"Collision/Stall: {data_string}")
                return

            if "_DBG" in data_string:
                if "SETTINGS" in views and views["SETTINGS"]:
                    try:
                        views["SETTINGS"].parse_debug_line(data_string)
                        views["SETTINGS"].handle_stall_alert(data_string)
                    except: pass
                return 

            if "EGRIP_SR_" in data_string:
                if "SETTINGS" in views and views["SETTINGS"]:
                    try: views["SETTINGS"].handle_stall_alert(data_string)
                    except: pass
                return

            if "STALL" in data_string:
                if "SETTINGS" in views and views["SETTINGS"]:
                    try: views["SETTINGS"].handle_stall_alert(data_string)
                    except: pass
                if "ERRORS" in views and views["ERRORS"]:
                    views["ERRORS"].add_log("WARNING", f"Stall detected: {data_string}")
                return

            # ==========================================================
            # 5. HEADER ERRORS (EMM - Missing Motor)
            # ==========================================================
            if "EMM" in data_string:
                # Format: EMM1, EMM2...
                try:
                    # Find which motor
                    import re
                    match = re.search(r"EMM(\d)", data_string)
                    if match:
                        idx = match.group(1)
                        # 1. Update Status (False / Red)
                        if "STATUS" in views and views["STATUS"]:
                            views["STATUS"].update_status(f"M{idx}_CONN", "False", ft.colors.RED_400)
                        
                        # 2. Trigger Error (if not already triggered by generic parser)
                        if "ERRORS" in views and views["ERRORS"]:
                            views["ERRORS"].handle_error_code(f"EMM{idx}")
                            
                except Exception:
                    pass
                return
            if "VAC_ON" in data_string:
                if "STATUS" in views and views["STATUS"]:
                    views["STATUS"].update_status("PUMP", "ON", ft.colors.GREEN_400)
                return
            if "VAC_OFF" in data_string:
                if "STATUS" in views and views["STATUS"]:
                    views["STATUS"].update_status("PUMP", "OFF", ft.colors.RED_400)
                return
            if "VALVEON" in data_string:
                if "STATUS" in views and views["STATUS"]:
                    views["STATUS"].update_status("VALVE", "CLOSED", ft.colors.ORANGE_400)
                return
            if "VALVEOFF" in data_string:
                if "STATUS" in views and views["STATUS"]:
                    views["STATUS"].update_status("VALVE", "OPEN", ft.colors.GREEN_400)
                return

            # ==========================================================
            # 7b. PRESSURE DATA (New)
            # ==========================================================
            # Format: P:-0.45
            if data_string.startswith("P:"):
                try:
                    pressure_val = data_string[2:].strip()
                    float(pressure_val) 
                    if "STATUS" in views and views["STATUS"]:
                        views["STATUS"].update_status("PRESSURE", f"{pressure_val} kPa", ft.colors.CYAN_400)
                except ValueError:
                    pass
                return

            # ==========================================================
            # 7a. LIMIT SWITCHES (H=Hit/Home, R=Release)
            # ==========================================================
            # Format: H1, H2... (Pressed) / R1, R2... (Released)
            if data_string.startswith("H") or data_string.startswith("R"):
                import re
                # Check for Hit (H1..6)
                match_h = re.match(r"^H(\d+)$", data_string)
                if match_h:
                    idx = match_h.group(1)
                    if "STATUS" in views and views["STATUS"]:
                        views["STATUS"].update_status(f"LS{idx}", "PRESSED", ft.colors.RED_400)
                    return
                
                # Check for Release (R1..6)
                match_r = re.match(r"^R(\d+)$", data_string)
                if match_r:
                    idx = match_r.group(1)
                    if "STATUS" in views and views["STATUS"]:
                        views["STATUS"].update_status(f"LS{idx}", "RELEASED", ft.colors.GREEN_400)
                    return

            # ==========================================================
            # 8. PROT_ DATA HANDLING (Temperatures and Power)
            # ==========================================================
            # Format: PROT_p3v3,p5v,pok,pstat,t1,t2,t3,t4
            if data_string.startswith("PROT_"):
                try:
                    content = data_string[5:] # Remove PROT_
                    parts = content.split(',')
                    if len(parts) >= 8:
                        # 1. Parse Power Status
                        p3v3 = int(parts[0])
                        p5v = int(parts[1])
                        pok = int(parts[2])
                        pstat = int(parts[3])
                        
                        # 2. Parse Temperatures
                        t1 = float(parts[4])
                        t2 = float(parts[5])
                        t3 = float(parts[6])
                        t4 = float(parts[7])
                        
                        # 3. Update Status View
                        if "STATUS" in views and views["STATUS"]:
                            status = views["STATUS"]
                            # Power
                            status.update_status("PWR3V3", "OK" if p3v3 else "FAIL", ft.colors.GREEN_400 if p3v3 else ft.colors.RED_400)
                            status.update_status("PWR5V", "OK" if p5v else "FAIL", ft.colors.GREEN_400 if p5v else ft.colors.RED_400)
                            status.update_status("PWROK", "OK" if pok else "FAIL", ft.colors.GREEN_400 if pok else ft.colors.RED_400)
                            status.update_status("PWRSTAT", str(pstat), ft.colors.BLUE_400)
                            
                            # Temps
                            status.update_status("TEMP1", f"{t1:.1f} °C", ft.colors.ORANGE_300)
                            status.update_status("TEMP2", f"{t2:.1f} °C", ft.colors.ORANGE_300)
                            status.update_status("TEMP3", f"{t3:.1f} °C", ft.colors.ORANGE_300)
                            status.update_status("TEMP4", f"{t4:.1f} °C", ft.colors.ORANGE_300)

                        # 4. Check Thresholds against Global Settings
                        if "SETTINGS" in views and views["SETTINGS"] and "ERRORS" in views and views["ERRORS"]:
                            settings = views["SETTINGS"].global_settings_data
                            errors = views["ERRORS"]
                            
                            # Helper to check one sensor
                            def check_sensor(idx, val):
                                ot_limit = settings.get(f"sensor_{idx}_ot", 50) # Changed default to 50 to match settings.py
                                ct_limit = settings.get(f"sensor_{idx}_ct", 90)

                                # Critical (CT) check
                                if val > ct_limit:
                                    errors.handle_error_code(f"CT{idx}")
                                # Warning (OT) check - only if not already critical
                                elif val > ot_limit:
                                    errors.handle_error_code(f"OT{idx}")

                            check_sensor(1, t1)
                            check_sensor(2, t2)
                            check_sensor(3, t3)
                            check_sensor(4, t4)

                except Exception:
                    pass
                return

            # ==========================================================
            # 5. AXIS POSITIONS (JOG & CARTESIAN - GLOBAL)
            # ==========================================================
            if data_string.startswith("A_"):
                try:
                    content = data_string[2:]
                    parts = [p for p in content.split('_') if p.strip()]
                    
                    if len(parts) == 6:
                        joint_values = {
                            "J1": float(parts[0]), "J2": float(parts[1]),
                            "J3": float(parts[2]), "J4": float(parts[3]),
                            "J5": float(parts[4]), "J6": float(parts[5])
                        }

                        if "JOG" in views and views["JOG"]:
                            views["JOG"].update_joints_and_fk(joint_values)
                        
                        if "CARTESIAN" in views and views["CARTESIAN"]:
                            if hasattr(views["CARTESIAN"], 'update_from_feedback'):
                                views["CARTESIAN"].update_from_feedback(joint_values)

                        if "SETTINGS" in views and views["SETTINGS"]:
                            settings = views["SETTINGS"]
                            idx = settings.selected_motor_index
                            key = f"J{idx}"
                            
                            if key in joint_values:
                                raw_val = joint_values[key]
                                if key in ["J1", "J2", "J3", "J4", "J5"]:
                                    settings.current_test_pos = -raw_val
                                else:
                                    settings.current_test_pos = raw_val

                except: pass
                return

            # ==========================================================
            # 6. GENERAL ERRORS
            # ==========================================================
            if data_string.startswith("ERROR_"):
                if "ERRORS" in views and views["ERRORS"]:
                    views["ERRORS"].add_log("ERROR", data_string[6:].strip())
                return

            # ==========================================================
            # 7. KODY BŁĘDÓW (E1, E2, W1, W2, IKE, COM, OOR1, CT1, EMM1, STL1, NRL1, etc.)
            # ==========================================================
            import re
            # Match all known error code patterns
            error_code_pattern = r'^(E\d+|W\d+|OT\d+|CT\d+|EMM\d+|OOR\d+|NRL\d+|STL\d+|IKE|COM|COL|OVL|GRE|SLW|HMS|CFG|GRW|SPD|HMD|CON|DIS|RDY|PRG)$'
            error_code_match = re.match(error_code_pattern, data_string)
            if error_code_match:
                if "ERRORS" in views and views["ERRORS"]:
                    views["ERRORS"].handle_error_code(data_string)
                return 

            # ==========================================================
            # 9. OTHER FORMATS (Safety)
            # ==========================================================
            if any(x in data_string for x in ["J1", "J2", "J3", "J4", "J5", "J6"]) and \
               any(x in data_string for x in ["_", ":", "="]):
                if "_DBG" not in data_string and "COLLISION" not in data_string and "A_" not in data_string:
                     if "SETTINGS" in views and views["SETTINGS"]:
                        try: views["SETTINGS"].handle_stall_alert(data_string)
                        except: pass

    communicator.on_data_received = handle_uart_data
    
    # 2. MIDDLE 

    # --- 3. BOTTOM (Footer) ---
    def change_mode_clicked(e):
        mode_name = e.control.data
        
        if mode_name in views:
            frame_middle.content = views[mode_name]
        else:
            frame_middle.content = ft.Text(f"View missing: {mode_name}", size=30, color="red")
            
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
    
    # footer_buttons_map defined above
    
    footer_buttons = []
    
    for name, img_file in buttons_data:
        btn = ft.ElevatedButton(
            data=name, 
            content=ft.Image(
                src=img_file,
                height=70,
                fit=ft.ImageFit.CONTAIN,
                error_content=ft.Text(name, size=16, weight="bold", color="white") 
            ),
            style=ft.ButtonStyle(
                bgcolor="#444444",
                shape=ft.RoundedRectangleBorder(radius=8),
                side={
                    ft.MaterialState.DEFAULT: ft.BorderSide(0, ft.colors.TRANSPARENT),
                }
            ),
            height=90, 
            expand=True, 
            on_click=change_mode_clicked 
        )
        footer_buttons.append(btn)
        footer_buttons_map[name] = btn

    
    def wrapped_change_mode_clicked(e):
        mode_name = e.control.data
        
      
        if mode_name == "ERRORS":
            nonlocal current_alert_level
            if current_alert_level == "WARNING":
                update_global_error_state("NONE")
        
        
        import numpy as np
        
        if mode_name == "CARTESIAN" and "JOG" in views and views["JOG"] and "CARTESIAN" in views and views["CARTESIAN"]:

            if views["JOG"].initial_sync_done:
                jog_joints = views["JOG"].internal_target_values
                cartesian_joints = [np.radians(jog_joints.get(f"J{i+1}", 0.0)) for i in range(6)]
                views["CARTESIAN"].commanded_joints = cartesian_joints
 
            
        elif mode_name == "JOG" and "CARTESIAN" in views and views["CARTESIAN"] and "JOG" in views and views["JOG"]:
        
            cartesian_joints = views["CARTESIAN"].commanded_joints
            for i in range(6):
                deg_val = np.degrees(cartesian_joints[i])
                views["JOG"].internal_target_values[f"J{i+1}"] = deg_val
                views["JOG"].current_raw_values[f"J{i+1}"] = deg_val  
            views["JOG"].initial_sync_done = True  
            views["JOG"]._calculate_forward_kinematics()
            if views["JOG"].page:
                views["JOG"].page.update()
        
        if mode_name in views:
            frame_middle.content = views[mode_name]
        else:
            frame_middle.content = ft.Text(f"View missing: {mode_name}", size=30, color="red")
            
        if mode_name == "SETTINGS" and "SETTINGS" in views:
            views["SETTINGS"].reset_view()
        
        frame_middle.alignment = ft.alignment.center
        page.update()

    for btn in footer_buttons:
        btn.on_click = wrapped_change_mode_clicked

    frame_bottom = ft.Container(
        content=ft.Row(controls=footer_buttons, spacing=10), 
        height=100,
        **STYL_RAMKI 
    )

    main_layout_column = ft.Column(
        controls=[frame_top, frame_middle, frame_bottom],
        expand=True,
        spacing=10
    )
    

    main_layout_container = ft.Container(
        content=main_layout_column,
        padding=10,
        expand=True
    )

    # --- MAIN STACK (LAYERS) ---
    root_stack = ft.Stack(
        controls=[
            main_layout_container, # Layer 0: Application
            estop_overlay          # Layer 1: ESTOP (above application)
        ],
        expand=True
    )

    page.add(root_stack)
    
    # --- Clock Thread ---
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
    
    # Default view setup
    if "JOG" in views:
        frame_middle.content = views["JOG"]
    else:
        frame_middle.content = ft.Text("JOG view unavailable", color="red")
        
    frame_middle.alignment = ft.alignment.center

    page.update()

# --- App Start ---
if __name__ == "__main__":
    # Folder and placeholder handling
    resources_dir = "resources"
    os.makedirs(resources_dir, exist_ok=True)
    
    gui_dir = os.path.join(os.getcwd(), "gui")
    os.makedirs(gui_dir, exist_ok=True)
    init_py = os.path.join(gui_dir, "__init__.py")
    if not os.path.exists(init_py): open(init_py, 'a').close()
    
    # Generating placeholder for AT
    at_img_path = os.path.join(resources_dir, "AT.png")
    if not os.path.exists(at_img_path) and Image:
        img = Image.new('RGB', (100, 100), color="#0055A4")
        img_draw = Image.new('RGB', (50, 50), color="#FFD700")
        img.paste(img_draw, (25, 25))
        img.save(at_img_path)
        
    # Generating placeholder for PoweredBy
    poweredby_img_path = os.path.join(resources_dir, "poweredby.png")
    if not os.path.exists(poweredby_img_path) and Image:
        Image.new('RGB', (200, 80), color="purple").save(poweredby_img_path)

    # Generating placeholder for ESTOP (if no file)
    estop_img_path = os.path.join(resources_dir, "ESTOP.png")
    if not os.path.exists(estop_img_path) and Image:
        # Red square with STOP text (simulation)
        Image.new('RGB', (300, 300), color="#FF0000").save(estop_img_path)

    # Generating buttons
    button_image_files = ["JOG.png", "CARTESIAN.png", "SETTINGS.png", "STATUS.png", "ERRORS.png"]
    button_colors = ["#FF6347", "#1E90FF", "#32CD32", "#FFD700", "#DC143C"]
    for img_file, color in zip(button_image_files, button_colors):
        img_path = os.path.join(resources_dir, img_file)
        if not os.path.exists(img_path) and Image:
            Image.new('RGB', (150, 70), color=color).save(img_path)

    ft.app(target=main, assets_dir="resources")