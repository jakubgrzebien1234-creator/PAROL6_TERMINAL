import flet
import numpy as np
import threading
import time
import warnings
import xml.etree.ElementTree as ET
from ikpy.chain import Chain
from scipy.spatial.transform import Rotation as R
from scipy.spatial.transform import Slerp

# === TOOL DICTIONARY ===
ROBOT_TOOLS = {
    "CHWYTAK_MALY": {
        "translation": [0.100, 0.0, -0.090],
        "orientation": [0.0, -180.0, 0.0]
    },
    
    "CHWYTAK_DUZY": {
        "translation": [0.0, 0.0, -0.18831],
        "orientation": [0.0, -90.0, 0.0]
    }
}

# ==============================================================================
# ==============================================================================
# 1. KINEMATICS ENGINE
# ==============================================================================
class KinematicsEngine:
    def __init__(self, urdf_path, active_links_mask=None):
        self.chain = None
        self.urdf_path = urdf_path
        self.n_active_joints = 6
        self.visual_origins = {}
        self.joint_limits_rad = [(-np.pi, np.pi)] * 6
        
        self.tool_translation = np.zeros(3) 
        self.tool_rotation_matrix = np.eye(3) 
        self.current_tool = "NONE"
        
        self.world_offset = np.array([0.0, 0.0, 0.0]) 

        try:
            # Loading URDF
            
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                self.chain = Chain.from_urdf_file(urdf_path)
            
            
            mask = []
            for link in self.chain.links:
                if link.joint_type == 'fixed':
                    mask.append(False)
                else:
                    mask.append(True)
            
            self.chain.active_links_mask = mask
            self.active_links_mask = mask
            
            # === INCREASED PRECISION ===
            self.chain.max_iterations = 50
            self.chain.convergence_limit = 1e-4
            
            self.joint_limits_rad = self._load_active_joint_limits()
            self.visual_origins = self._load_visual_origins(urdf_path)
            
            self.set_tool("CHWYTAK_MALY")

        except Exception as e:
            self._setup_mock_chain()

    def set_tool(self, tool_name):
        if tool_name not in ROBOT_TOOLS:
            return

        tool_data = ROBOT_TOOLS[tool_name]
        self.tool_translation = np.array(tool_data["translation"])
        rpy = tool_data.get("orientation", [0,0,0])
        self.tool_rotation_matrix = R.from_euler('xyz', rpy, degrees=True).as_matrix()
        
        self.current_tool = tool_name

    # ================= KINEMATICS =================

    def forward_kinematics(self, active_angles):
        full_joints = self._active_to_full(active_angles)
        flange_matrix = self.chain.forward_kinematics(full_joints)
        
        R_flange = flange_matrix[:3, :3]
        P_flange = flange_matrix[:3, 3]
        
        offset_global = R_flange @ self.tool_translation
        P_tcp = P_flange + offset_global + self.world_offset
        
        tcp_matrix = np.eye(4)
        tcp_matrix[:3, 3] = P_tcp
        tcp_matrix[:3, :3] = R_flange @ self.tool_rotation_matrix
        
        return tcp_matrix

    def inverse_kinematics(self, target_position, target_orientation, initial_guess=None):
        if initial_guess is None: initial_guess = np.zeros(6)
        
        target_raw = target_position - self.world_offset
        
        target_rot_matrix = target_orientation 
        flange_rot_matrix = target_rot_matrix @ np.linalg.inv(self.tool_rotation_matrix)
        
        offset_global = flange_rot_matrix @ self.tool_translation
        target_pos_flange = target_raw - offset_global
        
        full_guess = self._active_to_full(initial_guess)
        
        full_sol = self.chain.inverse_kinematics(
            target_position=target_pos_flange,
            target_orientation=flange_rot_matrix, 
            orientation_mode='all', 
            initial_position=full_guess
        )
        
        return self._full_to_active(full_sol)

    # ================= HELPERS =================

    def _active_to_full(self, active_joints):
        arr = np.array(active_joints, dtype=float).flatten()
        if len(arr) == 7: arr = arr[1:] 
        if len(arr) != 6: arr = np.resize(arr, 6)
        
        full = np.zeros(len(self.chain.links))
        curr = 0
        for i, act in enumerate(self.active_links_mask):
            if act and curr < 6:
                full[i] = arr[curr]
                curr += 1
        return full

    def _full_to_active(self, full_vector):
        if self.active_links_mask: return np.compress(self.active_links_mask, full_vector)
        return np.zeros(6)
    
    def _load_active_joint_limits(self):
        deg = [
            (-90, 90),
            (-50, 140),
            (-100, 70),
            (-100, 180),
            (-120, 110),
            (-110, 180)
        ]
        return [(np.deg2rad(mn), np.deg2rad(mx)) for mn, mx in deg]

    def _load_visual_origins(self, urdf_path):
        origins = {}
        try:
            tree = ET.parse(urdf_path); root = tree.getroot()
            for link in root.findall('link'):
                vis = link.find('visual')
                if vis:
                    o = vis.find('origin')
                    if o is not None:
                        xyz = [float(x) for x in o.attrib.get('xyz','0 0 0').split()]
                        rpy = [float(r) for r in o.attrib.get('rpy','0 0 0').split()]
                        origins[link.attrib.get('name')] = (xyz, rpy)
        except: pass
        return origins

    def _setup_mock_chain(self):
        self.chain = type('Mock', (object,), {
            'links': [], 
            'active_links_mask': [], 
            'forward_kinematics': lambda *a, **k: np.eye(4), 
            'inverse_kinematics': lambda *a, **k: np.zeros(8)
        })()


