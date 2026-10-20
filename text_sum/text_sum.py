import sys
import re
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QTextEdit, QLabel)
from PySide6.QtGui import QIcon
import os

launcher_root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    from Fusure_tools import text_sum_icon
    text_sum_icon = os.path.abspath(text_sum_icon)
except Exception as e:
    text_sum_icon = os.path.abspath(os.path.dirname(__file__) + r'\..\..\logo\default_icon.ico')

class TextCountWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("文本字符统计工具")
        self.resize(550, 380)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        # 全局间距、边距缩小，布局更紧凑
        main_layout.setSpacing(4)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # 文本输入框
        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("请在此输入需要统计的文本...")
        main_layout.addWidget(self.text_input)

        # 第一行水平布局：中文 + 英文
        h_layout1 = QHBoxLayout()
        h_layout1.setSpacing(12)  # 同行间标签间距
        self.label_chinese = QLabel("中文字符数：0")
        self.label_english = QLabel("英文字符数：0")
        h_layout1.addWidget(self.label_chinese)
        h_layout1.addWidget(self.label_english)
        row1_widget = QWidget()
        row1_widget.setLayout(h_layout1)

        # 第二行水平布局：总字符 + 符号
        h_layout2 = QHBoxLayout()
        h_layout2.setSpacing(12)
        self.label_total = QLabel("总字符数：0")
        self.label_symbol = QLabel("符号/标点数量：0")
        h_layout2.addWidget(self.label_total)
        h_layout2.addWidget(self.label_symbol)
        row2_widget = QWidget()
        row2_widget.setLayout(h_layout2)

        main_layout.addWidget(row1_widget)
        main_layout.addWidget(row2_widget)

        self.text_input.textChanged.connect(self.count_text)

    def count_text(self):
        text = self.text_input.toPlainText()
        total_len = len(text)

        chinese_num = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_num = len(re.findall(r'[a-zA-Z]', text))
        symbol_num = len(re.findall(r'[^\u4e00-\u9fffa-zA-Z0-9\s]', text))

        self.label_total.setText(f"总字符数：{total_len}")
        self.label_chinese.setText(f"中文字符数：{chinese_num}")
        self.label_english.setText(f"英文字符数：{english_num}")
        self.label_symbol.setText(f"符号/标点数量：{symbol_num}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(text_sum_icon))
    win = TextCountWindow()
    win.show()
    sys.exit(app.exec())