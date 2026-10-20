from pynput import keyboard
from pynput.keyboard import Key, KeyCode, Controller as KeyboardController
from pynput.mouse import Button, Controller as MouseController
import threading
import time
import json
import os
import platform

# ======================= 配置文件说明 =======================
# 配置文件格式：
# {
#     "hotkeys": {
#         "stop_clear": ["space", "backspace"],  # 停止/清除热键
#         "start_stop": ["ctrl", "f8"]          # 启停组合键
#     },
#     "mouse_map": {                            # 鼠标按键映射
#         "left": "left",                      # 左键对应键盘按键
#         "middle": "down",                    # 中键对应键盘按键
#         "right": "right"                     # 右键对应键盘按键
#     },
#     "click_sequence": ["a", "b", "right"],   # 连点按键序列
#     "interval": 0.1                          # 连点间隔时间（秒）
# }
# ===========================================================

class ConfigManager:
    """配置文件管理类"""
    CONFIG_FILE = r"C:\Fusure works\Fusure clicks\autoclicker_config.json"
    DEFAULT_CONFIG = {
        "hotkeys": {
            "stop_clear": ["space", "backspace"],
            "start_stop": ["ctrl", "f8"]
        },
        "mouse_map": {
            "left": "left",
            "middle": "down",
            "right": "right"
        },
        "click_sequence": [],
        "interval": 0.1
    }

    def __init__(self):
        self.config = self.load_or_create_config()

    def key_to_str(self, key):
        """将 Key 对象转换为字符串"""
        if isinstance(key, Key):
            key_name = key.name
            if key_name.endswith('_l') or key_name.endswith('_r'):
                return key_name[:-2]  # 去除 _l 或 _r
            return key_name
        if isinstance(key, KeyCode):
            return key.char if key.char else f"KeyCode({key.vk})"
        return str(key)

    def str_to_key(self, key_str):
        """将字符串转换为 Key 对象"""
        try:
            # 尝试直接获取键
            return Key[key_str]
        except KeyError:
            # 尝试添加 _l 或 _r 后获取键
            for suffix in ('_l', '_r'):
                try:
                    return Key[key_str + suffix]
                except KeyError:
                    pass
            if len(key_str) == 1:
                return KeyCode.from_char(key_str)
            return KeyCode.from_vk(int(key_str.split('(')[1].strip(')')))

    def load_or_create_config(self):
        """加载或创建配置文件（自动建立父文件夹）"""
        config_dir = os.path.dirname(self.CONFIG_FILE)
        # 自动创建完整目录，文件夹存在不会报错
        os.makedirs(config_dir, exist_ok=True)

        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'r', encoding="utf-8") as f:
                    config = json.load(f)
                    # 验证配置完整性
                    if all(k in config for k in self.DEFAULT_CONFIG):
                        return config
            except Exception as e:
                print(f"配置文件损坏，将使用默认配置: {str(e)}")

        # 创建默认配置
        with open(self.CONFIG_FILE, 'w', encoding="utf-8") as f:
            json.dump(self.DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
        return self.DEFAULT_CONFIG.copy()

    def save_config(self):
        """保存当前配置到文件"""
        config_dir = os.path.dirname(self.CONFIG_FILE)
        os.makedirs(config_dir, exist_ok=True)
        with open(self.CONFIG_FILE, 'w', encoding="utf-8") as f:
            json.dump(self.config, f, indent=4, ensure_ascii=False)

    def delete_config(self):
        if os.path.exists(self.CONFIG_FILE):
            os.remove(self.CONFIG_FILE)


class AutoClicker:
    """连点器主类"""

    def __init__(self):
        self.config_mgr = ConfigManager()
        self.is_running = False
        self.running = threading.Event()
        self.active_keys = set()
        self.active_combo_keys = set()  # 新增：跟踪模式2的组合键状态
        self.combo_locked = False
        self.current_mode = 1

        # 初始化配置
        self.stop_clear_keys = self._parse_keys(self.config_mgr.config["hotkeys"]["stop_clear"])
        self.start_stop_combo = set(self._parse_keys(self.config_mgr.config["hotkeys"]["start_stop"]))
        self.mouse_map = {k: self.config_mgr.str_to_key(v) for k, v in self.config_mgr.config["mouse_map"].items()}
        self.click_sequence = [self.config_mgr.str_to_key(k) for k in self.config_mgr.config["click_sequence"]]
        self.interval = self.config_mgr.config["interval"]

        self.mouse = MouseController()
        self.keyboard = KeyboardController()
        self.listener = None

    def _parse_keys(self, keys):
        """解析键列表"""
        return [self.config_mgr.str_to_key(key) for key in keys]

    def normalize_key(self, key):
        """标准化键"""
        return self.config_mgr.key_to_str(key)

    def show_config(self):
        """显示当前配置"""
        print(f"停止/清除热键: {'+'.join([self.config_mgr.key_to_str(k) for k in self.stop_clear_keys])}")
        print(f"启动/停止热键: {'+'.join([self.config_mgr.key_to_str(k) for k in self.start_stop_combo])}")
        print(f"鼠标映射: {self.config_mgr.config['mouse_map']}")
        print(f"连点序列: {[self.config_mgr.key_to_str(k) for k in self.click_sequence]}")
        print(f"连点间隔: {self.interval} 秒")

    def config_wizard(self):
        """配置向导"""
        if self.ask_yesno("是否要重新配置热键和鼠标映射？", default='n'):
            self.reconfigure_hotkeys_and_mouse_map()

        current_interval = self.interval
        if self.ask_yesno(f"是否要设置连点间隔？当前间隔为 {current_interval} 秒。", default='n'):
            self.set_interval()

        current_sequence = [self.config_mgr.key_to_str(k) for k in self.click_sequence]
        if self.ask_yesno(f"是否要设置连点序列？当前序列为 {current_sequence}。", default='n'):
            self.set_click_sequence()

    def ask_yesno(self, prompt, default=None):
        """获取是/否输入"""
        if default:
            prompt += f" (默认: {default}, 按回车使用默认值)"
        while True:
            response = input(f"{prompt} (y/n): ").lower()
            if not response and default:
                return default == 'y'
            if response in ('y', 'n'):
                return response == 'y'
            print("请输入 y 或 n")

    def reconfigure_hotkeys_and_mouse_map(self):
        while True:
            print("\n请选择要修改的配置项：")
            print("1. 启停组合键")
            print("2. 停止/清除键")
            print("3. 鼠标左键映射")
            print("4. 鼠标中键映射")
            print("5. 鼠标右键映射")
            print("6. 删除配置文件（恢复默认配置）")
            print("0. 退出修改配置")
            choice = input("请输入对应的数字: ")
            if choice == '0':
                break
            elif choice == '1':
                print("\n配置启停组合键（输入组合键后按空格结束）：")
                self.start_stop_combo = set(self.record_combo())
                self.config_mgr.config["hotkeys"]["start_stop"] = [self.config_mgr.key_to_str(k) for k in
                                                                   self.start_stop_combo]
                self.config_mgr.save_config()
            elif choice == '2':
                print("\n配置停止/清除热键（按顺序输入两个键）：")
                self.stop_clear_keys = self.record_key_sequence(2)
                self.config_mgr.config["hotkeys"]["stop_clear"] = [self.config_mgr.key_to_str(k) for k in
                                                                   self.stop_clear_keys]
                self.config_mgr.save_config()
            elif choice == '3':
                print("\n配置鼠标左键映射：")
                self.mouse_map["left"] = self.record_single_key()
                self.config_mgr.config["mouse_map"]["left"] = self.config_mgr.key_to_str(self.mouse_map["left"])
                self.config_mgr.save_config()
            elif choice == '4':
                print("\n配置鼠标中键映射：")
                self.mouse_map["middle"] = self.record_single_key()
                self.config_mgr.config["mouse_map"]["middle"] = self.config_mgr.key_to_str(self.mouse_map["middle"])
                self.config_mgr.save_config()
            elif choice == '5':
                print("\n配置鼠标右键映射：")
                self.mouse_map["right"] = self.record_single_key()
                self.config_mgr.config["mouse_map"]["right"] = self.config_mgr.key_to_str(self.mouse_map["right"])
                self.config_mgr.save_config()
            elif choice == '6':
                self.config_mgr.delete_config()
                print("配置文件已删除")
            else:
                print("无效的选择，请输入有效的数字。")

    def set_interval(self):
        """设置连点间隔"""
        while True:
            try:
                self.interval = float(input("请输入连点间隔（秒）："))
                self.config_mgr.config["interval"] = self.interval
                self.config_mgr.save_config()
                break
            except ValueError:
                print("请输入有效的数字！")

    def set_click_sequence(self):
        """设置连点序列"""
        print(f"结束输入: {self.config_mgr.key_to_str(self.stop_clear_keys[0])}")
        print(f"清除序列: {self.config_mgr.key_to_str(self.stop_clear_keys[1])}")
        print("\n输入连点序列：")
        self.click_sequence = self.record_key_sequence()
        self.config_mgr.config["click_sequence"] = [self.config_mgr.key_to_str(k) for k in self.click_sequence]
        self.config_mgr.save_config()

    def record_single_key(self):
        """录制单个按键"""
        result = []

        def on_press(key):
            result.append(key)
            return False

        with keyboard.Listener(on_press=on_press) as listener:
            listener.join()
        return result[0]

    def record_key_sequence(self, max_keys=None):
        """录制按键序列"""
        sequence = []
        stop_key = self.stop_clear_keys[0]
        clear_key = self.stop_clear_keys[1]

        def on_press(key):
            if key == stop_key:
                return False
            if key == clear_key:
                if sequence:
                    sequence.pop()
                    print(f"当前序列: {[self.config_mgr.key_to_str(k) for k in sequence]}")
            else:
                sequence.append(key)
                print(f"当前序列: {[self.config_mgr.key_to_str(k) for k in sequence]}")

            if max_keys and len(sequence) >= max_keys:
                return False

        print("开始录制...")
        with keyboard.Listener(on_press=on_press) as listener:
            listener.join()
        return sequence

    def record_combo(self):
        """录制组合键"""
        combo = []

        def on_press(key):
            if key == Key.space:
                return False
            combo.append(key)
            print(f"当前组合键: {[self.config_mgr.key_to_str(k) for k in combo]}")

        with keyboard.Listener(on_press=on_press) as listener:
            listener.join()
        return combo

    def mode_choose(self):
        """模式选择方法"""
        print("\n请选择连点模式：")
        print("1. 一键停启模式：使用组合键启动/停止")
        print("2. 长按停启模式：按住组合键中任意一个即可运行，松开停止")
        print("3. 文本粘贴模式：启动时粘贴剪贴板内容并执行连点序列")
        while True:
            mode = input("请输入模式编号（1/2/3）: ").strip()
            if mode in ('1', '2', '3'):
                self.current_mode = int(mode)
                break
            print("输入错误，请重新输入！")

    def start(self):
        """主程序入口"""
        print("=" * 20, " 自动连点器 ", "=" * 20)
        print("当前配置：")
        self.show_config()

        self.config_wizard()
        self.mode_choose()

        print("\n操作指南：")
        print(f"启动/停止: {'+'.join([self.config_mgr.key_to_str(k) for k in self.start_stop_combo])}")
        print("=" * 50)

        # 根据模式绑定处理函数
        handlers = {
            1: self.on_press_mode1,
            2: self.on_press_mode2,
            3: self.on_press_mode3
        }
        current_handler = handlers[self.current_mode]

        self.listener = keyboard.Listener(
            on_press=current_handler,
            on_release=self.on_release
        )
        self.listener.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.listener.stop()

    def on_press_mode1(self, key):
        """模式1按键处理（组合键切换）"""
        normalized_key = self.normalize_key(key)
        self.active_keys.add(normalized_key)

        # 使用集合判断组合键
        normalized_combo = {self.normalize_key(k) for k in self.start_stop_combo}
        if normalized_combo.issubset(self.active_keys) and not self.combo_locked:
            self.toggle_clicker()
            self.combo_locked = True

    def on_press_mode2(self, key):
        """模式2按键处理（按下启动）"""
        normalized_key = self.normalize_key(key)
        combo_keys = {self.normalize_key(k) for k in self.start_stop_combo}

        if normalized_key in combo_keys:
            self.active_combo_keys.add(normalized_key)
            if not self.is_running:
                self.toggle_clicker()

    def on_press_mode3(self, key):
        """模式3按键处理（组合键切换+粘贴）"""
        self.on_press_mode1(key)  # 复用模式1的逻辑

    def on_release(self, key):
        """通用释放处理"""
        try:
            normalized_key = self.normalize_key(key)

            # 更新活动键集合
            if normalized_key in self.active_keys:
                self.active_keys.remove(normalized_key)

            # 模式2专用逻辑
            if self.current_mode == 2:
                combo_keys = {self.normalize_key(k) for k in self.start_stop_combo}
                if normalized_key in combo_keys:
                    if normalized_key in self.active_combo_keys:
                        self.active_combo_keys.remove(normalized_key)
                    # 当所有组合键释放时停止
                    if not self.active_combo_keys and self.is_running:
                        self.toggle_clicker()

            # 其他模式的组合键解锁逻辑
            if self.current_mode != 2:
                normalized_combo = {self.normalize_key(k) for k in self.start_stop_combo}
                if not normalized_combo.intersection(self.active_keys):
                    self.combo_locked = False
        except KeyError:
            pass

    def toggle_clicker(self):
        """切换连点器状态"""
        self.is_running = not self.is_running
        if self.is_running:
            print('连点器已启动')
            self.running.set()
            threading.Thread(target=self.click_loop, args=(self.current_mode,)).start()
        else:
            print('连点器已关闭')
            self.running.clear()

    def press_key(self, key):
        """执行单个按键操作"""
        try:
            # 处理鼠标映射
            mouse_mapped = False
            for button, mapped_key in self.mouse_map.items():
                if key == mapped_key:
                    if button == "left":
                        self.mouse.click(Button.left)
                    elif button == "middle":
                        self.mouse.click(Button.middle)
                    elif button == "right":
                        self.mouse.click(Button.right)
                    mouse_mapped = True
                    break
            # 处理普通按键
            if not mouse_mapped:
                self.keyboard.press(key)
                self.keyboard.release(key)
        except Exception as e:
            print(f"执行按键时出错: {str(e)}")

    def click_loop(self, mode):
        """连点循环"""
        while self.running.is_set():
            try:
                # 模式3：粘贴剪贴板内容
                if mode == 3:
                    self.paste_from_clipboard()

                # 执行连点序列
                for key in self.click_sequence:
                    if not self.running.is_set():
                        break
                    self.press_key(key)
                    time.sleep(self.interval)
            except KeyboardInterrupt:
                self.running.clear()

    def paste_from_clipboard(self):
        """执行粘贴操作"""
        system = platform.system()
        modifier = Key.cmd if system == 'Darwin' else Key.ctrl
        with self.keyboard.pressed(modifier):
            self.keyboard.press('v')
            self.keyboard.release('v')
        time.sleep(0.1)  # 确保粘贴完成


if __name__ == "__main__":
    clicker = AutoClicker()
    clicker.start()
