from tkinter import *
import tkinter as tk
import InterfaceForm as IF
import SimpleClient as SC
import SimpleServer as SS
import OnlyClient as OC
import OnlyServer as OS
import winsound
import operator
import time

HEIGHT = 600
WIDTH = 600
TILE_SIZE = 25

listColor = ['orange', 'green', 'yellow', 'white', 'azure', 'purple', 'red']

class Window():
    mylogs = []
    def __init__(self, ID, recipientName, maskIP, destination, cache, mode):
        self.ID = ID
        self.win = tk.Tk()
        self.win.title(ID)
        self.cache = cache
        self.mode = mode
        self.currentUsers = {}
        self.colorIndex = 0
        self.win.geometry("600x600")
        self.win.resizable(False, False)
        self.win.configure(background = "black")

        firstLab_font = ("Helvetica", 15)
        other_font = ("Helvetica", 10, "bold")
        self.firstLab = Label(self.win, text = "Communicating with the user: {}".format(recipientName),
                              fg = 'White', background = 'black', font = firstLab_font)
        self.firstLab.grid(row=0, padx = 20, pady = 15, column=0, sticky = "WE",columnspan = 2)

        self.lb = Listbox(self.win, yscrollcommand=True, fg='white', highlightbackground='black', highlightcolor='black', bg='black', width=99, height=29, font = other_font)
        self.lb.grid(column=0, row=1, columnspan=WIDTH)

        self.message = tk.Entry(self.win, width = 80, textvariable="Enter something", font = other_font)
        self.message.bind('<Return>', self.send)
        self.message.grid(row=2, column=0, pady = 10)
        self.first_button = tk.Button(self.win, text="Send", command = self.Send)
        self.first_button.grid(row=2, column=5)

        self.winAfter()
        self.win.mainloop()

    def send(self, event = None):  # handler
        self.Send()

    def Send(self):
        if len(self.message.get())==0: return
        self.cache.append(self.message.get())
        self.message.delete(0, "end")

    def winAfter(self):
        act_logs = []
        if self.mode == 'all': all_logs = SC.logs + SS.logs
        else: all_logs = OC.logs + OS.logs

        for log in all_logs:
            if log.ID == self.ID:
                act_logs.append(log)
        self.update(act_logs)
        if not self.ID in IF.activeForms:
            self.win.destroy()
            return
        self.win.after(50, self.winAfter)

    def update(self, logs):
        if(len(logs) == len(self.mylogs)):
            return
        self.mylogs =  []
        self.lb.delete(0,"end")
        sorted_logs = sorted(logs, key=operator.attrgetter('time'))
        winsound.Beep(400, 150)
        index = 0
        for log in sorted_logs:
            if log.maskedSend not in self.currentUsers:
                self.assignColor(log.maskedSend)
            self.mylogs.append(log)
            color = self.currentUsers[log.maskedSend]
            strings = self.cutString(log.showList())
            for string in strings:
                self.lb.insert("end", string)
                self.lb.itemconfig(index, foreground=color)
                index += 1
        self.lb.see(END)

    def cutString(self, string):
        list = []
        limit = 50
        while len(string)>0:
            if len(list) == 0:
                list.append(string[:limit+13])
                string = string[limit + 13:]
            else:
                list.append('                    ' + string[:limit])
                string = string[limit:]
        return list


    def assignColor(self, user):
        global listColor
        if self.colorIndex == len(listColor):
            self.colorIndex = 0
        self.currentUsers[user] = listColor[self.colorIndex]
        self.colorIndex += 1