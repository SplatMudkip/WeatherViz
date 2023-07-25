import threading
from PIL.ImageQt import ImageQt
from WeatherViz import renderer
from PySide2.QtWidgets import QApplication, QLabel, QGroupBox, QPushButton, QVBoxLayout, QHBoxLayout, QMainWindow, \
    QWidget, QDateEdit, QCalendarWidget, QGridLayout, QSlider, QRadioButton
from PySide2.QtGui import QPalette, QColor, QPixmap, QPainter, QIcon, Qt, QFont
from PySide2.QtCore import QDate, Slot, QPoint, QThread, QMetaObject, QRect
from PySide2 import QtCore
import sys
import io
from PIL import Image
from threading import Thread
import requests
import concurrent.futures


from WeatherViz.UIRescale import UIRescale
from WeatherViz.gui.ArrowPad import ArrowPad
from WeatherViz.gui.Map import MapWidget
from WeatherViz.gui.TransparentRectangle import TransparentRectangle

import json
from WeatherViz.renderer import Renderer

from WeatherViz.gui.DateRangeSlider import DateRangeSlider

from WeatherViz.gui.PlayButton import PlayButton

from WeatherViz.gui.ProgressBar import ProgressBar
from WeatherViz.Worker import Worker

from WeatherViz.gui.NonCollapsiblePanel import NonCollapsiblePanel

from WeatherViz.gui.DateRangeChooser import DateRangeChooser
from WeatherViz.gui.QueryPane import QueryPane

from WeatherViz.gui.Panel import Panel

from WeatherViz.gui.Toolbar import Toolbar

from WeatherViz.gui.ScrollableContent import ScrollableContent

from WeatherViz.gui.Help import Help

from WeatherViz.gui.MapLegend import MapLegend


