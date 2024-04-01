import time
import pyaudio
import keyboard
from keyboard._keyboard_event import KEY_DOWN, KEY_UP
import threading
import speech_recognition as sr
from llm_functionality import State, LLM


class Recorder:
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 44100
    CHUNK = 1024

    audio_frames = []
    is_recording = False
    is_processing = False
    data_recorded = True

    def __init__(self, mic_name, activation, state, llm) -> None:
        self.mic_name = mic_name
        self.state = state
        self.llm = llm

        def on_action(event):
            if event.event_type == KEY_DOWN:
                on_press(event.name)

            elif event.event_type == KEY_UP:
                on_release(event.name)

        def on_press(key):
            if key == activation:
                self.start_recording()

        def on_release(key):
            if key == activation:
                self.stop_recording()

        keyboard.hook(lambda e: on_action(e))
        keyboard.wait('esc')

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
        # print("Start Recording.")
        self.data_recorded = False

        while self.is_recording:
            data = stream.read(self.CHUNK)
            self.audio_frames.append(data)

        stream.stop_stream()
        stream.close()
        p.terminate()

        self.data_recorded = True
        # print("Stopped recording.")

    def start_recording(self):
        if self.is_processing:
            return
        self.is_processing = True
        print("Processing started")
        self.state.set_waiting(True)
        threading.Thread(target=self.get_audio).start()

    def stop_recording(self):
        if not self.is_recording:
            return
        time.sleep(0.4)
        self.is_recording = False
        threading.Thread(target=self.process_audio).start()

    def process_audio(self):
        while not self.data_recorded:
            time.sleep(0.01)

        r = sr.Recognizer()
        audio_data = sr.AudioData(b''.join(self.audio_frames), self.RATE, 2)
        
        try:
            self.state.set_waiting(False)
            text = r.recognize_google(audio_data)
            self.llm.process_text(text)
            print("Recorded text: " + text)
        except sr.UnknownValueError:
            print("Audio not recognized.")
        except sr.RequestError as e:
            print("Could not request results from Google Speech Recognition service; {0}".format(e))
        self.is_processing = False
        print("Processing finished")


state = State()
llm = LLM(state)
Recorder(mic_name='Microphone (2- USB PnP Audio Device)', activation='f13', state=state, llm=llm)
