import flet
import numpy as np
import threading
import time
import json
import os
from ikpy.chain import Chain
from scipy.spatial.transform import Rotation as R

# ==============================================================================
# 1. KINEMATICS ENGINE (UNCHANGED)
# ==============================================================================
class KinematicsEngine:
    def __init__(self, urdf_path):
        self.chain = None
        # Dodajemy jedno 'False' na końcu, bo tcp_link jest nieruchomy względem L6
        self.hardcoded_mask = [False, True, True, True, True, True, True, False, False] 
        try:
            self.chain = Chain.from_urdf_file(urdf_path)
            if len(self.chain.links) != len(self.hardcoded_mask):
                self.hardcoded_mask = [True] * len(self.chain.links)
                self.hardcoded_mask[0] = False 
            self.chain.active_links_mask = self.hardcoded_mask
            self.chain.max_iterations = 1000
            self.chain.convergence_limit = 1e-3
            self.n_active_joints = sum(1 for x in self.hardcoded_mask if x)
            print(f"[IK] Kinematics OK. Active joints: {self.n_active_joints}")
        except Exception as e:
            print(f"[IK ERROR] {e}")
            self.chain = None
            self.n_active_joints = 6

    def _active_to_full(self, active_joints):
        active_arr = np.array(active_joints, dtype=float)
        if len(active_arr) != self.n_active_joints:
            active_arr = np.resize(active_arr, self.n_active_joints)
        full = np.zeros(len(self.chain.links))
        np.place(full, self.chain.active_links_mask, active_arr)
        return full

    def _full_to_active(self, full_vector):
        return np.compress(self.chain.active_links_mask, full_vector)

    def forward_kinematics(self, active_joints):
        full = self._active_to_full(active_joints)
        return self.chain.forward_kinematics(full)

    def inverse_kinematics(self, target_pos, target_orient, prev_joints):
        full_prev = self._active_to_full(prev_joints)
        full_sol = self.chain.inverse_kinematics(
            target_position=target_pos, target_orientation=target_orient,
            orientation_mode='all', initial_position=full_prev
        )
        return self._full_to_active(full_sol)

    def continuous_ik(self, target_pos, target_orient, prev_active_angles):
        prev = np.array(prev_active_angles)
        sol_A = self.inverse_kinematics(target_pos, target_orient, prev)
        
        # --- TU BYŁ BŁĄD / BRAK ---
        alt_prev = prev.copy()
        # Musimy pozwolić solverowi szukać rozwiązania "z drugiej strony"
        if len(alt_prev) >= 6: 
            alt_prev[0] *= -1  # Baza
            alt_prev[2] *= -1  # Łokieć (J3) - TO JEST KLUCZOWE DLA OSI Z!
            alt_prev[4] *= -1  # Nadgarstek (J5)
        # --------------------------

        sol_B = self.inverse_kinematics(target_pos, target_orient, alt_prev)
        
        def angle_diff(a, b): return np.sum(np.abs((a - b + np.pi) % (2*np.pi) - np.pi))
        
        # Wybierz to rozwiązanie, które wymaga mniejszego ruchu od aktualnej pozycji
        return sol_A if angle_diff(sol_A, prev) < angle_diff(sol_B, prev) else sol_B


