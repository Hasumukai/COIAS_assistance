import sys
import pyautogui
import pytesseract
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QLineEdit
from PyQt5.QtGui import QPainter, QPen, QColor, QFont
from PyQt5.QtCore import Qt, QTime

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


# ============================================================
#   ★ 赤枠オーバーレイ（70×30固定・移動のみ・消えない）
# ============================================================
class TimeCaptureOverlay(QWidget):
    def __init__(self, parent_window):
        super().__init__()
        self.parent_window = parent_window

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 固定サイズ
        self.x, self.y = 300, 200
        self.w, self.h = 70, 30

        self.dragging = False

        self.setGeometry(self.x, self.y, self.w, self.h)
        self.show()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(QPen(QColor(255, 0, 0), 3))
        painter.drawRect(0, 0, self.w - 1, self.h - 1)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_start = event.pos()

    def mouseMoveEvent(self, event):
        if self.dragging:
            dx = event.x() - self.drag_start.x()
            dy = event.y() - self.drag_start.y()
            self.x += dx
            self.y += dy
            self.setGeometry(self.x, self.y, self.w, self.h)

    def mouseReleaseEvent(self, event):
        self.dragging = False

    # ★ capture_time は外部から呼ばれる
    def capture_time(self):
        screenshot = pyautogui.screenshot(region=(self.x, self.y, self.w, self.h))
        text = pytesseract.image_to_string(screenshot, lang="eng")

        import re
        match = re.search(r"\b\d{1,2}:\d{2}:\d{2}\b", text)

        if match:
            return match.group()
        return None

    # ★ アプリ終了時に赤枠も閉じる
    def close_overlay(self):
        self.close()


