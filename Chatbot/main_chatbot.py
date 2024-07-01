import time
import pyaudio
import keyboard
from keyboard._keyboard_event import KEY_DOWN, KEY_UP
import threading
import speech_recognition as sr
from llm_functionality import State, Model, LLM, SpeechManager


class Recorder:
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 44100
    CHUNK = 1024

    audio_frames = []
    is_recording = False
    is_processing = False
    data_recorded = True

    def __init__(self, mic_name, state, llm, activations) -> None:
        self.mic_name = mic_name
        self.state = state
        self.llm = llm
        self.pressed_keys = set()
        self.cur_model = None
        
        self.activations = {k: set(activation.replace(' ', '').split('+')) for k, activation in activations.items()}
        self.actv_keys = set([e for v in self.activations.values() for e in v])
        # threading.Thread(target=self.clean_keys_pressed)
        # self.index = 0

        def on_action(event):
            if event.event_type == KEY_DOWN:
                on_press(event.name)

            elif event.event_type == KEY_UP:
                on_release(event.name) 

        def on_press(key):
            # if key == 'a':
            #     if self.state.is_waiting or self.is_recording or self.is_processing:
            #         self.stop_recording()
            #     else:
            #         self.start_recording()
            #     return
            if not key in self.actv_keys:
                return
            # print(f'pressed {key} / {self.pressed_keys}')
            self.pressed_keys.add(key)
            for k, act in self.activations.items():
                if act == self.pressed_keys:
                    self.cur_model = k
                    self.start_recording()
                    break

        def on_release(key):
            if key in self.pressed_keys:
                self.pressed_keys.remove(key)
            for act in self.activations.values():
                if act.issubset(self.pressed_keys):
                    return
            self.stop_recording()

        keyboard.hook(lambda e: on_action(e))
        while True:
            time.sleep(1)
    
    # def clean_keys_pressed(self):
    #     while True:
    #         self.index += 1
    #         time.sleep(1)
    #         if self.index % 5 == 0:
    #             self.pressed_keys = {}


    def list_microphones(self):
        mic_list = sr.Microphone.list_microphone_names()
        mics = {}
        for index, name in enumerate(mic_list):
            mics[name] = index
        return mics

    def get_primary_input_index(self):
        mic_index = 0
        for name, index in self.list_microphones().items():
            if len(name) >= len(self.mic_name):
                if name.startswith(self.mic_name):
                    mic_index = index
                    break
            else:
                if self.mic_name.startswith(name):
                    mic_index = index
                    break
        return mic_index
    
    def get_audio(self):
        self.audio_frames = []
        self.is_recording = True

        p = pyaudio.PyAudio()
        stream = p.open(format=self.FORMAT, channels=self.CHANNELS, rate=self.RATE, input=True, 
                        frames_per_buffer=self.CHUNK, input_device_index=self.get_primary_input_index())
        print("Start Recording.")
        self.data_recorded = False

        while self.is_recording:
            data = stream.read(self.CHUNK)
            self.audio_frames.append(data)

        stream.stop_stream()
        stream.close()
        p.terminate()

        self.data_recorded = True
        print("Stopped recording.")

    def start_recording(self):
        if self.is_processing:
            # print("Processing is already on")
            return
        self.is_processing = True
        print("Processing started")
        threading.Thread(target=self.get_audio).start()
        self.state.set_waiting(True)

    def stop_recording(self):
        if not self.is_recording:
            return
        time.sleep(0.4)
        self.is_recording = False
        threading.Thread(target=self.process_audio).start()
        self.state.set_waiting(False)
        self.state.set_thinking(True)

    def process_audio(self):
        while not self.data_recorded:
            time.sleep(0.01)

        r = sr.Recognizer()
        audio_data = sr.AudioData(b''.join(self.audio_frames), self.RATE, 2)
        
        try:
            text = r.recognize_google(audio_data)
            reply, commands, messages, model = self.llm.process_text(text, model=self.cur_model)
            self.state.set_thinking(False)
            self.llm.take_action(reply, commands, messages, model)
            print("Recorded text: " + text)
        except sr.UnknownValueError:
            self.state.set_thinking(False)
            self.state.set_error(True)
            print("Audio not recognized.")
            time.sleep(2)
            self.state.set_error(False)
        except sr.RequestError as e:
            self.state.set_thinking(False)
            print("Could not request results from Google Speech Recognition service; {0}".format(e))
        
        self.is_processing = False
        print("Processing finished")


if __name__ == '__main__':
    speech_manager = SpeechManager()
    state = State(speech_manager)
    llm = LLM(state)
    Recorder(mic_name='Microphone (2- USB PnP Audio Device)', state=state, llm=llm, activations=
            {Model.Gemini: 'f13', 
            Model.ChatGPT3: 'ctrl+f15',
            Model.ChatGPT4: 'alt+f13',
            })
