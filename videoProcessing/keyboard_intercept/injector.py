from keyboard_intercept import intercept
import threading
import time


def g_cb():
    print("Sei uno stupratore")


def ctrl_asd_cb():
    print("Fuck you")


actions = {
    "g": g_cb,
    "left_windows a d s": ctrl_asd_cb,
}


signal = {"kill": False}

keyboard_task = threading.Thread(target=intercept, args=(signal, actions,))
keyboard_task.start()

time.sleep(10)
signal["kill"] = True
keyboard_task.join()