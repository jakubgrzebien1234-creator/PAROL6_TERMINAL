import flet
import threading
import time
import math

class JogView(flet.Container):
    """
    JOG View - Wersja naprawiona
    Poprawnie zamyka okno Homing po otrzymaniu sygnału.
    """

    def __init__(self, uart_communicator, on_status_update=None):
        super().__init__()
        
        self.uart = uart_communicator
        self.on_status_update = on_status_update 
        
        # --- KONFIGURACJA KIERUNKÓW ---
        self.AXIS_DIRECTIONS = {
            "J1": -1, "J2": -1, "J3": -1, "J4": -1, "J5": -1, "J6": -1
        }
        self.DISPLAY_INVERTED = ["J1", "J2", "J3", "J4", "J5"]
        
        # --- ZMIENNE STANU ---
        self.is_jogging = False
        self.active_jog_btn = None
        self.speed_percent = 50 
        self.is_robot_homed = False 
        
        # Zmienna przechowująca referencję do okna dialogowego
        self.homing_loading_dialog = None

        self.gripper_states = {"pneumatic": False, "electric": False}
        self.current_raw_values = { f"J{i}": 0.0 for i in range(1, 7) }
        self.internal_target_values = { f"J{i}": 0.0 for i in range(1, 7) }
        self.initial_sync_done = False

        # Limity i parametry DH
        self.joint_limits = {
            "J1": (-90, 90), "J2": (-50, 140), "J3": (-100, 70),
            "J4": (-100, 180), "J5": (-120, 110), "J6": (-110, 180) 
        }
        self.dh_params = [
            {"a": 23.42,   "alpha": -math.pi/2, "d": 110.50,  "theta": 0},
            {"a": 180.00,  "alpha": math.pi,    "d": 0,       "theta": -math.pi/2},
            {"a": -43.50,  "alpha": math.pi/2,  "d": 0,       "theta": math.pi},
            {"a": 0,       "alpha": -math.pi/2, "d": -176.35, "theta": 0},
            {"a": 0,       "alpha": math.pi/2,  "d": 0,       "theta": 0},
            {"a": -100.00, "alpha": math.pi,    "d": -62.80,  "theta": math.pi}
        ]

        self.padding = 10 
        self.motors_list = ["Motor 1 (J1)", "Motor 2 (J2)", "Motor 3 (J3)", "Motor 4 (J4)", "Motor 5 (J5)", "Motor 6 (J6)"]
        self.grippers_list = ["Electric Gripper", "Pneumatic Gripper"]
        self._setup_ui()

    def _setup_ui(self):
        # [Tutaj UI bez zmian, skrócone dla czytelności]
        panel_style = {"bgcolor": "#2D2D2D", "border_radius": 10, "border": flet.border.all(1, "#555555"), "padding": 10}

        motors_column = flet.Column(spacing=5, expand=True)
        for i in range(0, len(self.motors_list), 2):
            if i+1 < len(self.motors_list):
                panel1 = self._create_joint_control(self.motors_list[i])
                panel2 = self._create_joint_control(self.motors_list[i+1])
                motors_column.controls.append(flet.Row(controls=[panel1, panel2], spacing=5, expand=True))

        gripper_row = flet.Row(spacing=5, expand=True)
        for g_name in self.grippers_list:
            gripper_row.controls.append(self._create_joint_control(g_name))
        motors_column.controls.append(gripper_row)
        motors_container = flet.Container(content=motors_column, expand=20)
        
        self.lbl_speed = flet.Text(f"{self.speed_percent}%", size=24, weight="bold", color="cyan")
        speed_panel = flet.Container(
            content=flet.Column([
                flet.Text("VELOCITY", size=14, color="grey", weight="bold"),
                flet.Row([
                    flet.IconButton(flet.Icons.REMOVE, icon_color="white", bgcolor="#444", on_click=lambda e: self.change_speed(-10), icon_size=24),
                    flet.Container(content=self.lbl_speed, alignment=flet.alignment.center, width=80, bgcolor="#222", border_radius=5, padding=5),
                    flet.IconButton(flet.Icons.ADD, icon_color="white", bgcolor="#444", on_click=lambda e: self.change_speed(10), icon_size=24)
                ], alignment="center", spacing=10)
            ], horizontal_alignment="center", spacing=5),
            bgcolor="#2D2D2D", border_radius=10, border=flet.border.all(1, "#555555"), padding=10
        )

        TOOL_BTN_H = 40 
        tools_column = flet.Column([
            speed_panel, flet.Container(height=5),
            flet.ElevatedButton("HOME", icon=flet.Icons.HOME, style=flet.ButtonStyle(bgcolor=flet.Colors.BLUE_GREY_700, color="white", shape=flet.RoundedRectangleBorder(radius=8)), height=TOOL_BTN_H, width=10000, on_click=self.on_home_click),
            flet.ElevatedButton("SAFETY", icon=flet.Icons.SHIELD, style=flet.ButtonStyle(bgcolor=flet.Colors.TEAL_700, color="white", shape=flet.RoundedRectangleBorder(radius=8)), height=TOOL_BTN_H, width=10000, on_click=self.on_safety_click),
            flet.ElevatedButton("GRIPPER CHANGE", icon=flet.Icons.HANDYMAN, style=flet.ButtonStyle(bgcolor=flet.Colors.PURPLE_700, color="white", shape=flet.RoundedRectangleBorder(radius=8)), height=TOOL_BTN_H, width=10000, on_click=self.on_change_tool_click),
            flet.ElevatedButton("STOP", icon=flet.Icons.STOP_CIRCLE, style=flet.ButtonStyle(bgcolor=flet.Colors.RED_700, color="white", shape=flet.RoundedRectangleBorder(radius=8)), height=TOOL_BTN_H, width=10000, on_click=self.on_stop_click),
            flet.ElevatedButton("STANDBY", icon=flet.Icons.ACCESSIBILITY, style=flet.ButtonStyle(bgcolor=flet.Colors.ORANGE_900, color="white", shape=flet.RoundedRectangleBorder(radius=8)), height=TOOL_BTN_H, width=10000, on_click=self.on_standby_click),
            flet.Container(expand=True),
            flet.ElevatedButton("ERROR RESET", icon=flet.Icons.RESTART_ALT, style=flet.ButtonStyle(bgcolor=flet.Colors.ORANGE_800, color="white", shape=flet.RoundedRectangleBorder(radius=8)), height=TOOL_BTN_H, width=10000, on_click=self.on_reset_click)
        ], spacing=5, expand=True)
        tools_container = flet.Container(content=tools_column, expand=5, padding=flet.padding.symmetric(horizontal=5))

        pos_list = flet.Column(spacing=8, horizontal_alignment="stretch")
        pos_list.controls.append(flet.Text("POSITION", size=16, weight="bold", color="white", text_align="center"))
        self.position_value_labels = {} 
        for name in ["J1", "J2", "J3", "J4", "J5", "J6"]:
            lbl = flet.Text("0.00°", size=15, color="cyan", weight="bold")
            self.position_value_labels[name] = lbl
            pos_list.controls.append(flet.Row([flet.Text(f"{name}:", weight="bold"), lbl], alignment="spaceBetween"))
        
        pos_list.controls.append(flet.Divider(height=10, color="#555"))
        
        self.tcp_labels = {}
        for name in ["X", "Y", "Z", "A", "B", "C"]:
            col = "cyan" if name in ["X", "Y", "Z"] else "orange"
            unit = "mm" if name in ["X", "Y", "Z"] else "°"
            lbl = flet.Text(f"0.00 {unit}", size=15, color=col, weight="bold")
            self.tcp_labels[name] = lbl
            pos_list.controls.append(flet.Row([flet.Text(f"{name}:", weight="bold"), lbl], alignment="spaceBetween"))

        position_frame = flet.Container(content=pos_list, **panel_style, expand=4)
        self.content = flet.Row([motors_container, tools_container, position_frame], spacing=10, vertical_alignment=flet.CrossAxisAlignment.STRETCH)

    def update_joints_and_fk(self, joint_values: dict):
        for k, v in joint_values.items():
            self.current_raw_values[k] = v 
            if not self.initial_sync_done and not self.is_jogging:
                self.internal_target_values[k] = v
            
            display_val = v
            if k in self.DISPLAY_INVERTED:
                display_val = -v
            if k in self.position_value_labels:
                self.position_value_labels[k].value = f"{display_val:.2f}°"
        
        if joint_values:
            self.initial_sync_done = True
        self._calculate_forward_kinematics()
        if self.page: self.page.update()

    def _jog_thread(self, joint_code, button_type):
        STEP_INCREMENT = 0.5
        direction_multiplier = self.AXIS_DIRECTIONS.get(joint_code, 1)

        while self.is_jogging:
            current_target = self.internal_target_values.get(joint_code, 0.0)
            button_dir = 1 if button_type == "plus" else -1
            delta = STEP_INCREMENT * button_dir * direction_multiplier
            new_target = current_target + delta
            
            if joint_code in self.joint_limits:
                min_limit, max_limit = self.joint_limits[joint_code]
                if new_target < min_limit: new_target = min_limit
                elif new_target > max_limit: new_target = max_limit

            self.internal_target_values[joint_code] = new_target
            if self.uart and self.uart.is_open():
                try: 
                    self.uart.send_message(f"J{joint_code[1]}_{new_target:.2f}")
                except: pass
            time.sleep(0.05)

    def on_jog_start(self, e, joint_code, direction, btn):
        if not self.is_robot_homed:
            self.show_homing_required_dialog()
            return 
        if self.is_jogging: return
        self.active_jog_btn = btn
        self.is_jogging = True
        btn.content.bgcolor = "#111111"
        btn.content.border = flet.border.all(1, "cyan")
        btn.content.update()
        threading.Thread(target=self._jog_thread, args=(joint_code, direction), daemon=True).start()

    def on_jog_stop(self, e, joint_code, direction, btn):
        self.is_jogging = False
        self.active_jog_btn = None
        btn.content.bgcolor = "#444444"
        btn.content.border = flet.border.all(1, "#666")
        btn.content.update()

    # --- KLUCZOWA METODA DO ZAMYKANIA OKNA ---
    def set_homed_status(self, is_homed: bool):
        print(f"[JOG] set_homed_status wywołane: {is_homed}") # DEBUG
        self.is_robot_homed = is_homed
        if is_homed:
            self.internal_target_values = { f"J{i}": 0.0 for i in range(1, 7) }
            self.initial_sync_done = True 

        if self.page:
            # Zamykanie okna dialogowego
            if self.homing_loading_dialog:
                print("[JOG] Zamykam dialog...") # DEBUG
                self.homing_loading_dialog.open = False
                self.page.update()
                try:
                    self.page.close(self.homing_loading_dialog)
                except Exception as e:
                    print(f"Błąd close: {e}")
                self.homing_loading_dialog = None
            
            msg = "Robot homed!" if is_homed else "Homing lost!"
            color = flet.Colors.GREEN if is_homed else flet.Colors.RED
            self.page.snack_bar = flet.SnackBar(flet.Text(msg), bgcolor=color)
            self.page.snack_bar.open = True
            self.page.update()

    def on_home_click(self, e):
        if self.uart: 
            print("[JOG] Start Homing")
            self.uart.send_message("HOME")
            self._show_homing_progress_dialog()

    def _show_homing_progress_dialog(self):
        if not self.page: return
        # Zabezpieczenie przed podwójnym oknem
        if self.homing_loading_dialog is not None: return

        self.homing_loading_dialog = flet.AlertDialog(
            title=flet.Text("HOMING..."),
            content=flet.Container(
                height=150,
                content=flet.Column([
                    flet.Row([flet.ProgressRing(width=50, height=50, stroke_width=4, color="cyan")], alignment=flet.MainAxisAlignment.CENTER),
                    flet.Container(height=20),  
                    flet.Text("Please wait...", size=12, color="grey")
                ], alignment=flet.MainAxisAlignment.CENTER, horizontal_alignment=flet.CrossAxisAlignment.CENTER)
            ),
            modal=True
        )
        self.page.open(self.homing_loading_dialog)
        self.page.update()

    def show_homing_required_dialog(self):
        if not self.page: return
        self.page.open(flet.AlertDialog(title=flet.Text("Homing Required!")))
        self.page.update()

    def on_stop_click(self, e):
        if self.uart: self.uart.send_message("EGRIP_STOP"); self.is_jogging = False
        
    def on_reset_click(self, e):
        if self.uart: self.uart.send_message("COLLISION_OK")
        self.internal_target_values = self.current_raw_values.copy()
        
    def on_change_tool_click(self, e):
        if self.uart: self.uart.send_message("TOOL_CHANGE")
                
    def on_standby_click(self, e):
        if self.uart:
            for i in range(1, 7): 
                self.internal_target_values[f"J{i}"] = 0.0
                self.uart.send_message(f"J{i}_0.00")
                time.sleep(0.02)
                
    def on_safety_click(self, e):
        visual_targets = [0, 50, -70, -90, 0, 0]
        if self.uart:
            for i, vis_val in enumerate(visual_targets):
                idx = f"J{i+1}"
                raw_val = vis_val
                if idx in self.DISPLAY_INVERTED: raw_val = -vis_val 
                self.internal_target_values[idx] = raw_val
                self.uart.send_message(f"{idx}_{raw_val:.2f}")
                time.sleep(0.02)
    
    def change_speed(self, delta):
        self.speed_percent = max(10, min(100, self.speed_percent + delta))
        self.lbl_speed.value = f"{self.speed_percent}%"
        self.lbl_speed.update()

    def on_gripper_toggle_click(self, e):
        g_type = e.control.data 
        new_state = not self.gripper_states.get(g_type, False)
        self.gripper_states[g_type] = new_state
        cmd = "VAC_ON" if new_state else "VAC_OFF"
        if g_type == "electric": cmd = "EGRIP_CLOSE" if new_state else "EGRIP_OPEN"
        e.control.style.bgcolor = flet.Colors.GREEN_600 if new_state else flet.Colors.RED_600
        e.control.content.value = "ON" if new_state else "OFF"
        if g_type == "electric": e.control.content.value = "CLOSED" if new_state else "OPEN"
        e.control.update()
        if self.uart: self.uart.send_message(cmd)

    def _create_joint_control(self, display_name: str) -> flet.Container:
        container_style = {"bgcolor": "#2D2D2D", "border_radius": 8, "border": flet.border.all(1, "#555555"), "padding": 5, "expand": True}
        if "gripper" in display_name.lower():
            g_type = "electric" if "electric" in display_name.lower() else "pneumatic"
            state = self.gripper_states[g_type]
            txt = "CLOSED" if state and g_type=="electric" else ("OPEN" if g_type=="electric" else ("ON" if state else "OFF"))
            btn = flet.ElevatedButton(content=flet.Text(txt, size=14), style=flet.ButtonStyle(bgcolor=flet.Colors.GREEN_600 if state else flet.Colors.RED_600), on_click=self.on_gripper_toggle_click, data=g_type, height=50, expand=True)
            return flet.Container(content=flet.Column([flet.Text(display_name, size=13, color="white", text_align="center"), flet.Row([btn], expand=True)], spacing=2), **container_style)
        else:
            joint_code = "UNK"
            if "(" in display_name: joint_code = display_name.split("(")[1].split(")")[0]
            def mk_btn(txt, d, code):
                c = flet.Container(content=flet.Text(txt, size=30, weight="bold", color="white"), bgcolor="#444444", border_radius=8, alignment=flet.alignment.center, height=65, shadow=flet.BoxShadow(blur_radius=2, color="black"), border=flet.border.all(1, "#666"))
                gest = flet.GestureDetector(content=c, on_tap_down=lambda e: self.on_jog_start(e, code, d, gest), on_tap_up=lambda e: self.on_jog_stop(e, code, d, gest), on_long_press_end=lambda e: self.on_jog_stop(e, code, d, gest), on_pan_end=lambda e: self.on_jog_stop(e, code, d, gest))
                return flet.Container(content=gest, expand=True)
            return flet.Container(content=flet.Column([flet.Text(display_name, size=14, weight="bold", color="white", text_align="center"), flet.Row([mk_btn("-", "minus", joint_code), mk_btn("+", "plus", joint_code)], spacing=5, expand=True)], spacing=2), **container_style)

    def _calculate_forward_kinematics(self):
        try:
            joints_visual = {}
            for k, v in self.current_raw_values.items():
                if k in self.DISPLAY_INVERTED: joints_visual[k] = -v
                else: joints_visual[k] = v
            th = [math.radians(joints_visual[f"J{i}"]) for i in range(1, 7)]
            T = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
            for i in range(6):
                a, alpha, d, theta = self.dh_params[i]["a"], self.dh_params[i]["alpha"], self.dh_params[i]["d"], th[i] + self.dh_params[i]["theta"]
                ct, st, ca, sa = math.cos(theta), math.sin(theta), math.cos(alpha), math.sin(alpha)
                Ti = [[ct, -st*ca, st*sa, a*ct], [st, ct*ca, -ct*sa, a*st], [0, sa, ca, d], [0, 0, 0, 1]]
                T_new = [[sum(T[r][k]*Ti[k][c] for k in range(4)) for c in range(4)] for r in range(4)]
                T = T_new
            x, y, z = T[0][3], T[1][3], T[2][3]
            pitch = math.atan2(-T[2][0], math.sqrt(T[0][0]**2 + T[1][0]**2))
            yaw, roll = (0, math.atan2(T[0][1], T[1][1])) if math.isclose(math.cos(pitch), 0) else (math.atan2(T[1][0], T[0][0]), math.atan2(T[2][1], T[2][2]))
            if "X" in self.tcp_labels: self.tcp_labels["X"].value = f"{x:.2f} mm"
            if "Y" in self.tcp_labels: self.tcp_labels["Y"].value = f"{y:.2f} mm"
            if "Z" in self.tcp_labels: self.tcp_labels["Z"].value = f"{z:.2f} mm"
            if "A" in self.tcp_labels: self.tcp_labels["A"].value = f"{math.degrees(yaw):.2f}°"
            if "B" in self.tcp_labels: self.tcp_labels["B"].value = f"{math.degrees(pitch):.2f}°"
            if "C" in self.tcp_labels: self.tcp_labels["C"].value = f"{math.degrees(roll):.2f}°"
        except: pass