class MainWindow(QWidget):
    progress_updated = QtCore.Signal()
    def __init__(self):
        super().__init__()

        self.freezeMap = False
        self.is_querying = False

        self.setWindowTitle("WeatherViz")
        self.setStyleSheet("background-color: rgba(32, 32, 32, 255); border-radius: 5px;")  # Change as needed
        self.setContentsMargins(0, 0, 0, 0)
        self.layout = QHBoxLayout(self)

        self.image = None
        self.apicalled = False
        self.query_daily = True
        self.query_start_date = QDate.currentDate()
        self.query_end_date = QDate.currentDate()
        self.map_widget = MapWidget([27.75, -83.25], 7)
        self.map_widget.mapChanged.connect(self.update_overlay)
        self.progress_updated.connect(self.update_progress, QtCore.Qt.QueuedConnection)
        self.start_date = QDateEdit(calendarPopup=True)
        self.start_date.setDate(QDate.currentDate())
        self.end_date = QDateEdit(calendarPopup=True)
        self.slider = DateRangeSlider(self.start_date, self.end_date, self)
        self.slider.playback_speed.get_button(0).clicked.connect(lambda: self.changePlaybackSpeed("1x"))
        self.slider.playback_speed.get_button(1).clicked.connect(lambda: self.changePlaybackSpeed("2x"))
        self.slider.playback_speed.get_button(2).clicked.connect(lambda: self.changePlaybackSpeed("3x"))
        self.slider.get_slider().valueChanged.connect(self.update_overlay)
        self.date_selector = DateRangeChooser(self.start_date, self.end_date, self.slider, self)
        self.date_selector.setGeometry(45 * UIRescale.Scale, 15 * UIRescale.Scale, 425 * UIRescale.Scale, 90 * UIRescale.Scale)
        # self.date_selector.setStyleSheet("background-color: rgba(90, 90, 90, 255);  border-radius: 3px;")
        self.hourly = QRadioButton("Hourly")
        # self.hourly.setStyleSheet("background-color: rgba(90, 90, 90, 255);  border-radius: 3px;")
        self.daily = QRadioButton("Daily")
        # self.daily.setStyleSheet("background-color: rgba(90, 90, 90, 255);  border-radius: 3px;")
        self.daily.setChecked(True)
        self.twobytwo = QRadioButton("2x2")
        self.fourbyfour = QRadioButton("4x4")
        self.fourbyfour.setChecked(True)
        self.sixteenbysixteen = QRadioButton("16x16")
        self.rain = QRadioButton("Rain")
        self.temperature = QRadioButton("Temperature")
        self.temperature.setChecked(True)
        self.wind = QRadioButton("Wind")
        self.progress = ProgressBar(self)
        self.progress.set_progress(4, 4)
        self.submit_button = QPushButton('Query', self)
        self.submit_button.setFixedHeight(50 * UIRescale.Scale)
        self.submit_button.setStyleSheet("background-color: rgba(90, 90, 90, 255);  border-radius: 3px;")

        self.submit_button.clicked.connect(self.query)
        content = [ScrollableContent([QLabel("Date Range"), self.date_selector,
                   Panel("Timeline Interval", "Tooltip", [self.hourly, self.daily]),
                   Panel("Heatmap Resolution", "Tooltip", [self.twobytwo, self.fourbyfour, self.sixteenbysixteen]),
                   Panel("Weather Type", "Tooltip", [self.temperature, self.rain, self.wind])], self),
                   self.submit_button, self.progress]
        # content = [ScrollableContent([QLabel("Date Range")])]
        self.queryPane = QueryPane(content, self)
        self.layout.addWidget(self.queryPane, alignment=Qt.AlignTop)
        self.layout.addWidget(self.map_widget)

        # Instruction pop-up goes here - for Aidan
        # self.trigger_instruction_panel()

        self.setLayout(self.layout)

        self.play_button = PlayButton(self.slider.get_slider(), self)
        self.toolbar = Toolbar([self.slider, self.play_button], self)
        self.toolbar.setGeometry(450 * UIRescale.Scale, 30 * UIRescale.Scale, self.map_widget.rect().width() - 70 * UIRescale.Scale, 100 * UIRescale.Scale)

        self.arrow_pad = ArrowPad(self)
        self.arrow_pad.setGeometry(1300 * UIRescale.Scale, 550 * UIRescale.Scale, 150 * UIRescale.Scale, 230 * UIRescale.Scale)  # Set the position and size of the arrow pad
        self.arrow_pad.up_button.clicked.connect(self.move_up)
        self.arrow_pad.down_button.clicked.connect(self.move_down)
        self.arrow_pad.left_button.clicked.connect(self.move_left)
        self.arrow_pad.right_button.clicked.connect(self.move_right)
        self.arrow_pad.zoom_in.clicked.connect(self.zoom_in)
        self.arrow_pad.zoom_out.clicked.connect(self.zoom_out)
        self.arrow_pad.show()

        colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (0, 0, 0)]
        labels = ["75%", "50%", "25%", "0%"]
        title = "Rain"

        self.legend_widget = MapLegend(colors, labels, title, self)
        self.legend_widget.setGeometry(self.queryPane.rect().width() + 50 * UIRescale.Scale,
                              self.rect().height() - 400 * UIRescale.Scale,
                              400 * UIRescale.Scale,
                              150 * UIRescale.Scale)

        self.help = Help(self)
        self.help.setGeometry(self.queryPane.rect().width() + 50 * UIRescale.Scale,
                              self.rect().height() - self.help.rect().height() - 50 * UIRescale.Scale,
                              self.map_widget.rect().width() - 70 * UIRescale.Scale,
                              400 * UIRescale.Scale)

    def changePlaybackSpeed(self, state):
        if state == "1x":
            self.play_button.speed = 1000
        elif state == "2x":
            self.play_button.speed = 500
        else:
            self.play_button.speed = 250

        if self.play_button.playButton.isChecked():
            self.play_button.timer.stop()
            self.play_button.timer.start(self.play_button.speed)

    def trigger_instruction_panel(self):
        # self.instructionPopUp = QGroupBox()
        # self.instructionPopUp.setWindowTitle("Instructions")
        # self.instructionPopUp.setFixedSize(1150, 500)
        # self.instructionPopUp.setStyleSheet("background-color: rgba(225, 225, 225, 255)")

        self.instructionText1 = QLabel(self)
        self.instructionText1.setText("     Welcome to WeatherViz!")
        self.instructionText1.setFont(QFont("Arial", 36, QFont.Bold))
        self.instructionText1.setGeometry(QRect(345, 95, 830, 75))
        self.instructionText1.setStyleSheet("background-color: rgba(125, 125, 125, 130); border-radius: 5px;")
        self.instructionText2 = QLabel(self)
        self.instructionText2.setText("\t          Instructions:")
        self.instructionText2.setFont(QFont("Arial", 28))
        self.instructionText2.setGeometry(QRect(345, 182, 830, 55))
        self.instructionText2.setStyleSheet("background-color: rgba(125, 125, 125, 130); border-radius: 5px;")
        self.instructionText3 = QLabel(self)
        self.instructionText3.setText("    ∙ Use the buttons in the bottom right corner to move and zoom around the map\n    "
                                      "∙ WASD can also be used to move plus Q to zoom in and E to zoom out\n    "
                                      "∙ Set the Date Range to fetch between the two dates\n    "
                                      "∙ The Timeline Interval lets you select between hourly and daily data\n    "
                                      "∙ The Heatmap Resolution decides how many points will be rendered on the map\n         "
                                      "◦ Higher resolutions will take longer to query\n    "
                                      "∙ Choose the weather statistic you want to query using the Weather Type setting\n    "
                                      "∙ Press the Query button to begin a query\n         "
                                      "◦ A progress bar will let you know how much of the query is currently completed\n    "
                                      "∙ When the query is completed, the heatmap will automatically appear on the map\n         "
                                      "◦ Press the play button in the upper-right corner to start a timelapse of the heatmap\n    "
                                      "∙ Press the Close button below to enable map movement and querying")
        self.instructionText3.setGeometry(QRect(345, 250, 830, 255))
        self.instructionText3.setStyleSheet("background-color: rgba(125, 125, 125, 130); border-radius: 5px; font-size: 13pt;")
        self.instructionButton = QPushButton(self)
        self.instructionButton.setText("Close")
        self.instructionButton.setGeometry(QRect(715, 515, 75, 40))
        self.instructionButton.setStyleSheet("background-color: rgba(125, 125, 125, 130); border-radius: 5px; font-size: 14pt;")
        self.instructionButton.clicked.connect(self.clearInstructions)
        # self.instructionPopUp.show()


    def clearInstructions(self):
        self.instructionButton.lower()
        self.instructionText1.lower()
        self.instructionText2.lower()
        self.instructionText3.lower()
        self.freezeMap = False
        self.map_widget.freezeMap = False
        self.play_button.freezeMap = False

    def showInstructions(self):
        self.instructionButton.raise_()
        self.instructionText3.raise_()
        self.freezeMap = True
        self.map_widget.freezeMap = True
        self.play_button.freezeMap = True

    #Navigation Functions
    def resizeEvent(self, event):
        self.toolbar.setGeometry(self.queryPane.rect().width() + 50 * UIRescale.Scale, 30 * UIRescale.Scale, self.map_widget.rect().width() - 70 * UIRescale.Scale, 100 * UIRescale.Scale)
        self.arrow_pad.setGeometry(self.rect().width() - 200 * UIRescale.Scale, self.rect().height() - 300 * UIRescale.Scale, 150 * UIRescale.Scale, 230 * UIRescale.Scale)
        self.help.setGeometry(self.queryPane.rect().width() + 50 * UIRescale.Scale,
                              self.rect().height() - self.help.rect().height() - 50 * UIRescale.Scale, self.map_widget.rect().width() - 70 * UIRescale.Scale,
                              400 * UIRescale.Scale)
        self.legend_widget.setGeometry(self.rect().width() - 200 * UIRescale.Scale,
                                        self.toolbar.rect().height() + 75 * UIRescale.Scale,
                                       150 * UIRescale.Scale,
                                       400 * UIRescale.Scale)
        super().resizeEvent(event)

    def move_up(self):
        if self.freezeMap is False:
            self.map_widget.location[0] += 1 / (2 ** (self.map_widget.zoom - 8))
            self.update_overlay()

    def move_down(self):
        if self.freezeMap is False:
            self.map_widget.location[0] -= 1 / (2 ** (self.map_widget.zoom - 8))
            self.update_overlay()

    def move_left(self):
        if self.freezeMap is False:
            self.map_widget.location[1] -= 1 / (2 ** (self.map_widget.zoom - 8))
            self.update_overlay()

    def move_right(self):
        if self.freezeMap is False:
            self.map_widget.location[1] += 1 / (2 ** (self.map_widget.zoom - 8))
            self.update_overlay()

    def zoom_in(self):
        if self.freezeMap is False:
            self.map_widget.zoom += 1
            self.update_overlay()

    def zoom_out(self):
        if self.freezeMap is False:
            self.map_widget.zoom -= 1
            self.update_overlay()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_W:  # W
            self.move_up()
        elif event.key() == Qt.Key_S:  # S
            self.move_down()
        elif event.key() == Qt.Key_A:  # A
            self.move_left()
        elif event.key() == Qt.Key_D:  # D
            self.move_right()
        elif self.map_widget.zoom > 0 and event.key() == Qt.Key_E:  # E
            self.zoom_out()
        elif self.map_widget.zoom < 18 and event.key() == Qt.Key_Q:  # Q
            self.zoom_in()

    def update_overlay(self):
        if self.apicalled:
            byte_array = self.ren.render(self.slider.get_slider().value(), self.map_widget.location[0], self.map_widget.location[1],
                                         self.map_widget.zoom, self.map_widget.web_map.width(),
                                         self.map_widget.web_map.height())
            image = Image.frombytes("RGBA", (self.map_widget.web_map.width(), self.map_widget.web_map.height()), byte_array)
            self.map_widget.refresh(image)
        else:
            self.map_widget.refresh()

    def change_opacity(self, image_path, opacity_level):
        img = Image.open(image_path).convert("RGBA")

        for x in range(img.width):
            for y in range(img.height):
                r, g, b, a = img.getpixel((x, y))
                img.putpixel((x, y), (r, g, b, int(a * opacity_level)))

        img.save(image_path)

    def color_overlay(self, image_path, color, opacity_level):
        img = Image.open(image_path).convert("RGBA")
        overlay = Image.new('RGBA', img.size, color)
        blended = Image.blend(img, overlay, opacity_level)
        blended.save(image_path, 'PNG')

    def is_hourly(self):
        return self.hourly.isChecked()

    def is_daily(self):
        return self.daily.isChecked()

    def query(self):
        if self.freezeMap is False:
            self.submit_button.setChecked(True)
            self.submit_button.setText("Querying...")
            threading.Thread(target=self.get_data).start()

    def update_progress(self):
        self.progress.increment_progress()

    @QtCore.Slot()
    def update_slider_range(self):
        self.play_button.togglePlay(False)
        self.slider.update_range(self.query_start_date, self.query_end_date, self.query_daily)

    def get_data(self):
        #Resolution
        if self.twobytwo.isChecked():
            RESOLUTION = 2
        elif self.fourbyfour.isChecked():
            RESOLUTION = 4
        elif self.sixteenbysixteen.isChecked():
            RESOLUTION = 16
        else:
            RESOLUTION = 2

        #Time interval
        if self.daily.isChecked():
            DAILY = True
        else:
            DAILY = False
        self.query_daily = DAILY

        #Weather event
        if self.temperature.isChecked():
            self.legend_widget.title = "Temperature"
            if DAILY:
                VARIABLE = "temperature_2m_mean"
            else:
                VARIABLE = "temperature_2m"
        elif self.wind.isChecked(): #TODO: Edit this for actual wind speed data
            self.legend_widget.title = "Wind"
            if DAILY:
                VARIABLE = "windspeed_10m_max"
            else:
                VARIABLE = "windspeed_10m"
        elif self.rain.isChecked():
            self.legend_widget.title = "Rain"
            if DAILY:
                VARIABLE = "rain_sum"
            else:
                VARIABLE = "rain"
        TEMPERATURE_UNIT = "fahrenheit"
        WINDSPEED_UNIT = "mph"
        PRECIPITATION_UNIT = "inch"
        TIMEZONE = "EST"
        self.progress.set_total(RESOLUTION*RESOLUTION)
        self.progress.set_progress(0, RESOLUTION*RESOLUTION)

        self.query_start_date = self.date_selector.start_date.date()
        self.query_end_date = self.date_selector.end_date.date()
        start_date = self.query_start_date.toString("yyyy-MM-dd")
        end_date = self.query_end_date.toString("yyyy-MM-dd")

        geocoords = renderer.geocoords(self.map_widget.web_map.width(), self.map_widget.web_map.height(), RESOLUTION,
                                   self.map_widget.location[0], self.map_widget.location[1], self.map_widget.zoom)

        session = requests.Session()

        def api_call(lat, lon):
            url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={start_date}&end_date={end_date}&temperature_unit={TEMPERATURE_UNIT}&windspeed_unit={WINDSPEED_UNIT}&precipitation_unit={PRECIPITATION_UNIT}&timezone={TIMEZONE}&models=best_match&cell_selection=nearest"

            if DAILY:
                url += f"&daily={VARIABLE}"
            else:
                url += f"&hourly={VARIABLE}"

            self.progress_updated.emit()
            res = session.get(url)

            if res.status_code == requests.codes.ok:
                return res.json()
            else:
                raise RuntimeError(f"The request failed w/ code {res.status_code}, text {res.text}")

        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = executor.map(lambda coords: api_call(*coords), geocoords)

        responses = {}
        for result, (lat, lon) in zip(results, geocoords):
            key = (str(lat), str(lon))
            responses[key] = result["daily" if DAILY else "hourly"][VARIABLE]
            #print(responses[key])

        self.ren = Renderer()
        self.ren.set_data(responses)
        self.apicalled = True
        QMetaObject.invokeMethod(self, "update_overlay", QtCore.Qt.QueuedConnection)
        QMetaObject.invokeMethod(self, "update_slider_range", QtCore.Qt.QueuedConnection)
        self.submit_button.setText("Query")


