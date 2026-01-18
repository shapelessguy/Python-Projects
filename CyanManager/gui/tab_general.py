import ctypes
import os
import sys
import threading
import json
from utils import pprint
from functools import partial
from PyQt5.QtWidgets import QWidget, QLabel, QPushButton, QHBoxLayout, QLineEdit
from PyQt5.QtGui import QColor, QPainter, QIcon, QIntValidator
from PyQt5.QtCore import Qt, QTime
from PyQt5.QtWinExtras import QtWin


def on_profile_change(ui_manager):
    ui_manager.signal.set_profile(ui_manager.ui.profile.currentText())


suspend_change = True
def on_change_ad(ui_manager):
    global suspend_change
    if suspend_change:
        return
    ad = ui_manager.signal.get_audio_devices()
    d_str = json.dumps(ad)
    ad["speakers"] = ui_manager.ui.speakers.text()
    ad["headphones"] = ui_manager.ui.headphones.text()
    if d_str != json.dumps(ad):
        ui_manager.signal.set_audio_devices(ad)


def time_to_str(obj):
    t = obj.time()
    return f"{t.hour():02d}:{t.minute():02d}"


def on_change_rs(ui_manager):
    global suspend_change
    if suspend_change:
        return
    rs = ui_manager.signal.get_roomserver_settings()
    d_str = json.dumps(rs)
    rs["url"] = ui_manager.ui.roomserver_hostname.text()
    rs["port"] = ui_manager.ui.roomserver_port.text()
    rs["auto_from"] = time_to_str(ui_manager.ui.auto_from)
    rs["auto_to"] = time_to_str(ui_manager.ui.auto_to)
    if d_str != json.dumps(rs):
        ui_manager.signal.set_roomserver_settings(rs)


def on_change_ro(ui_manager):
    global suspend_change
    if suspend_change:
        return
    ro = ui_manager.signal.get_restart_options()
    d_str = json.dumps(ro)
    ro["active"] = ui_manager.ui.shutdown_active.isChecked()
    ro["mouse_jiggle"] = ui_manager.ui.mouse_jiggle.isChecked()
    ro["from"] = time_to_str(ui_manager.ui.shutdown_from)
    ro["to"] = time_to_str(ui_manager.ui.shutdown_to)
    ro["inactive_delay"] = time_to_str(ui_manager.ui.inactivity)
    if d_str != json.dumps(ro):
        ui_manager.signal.set_restart_options(ro)


def set_gen_layout(ui_manager):
    global suspend_change
    suspend_change = True
    cur_profile = ui_manager.signal.profile
    all_profiles = ui_manager.signal.get_all_profiles()
    ui_manager.ui.profile.addItems(all_profiles)
    ui_manager.ui.profile.setCurrentText(cur_profile)
    ui_manager.ui.profile.currentTextChanged.connect(lambda _: on_profile_change(ui_manager))
    
    ui_manager.ui.speakers.textChanged.connect(partial(on_change_ad, ui_manager))
    ui_manager.ui.headphones.textChanged.connect(partial(on_change_ad, ui_manager))
    ui_manager.ui.roomserver_hostname.textChanged.connect(partial(on_change_rs, ui_manager))
    ui_manager.ui.roomserver_port.textChanged.connect(partial(on_change_rs, ui_manager))
    ui_manager.ui.auto_from.timeChanged.connect(partial(on_change_rs, ui_manager))
    ui_manager.ui.auto_to.timeChanged.connect(partial(on_change_rs, ui_manager))
    ui_manager.ui.shutdown_from.timeChanged.connect(partial(on_change_ro, ui_manager))
    ui_manager.ui.shutdown_to.timeChanged.connect(partial(on_change_ro, ui_manager))
    ui_manager.ui.inactivity.timeChanged.connect(partial(on_change_ro, ui_manager))
    ui_manager.ui.shutdown_active.toggled.connect(partial(on_change_ro, ui_manager))
    ui_manager.ui.mouse_jiggle.toggled.connect(partial(on_change_ro, ui_manager))
    
    ad = ui_manager.signal.get_audio_devices()
    ui_manager.ui.speakers.setText(ad["speakers"])
    ui_manager.ui.headphones.setText(ad["headphones"])

    rs = ui_manager.signal.get_roomserver_settings()
    ui_manager.ui.roomserver_hostname.setText(rs["url"])
    ui_manager.ui.roomserver_port.setText(str(rs["port"]))
    ui_manager.ui.auto_from.setTime(QTime(int(rs["auto_from"].split(":")[0]), int(rs["auto_from"].split(":")[1]), 00))
    ui_manager.ui.auto_to.setTime(QTime(int(rs["auto_to"].split(":")[0]), int(rs["auto_to"].split(":")[1]), 00))

    ro = ui_manager.signal.get_restart_options()
    ui_manager.ui.shutdown_from.setTime(QTime(int(ro["from"].split(":")[0]), int(ro["from"].split(":")[1]), 00))
    ui_manager.ui.shutdown_to.setTime(QTime(int(ro["to"].split(":")[0]), int(ro["to"].split(":")[1]), 00))
    ui_manager.ui.inactivity.setTime(QTime(int(ro["inactive_delay"].split(":")[0]), int(ro["inactive_delay"].split(":")[1]), 00))
    ui_manager.ui.shutdown_active.setChecked(ro["active"])
    ui_manager.ui.mouse_jiggle.setChecked(ro["mouse_jiggle"])
    suspend_change = False
