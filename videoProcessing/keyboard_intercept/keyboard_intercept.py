import keyboard
import time


MODIFIERS = {
    "shift": 42,
    "ctrl": 29,
    "left_windows": 91,
    "alt": 56,
    "alt_gr": 541,
    "right_shift": 54
}


class Key:
    def __init__(self, event):
        self.event = event
        self.name = ("PAD" if event.is_keypad else "") + event.name
        self.is_modifier = event.scan_code in MODIFIERS.values()
        if event.event_type == keyboard.KEY_DOWN:
            self.pressed = True
        elif event.event_type == keyboard.KEY_UP:
            self.pressed = False
    
    def __str__(self):
        return f"{self.name} - {'PRESSED' if self.pressed else 'RELEASED'}"


class KeyBucket(list):
    def __init__(self, actions):
        clean_actions = {" ".join(sorted([x for x in k.split(" ") if x != ""])): v for k, v in actions.items()}
        self.actions = clean_actions

    def add(self, key: Key):
        if len([x for x in self if x.name == key.name]) == 0:
            self.append(key)

    def remove(self, key: Key):
        self[:] = [x for x in self if x.name != key.name]
    
    def execute(self, key: Key):
        if key.pressed:
            self.add(key)
            if not key.is_modifier:
                self.perform_action(str(self))
        else:
            self.remove(key)
    
    def perform_action(self, keyId: str):
        if keyId in self.actions:
            self.actions[keyId]()
    
    def __str__(self):
        modifier_ids = [next(n for n, code in MODIFIERS.items() if code == x.event.scan_code) for x in self if x.is_modifier]
        actuator_ids = [x.name for x in self if not x.is_modifier]
        global_id = sorted(modifier_ids + actuator_ids)
        keyId = " ".join(global_id)
        return keyId


def intercept(signal: dict, actions: dict[str, any]):
    bucket = KeyBucket(actions)

    def on_key(event):
        bucket.execute(Key(event))

    keyboard.hook(on_key)

    while not signal["kill"]:
        time.sleep(0.1)


if __name__ == '__main__':
   
    def test():
        print("TEST SUCCESSFUL")

    actions = {
        "ctrl t": test
    }

    intercept({'kill': False}, actions)