# ============================================================
#   ★ メインアプリ（軌道推定 GUI）
# ============================================================
class TimeStampedFitWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("時刻付き点と近似直線＋推定位置＋右クリック削除")
        self.setGeometry(100, 100, 900, 650)

        # ★ キーボードフォーカスを受け取らない（下のアプリにキーを渡す）
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.Window |
            Qt.WindowDoesNotAcceptFocus
        )

        self.setWindowOpacity(0.7)

        self.points = []
        self.time_inputs = []
        self.estimate_point = None
        self.last_clicked_time_input = None

        # --------------------------------------------------------
        # ★ 上段のボタン配置（左→右）
        # 1. 推定時刻取得
        # 2. 推定セル
        # 3. 推定ボタン
        # 4. リセットボタン
        # --------------------------------------------------------

        # 1. 推定時刻取得
        self.capture_estimate_button = QPushButton("推定時刻取得", self)
        self.capture_estimate_button.move(10, 10)
        self.capture_estimate_button.clicked.connect(self.capture_for_estimate)
        self.capture_estimate_button.setStyleSheet("background-color: white;")

        # 2. 推定セル
        self.estimate_input = QLineEdit(self)
        self.estimate_input.setPlaceholderText("hh:mm:ss")
        self.estimate_input.setFixedWidth(100)
        self.estimate_input.move(130, 10)

        # 3. 推定ボタン
        self.estimate_button = QPushButton("推定", self)
        self.estimate_button.move(240, 10)
        self.estimate_button.clicked.connect(self.estimate_position)
        self.estimate_button.setStyleSheet("background-color: white;")

        # 4. リセットボタン
        self.reset_button = QPushButton("リセット", self)
        self.reset_button.move(320, 10)
        self.reset_button.clicked.connect(self.reset_all)
        self.reset_button.setStyleSheet("background-color: white;")

        # --------------------------------------------------------
        # ★ 下段に「クリック点用の時刻取得」ボタン
        # --------------------------------------------------------
        self.capture_point_button = QPushButton("クリック点時刻取得", self)
        self.capture_point_button.move(10, 50)
        self.capture_point_button.clicked.connect(self.capture_for_point)
        self.capture_point_button.setStyleSheet("background-color: white;")

        self.show()

        # ★ 起動時に赤枠を表示
        self.overlay = TimeCaptureOverlay(self)

    # --------------------------------------------------------
    #   ★ 時刻取得（直近クリック点用）
    # --------------------------------------------------------
    def capture_for_point(self):
        time_str = self.overlay.capture_time()
        if time_str and self.last_clicked_time_input:
            self.last_clicked_time_input.setText(time_str)

    # --------------------------------------------------------
    #   ★ 時刻取得（推定セル用）
    # --------------------------------------------------------
    def capture_for_estimate(self):
        time_str = self.overlay.capture_time()
        if time_str:
            self.estimate_input.setText(time_str)

    # --------------------------------------------------------
    #   左クリックで点追加（直近点を記録）
    # --------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            x, y = event.x(), event.y()
            self.points.append((x, y))

            time_input = QLineEdit(self)
            time_input.setFixedWidth(80)
            time_input.move(100 + 90 * (len(self.time_inputs) % 7),
                            90 + 30 * (len(self.time_inputs) // 7))
            time_input.setPlaceholderText("hh:mm:ss")
            time_input.show()
            self.time_inputs.append(time_input)

            self.last_clicked_time_input = time_input
            self.update()

        elif event.button() == Qt.RightButton:
            if not self.points:
                return

            click_x, click_y = event.x(), event.y()

            # ★ 最接近点のみ削除
            min_index = None
            min_dist_sq = float('inf')

            for i, (x, y) in enumerate(self.points):
                dist_sq = (x - click_x)**2 + (y - click_y)**2
                if dist_sq < min_dist_sq:
                    min_dist_sq = dist_sq
                    min_index = i

            if min_index is not None:
                self.points.pop(min_index)
                self.time_inputs[min_index].deleteLater()
                self.time_inputs.pop(min_index)

                if self.time_inputs:
                    self.last_clicked_time_input = self.time_inputs[-1]
                else:
                    self.last_clicked_time_input = None

                self.update()

    # --------------------------------------------------------
    #   リセット
    # --------------------------------------------------------
    def reset_all(self):
        self.points.clear()
        self.estimate_point = None
        for input_box in self.time_inputs:
            input_box.deleteLater()
        self.time_inputs.clear()
        self.last_clicked_time_input = None
        self.estimate_input.clear()
        self.update()

    # --------------------------------------------------------
    #   推定処理
    # --------------------------------------------------------
    def estimate_position(self):
        if len(self.points) < 2:
            return

        time_values = []
        for input_box in self.time_inputs:
            t = QTime.fromString(input_box.text(), "hh:mm:ss")
            if not t.isValid():
                return
            time_values.append(t.msecsSinceStartOfDay() / 1000.0)

        t_est = QTime.fromString(self.estimate_input.text(), "hh:mm:ss")
        if not t_est.isValid():
            return
        t_query = t_est.msecsSinceStartOfDay() / 1000.0

        def linear_fit(t_list, v_list):
            n = len(t_list)
            sum_t = sum(t_list)
            sum_v = sum(v_list)
            sum_tt = sum(t*t for t in t_list)
            sum_tv = sum(t*v for t, v in zip(t_list, v_list))
            denom = n*sum_tt - sum_t**2
            if denom == 0:
                return None, None
            a = (n*sum_tv - sum_t*sum_v) / denom
            b = (sum_v - a*sum_t) / n
            return a, b

        xs, ys = zip(*self.points)
        ax, bx = linear_fit(time_values, xs)
        ay, by = linear_fit(time_values, ys)
        if None in (ax, ay):
            return

        x_est = ax * t_query + bx
        y_est = ay * t_query + by
        self.estimate_point = (x_est, y_est)
        self.update()

    # --------------------------------------------------------
    #   描画
    # --------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)

        for i, (x, y) in enumerate(self.points):
            painter.setPen(QPen(QColor(255, 0, 0), 6))
            painter.drawPoint(x, y)

            if i < len(self.time_inputs):
                time_text = self.time_inputs[i].text()
                if time_text:
                    painter.setPen(QPen(QColor(0, 0, 0)))
                    painter.setFont(QFont("Arial", 8))
                    painter.drawText(x + 5, y - 5, time_text)

        if len(self.points) >= 2:
            xs, ys = zip(*self.points)
            n = len(xs)
            sum_x = sum(xs)
            sum_y = sum(ys)
            sum_xx = sum(x*x for x in xs)
            sum_xy = sum(x*y for x, y in zip(xs, ys))
            denom = n*sum_xx - sum_x**2
            if denom != 0:
                m = (n*sum_xy - sum_x*sum_y) / denom
                b = (sum_y - m*sum_x) / n
                w = self.width()
                painter.setPen(QPen(QColor(0, 255, 0), 2))
                painter.drawLine(0, int(b), w, int(m*w + b))

        if self.estimate_point:
            x, y = self.estimate_point
            painter.setPen(QPen(QColor(0, 0, 255), 8))
            painter.drawPoint(int(x), int(y))

    # --------------------------------------------------------
    #   ★ アプリ終了時に赤枠も閉じる
    # --------------------------------------------------------
    def closeEvent(self, event):
        if hasattr(self, "overlay") and self.overlay:
            self.overlay.close_overlay()
        event.accept()

    # --------------------------------------------------------
    #   ★ キー入力を下のアプリに渡す
    # --------------------------------------------------------
    def keyPressEvent(self, event):
        event.ignore()


# ============================================================
#   ★ メイン
# ============================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TimeStampedFitWindow()
    sys.exit(app.exec_())