# ==============================================================================
# ==============================================================================
# 2. CARTESIAN VIEW
# ==============================================================================
class CartesianView(flet.Container):
    def __init__(self, uart_communicator, urdf_path, active_links_mask=None, on_error=None):
        super().__init__()
        self.uart = uart_communicator
        self.ik = KinematicsEngine(urdf_path, active_links_mask)
        self.on_error = on_error
        
        self.is_jogging = False
        self.is_jogging = False
        self.active_jog_control = None
        self.is_robot_homed = False
        self.alive = True 
        
        self.commanded_joints = [0.0] * 6
        
        self.feedback_joints_deg = [0.0] * 6
        
        self.gripper_states = {"pneumatic": False, "electric": False}
        self.jog_speed_percent = 50.0
        
        self.last_jog_time = 0.0

        self.padding = 10 

        self._setup_ui()

        self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self.update_thread.start()
        


    def did_unmount(self):
        self.alive = False
        self.is_jogging = False



    def _setup_ui(self):
        # ----------------------------------------------------------------------
        # STYLES (MATCHING JOG.PY)
        # ----------------------------------------------------------------------
        panel_style = {
            "bgcolor": "#2D2D2D", 
            "border_radius": 10, 
            "border": flet.border.all(1, "#555555"), 
            "padding": 10
        }
        
        # ----------------------------------------------------------------------
        # 1. LEFT COLUMN: AXIS CONTROLS
        # ----------------------------------------------------------------------
        axes_list = [
            ("X", "x"), ("A", "rx"),
            ("Y", "y"), ("B", "rz"),
            ("Z", "z"), ("C", "ry")
        ]

        controls_column = flet.Column(spacing=5, expand=True)
        for i in range(0, len(axes_list), 2):
            if i+1 < len(axes_list):
                name1, code1 = axes_list[i]
                name2, code2 = axes_list[i+1]
                controls_column.controls.append(
                    flet.Row([
                        self._create_axis_control(name1, code1), 
                        self._create_axis_control(name2, code2)
                    ], spacing=5, expand=True)
                )

        # Grippers Row
        gripper_row = flet.Row(spacing=5, expand=True)
        gripper_row.controls.append(self._create_gripper_control("Electric Gripper"))
        gripper_row.controls.append(self._create_gripper_control("Pneumatic Gripper"))
        controls_column.controls.append(gripper_row)

        controls_container = flet.Container(content=controls_column, expand=20)

        # ----------------------------------------------------------------------
        # ----------------------------------------------------------------------
        # 2. CENTER COLUMN: TOOLS & VELOCITY
        # ----------------------------------------------------------------------
        # Velocity Panel
        self.lbl_speed = flet.Text(f"{int(self.jog_speed_percent)}%", size=18, weight="bold", color="cyan", max_lines=1)
        speed_panel = flet.Container(
            content=flet.Column([
                flet.Text("VELOCITY", size=10, color="grey", weight="bold"),
                flet.Row([
                    flet.IconButton(flet.icons.REMOVE, icon_color="white", bgcolor="#444", on_click=lambda e: self.change_speed(-10), icon_size=18),
                    flet.Container(content=self.lbl_speed, alignment=flet.alignment.center, width=60, bgcolor="#222", border_radius=5, padding=2),
                    flet.IconButton(flet.icons.ADD, icon_color="white", bgcolor="#444", on_click=lambda e: self.change_speed(10), icon_size=18)
                ], alignment="center", spacing=0, vertical_alignment=flet.CrossAxisAlignment.CENTER, tight=True)
            ], horizontal_alignment=flet.CrossAxisAlignment.CENTER, spacing=0, tight=True),
            alignment=flet.alignment.center,
            bgcolor="#2D2D2D", border_radius=10, border=flet.border.all(1, "#555555"), padding=3, height=65
        )

        TOOL_BTN_H = 40
        tools_column = flet.Column([
            speed_panel, 
            flet.Container(height=5),
            flet.ElevatedButton("HOME", icon=flet.icons.HOME, style=flet.ButtonStyle(bgcolor=flet.colors.BLUE_GREY_700, color="white", shape=flet.RoundedRectangleBorder(radius=8)), on_click=self.on_home_click, expand=True, width=10000),
            flet.ElevatedButton("SAFETY", icon=flet.icons.SHIELD, style=flet.ButtonStyle(bgcolor=flet.colors.TEAL_700, color="white", shape=flet.RoundedRectangleBorder(radius=8)), on_click=self.on_safety_click, expand=True, width=10000),
            flet.ElevatedButton("GRIPPER CHANGE", icon=flet.icons.HANDYMAN, style=flet.ButtonStyle(bgcolor=flet.colors.PURPLE_700, color="white", shape=flet.RoundedRectangleBorder(radius=8)), on_click=self.on_change_tool_click, expand=True, width=10000),
            flet.ElevatedButton("STOP", icon=flet.icons.STOP_CIRCLE, style=flet.ButtonStyle(bgcolor=flet.colors.RED_700, color="white", shape=flet.RoundedRectangleBorder(radius=8)), on_click=self.on_stop_click, expand=True, width=10000),
            flet.ElevatedButton("STANDBY", icon=flet.icons.ACCESSIBILITY, style=flet.ButtonStyle(bgcolor=flet.colors.ORANGE_900, color="white", shape=flet.RoundedRectangleBorder(radius=8)), on_click=self.on_standby_click, expand=True, width=10000),

        ], spacing=5, expand=True)

        tools_container = flet.Container(content=tools_column, expand=5, padding=flet.padding.symmetric(horizontal=5))

        # ----------------------------------------------------------------------
        # 3. RIGHT COLUMN: POSITIONS (READOUT)
        # ----------------------------------------------------------------------
        pos_list = flet.Column(spacing=4, horizontal_alignment="stretch")
        pos_list.controls.append(flet.Text("POSITION", size=14, weight="bold", color="white", text_align="center"))
        
        
        self.lbl_cart = {}
        
        self.lbl_joints = []
        for i in range(self.ik.n_active_joints):
            lbl = flet.Text("0.00°", size=13, color="cyan", weight="bold", max_lines=1)
            self.lbl_joints.append(lbl)
            pos_list.controls.append(
                flet.Row([flet.Text(f"J{i+1}:", size=12, weight="bold"), lbl], alignment="spaceBetween")
            )
            
        pos_list.controls.append(flet.Divider(height=6, color="#555"))
        
        for ax in ["X", "Y", "Z", "A", "B", "C"]:
            col = "cyan" if ax in ["X", "Y", "Z"] else "orange"
            unit = "mm" if ax in ["X", "Y", "Z"] else "°"
            
            lbl = flet.Text(f"0.00 {unit}", size=13, color=col, weight="bold", max_lines=1)
            self.lbl_cart[ax] = lbl
            pos_list.controls.append(
                flet.Row([flet.Text(f"{ax}:", size=12, weight="bold"), lbl], alignment="spaceBetween")
            )

        position_frame = flet.Container(content=pos_list, **panel_style, expand=4)

        # ----------------------------------------------------------------------
        # MAIN LAYOUT
        # ----------------------------------------------------------------------
        self.content = flet.Row(
            [controls_container, tools_container, position_frame], 
            spacing=10, 
            vertical_alignment=flet.CrossAxisAlignment.STRETCH
        )

    # --- LOGIC METHODS ---

    def change_speed(self, delta):
        self.jog_speed_percent = max(10, min(100, self.jog_speed_percent + delta))
        self.lbl_speed.value = f"{int(self.jog_speed_percent)}%"
        self.lbl_speed.update()
    
    
    def did_mount(self):
        try:
            self._update_labels_logic()
            self.update() 
        except: pass
        
    def _update_loop(self):
        while self.alive:
            if not self.is_jogging:
                has_zeros = all(abs(v) < 0.001 for v in self.commanded_joints)
                has_feedback = any(abs(v) > 0.01 for v in self.feedback_joints_deg)
                
                if has_zeros and has_feedback:
                    try:
                        self.commanded_joints = [np.radians(v) for v in self.feedback_joints_deg]
                    except: pass

            self._update_labels_logic()
            
            
            if self.page:
                try: self.page.update()
                except: pass
            
            time.sleep(0.05)

        
    def set_homed_status(self, is_homed):
        if isinstance(is_homed, str):
            if is_homed.lower() == "true": is_homed = True
            else: is_homed = False
        
        self.is_robot_homed = bool(is_homed)
        
        msg = "Robot homed!" if self.is_robot_homed else "Homing lost! Homing required."
        color = flet.colors.GREEN if self.is_robot_homed else flet.colors.RED
        
        if self.page:
            self.page.snack_bar = flet.SnackBar(flet.Text(msg), bgcolor=color)
            self.page.snack_bar.open = True
            self.page.update()

    def show_homing_required_dialog(self):
        if not self.page: return
        if self.on_error: self.on_error("E1")
        
        def close_dlg(e):
            dlg.open = False
            self.page.update()

        dlg = flet.AlertDialog(
            modal=True,
            title=flet.Row([
                flet.Icon(flet.icons.WARNING_AMBER, color=flet.colors.AMBER_400, size=30),
                flet.Text("HOMING REQUIRED", color=flet.colors.RED_200, weight="bold")
            ], alignment=flet.MainAxisAlignment.START, spacing=10),
            content=flet.Container(
                content=flet.Text("The robot must be homed before performing any movement.\nPlease run the Homing sequence first.", size=16),
                padding=10
            ),
            actions=[
                flet.ElevatedButton("OK", on_click=close_dlg, style=flet.ButtonStyle(bgcolor=flet.colors.RED_700, color="white"))
            ],
            actions_alignment=flet.MainAxisAlignment.END,
            bgcolor="#1f1f1f",
        )
        self.page.dialog = dlg
        dlg.open = True
        self.page.update()

    def on_jog_start(self, e, axis, direction):
        if self.is_jogging: return
        self.is_jogging = True
        self.active_jog_control = e.control
        
        e.control.content.bgcolor = "#111111"
        e.control.content.border = flet.border.all(1, "cyan")
        e.control.content.update()
        
        threading.Thread(target=self._jog_thread, args=(axis, direction), daemon=True).start()

    def on_jog_stop(self, e):
        if e.control != self.active_jog_control: return
        self.is_jogging = False
        self.active_jog_control = None
        self.is_jogging = False
        self.active_jog_control = None
        self.last_jog_time = time.time()
        if hasattr(e, "control") and e.control:
            e.control.content.bgcolor = "#444444"
            e.control.content.border = flet.border.all(1, "#666")
            e.control.content.update()

    def update_from_feedback(self, joint_values: dict):
        try:
            for i in range(6):
                key = f"J{i+1}"
                if key in joint_values:
                    self.feedback_joints_deg[i] = joint_values[key]
            
            if self.is_jogging:
                return
            if (time.time() - self.last_jog_time) < 1.5:
                return
                
            feedback_rad = [np.radians(v) for v in self.feedback_joints_deg]
            for i in range(6):
                if abs(self.commanded_joints[i] - feedback_rad[i]) > np.radians(0.5):
                    self.commanded_joints[i] = feedback_rad[i]
                
        except Exception as e:
            pass

    def on_home_click(self, e):
        self._show_homing_choice_dialog()

    def _show_homing_choice_dialog(self):
        if not self.page: return
        
        def close_dlg(e):
            dlg.open = False
            self.page.update()

        def on_start_homing(e):
            close_dlg(e)
            if self.uart: 
                self.uart.send_message("HOME")
            # Reset local joints to 0
            self.commanded_joints = [0.0] * 6

        def on_confirm_position(e):
            close_dlg(e)
            if hasattr(self, 'on_global_set_homed') and self.on_global_set_homed:
                self.on_global_set_homed(True)
            else:
                self.set_homed_status(True)
            if self.on_error:
                self.on_error("HMS")
            self.page.snack_bar = flet.SnackBar(flet.Text("Position confirmed manually."), bgcolor="green")
            self.page.snack_bar.open = True
            self.page.update()

        dlg = flet.AlertDialog(
            title=flet.Text("Homing Selection"),
            content=flet.Container(
                width=350,
                content=flet.Text("Do you want to start automatic homing sequence or confirm that the robot is currently in the home position?")
            ),
            actions=[
                flet.TextButton("Start Homing", on_click=on_start_homing),
                flet.TextButton("Confirm Position", on_click=on_confirm_position),
            ],
            actions_alignment=flet.MainAxisAlignment.END,
        )
        self.page.dialog = dlg
        dlg.open = True
        self.page.update()

    def on_safety_click(self, e):
        if self.on_error:
            self.on_error("W2")
        target_rad = np.radians([0, -50, 70, 90, 0, 0]).tolist()
        self._animate_move(target_rad)

    def on_standby_click(self, e):
        target_rad = [0.0] * 6
        self._animate_move(target_rad)

    def _animate_move(self, target_joints_rad):
        if self.is_jogging: return

        try:
            fb_rad = [np.radians(v) for v in self.feedback_joints_deg]
            if np.linalg.norm(np.array(self.commanded_joints) - np.array(fb_rad)) > 0.1:
                self.commanded_joints = list(fb_rad)
        except: pass

        self.is_jogging = True
        
        def run():
            current_local = np.array(list(self.commanded_joints))
            target = np.array(target_joints_rad)
            
            try:
                while self.is_jogging and self.alive:
                    diff = target - current_local
                    dist = np.linalg.norm(diff)
                    
                    if dist < 0.005:
                        self.commanded_joints = target.tolist()
                        self.send_current_pose()
                        break
                    
                    factor = self.jog_speed_percent / 100.0
                    step_size = min(dist, 0.075 * factor)
                    
                    current_local = current_local + (diff / dist) * step_size
                    self.commanded_joints = current_local.tolist()
                    self.send_current_pose()
                    time.sleep(0.1)
            finally:
                self.is_jogging = False
                self.last_jog_time = time.time()
            
        threading.Thread(target=run, daemon=True).start()

    def on_stop_click(self, e):
        if self.on_error:
            self.on_error("W1")
        self.is_jogging = False
        if self.uart: self.uart.send_message("EGRIP_STOP")

    def on_change_tool_click(self, e):
        if not self.page: return
        
        self.tool_change_dialog = None
        
        def close_dlg(e=None):
            if self.tool_change_dialog:
                self.tool_change_dialog.open = False
                self.page.update()
        
        def select_vacuum(e):
            if hasattr(self, 'on_global_set_tool') and self.on_global_set_tool:
                self.on_global_set_tool("CHWYTAK_MALY")
            else:
                self.ik.set_tool("CHWYTAK_MALY")
            if self.uart: self.uart.send_message("TOOL_VAC")
            close_dlg()
            self._update_labels_logic()
            self.page.snack_bar = flet.SnackBar(flet.Text("Active Tool: Vacuum Gripper"), bgcolor=flet.colors.GREEN)
            self.page.snack_bar.open = True
            self.page.update()
        
        def select_electric(e):
            if hasattr(self, 'on_global_set_tool') and self.on_global_set_tool:
                self.on_global_set_tool("CHWYTAK_DUZY")
            else:
                self.ik.set_tool("CHWYTAK_DUZY")
            if self.uart: self.uart.send_message("TOOL_EGRIP")
            close_dlg()
            self._update_labels_logic()
            self.page.snack_bar = flet.SnackBar(flet.Text("Active Tool: Electric Gripper"), bgcolor=flet.colors.GREEN)
            self.page.snack_bar.open = True
            self.page.update()
        
        # Create clickable tool panels
        panel_style = {
            "bgcolor": "#3D3D3D",
            "border_radius": 10,
            "border": flet.border.all(2, "#555555"),
            "padding": 10,
            "width": 220,
            "height": 210,
            "alignment": flet.alignment.center,
        }
        
        def make_hover_effect(container, on_click_func):
            def on_hover(e):
                if e.data == "true":
                    container.border = flet.border.all(3, flet.colors.CYAN_400)
                    container.bgcolor = "#4D4D4D"
                else:
                    container.border = flet.border.all(2, "#555555")
                    container.bgcolor = "#3D3D3D"
                container.update()
            container.on_hover = on_hover
            container.on_click = on_click_func
        
        vacuum_panel = flet.Container(
            content=flet.Column([
                flet.Image(src="Gripper1.png", height=160, fit=flet.ImageFit.CONTAIN),
                flet.Text("Vacuum Gripper", size=15, weight="bold", color="white", text_align=flet.TextAlign.CENTER)
            ], horizontal_alignment=flet.CrossAxisAlignment.CENTER, spacing=8),
            **panel_style
        )
        make_hover_effect(vacuum_panel, select_vacuum)
        
        electric_panel = flet.Container(
            content=flet.Column([
                flet.Image(src="Gripper2.png", height=160, fit=flet.ImageFit.CONTAIN),
                flet.Text("Electric Gripper", size=15, weight="bold", color="white", text_align=flet.TextAlign.CENTER)
            ], horizontal_alignment=flet.CrossAxisAlignment.CENTER, spacing=8),
            **panel_style
        )
        make_hover_effect(electric_panel, select_electric)
        
        tools_row = flet.Row([
            vacuum_panel,
            electric_panel
        ], spacing=30, alignment=flet.MainAxisAlignment.CENTER)
        
        def on_change_click(e):
            if self.uart: self.uart.send_message("TOOL_CHANGE")
            self.page.snack_bar = flet.SnackBar(flet.Text("Tool change command sent"), bgcolor=flet.colors.BLUE)
            self.page.snack_bar.open = True
            self.page.update()
        
        change_button = flet.ElevatedButton(
            "CHANGE",
            icon=flet.icons.SWAP_HORIZ,
            style=flet.ButtonStyle(
                bgcolor=flet.colors.ORANGE_700,
                color="white",
                shape=flet.RoundedRectangleBorder(radius=10)
            ),
            height=60,
            width=300,
            on_click=on_change_click
        )
        
        dialog_content = flet.Column([
            tools_row,
            flet.Container(height=40),
            flet.Container(content=change_button, alignment=flet.alignment.center)
        ], horizontal_alignment=flet.CrossAxisAlignment.CENTER, spacing=0)
        
        title_row = flet.Row([
            flet.Text("CHANGE ACTIVE TOOL", size=22, weight="bold", color="white"),
            flet.IconButton(icon=flet.icons.CLOSE, icon_size=28, on_click=close_dlg)
        ], alignment=flet.MainAxisAlignment.SPACE_BETWEEN)
        
        self.tool_change_dialog = flet.AlertDialog(
            title=title_row,
            title_padding=flet.padding.only(left=20, right=10, top=10, bottom=0),
            content=flet.Container(content=dialog_content, padding=10, width=520, height=310),
            modal=True,
            bgcolor="#2D2D2D"
        )
        
        self.page.dialog = self.tool_change_dialog
        self.tool_change_dialog.open = True
        self.page.update()

    def _ui_updater_loop(self):
        while self.alive:
            try:
                if self.page:
                    self._update_labels_logic()
                    self.page.update()
            except: pass 
            time.sleep(0.10) 

    def _update_labels_logic(self):
        if not self.ik.chain: 
            return
        
        try:
            tcp_matrix = self.ik.forward_kinematics(self.commanded_joints)
            pos = tcp_matrix[:3, 3]
            rot = tcp_matrix[:3, :3]
            
            euler = R.from_matrix(rot).as_euler('xyz', degrees=True)
            
            self.lbl_cart["X"].value = f"{pos[0]*1000:.2f} mm"
            self.lbl_cart["Y"].value = f"{pos[1]*1000:.2f} mm"
            self.lbl_cart["Z"].value = f"{pos[2]*1000:.2f} mm"
            
            self.lbl_cart["A"].value = f"{euler[0]:.2f}°"
            self.lbl_cart["B"].value = f"{euler[1]:.2f}°"
            self.lbl_cart["C"].value = f"{euler[2]:.2f}°"

            for i, rad_val in enumerate(self.commanded_joints):
                if i < len(self.lbl_joints):
                    deg_val = np.degrees(rad_val)
                    self.lbl_joints[i].value = f"{deg_val:.2f}°"
                    
        except Exception as e:
            pass

    # --- MOTION LOGIC (AGGRESSIVE STABILITY) ---
    def _jog_thread(self, axis, direction):
        BASE_STEP_MM = 5.0
        BASE_STEP_RAD = 0.02
        
        WORKSPACE_LIMITS = {
            'x': (-0.500, 0.600),
            'y': (-0.550, 0.550),
            'z': (0.000, 0.600)
        }

        sign = 1 if direction == "plus" else -1
        
        while self.is_jogging:
            loop_start = time.time()
            
            factor = self.jog_speed_percent / 100.0
            step_mm = max(0.2, BASE_STEP_MM * factor)
            step_rad = max(0.002, BASE_STEP_RAD * factor)
            
            if self.ik.chain:
                current_raw = list(self.commanded_joints)
                
                current_tcp_matrix = self.ik.forward_kinematics(current_raw)
                current_pos = current_tcp_matrix[:3, 3]
                current_rot = current_tcp_matrix[:3, :3]
                
                dx, dy, dz = 0, 0, 0
                drx, dry, drz = 0, 0, 0
                
                if axis == 'x': dx = step_mm * sign
                elif axis == 'y': dy = step_mm * sign
                elif axis == 'z': dz = step_mm * sign
                elif axis == 'rx': drx = step_rad * sign
                elif axis == 'ry': dry = step_rad * sign
                elif axis == 'rz': drz = step_rad * sign
                
                proposed_pos = current_pos + np.array([dx, dy, dz]) / 1000.0
                target_pos = np.copy(proposed_pos)

                for i, ax_key in enumerate(['x', 'y', 'z']):
                    mn, mx = WORKSPACE_LIMITS[ax_key]
                    curr = current_pos[i]
                    prop = proposed_pos[i]
                    
                    if curr < mn:
                        if prop > curr: target_pos[i] = min(prop, mn) 
                        else: target_pos[i] = curr
                    elif curr > mx:
                        if prop < curr: target_pos[i] = max(prop, mx) 
                        else: target_pos[i] = curr
                    else:
                        target_pos[i] = np.clip(prop, mn, mx)
                
                if axis == 'rx':  
                    delta_rot = R.from_euler('x', drx).as_matrix()
                    target_rot = current_rot @ delta_rot
                
                elif axis == 'ry':  
                    delta_rot = R.from_euler('y', dry).as_matrix()
                    target_rot = current_rot @ delta_rot
                    
                elif axis == 'rz':  
                    delta_rot = R.from_euler('z', drz).as_matrix()
                    target_rot = current_rot @ delta_rot
                     
                else:
                    target_rot = current_rot
                
                try:
                    nj_model = self.ik.inverse_kinematics(target_pos, target_rot, current_raw)
                    
                    # --- STRICT VALIDATION ---
                    test_tcp = self.ik.forward_kinematics(nj_model)
                    test_pos = test_tcp[:3, 3]
                    
                    deviation = np.linalg.norm(test_pos - target_pos)
                    
                    if deviation > 0.001: 
                        if self.on_error:
                            if not hasattr(self, 'last_reach_warn') or (time.time() - self.last_reach_warn > 2.0):
                                self.on_error("OOR") 
                                self.last_reach_warn = time.time()
                        continue
                        
                    nj_model = [(q + np.pi) % (2*np.pi) - np.pi for q in nj_model]
                    
                    diffs = [abs(nj_model[i] - current_raw[i]) for i in range(6)]
                    max_diff = max(diffs)
                    
                    if max_diff < 0.15:  
                        self.commanded_joints = nj_model
                        
                except:
                    pass  

            self.send_current_pose()
            
            elapsed = time.time() - loop_start
            sleep_time = max(0.01, 0.10 - elapsed)
            time.sleep(sleep_time)

    def send_current_pose(self):
        if self.uart and self.uart.is_open():
            vals_deg = [np.degrees(r) for r in self.commanded_joints]
            data_str = ",".join([f"{v:.2f}" for v in vals_deg])
            self.uart.send_message(f"J_{data_str}")

    def on_gripper_toggle_click(self, e):
        g_type = e.control.data 
        new_state = not self.gripper_states.get(g_type, False)
        self.gripper_states[g_type] = new_state
        
        cmd = "VGripON" if new_state else "VGripOFF"
        if g_type == "electric": 
            cmd = "EGRIP_CLOSE" if new_state else "EGRIP_OPEN"
            
        e.control.style.bgcolor = flet.colors.GREEN_600 if new_state else flet.colors.RED_600
        e.control.content.value = "ON" if new_state else "OFF"
        if g_type == "electric": 
            e.control.content.value = "CLOSED" if new_state else "OPEN"
            
        e.control.update()
        if self.uart: 
            self.uart.send_message(cmd)

    def _create_gripper_control(self, display_name: str) -> flet.Container:
        container_style = {
            "bgcolor": "#2D2D2D", 
            "border_radius": 8, 
            "border": flet.border.all(1, "#555555"), 
            "padding": 5, 
            "expand": True
        }
        g_type = "electric" if "electric" in display_name.lower() else "pneumatic"
        state = self.gripper_states[g_type]
        
        txt = "CLOSED" if state and g_type=="electric" else ("OPEN" if g_type=="electric" else ("ON" if state else "OFF"))
        color = flet.colors.GREEN_600 if state else flet.colors.RED_600
        
        btn = flet.ElevatedButton(
            content=flet.Text(txt, size=14), 
            style=flet.ButtonStyle(bgcolor=color), 
            on_click=self.on_gripper_toggle_click, 
            data=g_type, 
            height=50, 
            expand=True
        )
        return flet.Container(
            content=flet.Column([
                flet.Text(display_name, size=13, color="white", text_align="center"), 
                flet.Row([btn], expand=True)
            ], spacing=2), 
            **container_style
        )

    def _create_axis_control(self, display_name: str, code: str) -> flet.Container:
        container_style = {
            "bgcolor": "#2D2D2D", 
            "border_radius": 8, 
            "border": flet.border.all(1, "#555555"), 
            "padding": 5, 
            "expand": True
        }

        def mk_btn(txt, direction):
            c = flet.Container(
                content=flet.Text(txt, size=44, weight="bold", color="white"), 
                bgcolor="#444444", 
                border_radius=8, 
                alignment=flet.alignment.center, 
                height=110, 
                shadow=flet.BoxShadow(blur_radius=2, color="black"), 
                border=flet.border.all(1, "#666")
            )
            gest = flet.GestureDetector(
                content=c, 
                drag_interval=30,
                on_tap_down=lambda e: self.on_jog_start(e, code, direction), 
                on_tap_up=lambda e: self.on_jog_stop(e), 
                on_long_press_end=lambda e: self.on_jog_stop(e)
            )
            return flet.Container(content=gest, expand=True)

        return flet.Container(
            content=flet.Column([
                flet.Row([
                    mk_btn("-", "minus"), 
                    flet.Text(display_name, size=20, weight="bold", color="white", text_align="center"), 
                    mk_btn("+", "plus")
                ], spacing=10, expand=True, vertical_alignment=flet.CrossAxisAlignment.CENTER, tight=True)
            ], spacing=2), 
            **container_style
        )
