import tkinter as tk
from tkinter import *
import time
import SimpleServer as SS

HEIGHT = 600
WIDTH = 600

class Window():
    mylogs = []
    def __init__(self, ID):
        self.ID = ID
        self.win = tk.Tk()
        self.win.title(ID)
        self.win.geometry("600x600")
        self.win.resizable(False, False)
        self.win.configure(background = "black")

        self.lb = Listbox(self.win, yscrollcommand=True, fg='white', highlightcolor='black', bg='black', width=99, height=35)
        self.lb.grid(column=0, row=0, columnspan=WIDTH)

        self.nameEntered = tk.Entry(self.win, width=92, textvariable="Enter something")
        self.nameEntered.grid(row=1, column=0)
        self.first_button = tk.Button(self.win, text="Send")
        self.first_button.grid(row=1, column=5)

        self.winAfter()
        #self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.mainloop()


    def winAfter(self):
        self.update(SS.logs)
        self.win.after(100, self.winAfter)

    def update(self, logs):
        if(len(logs) == len(self.mylogs)):
            return
        self.mylogs =  []
        self.lb.delete(0,"end")
        for log in logs:
            if log.formID == self.ID:
                self.mylogs.append(log)