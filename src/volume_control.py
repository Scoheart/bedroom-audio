"""A visible volume thumb with click-to-position and a generous pointer target."""
import tkinter as tk

def percentage_at(x,width,padding=18):
    length=max(1,width-padding*2)
    return max(0,min(100,round((x-padding)*100/length)))

class VolumeSlider(tk.Canvas):
    def __init__(self,parent,variable,commit,**kwargs):
        super().__init__(parent,height=44,bg='white',highlightthickness=1,
                         highlightbackground='white',highlightcolor='#2264E8',
                         takefocus=True,cursor='hand2',**kwargs)
        self.variable=variable;self.commit=commit;self.dragging=False
        self.trace=variable.trace_add('write',self.redraw)
        self.bind('<Configure>',self.redraw)
        self.bind('<Button-1>',self.press)
        self.bind('<B1-Motion>',self.move)
        self.bind('<ButtonRelease-1>',self.release)
        self.bind('<MouseWheel>',self.wheel)
        for key,amount in [('Left',-1),('Right',1),('Down',-1),('Up',1)]:
            self.bind('<'+key+'>',lambda event,step=amount:self.step(step))
        self.bind('<Home>',lambda event:self.choose(0))
        self.bind('<End>',lambda event:self.choose(100))

    def redraw(self,*_):
        width=self.winfo_width();height=self.winfo_height()
        if width<38:return
        x=18+(width-36)*max(0,min(100,self.variable.get()))/100;y=height/2
        self.delete('all')
        self.create_line(18,y,width-18,y,fill='#DDE5F0',width=8,capstyle='round')
        if x>18:self.create_line(18,y,x,y,fill='#2264E8',width=8,capstyle='round')
        self.create_oval(x-13,y-13,x+13,y+13,fill='#2264E8',outline='white',width=2)
        self.create_oval(x-4,y-4,x+4,y+4,fill='white',outline='white')

    def press(self,event):
        self.focus_set();self.dragging=True;self.move(event)
        return 'break'

    def move(self,event):
        self.variable.set(percentage_at(event.x,self.winfo_width()))
        return 'break'

    def release(self,event):
        self.move(event);self.dragging=False;self.commit()
        return 'break'

    def choose(self,value):
        self.variable.set(max(0,min(100,value)));self.commit()
        return 'break'

    def step(self,amount):return self.choose(round(self.variable.get())+amount)
    def wheel(self,event):return self.step(1 if event.delta>0 else -1)

    def destroy(self):
        self.variable.trace_remove('write',self.trace)
        super().destroy()