# ==============================================================================
# 2. FLET VIEW - CARTESIAN CONTROL (Z OBSŁUGĄ TCP/OFFSETU)
# ==============================================================================
class CartesianView(flet.Container):
    def __init__(self, uart_communicator, urdf_path, active_links_mask=None):
        super().__init__()
        self.uart = uart_communicator
        self.ik = KinematicsEngine(urdf_path)
        self.is_jogging = False
        self.is_playing = False
        self.real_joints = [0.0] * self.ik.n_active_joints      
        self.commanded_joints = [0.0] * self.ik.n_active_joints 
        self.waypoints = []
        self.waypoints_file = "waypoints.json"
        
        # --- KONFIGURACJA CHWYTAKÓW (TCP) ---
        # Definiujemy przesunięcie [x, y, z] w metrach względem flanszy (L6)
        # Jeśli chwytak jest prosty i ma 15cm, to [0, 0, 0.15]
        self.tool_offset = np.array([0.0, 0.0, 0.18]) 
        # ------------------------------------

        self._load_waypoints()
        self.padding = 10
        self._setup_ui()
        self.sync_real_to_planned()

    def _setup_ui(self):
        panel_style = {
            "bgcolor": "#2D2D2D",
            "border_radius": 10,
            "border": flet.border.all(1, "#555555"),
            "padding": 10
        }

        # 1. LEFT SIDE (JOG CONTROLS)
        left_items = [("Axis X", "x"), ("Axis Y", "y"), ("Axis Z", "z"), ("Gripper E.", "gripper_e")]
        right_items = [("Rot A (Rx)", "rx"), ("Rot B (Ry)", "ry"), ("Rot C (Rz)", "rz"), ("Gripper P.", "gripper_p")]

        jog_col = flet.Column(spacing=15, expand=True)
        for i in range(4):
            jog_col.controls.append(flet.Row([
                self._create_btn(left_items[i][0], left_items[i][1]), 
                self._create_btn(right_items[i][0], right_items[i][1])
            ], spacing=15, expand=True))

        jog_container = flet.Container(content=jog_col, expand=55, padding=5)

        # 2. CENTER (POSITION DISPLAY)
        self.pos_labels = {}
        pos_list = flet.Column(spacing=5)
        pos_list.controls.append(flet.Text("TCP POSITION [mm]", size=12, color="orange", weight="bold", text_align="center"))

        for ax in ["X", "Y", "Z", "Rx", "Ry", "Rz"]:
            self.pos_labels[ax] = flet.Text("0.0", size=15, color="cyan", weight="bold")
            pos_list.controls.append(flet.Row([flet.Text(f"{ax}:", weight="bold", size=14, color="white"), self.pos_labels[ax]], alignment="spaceBetween"))
        
        self.lbl_ge = flet.Text("-", size=14, color="white"); self.lbl_gp = flet.Text("-", size=14, color="white")
        pos_list.controls.append(flet.Divider(color="#555", thickness=1))
        pos_list.controls.append(flet.Row([flet.Text("E:", weight="bold"), self.lbl_ge], alignment="spaceBetween"))
        pos_list.controls.append(flet.Row([flet.Text("P:", weight="bold"), self.lbl_gp], alignment="spaceBetween"))

        # PRZYCISKI DO ZMIANY NARZĘDZIA (OPCJONALNE)
        btn_tool1 = flet.ElevatedButton("TOOL 1 (15cm)", on_click=lambda e: self.set_tool(0.15), height=30)
        btn_tool2 = flet.ElevatedButton("TOOL 2 (5cm)", on_click=lambda e: self.set_tool(0.05), height=30)

        # Control Buttons
        BTN_H = 40
        row_aux = flet.Row([
            flet.ElevatedButton("HOME", icon=flet.Icons.HOME, style=flet.ButtonStyle(bgcolor=flet.Colors.BLUE_900, color="white", shape=flet.RoundedRectangleBorder(radius=5), padding=0), height=BTN_H, expand=True, on_click=self.on_home_click),
            flet.ElevatedButton("STBY", icon=flet.Icons.ACCESSIBILITY, style=flet.ButtonStyle(bgcolor=flet.Colors.ORANGE_900, color="white", shape=flet.RoundedRectangleBorder(radius=5), padding=0), height=BTN_H, expand=True, on_click=self.on_standby_click)
        ], spacing=5)
        
        btn_exec = flet.ElevatedButton("EXECUTE", icon=flet.Icons.SEND, style=flet.ButtonStyle(bgcolor=flet.Colors.GREEN_700, color="white", shape=flet.RoundedRectangleBorder(radius=5)), height=45, width=1000, on_click=self.on_send_move_click)
        btn_stop = flet.ElevatedButton("STOP", icon=flet.Icons.STOP_CIRCLE, style=flet.ButtonStyle(bgcolor=flet.Colors.RED_700, color="white", shape=flet.RoundedRectangleBorder(radius=5)), height=45, width=1000, on_click=self.on_stop_click)

        pos_frame = flet.Container(content=flet.Column([flet.Container(content=pos_list, expand=True), flet.Row([btn_tool1, btn_tool2]), flet.Divider(color="#444"), row_aux, btn_exec, btn_stop], spacing=5), **panel_style, expand=20)

        # 3. RIGHT SIDE (WAYPOINTS LIST)
        self.waypoints_list_view = flet.ListView(expand=True, spacing=5, padding=5)
        clear_btn = flet.IconButton(icon=flet.Icons.DELETE_FOREVER, icon_size=20, icon_color="red", tooltip="Clear List", on_click=self.clear_waypoints)
        teach_buttons = flet.Column([
            flet.ElevatedButton("SAVE POINT", icon=flet.Icons.ADD_LOCATION, style=flet.ButtonStyle(bgcolor=flet.Colors.BLUE_700, color="white", shape=flet.RoundedRectangleBorder(radius=8)), height=40, width=1000, on_click=self.add_waypoint),
            flet.ElevatedButton("PLAYBACK", icon=flet.Icons.PLAY_ARROW, style=flet.ButtonStyle(bgcolor=flet.Colors.PURPLE_700, color="white", shape=flet.RoundedRectangleBorder(radius=8)), height=45, width=1000, on_click=self.run_playback)
        ], spacing=10)

        teach_frame = flet.Container(content=flet.Column([flet.Row([flet.Text("WAYPOINTS", size=14, weight="bold"), clear_btn], alignment="spaceBetween"), flet.Container(content=self.waypoints_list_view, expand=True, bgcolor="#1A1A1A", border_radius=5, border=flet.border.all(1, "#444")), flet.Container(height=5), teach_buttons]), **panel_style, expand=25)

        self.content = flet.Row([jog_container, pos_frame, teach_frame], spacing=10)
        self._refresh_waypoints_list()

    def set_tool(self, length_m):
        self.tool_offset = np.array([0.0, 0.0, length_m])
        print(f"Zmieniono narzędzie. Długość: {length_m}m")
        self.update_display_positions()

    # --- CREATE JOG BUTTONS ---
    def _create_btn(self, label, code):
        container_style = {
            "bgcolor": "#2D2D2D",
            "border_radius": 8,
            "padding": 5,
            "border": flet.border.all(1, "#555555")
        }

        if "gripper" in code:
            return flet.Container(content=flet.Column([
                flet.Text(label, weight="bold", size=14, text_align="center"),
                flet.Row([
                    flet.ElevatedButton("OFF", style=flet.ButtonStyle(shape=flet.RoundedRectangleBorder(radius=5), padding=0), on_click=lambda e: self._send_grip(code, 'OFF'), expand=True, height=45),
                    flet.ElevatedButton("ON", style=flet.ButtonStyle(shape=flet.RoundedRectangleBorder(radius=5), padding=0), on_click=lambda e: self._send_grip(code, 'ON'), expand=True, height=45)
                ], spacing=5)
            ], spacing=2, horizontal_alignment="center"), **container_style, expand=True)
        
        def mk_jog_btn(txt, direction):
            btn_visual = flet.Container(
                content=flet.Text(txt, size=24, weight="bold", color="white"),
                bgcolor="#444444", 
                border_radius=8,
                alignment=flet.alignment.center,
                border=flet.border.all(1, "#666"),
                expand=True
            )
            return flet.GestureDetector(content=btn_visual, on_tap_down=lambda e: self.on_jog_start(e, code, direction, btn_visual), on_tap_up=lambda e: self.on_jog_stop(e, code, direction, btn_visual), on_pan_end=lambda e: self.on_jog_stop(e, code, direction, btn_visual), expand=True)

        return flet.Container(content=flet.Column([
            flet.Text(label, weight="bold", size=14, text_align="center"),
            flet.Row([mk_jog_btn("-", "minus"), mk_jog_btn("+", "plus")], spacing=5, expand=True)
        ], spacing=2, horizontal_alignment="center", expand=True), **container_style, height=85, expand=True)

    # --- LOGIC ---
    def add_waypoint(self, e):
        mat = self.ik.forward_kinematics(self.commanded_joints)
        pos_flange = mat[:3, 3]
        rot_flange = mat[:3, :3]
        pos_tcp = pos_flange + rot_flange @ self.tool_offset
        
        idx = len(self.waypoints) + 1
        xu, yu, zu = self._convert_robot_to_user(pos_tcp)
        coords_str = f"X:{xu:.0f} Y:{yu:.0f} Z:{zu:.0f}"
        point_data = {"name": f"P{idx}", "joints": list(self.commanded_joints), "coords": coords_str, "gripper_e": self.lbl_ge.value, "gripper_p": self.lbl_gp.value}
        self.waypoints.append(point_data)
        self._save_waypoints()
        self._refresh_waypoints_list()

    def _refresh_waypoints_list(self):
        self.waypoints_list_view.controls.clear()
        for i, wp in enumerate(self.waypoints):
            row = flet.Container(content=flet.Row([flet.Text(f"{i+1}. {wp['coords']}", size=12, color="white", expand=True, no_wrap=True), flet.IconButton(flet.Icons.CLOSE, icon_size=14, icon_color="red", on_click=lambda e, idx=i: [self.waypoints.pop(idx), self._save_waypoints(), self._refresh_waypoints_list()])], alignment="spaceBetween"), bgcolor="#333", border_radius=5, padding=5)
            self.waypoints_list_view.controls.append(row)
        if self.page: self.page.update()

    def run_playback(self, e):
        if self.is_playing or not self.waypoints: return
        def playback_thread():
            self.is_playing = True; print("--- PLAYBACK START ---")
            for i, wp in enumerate(self.waypoints):
                if not self.is_playing: break 
                self.commanded_joints = list(wp['joints']); self.update_display_positions()
                if self.uart and self.uart.is_open():
                    for j, rad in enumerate(wp['joints']): self.uart.send_message(f"J{j+1}_{np.degrees(rad):.2f}"); time.sleep(0.01)
                    self.uart.send_message(f"EGRIP{'_CLOSED' if wp['gripper_e']=='CLOSED' else '_OPEN'}")
                    self.uart.send_message(f"VAC_{'ON' if wp['gripper_p']=='ON' else 'OFF'}")
                diff = np.max(np.abs(np.array(wp['joints']) - np.array(self.real_joints))); time.sleep(max(1.5, diff * 2.5))
            print("--- PLAYBACK END ---"); self.is_playing = False; self.sync_real_to_planned()
        threading.Thread(target=playback_thread, daemon=True).start()

    def on_stop_click(self, e): self.is_jogging = False; self.is_playing = False; self.sync_real_to_planned()
    def on_home_click(self, e): 
        if self.uart: self.uart.send_message("HOME"); threading.Thread(target=lambda: [time.sleep(5), self.sync_real_to_planned()], daemon=True).start()
    def on_standby_click(self, e):
        sb = [0, -15, 45, 0, 0, 0]; self.commanded_joints = [np.deg2rad(a) for a in sb]; self.update_display_positions()
        if self.uart: [self.uart.send_message(f"J{i+1}_{d:.2f}") or time.sleep(0.02) for i, d in enumerate(sb)]

    # --- POPRAWKI SKŁADNIOWE ---
    def _save_waypoints(self): 
        try:
            with open(self.waypoints_file, 'w') as f:
                json.dump(self.waypoints, f)
        except:
            pass

    def _load_waypoints(self):
        if os.path.exists(self.waypoints_file):
            try:
                with open(self.waypoints_file, 'r') as f:
                    self.waypoints = json.load(f)
            except:
                self.waypoints = []

    def clear_waypoints(self, e):
        self.waypoints = []
        self._save_waypoints()
        self._refresh_waypoints_list()
        
    def sync_real_to_planned(self): self.commanded_joints = list(self.real_joints); self.update_display_positions()
    def _on_uart_data(self, data: str):
        if "_" in data and data.startswith("A"):
            try: 
                idx = int(data.split("_")[0][1:]) - 1; val = float(data.split("_")[1])
                if 0 <= idx < self.ik.n_active_joints: self.real_joints[idx] = np.deg2rad(val)
            except: pass
    def _convert_robot_to_user(self, p): return -p[1]*1000, p[0]*1000, p[2]*1000
    def _convert_user_delta_to_robot(self, dx, dy, dz): return dy, -dx, dz

    def update_display_positions(self):
        if not self.ik.chain: return
        
        # 1. Kinematyka prosta do FLANSZY
        mat = self.ik.forward_kinematics(self.commanded_joints)
        pos_flange = mat[:3, 3]
        rot_flange = mat[:3, :3]
        
        # 2. Dodajemy offset (TCP = Flansza + Rotacja * Offset)
        pos_tcp = pos_flange + rot_flange @ self.tool_offset
        
        rot_euler = R.from_matrix(rot_flange).as_euler('xyz', degrees=False)
        xu, yu, zu = self._convert_robot_to_user(pos_tcp)
        
        self.pos_labels["X"].value = f"{xu:.1f}"
        self.pos_labels["Y"].value = f"{yu:.1f}"
        self.pos_labels["Z"].value = f"{zu:.1f}"
        self.pos_labels["Rx"].value = f"{rot_euler[0]:.2f}"
        self.pos_labels["Ry"].value = f"{rot_euler[1]:.2f}"
        self.pos_labels["Rz"].value = f"{rot_euler[2]:.2f}"
        if self.page: self.page.update()
    
    def calculate_step(self, axis, direction):
        if not self.ik.chain: return
        
        mat = self.ik.forward_kinematics(self.commanded_joints)
        pos_flange = mat[:3, 3]
        rot_flange = mat[:3, :3]
        
        curr_pos_tcp = pos_flange + rot_flange @ self.tool_offset
        curr_rot = rot_flange
        
        step_mm = 5.0
        step_rad = 0.05
        sign = 1 if direction == "plus" else -1
        
        dx, dy, dz = 0, 0, 0
        drx, dry, drz = 0, 0, 0
        
        if axis == 'x': dx = step_mm * sign
        elif axis == 'y': dy = step_mm * sign
        elif axis == 'z': dz = step_mm * sign
        elif axis == 'rx': drx = step_rad * sign
        elif axis == 'ry': dry = step_rad * sign
        elif axis == 'rz': drz = step_rad * sign
        
        dx_r, dy_r, dz_r = self._convert_user_delta_to_robot(dx, dy, dz)
        
        target_pos_tcp = curr_pos_tcp + np.array([dx_r, dy_r, dz_r]) / 1000.0
        
        if axis in ['rx','ry','rz']:
            target_rot = R.from_euler('xyz', [drx, dry, drz]).as_matrix() @ curr_rot
        else:
            target_rot = curr_rot

        target_pos_flange = target_pos_tcp - target_rot @ self.tool_offset

        try:
            nj = self.ik.continuous_ik(target_pos_flange, target_rot, self.commanded_joints)
            nj = [(q + np.pi) % (2*np.pi) - np.pi for q in nj]
            
            diff = np.sum(np.abs(np.array(nj) - np.array(self.commanded_joints)))
            
            if diff > 0.0001:
                self.commanded_joints = nj
                self.update_display_positions()
                print(f"Planowanie {axis}: Nowa pozycja (TCP Offset={self.tool_offset[2]})")
            else:
                print(f"Planowanie {axis}: Brak rozwiązania IK")

        except Exception as e:
            print(f"Błąd w calculate_step: {e}")

    def on_send_move_click(self, e):
        print("Wysyłanie zaplanowanej pozycji do robota...")
        if self.uart: 
            for i, r in enumerate(self.commanded_joints):
                msg = f"J{i+1}_{np.degrees(r):.2f}"
                self.uart.send_message(msg)
                time.sleep(0.01)

    def _jog_thread(self, ax, d):
        while self.is_jogging: self.calculate_step(ax, d); time.sleep(0.05)
    def on_jog_start(self, e, c, d, b): b.bgcolor = "#666"; b.update(); self.is_jogging = True; threading.Thread(target=self._jog_thread, args=(c, d), daemon=True).start()
    def on_jog_stop(self, e, c, d, b): self.is_jogging = False; b.bgcolor = "#444"; b.update()
    def _send_grip(self, c, s):
        if c == "gripper_p": self.lbl_gp.value = "ON" if s=='ON' else "OFF"; self.uart.send_message(f"VAC_{s}")
        else: self.lbl_ge.value = "CLOSED" if s=='ON' else "OPEN"; self.uart.send_message(f"VALVE{'ON' if s=='ON' else 'OFF'}")
        self.page.update()