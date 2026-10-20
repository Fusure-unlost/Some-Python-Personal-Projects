import sys
import os
import json
import cv2
import traceback
import numpy as np
from PySide6.QtCore import Qt, Signal, QObject, QFile
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QFileDialog,
                               QFormLayout, QProgressBar, QMessageBox,
                               QCheckBox, QSlider, QSizePolicy, QComboBox)
from PySide6.QtGui import QIcon

launcher_root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    from Fusure_tools import image_to_Silkscreen_icon
    image_to_Silkscreen_icon = os.path.abspath(image_to_Silkscreen_icon)
except Exception as e:
    image_to_Silkscreen_icon = os.path.abspath(os.path.dirname(__file__) + r'\..\..\logo\default_icon.ico')


class ProcessSignals(QObject):
    error_occurred = Signal(str)
    progress_updated = Signal(int)


class ImageProcessor(QWidget):
    CONFIG_PATH = r"C:\Fusure works\image 2 skillscreen\config.json"

    def __init__(self):
        super().__init__()
        self.progress_steps = [
            "加载图像", "灰度转换",
            "匀色处理", "背景去除",
            "降噪处理", "对比度增强",
            "图像处理", "完成"
        ]
        self.current_image = None
        self.processed_image = None

        self.signals = ProcessSignals()
        self.init_config()
        self.init_ui()
        self.setup_connections()

    def init_config(self):
        try:
            config_dir = os.path.dirname(self.CONFIG_PATH)
            if not QFile.exists(config_dir):
                os.makedirs(config_dir, exist_ok=True)

            default_config = {
                "input_dir": os.path.join(config_dir, "input"),
                "output_dir": os.path.join(config_dir, "output"),
                "alpha": 1.0,
                "beta": 0,
                "threshold": 128,
                "balance_threshold": 90,  # 根据截图更新
                "noise_threshold": 3,
                "bg_threshold": 98,  # 根据截图更新
                "invert": False,
                "edge_detect": False,
                "color_balance_enabled": True,
                "color_balance_method": "Histogram",  # 根据截图更新
                "noise_remove_enabled": True,
                "noise_remove_method": "Bilateral",  # 修正拼写错误
                "bg_remove_enabled": True,
                "bg_remove_method": "AdaptiveThreshold"  # 替换GrabCut
            }

            if not QFile.exists(self.CONFIG_PATH):
                with open(self.CONFIG_PATH, 'w', encoding='utf-8') as f:
                    json.dump(default_config, f, ensure_ascii=False, indent=2)
                os.makedirs(default_config["input_dir"], exist_ok=True)
                os.makedirs(default_config["output_dir"], exist_ok=True)
            else:
                with open(self.CONFIG_PATH, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    default_config.update(config)

            self.current_config = default_config

        except Exception as e:
            QMessageBox.critical(self, "配置错误", f"初始化配置失败:\n{str(e)}")

    def init_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # 文件路径区域
        path_layout = QHBoxLayout()
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(4)

        self.input_edit = QLineEdit()
        self.input_edit.setFixedHeight(24)
        self.input_edit.setPlaceholderText("输入图像路径 (支持PNG/JPG/BMP)")
        self.output_edit = QLineEdit()
        self.output_edit.setFixedHeight(24)
        self.output_edit.setPlaceholderText("输出保存路径 (自动创建目录)")

        self.browse_btn = QPushButton("选择输入")
        self.browse_btn.setFixedSize(80, 24)
        self.browse_btn.setToolTip("选择要处理的图像文件")
        self.save_btn = QPushButton("保存输出")
        self.save_btn.setFixedSize(80, 24)
        self.save_btn.setToolTip("保存处理后的图像")

        path_layout.addWidget(QLabel("输入:"), stretch=0)
        path_layout.addWidget(self.input_edit, stretch=3)
        path_layout.addWidget(self.browse_btn, stretch=0)
        path_layout.addWidget(QLabel("输出:"), stretch=0)
        path_layout.addWidget(self.output_edit, stretch=3)
        path_layout.addWidget(self.save_btn, stretch=0)

        # 参数控制区域
        param_layout = QFormLayout()
        param_layout.setContentsMargins(0, 0, 0, 0)
        param_layout.setSpacing(6)
        param_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        # 基础参数
        self.alpha_slider = self.create_slider(1, 50, int(self.current_config["alpha"] * 10))
        self.alpha_slider.setToolTip("调整图像对比度 (1.0-5.0)\n值越大对比越强烈")
        self.beta_slider = self.create_slider(0, 255, self.current_config["beta"])
        self.beta_slider.setToolTip("调整图像亮度 (0-255)\n值越大图像越亮")
        self.threshold_slider = self.create_slider(0, 255, self.current_config["threshold"])
        self.threshold_slider.setToolTip("二值化阈值 (0-255)\n用于边缘检测和分割")

        self.alpha_label = QLabel(f"{self.current_config['alpha']:.1f}")
        self.beta_label = QLabel(str(self.current_config["beta"]))
        self.threshold_label = QLabel(str(self.current_config["threshold"]))

        # 匀色控制 (新增算法)
        self.balance_check = QCheckBox("匀色处理")
        self.balance_check.setToolTip("启用颜色均衡处理\n改善光照不均匀问题")
        self.balance_combo = QComboBox()
        self.balance_combo.addItems([
            "Histogram",  # 根据截图保留
            "CLAHE",  # 对比度受限自适应直方图均衡
            "Gamma",  # 新增伽马校正
            "Log",  # 新增对数变换
            "ContrastStretch"  # 新增对比度拉伸
        ])
        self.balance_combo.setToolTip(
            "匀色算法选择:\n"
            "Histogram - 全局直方图均衡\n"
            "CLAHE - 自适应直方图均衡(适合局部对比度)\n"
            "Gamma - 伽马校正(调整亮度曲线)\n"
            "Log - 对数变换(增强暗部细节)\n"
            "ContrastStretch - 对比度拉伸"
        )
        self.balance_slider = self.create_slider(1, 100, self.current_config["balance_threshold"])
        self.balance_slider.setToolTip("匀色强度 (1-100)\n控制均衡化程度")
        self.balance_label = QLabel(str(self.current_config["balance_threshold"]))

        # 背景去除 (替换GrabCut)
        self.bg_check = QCheckBox("背景去除")
        self.bg_check.setToolTip("启用背景去除功能\n适用于文档/产品图像")
        self.bg_combo = QComboBox()
        self.bg_combo.addItems([
            "AdaptiveThreshold",  # 替换GrabCut
            "Morphology",  # 形态学方法
            "Threshold",  # 全局阈值
            "EdgeBased",  # 新增基于边缘的方法
            "KMeans"  # 新增K均值聚类
        ])
        self.bg_combo.setToolTip(
            "背景去除算法:\n"
            "AdaptiveThreshold - 自适应阈值分割\n"
            "Morphology - 形态学开运算\n"
            "Threshold - 全局阈值分割\n"
            "EdgeBased - 边缘检测+填充\n"
            "KMeans - K均值聚类分割"
        )
        self.bg_slider = self.create_slider(1, 100, self.current_config["bg_threshold"])
        self.bg_slider.setToolTip("去除强度 (1-100)\n控制背景去除程度")
        self.bg_label = QLabel(str(self.current_config["bg_threshold"]))

        # 降噪控制 (修正拼写)
        self.noise_check = QCheckBox("降噪处理")
        self.noise_check.setToolTip("启用降噪功能\n减少图像噪声")
        self.noise_combo = QComboBox()
        # 在init_ui方法中修改降噪选项：
        self.noise_combo.addItems([
            "Bilateral",  # 双边滤波
            "Median",  # 中值滤波
            "Gaussian",  # 高斯模糊
            "NLM",  # 非局部均值
        ])
        self.noise_combo.setToolTip(
            "降噪算法:\n"
            "Bilateral - 双边滤波(保留边缘)\n"
            "Median - 中值滤波(适合椒盐噪声)\n"
            "Gaussian - 高斯模糊(快速去噪)\n"
            "NLM - 非局部均值(高级去噪)\n"
        )
        self.noise_slider = self.create_slider(1, 15, self.current_config["noise_threshold"])
        self.noise_slider.setToolTip("降噪强度 (1-15)\n值越大效果越明显")
        self.noise_label = QLabel(str(self.current_config["noise_threshold"]))

        # 后处理选项
        self.invert_check = QCheckBox("反色处理")
        self.invert_check.setToolTip("反转图像颜色\n黑白颜色互换")
        self.edge_check = QCheckBox("边缘提取")
        self.edge_check.setToolTip("启用边缘检测\n使用Canny算法提取轮廓")

        # 布局参数控件
        param_layout.addRow("对比度:", self.create_slider_row(self.alpha_slider, self.alpha_label))
        param_layout.addRow("亮度:", self.create_slider_row(self.beta_slider, self.beta_label))
        param_layout.addRow("二值化阈值:", self.create_slider_row(self.threshold_slider, self.threshold_label))

        # 匀色控制行
        balance_layout = QHBoxLayout()
        balance_layout.addWidget(self.balance_check)
        balance_layout.addWidget(QLabel("算法:"))
        balance_layout.addWidget(self.balance_combo)
        param_layout.addRow("匀色控制:", balance_layout)
        param_layout.addRow("匀色强度:", self.create_slider_row(self.balance_slider, self.balance_label))

        # 背景去除控制行
        bg_layout = QHBoxLayout()
        bg_layout.addWidget(self.bg_check)
        bg_layout.addWidget(QLabel("算法:"))
        bg_layout.addWidget(self.bg_combo)
        param_layout.addRow("背景去除:", bg_layout)
        param_layout.addRow("去除强度:", self.create_slider_row(self.bg_slider, self.bg_label))

        # 降噪控制行
        noise_layout = QHBoxLayout()
        noise_layout.addWidget(self.noise_check)
        noise_layout.addWidget(QLabel("算法:"))
        noise_layout.addWidget(self.noise_combo)
        param_layout.addRow("降噪控制:", noise_layout)
        param_layout.addRow("降噪强度:", self.create_slider_row(self.noise_slider, self.noise_label))

        # 后处理选项
        option_layout = QHBoxLayout()
        option_layout.addWidget(self.invert_check)
        option_layout.addWidget(self.edge_check)
        param_layout.addRow("后处理:", option_layout)

        # 进度反馈
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setToolTip("当前处理进度")
        self.status_label = QLabel()
        self.status_label.setFixedHeight(18)
        self.status_label.setToolTip("当前处理状态")

        # 预览区域
        preview_layout = QHBoxLayout()
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(6)
        self.ori_preview = self.create_preview_label()
        self.ori_preview.setToolTip("原始图像预览")
        self.proc_preview = self.create_preview_label()
        self.proc_preview.setToolTip("处理结果预览")

        preview_layout.addWidget(self.ori_preview)
        preview_layout.addWidget(self.proc_preview)

        # 组装主界面
        main_layout.addLayout(path_layout)
        main_layout.addLayout(param_layout)
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(self.status_label)
        main_layout.addLayout(preview_layout)

        self.setLayout(main_layout)
        self.setWindowTitle("PCB丝印生成工具")
        self.setMinimumSize(800, 500)
        self.resize(900, 550)

        # 初始化状态 (根据截图更新)
        self.input_edit.setText(self.current_config["input_dir"])
        self.output_edit.setText(self.current_config["output_dir"])
        self.invert_check.setChecked(self.current_config["invert"])
        self.edge_check.setChecked(self.current_config["edge_detect"])
        self.balance_check.setChecked(self.current_config["color_balance_enabled"])
        self.balance_combo.setCurrentText(self.current_config["color_balance_method"])
        self.balance_slider.setValue(self.current_config["balance_threshold"])
        self.bg_check.setChecked(self.current_config["bg_remove_enabled"])
        self.bg_combo.setCurrentText(self.current_config["bg_remove_method"])
        self.bg_slider.setValue(self.current_config["bg_threshold"])
        self.noise_check.setChecked(self.current_config["noise_remove_enabled"])
        self.noise_combo.setCurrentText(self.current_config["noise_remove_method"])
        self.noise_slider.setValue(self.current_config["noise_threshold"])

    # ... [保留create_slider, create_slider_row, create_preview_label方法] ...
    def create_slider(self, min_val, max_val, init_val):
        slider = QSlider(Qt.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(init_val)
        slider.setFixedHeight(20)
        slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return slider

    def create_slider_row(self, slider, label):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        row.addWidget(slider, stretch=4)
        row.addWidget(label, stretch=1)
        return row

    def create_preview_label(self):
        label = QLabel(alignment=Qt.AlignCenter)
        label.setMinimumSize(300, 200)
        label.setFrameShape(QLabel.Box)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return label

    def setup_connections(self):
        self.browse_btn.clicked.connect(self.load_image)
        self.save_btn.clicked.connect(self.save_image)
        self.alpha_slider.valueChanged.connect(self.on_alpha_changed)
        self.beta_slider.valueChanged.connect(self.on_beta_changed)
        self.threshold_slider.valueChanged.connect(self.on_threshold_changed)
        self.balance_slider.valueChanged.connect(self.on_balance_changed)
        self.bg_slider.valueChanged.connect(self.on_bg_changed)
        self.noise_slider.valueChanged.connect(self.on_noise_changed)
        self.invert_check.stateChanged.connect(self.update_config_and_process)
        self.edge_check.stateChanged.connect(self.update_config_and_process)
        self.balance_check.stateChanged.connect(self.update_config_and_process)
        self.balance_combo.currentTextChanged.connect(self.update_config_and_process)
        self.bg_check.stateChanged.connect(self.update_config_and_process)
        self.bg_combo.currentTextChanged.connect(self.update_config_and_process)
        self.noise_check.stateChanged.connect(self.update_config_and_process)
        self.noise_combo.currentTextChanged.connect(self.update_config_and_process)
        self.signals.error_occurred.connect(self.show_error)
        self.signals.progress_updated.connect(self.update_progress)

    # ... [保留on_*_changed方法] ...
    def on_alpha_changed(self, value):
        self.alpha_label.setText(f"{value / 10:.1f}")
        self.update_config_and_process()

    def on_beta_changed(self, value):
        self.beta_label.setText(str(value))
        self.update_config_and_process()

    def on_threshold_changed(self, value):
        self.threshold_label.setText(str(value))
        self.update_config_and_process()

    def on_balance_changed(self, value):
        self.balance_label.setText(str(value))
        self.update_config_and_process()

    def on_bg_changed(self, value):
        self.bg_label.setText(str(value))
        self.update_config_and_process()

    def on_noise_changed(self, value):
        self.noise_label.setText(str(value))
        self.update_config_and_process()

    def update_config_and_process(self):
        self.current_config.update({
            "alpha": self.alpha_slider.value() / 10,
            "beta": self.beta_slider.value(),
            "threshold": self.threshold_slider.value(),
            "balance_threshold": self.balance_slider.value(),
            "bg_threshold": self.bg_slider.value(),
            "noise_threshold": self.noise_slider.value(),
            "invert": self.invert_check.isChecked(),
            "edge_detect": self.edge_check.isChecked(),
            "color_balance_enabled": self.balance_check.isChecked(),
            "color_balance_method": self.balance_combo.currentText(),
            "bg_remove_enabled": self.bg_check.isChecked(),
            "bg_remove_method": self.bg_combo.currentText(),
            "noise_remove_enabled": self.noise_check.isChecked(),
            "noise_remove_method": self.noise_combo.currentText()
        })
        self.update_config()
        self.update_processing()

    # ... [保留update_progress, show_error, load_image, save_image, update_config方法] ...
    def update_progress(self, value):
        if 0 <= value < len(self.progress_steps):
            self.status_label.setText(f"正在处理: {self.progress_steps[value]}（请忽略那个仅有视觉效果的进度条）")
            self.progress_bar.setValue(value)
        elif value >= len(self.progress_steps):
            self.status_label.setText("处理完成！（请忽略那个仅有视觉效果的进度条）")
            self.progress_bar.setValue(len(self.progress_steps) - 1)

    def show_error(self, msg):
        QMessageBox.critical(self, "处理错误",
                             f"发生异常:\n{msg}\n\n详细追踪:\n{traceback.format_exc()}")

    def load_image(self):
        try:
            default_dir = self.current_config["input_dir"]
            path, _ = QFileDialog.getOpenFileName(
                self, "选择图片", default_dir,
                "Image Files (*.png *.jpg *.bmp);;All Files (*)"
            )

            if path:
                self.current_config["input_dir"] = os.path.dirname(path)
                self.update_config()
                self.input_edit.setText(path)

                with open(path, 'rb') as f:
                    data = np.frombuffer(f.read(), dtype=np.uint8)
                    self.current_image = cv2.imdecode(data, cv2.IMREAD_COLOR)

                if self.current_image is None:
                    raise ValueError("无法解码图像文件")
                self.signals.progress_updated.emit(0)
                self.update_processing()
        except Exception as e:
            self.signals.error_occurred.emit(str(e))

    def save_image(self):
        try:
            if self.processed_image is None:
                raise ValueError("没有可保存的处理结果")

            default_dir = self.current_config["output_dir"]
            path, _ = QFileDialog.getSaveFileName(
                self, "保存图像", default_dir,
                "PNG Files (*.png);;JPEG Files (*.jpg)"
            )

            if path:
                self.current_config["output_dir"] = os.path.dirname(path)
                self.update_config()
                self.output_edit.setText(path)

                ext = os.path.splitext(path)[1].lower()
                if ext in ('.jpg', '.jpeg'):
                    ret, buf = cv2.imencode(ext, self.processed_image,
                                            [cv2.IMWRITE_JPEG_QUALITY, 100])
                else:
                    ret, buf = cv2.imencode(ext, self.processed_image)

                if ret:
                    with open(path, 'wb') as f:
                        buf.tofile(f)
                    QMessageBox.information(self, "保存成功",
                                            f"文件已保存至:\n{path}")
                    self.signals.progress_updated.emit(len(self.progress_steps))
        except Exception as e:
            self.signals.error_occurred.emit(str(e))

    def update_config(self):
        try:
            with open(self.CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.current_config, f,
                          ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "配置错误",
                                 f"更新配置失败:\n{str(e)}")

    def update_processing(self):
        if self.current_image is not None:
            try:
                self.process_image()
                self.update_previews()
            except Exception as e:
                self.signals.error_occurred.emit(str(e))

    def process_image(self):
        try:
            # 灰度转换
            gray = cv2.cvtColor(self.current_image, cv2.COLOR_BGR2GRAY)
            self.signals.progress_updated.emit(1)

            # 匀色处理 (新增算法)
            if self.current_config["color_balance_enabled"]:
                gray = self.apply_color_balance(gray)
            self.signals.progress_updated.emit(2)

            # 背景去除 (替换GrabCut)
            if self.current_config["bg_remove_enabled"]:
                gray = self.apply_bg_removal(gray)
            self.signals.progress_updated.emit(3)

            # 降噪处理 (新增算法)
            if self.current_config["noise_remove_enabled"]:
                gray = self.apply_noise_removal(gray)
            self.signals.progress_updated.emit(4)

            # 对比度增强
            enhanced = cv2.convertScaleAbs(
                gray,
                alpha=self.current_config["alpha"],
                beta=self.current_config["beta"]
            )
            self.signals.progress_updated.emit(5)

            # 图像处理
            if self.current_config["edge_detect"]:
                edges = cv2.Canny(enhanced,
                                  self.current_config["threshold"] // 2,
                                  self.current_config["threshold"])
                processed = edges
            else:
                _, processed = cv2.threshold(
                    enhanced,
                    self.current_config["threshold"],
                    255,
                    cv2.THRESH_BINARY
                )

            if self.current_config["invert"]:
                processed = cv2.bitwise_not(processed)

            self.signals.progress_updated.emit(6)

            self.processed_image = cv2.cvtColor(processed, cv2.COLOR_GRAY2BGR)
            self.signals.progress_updated.emit(7)

        except Exception as e:
            self.signals.error_occurred.emit(str(e))
            raise

    def apply_color_balance(self, img):
        method = self.current_config["color_balance_method"]
        threshold = self.current_config["balance_threshold"]

        if method == "Histogram":
            return cv2.equalizeHist(img)
        elif method == "CLAHE":
            clahe = cv2.createCLAHE(
                clipLimit=threshold / 50,
                tileGridSize=(8, 8))
            return clahe.apply(img)
        elif method == "Gamma":
            gamma = 1 + threshold / 100  # 1.01-2.0
            table = np.array([((i / 255.0) ** gamma) * 255
                              for i in np.arange(0, 256)]).astype("uint8")
            return cv2.LUT(img, table)
        elif method == "Log":
            c = threshold / 10
            return np.uint8(c * np.log(1 + img))
        elif method == "ContrastStretch":
            min_val = np.min(img)
            max_val = np.max(img)
            return cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX)
        return img

    def apply_bg_removal(self, img):
        method = self.current_config["bg_remove_method"]
        threshold = self.current_config["bg_threshold"]

        if method == "AdaptiveThreshold":
            block_size = max(3, threshold // 2 * 2 + 1)
            return cv2.adaptiveThreshold(
                img, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV,
                block_size,
                threshold // 10 + 1
            )
        elif method == "Morphology":
            kernel = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE,
                (threshold // 5 + 1, threshold // 5 + 1)
            )
            return cv2.morphologyEx(img, cv2.MORPH_OPEN, kernel)
        elif method == "Threshold":
            _, thresh = cv2.threshold(
                img,
                threshold,
                255,
                cv2.THRESH_BINARY_INV
            )
            return thresh
        elif method == "EdgeBased":
            edges = cv2.Canny(img, threshold, threshold * 2)
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            dilated = cv2.dilate(edges, kernel, iterations=2)
            contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            mask = np.zeros_like(img)
            cv2.drawContours(mask, contours, -1, 255, cv2.FILLED)
            return cv2.bitwise_and(img, mask)
        elif method == "KMeans":
            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
            _, labels, centers = cv2.kmeans(
                img.reshape(-1, 1).astype(np.float32),
                2, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS
            )
            mask = np.uint8(labels.reshape(img.shape) * 255)
            return cv2.bitwise_and(img, mask)
        return img

    def apply_noise_removal(self, img):
        """仅使用OpenCV原生算法的降噪处理"""
        method = self.current_config["noise_remove_method"]
        threshold = self.current_config["noise_threshold"]

        try:
            if method == "Bilateral":
                # 双边滤波 - 保留边缘 (OpenCV原生)
                return cv2.bilateralFilter(
                    img,
                    d=9,
                    sigmaColor=threshold * 10,
                    sigmaSpace=threshold * 10
                )

            elif method == "Median":
                # 中值滤波 - 适合椒盐噪声 (OpenCV原生)
                ksize = max(3, threshold * 2 + 1)  # 确保为奇数
                return cv2.medianBlur(img, ksize)

            elif method == "Gaussian":
                # 高斯模糊 - 快速去噪 (OpenCV原生)
                ksize = max(3, threshold * 2 + 1)  # 确保为奇数
                return cv2.GaussianBlur(img, (ksize, ksize), 0)

            elif method == "NLM":
                # 非局部均值 - 高级去噪 (OpenCV原生)
                return cv2.fastNlMeansDenoising(
                    img,
                    h=threshold * 2,
                    templateWindowSize=7,
                    searchWindowSize=21
                )

            return img

        except Exception as e:
            self.signals.error_occurred.emit(f"降噪处理失败({method}): {str(e)}")
            return img

    def update_previews(self):
        # 原图预览
        if self.current_image is not None:
            h, w, c = self.current_image.shape
            bytes_per_line = w * c
            q_img = QImage(
                np.ascontiguousarray(self.current_image).data,
                w, h,
                bytes_per_line,
                QImage.Format_BGR888
            )
            self.ori_preview.setPixmap(
                QPixmap.fromImage(q_img).scaled(
                    self.ori_preview.width(),
                    self.ori_preview.height(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
            )

        # 处理结果预览
        if self.processed_image is not None:
            h, w, c = self.processed_image.shape
            bytes_per_line = w * c
            q_img = QImage(
                np.ascontiguousarray(self.processed_image).data,
                w, h,
                bytes_per_line,
                QImage.Format_BGR888
            )
            self.proc_preview.setPixmap(
                QPixmap.fromImage(q_img).scaled(
                    self.proc_preview.width(),
                    self.proc_preview.height(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
            )


if __name__ == "__main__":
    os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '1'
    os.environ['QT_SCALE_FACTOR'] = '1'
    os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = '--disable-gpu'

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(image_to_Silkscreen_icon))
    window = ImageProcessor()
    window.show()
    sys.exit(app.exec())