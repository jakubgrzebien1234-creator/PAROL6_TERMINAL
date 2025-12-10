import flet
import threading
import time
import math

class JogView(flet.Container):
    """
    JOG View (Joint Mode) - FINAL TOGGLE VERSION.
    - Electric Gripper: Toggle Button -> Sends EGRIP_OPEN / EGRIP_CLOSE
    - Pneumatic Gripper: Toggle Button -> Sends VAC_ON / VAC_OFF
    """

    def __init__(self, uart_communicator, on_status_update=None):
        super().__init__()
        
        self.uart = uart_communicator
        self.on_status_update = on_status_update 
        
        # --- STATE VARIABLES ---
        self.is_jogging = False
        self.active_jog_btn = None
        self.speed_percent = 50 
        
        # Homing flag
        self.is_robot_homed = False 
        self.homing_loading_dialog = None

        # Gripper states (True = Active/Closed, False = Inactive/Open)
        self.gripper_states = {
            "pneumatic": False, 
            "electric": False 
        }
        
        self.current_joint_values = {
            "J1": 0.0, "J2": 0.0, "J3": 0.0, 
            "J4": 0.0, "J5": 0.0, "J6": 0.0
        }
        
        self.target_joint_values = self.current_joint_values.copy()

        self.joint_limits = {
            "J1": (-90, 90), "J2": (-190, 48), "J3": (-69, 80),
            "J4": (-180, 120), "J5": (-120, 120), "J6": (-85, 260) 
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

    # --- DIALOGS ---
    def _show_homing_progress_dialog(self):
        if not self.page: return
        self.homing_loading_dialog = flet.AlertDialog(
            title=flet.Text("HOMING..."),
            content=flet.Container(
                height=150,
                content=flet.Column([
                    flet.ProgressRing(width=50, height=50, stroke_width=4),
                    flet.Container(height=20),  
                    flet.Text("Please wait, do not turn off the power.", size=12, color="grey")
                ], alignment=flet.MainAxisAlignment.CENTER, horizontal_alignment=flet.CrossAxisAlignment.CENTER)
            ),
            modal=True,
        )
        self.page.open(self.homing_loading_dialog)
        self.page.update()

    def show_homing_required_dialog(self):
        if not self.page: return
        def close_dlg(e): self.page.close(dlg)
        def start_homing_from_dlg(e):
            self.page.close(dlg)
            self.on_home_click(None)

        dlg = flet.AlertDialog(
            title=flet.Text("⚠️ Robot requires homing!"),
            content=flet.Text("To perform a move, you must first complete the homing procedure."),
            actions=[
                flet.TextButton("Cancel", on_click=close_dlg),
                flet.ElevatedButton("Start Homing", on_click=start_homing_from_dlg, bgcolor=flet.Colors.BLUE_700, color="white", icon=flet.Icons.HOME),
            ],
            actions_alignment=flet.MainAxisAlignment.END,
        )
        self.page.open(dlg)
        self.page.update()

    # --- STATUS METHODS ---
    def set_homed_status(self, is_homed: bool):
        self.is_robot_homed = is_homed
        print(f"[JogView] Robot homed status: {is_homed}")
        
        if self.page:
            if self.homing_loading_dialog and self.homing_loading_dialog.open:
                time.sleep(5.0) 
                try: self.page.close(self.homing_loading_dialog)
                except: pass
                self.homing_loading_dialog = None

            msg = "Robot homed - Control unlocked!" if is_homed else "Homing lost!"
            color = flet.Colors.GREEN if is_homed else flet.Colors.RED
            self.page.snack_bar = flet.SnackBar(flet.Text(msg), bgcolor=color)
            self.page.snack_bar.open = True
            self.page.update()

    def change_speed(self, delta):
        self.speed_percent = max(10, min(100, self.speed_percent + delta))
        self.lbl_speed.value = f"{self.speed_percent}%"
        self.page.update()

    def update_joints_and_fk(self, joint_values: dict):
        self.current_joint_values.update(joint_values)
        for k, v in joint_values.items():
            if k in self.position_value_labels:
                self.position_value_labels[k].value = f"{v:.2f}°"
        self._calculate_forward_kinematics()
        if self.page: self.page.update()

    def _calculate_forward_kinematics(self):
        try:
            th = [math.radians(self.current_joint_values[f"J{i}"]) for i in range(1, 7)]
            T = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]

            for i in range(6):
                a = self.dh_params[i]["a"]
                alpha = self.dh_params[i]["alpha"]
                d = self.dh_params[i]["d"]
                theta = th[i] + self.dh_params[i]["theta"]

                ct, st = math.cos(theta), math.sin(theta)
                ca, sa = math.cos(alpha), math.sin(alpha)

                Ti = [
                    [ct,    -st*ca,   st*sa,    a*ct],
                    [st,    ct*ca,    -ct*sa,   a*st],
                    [0,     sa,       ca,       d],
                    [0,     0,        0,        1]
                ]
                
                T_new = [[0]*4 for _ in range(4)]
                for r in range(4):
                    for c in range(4):
                        val = 0
                        for k in range(4):
                            val += T[r][k] * Ti[k][c]
                        T_new[r][c] = val
                T = T_new

            x, y, z = T[0][3], T[1][3], T[2][3]
            pitch = math.atan2(-T[2][0], math.sqrt(T[0][0]**2 + T[1][0]**2))
            if math.isclose(math.cos(pitch), 0):
                yaw = 0; roll = math.atan2(T[0][1], T[1][1])
            else:
                yaw = math.atan2(T[1][0], T[0][0]); roll = math.atan2(T[2][1], T[2][2])

            a_deg, b_deg, c_deg = math.degrees(yaw), math.degrees(pitch), math.degrees(roll)

            if "X" in self.tcp_labels: self.tcp_labels["X"].value = f"{x:.2f} mm"
            if "Y" in self.tcp_labels: self.tcp_labels["Y"].value = f"{y:.2f} mm"
            if "Z" in self.tcp_labels: self.tcp_labels["Z"].value = f"{z:.2f} mm"
            if "A" in self.tcp_labels: self.tcp_labels["A"].value = f"{a_deg:.2f}°"
            if "B" in self.tcp_labels: self.tcp_labels["B"].value = f"{b_deg:.2f}°"
            if "C" in self.tcp_labels: self.tcp_labels["C"].value = f"{c_deg:.2f}°"

        except Exception as e:
            print(f"FK Error: {e}")

    def _jog_thread(self, joint_code, direction):
        MAX_STEP_SIZE = 2.0 
        
        while self.is_jogging:
            speed_factor = self.speed_percent / 100.0
            
            # --- LOGIKA DLA SILNIKÓW ROBOTA (J1-J6) ---
            # Chwytaki są teraz obsługiwane przez przyciski (Events), nie Thread
            if joint_code in self.target_joint_values:
                current_step_size = max(0.05, MAX_STEP_SIZE * (speed_factor ** 1.5))
                if direction == "minus": current_step_size = -current_step_size
                
                potential_value = self.target_joint_values[joint_code] + current_step_size
                min_l, max_l = self.joint_limits.get(joint_code, (-180, 180))
                
                allow_move = False
                if min_l <= potential_value <= max_l: allow_move = True
                elif potential_value > max_l and current_step_size < 0: allow_move = True
                elif potential_value < min_l and current_step_size > 0: allow_move = True

                if allow_move:
                    if potential_value > max_l: potential_value = max_l
                    if potential_value < min_l: potential_value = min_l
                    
                    if abs(potential_value - self.target_joint_values[joint_code]) > 0.001:
                        self.target_joint_values[joint_code] = potential_value
                        if self.uart and self.uart.is_open():
                            val_to_send = potential_value
                            if joint_code in ["J2", "J3", "J5"]: val_to_send = -val_to_send
                            try: self.uart.send_message(f"J{joint_code[1]}_{val_to_send:.2f}")
                            except: pass
                            
            time.sleep(0.1)

    # --- EVENTS ---
    def on_jog_start(self, e, joint_code, direction, btn):
        if not self.is_robot_homed:
            self.show_homing_required_dialog()
            return 

        if self.is_jogging or self.active_jog_btn is not None: return
        self.active_jog_btn = btn
        self.is_jogging = True
        btn.bgcolor = "#111111"; btn.border = flet.border.all(1, "cyan"); btn.update()
        
        if joint_code in self.current_joint_values:
            self.target_joint_values[joint_code] = self.current_joint_values[joint_code]
            
        threading.Thread(target=self._jog_thread, args=(joint_code, direction), daemon=True).start()

    def on_jog_stop(self, e, joint_code, direction, btn):
        self.is_jogging = False
        self.active_jog_btn = None
        btn.bgcolor = "#444444"; btn.border = flet.border.all(1, "#666"); btn.update()

    def on_home_click(self, e):
        if self.uart: 
            self.uart.send_message("HOME")
            self._show_homing_progress_dialog()
        
    def on_stop_click(self, e):
        if self.uart: 
            self.uart.send_message("EGRIP_STOP")
        self.is_jogging = False
        
    def on_reset_click(self, e):
        if self.uart: self.uart.send_message("COLLISION_OK")
        if self.page: self.page.snack_bar = flet.SnackBar(flet.Text("Reset sent")); self.page.snack_bar.open = True; self.page.update()
        
    def on_change_tool_click(self, e):
        if self.uart:
            print("Sending tool change command...")
            self.uart.send_message("TOOL_CHANGE")
                
    def on_standby_click(self, e):
        if not self.is_robot_homed:
            self.show_homing_required_dialog()
            return
        standby = [0, 0, 0, 0, 0, 0]
        if self.uart:
            for i, val in enumerate(standby):
                val_to_send = val
                if (i+1) in [2, 3, 5]: val_to_send = -val 
                self.uart.send_message(f"J{i+1}_{val_to_send:.2f}"); time.sleep(0.02)
                
    def on_safety_click(self, e):
        if not self.is_robot_homed:
            self.show_homing_required_dialog()
            return
        safety_pos = [0, -45, 90, 0, -45, 0] 
        if self.uart:
            for i, val in enumerate(safety_pos):
                val_to_send = val
                if (i+1) in [2, 3, 5]: val_to_send = -val 
                self.uart.send_message(f"J{i+1}_{val_to_send:.2f}")
                time.sleep(0.02)

    def on_gripper_toggle_click(self, e):
        # Pobieramy typ chwytaka z danych przycisku (pneumatic lub electric)
        g_type = e.control.data 
        
        # Zmiana stanu
        new_state = not self.gripper_states.get(g_type, False)
        self.gripper_states[g_type] = new_state
        
        # Logika dla Pneumatycznego
        if g_type == "pneumatic":
            txt = "ON" if new_state else "OFF"
            cmd = "VAC_ON" if new_state else "VAC_OFF"
            
        # Logika dla Elektrycznego
        elif g_type == "electric":
            txt = "CLOSED" if new_state else "OPEN"
            cmd = "EGRIP_CLOSE" if new_state else "EGRIP_OPEN"
        
        # Aktualizacja wyglądu przycisku
        e.control.style.bgcolor = flet.Colors.GREEN_600 if new_state else flet.Colors.RED_600
        e.control.content.value = txt
        e.control.update()
        
        # Wysłanie komendy
        if self.uart: self.uart.send_message(cmd)

    def _create_joint_control(self, display_name: str) -> flet.Container:
        container_style = {"bgcolor": "#2D2D2D", "border_radius": 8, "border": flet.border.all(1, "#555555"), "padding": 5, "expand": True}
        
        # --- OBSŁUGA CHWYTAKÓW (WSPÓLNA LOGIKA TOGGLE) ---
        if "gripper" in display_name.lower():
            g_type = "electric" if "electric" in display_name.lower() else "pneumatic"
            
            # Pobranie aktualnego stanu
            state = self.gripper_states[g_type]
            
            if g_type == "electric":
                txt = "CLOSED" if state else "OPEN"
            else:
                txt = "ON" if state else "OFF"
                
            color = flet.Colors.GREEN_600 if state else flet.Colors.RED_600
            
            # Przycisk typu TOGGLE
            btn = flet.ElevatedButton(
                content=flet.Text(txt, size=14, weight="bold"), 
                style=flet.ButtonStyle(bgcolor=color, shape=flet.RoundedRectangleBorder(radius=8), color="white"), 
                on_click=self.on_gripper_toggle_click, 
                data=g_type, # Przekazujemy typ, żeby wiedzieć co kliknięto
                height=50, 
                expand=True
            )
            return flet.Container(content=flet.Column([
                flet.Text(display_name, size=13, color="white", text_align="center"), 
                flet.Row([btn], expand=True)
            ], spacing=2, horizontal_alignment="stretch"), **container_style)

        # --- OBSŁUGA SILNIKÓW (J1-J6) +/- ---
        else:
            joint_code = "UNK"
            if "(" in display_name: joint_code = display_name.split("(")[1].split(")")[0]

            def mk_btn(txt, d, code):
                c = flet.Container(
                    content=flet.Text(txt, size=30, weight="bold", color="white"), 
                    bgcolor="#444444", 
                    border_radius=8, 
                    alignment=flet.alignment.center, 
                    height=65, 
                    expand=True, 
                    shadow=flet.BoxShadow(blur_radius=2, color="black"), 
                    border=flet.border.all(1, "#666")
                )
                return flet.GestureDetector(
                    content=c, 
                    on_tap_down=lambda e: self.on_jog_start(e, code, d, c), 
                    on_tap_up=lambda e: self.on_jog_stop(e, code, d, c), 
                    on_long_press_end=lambda e: self.on_jog_stop(e, code, d, c), 
                    on_pan_end=lambda e: self.on_jog_stop(e, code, d, c), 
                    expand=True
                )
            
            return flet.Container(content=flet.Column([
                flet.Text(display_name, size=14, weight="bold", color="white", text_align="center"), 
                flet.Row([mk_btn("-", "minus", joint_code), mk_btn("+", "plus", joint_code)], spacing=5, expand=True)
            ], spacing=2, horizontal_alignment="stretch"), **container_style)