"""Bedroom Audio desktop entry point (GUI or a hidden worker subprocess)."""
from __future__ import annotations
import argparse
import asyncio
import ctypes
import math
import os
from pathlib import Path
import queue
import struct
import sys
import threading
import time
import wave
import winsound
import common
from version import VERSION

BG='#F3F6FA';WHITE='#FFFFFF';INK='#19283D';MUTED='#69778C'
BLUE='#2264E8';GREEN='#12805C';RED='#BE3948';LINE='#E1E7F0'
FONT='Microsoft YaHei UI'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--version', action='version', version='Bedroom Audio '+VERSION)
    parser.add_argument('--configure', action='store_true')
    parser.add_argument('--output', help='Write discovery JSON to a file (useful for the GUI executable).')
    parser.add_argument('--worker',action='store_true')
    parser.add_argument('--data-dir')
    parser.add_argument('--scan',action='store_true')
    parser.add_argument('--list-receivers',action='store_true')
    parser.add_argument('--self-check',action='store_true')
    parser.add_argument('--repair-network',action='store_true')
    parser.add_argument('--parent-pid',type=int)
    args=parser.parse_args()
    folder=common.data_dir(args.data_dir)
    if args.repair_network:
        from network import repair_network
        repair_network(folder);return
    if args.self_check:
        from diagnostics import self_check
        result=self_check(folder)
        raise SystemExit(0 if result['ok'] else 1)
    if args.list_receivers:
        import json
        receivers=asyncio.run(common.list_receivers())
        if args.output:
            common.write_json(Path(args.output), receivers)
        elif sys.stdout is not None:
            print(json.dumps(receivers, ensure_ascii=False, indent=2))
        else:
            common.write_json(folder/'receivers.json', receivers)
        return
    if args.configure and not args.worker and not args.scan:
        from device_setup import run_setup
        if not run_setup(folder):return
    try:
        common.configure_devices(folder)
    except ValueError as error:
        if not args.worker and not args.scan:
            from device_setup import run_setup
            if not run_setup(folder, str(error)):return
            common.configure_devices(folder)
        else:raise
    if args.worker:
        from engine import worker
        if args.parent_pid:
            def guard():
                import psutil
                while psutil.pid_exists(args.parent_pid):time.sleep(1)
                (folder/'stop.request').write_text('parent exited',encoding='utf8')
            threading.Thread(target=guard,daemon=True).start()
        from realtime import run_audio
        run_audio(worker(folder));return
    if args.scan:
        records=asyncio.run(common.discover(folder,force=True))
        if args.output:common.write_json(Path(args.output), records)
        elif sys.stdout is not None:print(records)
        return
    import tkinter as tk
    from tkinter import ttk
    from latency import mode_name
    from volume_control import VolumeSlider
    from controller import start,stop,refresh

    try:ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except OSError:pass
    ctypes.windll.kernel32.CreateMutexW.restype=ctypes.c_void_p
    ctypes.windll.kernel32.CloseHandle.argtypes=[ctypes.c_void_p]
    mutex=ctypes.windll.kernel32.CreateMutexW(None,False,'Local\\BedroomAudioDesktop')
    if ctypes.windll.kernel32.GetLastError()==183:
        other=ctypes.windll.user32.FindWindowW(None,common.TITLE)
        if other:
            ctypes.windll.user32.ShowWindow(other,9)
            ctypes.windll.user32.SetForegroundWindow(other)
        return
    root=tk.Tk();root.title(common.TITLE)
    root.geometry('870x780');root.minsize(810,750);root.configure(bg=BG)
    def callback_error(kind,value,trace):
        import traceback
        with (folder/'interface-error.log').open('a',encoding='utf8') as log:
            traceback.print_exception(kind,value,trace,file=log)
    root.report_callback_exception=callback_error
    try:root.iconbitmap(str(common.RESOURCE/'bedroom.ico'))
    except tk.TclError:pass
    root.option_add('*Font',(FONT,10))
    events=queue.Queue();devices=common.initial_devices(folder)
    for device in devices:device['reachable']=None
    state={'busy':False,'scanning':False,'closing':False,'worker':None,'status':{},'test':False,'repairing':False,'notice':''}

    def label(parent,text='',size=10,color=INK,bg=WHITE,bold=False,**kwargs):
        return tk.Label(parent,text=text,font=(FONT,size,'bold' if bold else 'normal'),
                        fg=color,bg=bg,**kwargs)
    def button(parent,text,fn,primary=False):
        return tk.Button(parent,text=text,command=fn,bg=BLUE if primary else WHITE,
            fg=WHITE if primary else INK,activebackground='#1854CE' if primary else '#EAF0FA',
            activeforeground=WHITE if primary else INK,relief='flat',bd=0,cursor='hand2',
            padx=22,pady=12,font=(FONT,10,'bold' if primary else 'normal'),
            disabledforeground='#9AA6B8',highlightthickness=1,
            highlightbackground=BLUE if primary else LINE)

    page=tk.Frame(root,bg=BG,padx=28,pady=22);page.pack(fill='both',expand=True)
    head=tk.Frame(page,bg=BG);head.pack(fill='x',pady=(0,20))
    mark=tk.Canvas(head,width=52,height=52,bg=BG,highlightthickness=0)
    mark.pack(side='left',padx=(0,13));mark.create_rectangle(2,2,50,50,fill=BLUE,outline=BLUE)
    for x in (17,34):
        mark.create_rectangle(x-4,12,x+4,39,outline=WHITE,width=2)
        mark.create_oval(x-2,27,x+2,31,fill=WHITE,outline=WHITE)
    title=tk.Frame(head,bg=BG);title.pack(side='left')
    label(title,'Bedroom Audio',21,bg=BG,bold=True).pack(anchor='w')
    label(title,'电脑声音，一起送到卧室',10,MUTED,BG).pack(anchor='w',pady=(3,0))
    badge=label(head,'●  未启动',10,MUTED,BG,bold=True);badge.pack(side='right')

    banner=tk.Frame(page,bg=WHITE,highlightbackground=LINE,highlightthickness=1,padx=22,pady=18)
    banner.pack(fill='x',pady=(0,16))
    banner_top=tk.Frame(banner,bg=WHITE);banner_top.pack(fill='x')
    big=label(banner_top,'准备连接你的 Bedroom',19,bold=True);big.pack(side='left')
    repair_btn=tk.Button(banner_top,text='修复网络许可',command=lambda:repair(),bg=WHITE,fg=BLUE,
        relief='flat',cursor='hand2',font=(FONT,9))
    repair_btn.pack(side='right',padx=(12,0))
    detail=label(banner,'正在检查音箱与立体声配对…',10,MUTED,wraplength=735,justify='left')
    detail.pack(anchor='w',pady=(8,0))

    row=tk.Frame(page,bg=BG);row.pack(fill='x')
    row.columnconfigure(0,weight=1);row.columnconfigure(1,weight=1)
    cards={}
    for number,(identity,name) in enumerate(common.KNOWN.items()):
        card=tk.Frame(row,bg=WHITE,highlightbackground=LINE,highlightthickness=1,padx=18,pady=15)
        card.grid(row=0,column=number,sticky='nsew',padx=(0,8) if number==0 else (8,0))
        top=tk.Frame(card,bg=WHITE);top.pack(fill='x')
        label(top,name,14,bold=True).pack(side='left')
        dot=label(top,'●',14,MUTED);dot.pack(side='right')
        role=label(card,'配对信息待检测',9,MUTED);role.pack(anchor='w',pady=(4,14))
        status=label(card,'待检测',12,MUTED,bold=True);status.pack(anchor='w')
        address=label(card,'—',9,MUTED);address.pack(anchor='w',pady=(6,0))
        note=label(card,'正在读取设备状态',9,MUTED,wraplength=325,justify='left')
        note.pack(anchor='w',pady=(6,0))
        cards[identity]=(dot,role,status,address,note)

    pair=label(page,'两台组成一个立体声对，启动一次即可一起播放。',9,MUTED,BG)
    pair.pack(anchor='w',pady=(12,16))
    audio=tk.Frame(page,bg=WHITE,highlightbackground=LINE,highlightthickness=1,padx=18,pady=14)
    audio.pack(fill='x')
    audio_top=tk.Frame(audio,bg=WHITE);audio_top.pack(fill='x')
    label(audio_top,'电脑声音',10,bold=True).pack(side='left')
    activity=label(audio_top,'等待启动',9,MUTED);activity.pack(side='right')
    meter=tk.Canvas(audio,height=7,bg='#EAF0F7',highlightthickness=0);meter.pack(fill='x',pady=(10,8))
    fill=meter.create_rectangle(0,0,0,7,fill=BLUE,outline='')
    capture=label(audio,'默认输出设备将在启动时读取',8,MUTED,wraplength=735,justify='left')
    capture.pack(anchor='w')

    volume_panel=tk.Frame(page,bg=WHITE,highlightbackground=LINE,highlightthickness=1,padx=18,pady=10)
    volume_panel.pack(fill='x',pady=(12,0))
    volume_top=tk.Frame(volume_panel,bg=WHITE);volume_top.pack(fill='x')
    label(volume_top,'HomePod 音箱音量',10,bold=True).pack(side='left')
    volume_text=label(volume_top,'35%',10,BLUE,bold=True);volume_text.pack(side='right')
    volume_row=tk.Frame(volume_panel,bg=WHITE);volume_row.pack(fill='x')
    preferences=common.read_json(folder/'settings.json',{})
    volume_var=tk.DoubleVar(value=common.volume_value(preferences.get('volume',35)))
    previous=common.volume_value(preferences.get('unmuted_volume',35)) or 35
    volume_state={'pending':None,'timer':None,'sync':False,'previous':previous,'sent_at':0,'error':''}
    def remember_volume(value):
        if value:volume_state['previous']=value
        prefs=common.read_json(folder/'settings.json',{})
        changed=prefs.get('volume')!=value or prefs.get('unmuted_volume')!=volume_state['previous']
        if changed:
            prefs.update(volume=value,unmuted_volume=volume_state['previous'])
            common.write_json(folder/'settings.json',prefs)
    def send_volume():
        volume_state['timer']=None
        value=int(round(volume_var.get()))
        remember_volume(value)
        request=str(time.time_ns());volume_state['pending']=request;volume_state['sent_at']=time.time()
        common.write_json(folder/'volume.json',{'request':request,'volume':value})
    def volume_change(*_):
        if volume_state['sync']:return
        volume_state.update(pending='editing',sent_at=time.time(),error='')
        volume_text.config(text=f'{int(round(volume_var.get()))}%')
        if not volume_state['timer']:volume_state['timer']=root.after(120,send_volume)
    def finish_volume_edit():
        if volume_state['timer']:
            root.after_cancel(volume_state['timer']);volume_state['timer']=None
        send_volume()
    def nudge_volume(amount):
        volume_var.set(max(0,min(100,round(volume_var.get())+amount)));finish_volume_edit()
    def small_button(text,command):
        return tk.Button(volume_row,text=text,command=command,bg='#EAF0FA',fg=BLUE,
            activebackground='#DAE6FC',relief='flat',cursor='hand2',width=3,pady=7,font=(FONT,10,'bold'))
    small_button('−5',lambda:nudge_volume(-5)).pack(side='left',padx=(0,8))
    scale=VolumeSlider(volume_row,volume_var,finish_volume_edit)
    scale.pack(side='left',fill='x',expand=True)
    small_button('+5',lambda:nudge_volume(5)).pack(side='left',padx=(8,12))
    percent_var=tk.StringVar(value=str(round(volume_var.get())))
    percent_entry=tk.Entry(volume_row,textvariable=percent_var,width=4,justify='center',
        relief='solid',bd=1,font=(FONT,11))
    percent_entry.pack(side='left',ipady=5)
    label(volume_row,'%',10,MUTED).pack(side='left',padx=(4,10))
    def enter_volume(_event=None):
        value=common.volume_value(percent_var.get(),round(volume_var.get()))
        percent_var.set(str(value));volume_var.set(value);finish_volume_edit()
        return 'break'
    percent_entry.bind('<Return>',enter_volume)
    percent_entry.bind('<FocusOut>',enter_volume)
    # Variable traces run synchronously, so receiver readback cannot create a new command.
    volume_var.trace_add('write',volume_change)
    def toggle_mute():
        current=int(round(volume_var.get()))
        if current:volume_state['previous']=current
        volume_var.set(0 if current else volume_state['previous']);finish_volume_edit()
    mute_btn=tk.Button(volume_row,text='静音',command=toggle_mute,bg=WHITE,fg=INK,
        relief='flat',cursor='hand2',padx=10,pady=2)
    mute_btn.pack(side='right')
    volume_note=label(volume_panel,'这是音箱本身的音量，与 Windows 音量分别控制。',8,MUTED)
    volume_note.pack(anchor='w')

    controls=tk.Frame(page,bg=BG);controls.pack(fill='x',pady=(20,0))
    def background(kind,fn):
        def job():
            try:events.put((kind,fn(),None))
            except Exception as error:events.put((kind,None,str(error)))
        threading.Thread(target=job,daemon=True).start()

    def begin():
        if state['busy'] or state['closing'] or state['repairing']:return
        state['notice']=''
        if volume_state['timer']:
            root.after_cancel(volume_state['timer']);send_volume()
        state['busy']=True;big.config(text='正在启动转发…')
        detail.config(text='连接立体声组主机，并准备电脑声音。')
        background('start',lambda:start(folder))

    def repair():
        if state['repairing'] or state['busy'] or state['closing']:return
        state['repairing']=True
        state['notice']='请在 Windows 管理员提示中确认，仅放行两台 HomePod 到本程序的 UDP。'
        def job():
            from network import repair_network
            stop(folder)
            return repair_network(folder)
        background('repair',job)

    def halt():
        if state['busy']:return
        state['busy']=True;big.config(text='正在停止…');detail.config(text='正在结束音频会话，请稍候。')
        background('stop',lambda:stop(folder))

    def test_sound():
        if state['test']:return
        state['test']=True
        def play():
            path=folder/'test-tone.wav';rate=44100;frames=bytearray()
            notes=[523.25,659.25,783.99,659.25]
            for n in range(rate*4):
                within=(n%rate)/rate
                env=max(0,min(1,within/.03,(.8-within)/.08)) if within<.8 else 0
                v=int(10000*env*math.sin(2*math.pi*notes[n//rate]*n/rate))
                frames.extend(struct.pack('<hh',v,v))
            with wave.open(str(path),'wb') as stream:
                stream.setparams((2,2,rate,0,'NONE','not compressed'));stream.writeframes(frames)
            winsound.PlaySound(str(path),winsound.SND_FILENAME)
        background('test',play)

    def rescan(force=True):
        if state['scanning'] or state['closing']:return
        state['scanning']=True;scan_btn.config(text='正在刷新…',state='disabled')
        background('scan',lambda:refresh(folder,force))

    start_btn=button(controls,'▶  启动转发',begin,True);start_btn.pack(side='left',padx=(0,12))
    stop_btn=button(controls,'■  停止',halt);stop_btn.pack(side='left',padx=(0,12))
    test_btn=button(controls,'播放测试音',test_sound);test_btn.pack(side='left')
    scan_btn=button(controls,'刷新设备',rescan);scan_btn.pack(side='right')
    foot=tk.Frame(page,bg=BG);foot.pack(fill='x',side='bottom',pady=(17,0))
    label(foot,'播放模式',9,MUTED,BG).pack(side='left',padx=(0,7))
    modes={'实时 · 100 ms':'realtime','兼容 · 150 ms':'compatible','均衡 · 500 ms':'low','稳定 · 1500 ms':'stable'}
    selected=mode_name(preferences.get('latency_mode'))
    mode_var=tk.StringVar(value=next(k for k,v in modes.items() if v==selected))
    mode_box=ttk.Combobox(foot,textvariable=mode_var,values=list(modes),state='readonly',width=21)
    mode_box.pack(side='left')
    def change_mode(_event=None):
        prefs=common.read_json(folder/'settings.json',{})
        prefs['latency_mode']=modes[mode_var.get()];common.write_json(folder/'settings.json',prefs)
        if common.current_worker(folder):
            state['busy']=True;state['notice']='正在应用播放模式，稍后恢复声音。'
            big.config(text='正在切换播放模式…')
            def restart():stop(folder);return start(folder)
            background('mode',restart)
    mode_box.bind('<<ComboboxSelected>>',change_mode)
    latency_note=label(foot,'切换自动重连',8,MUTED,BG);latency_note.pack(side='left',padx=8)
    logs=label(foot,'查看日志',9,BLUE,BG,cursor='hand2');logs.pack(side='right')
    def open_logs(_event=None):
        path=folder/'audio.log'
        if not path.exists():path.write_text('尚无运行日志。',encoding='utf8')
        os.startfile(str(path))
    logs.bind('<Button-1>',open_logs)

    def paint():
        status=common.read_json(folder/'status.json',{})
        process=common.current_worker(folder)
        current=common.display_state(status,bool(process))
        state['worker']=process;state['status']=status
        active=current=='streaming';running=bool(process)
        mode_box.config(state='disabled' if state['busy'] or state['repairing'] or state['closing'] else 'readonly')
        if active:
            if status.get('latency_protection'):
                latency_note.config(text=f"稳定保护：{status.get('scheduled_latency_ms',0):.0f} ms",fg=BLUE)
            else:
                latency_note.config(text=f"本机排队 {status.get('capture_queue_ms',0):.0f} ms",fg=MUTED)
        else:latency_note.config(text='切换自动重连')
        texts={
            'stopped':('转发已停止','点击启动，把电脑声音送到这对音箱。','未启动',MUTED),
            'connecting':('正在连接…','正在建立音频连接，请稍候。','连接中',BLUE),
            'streaming':('正在转发到卧室','立体声对已连接。电脑播放音乐或视频时，两台会一起播放。','正在转发',GREEN),
            'stopping':('正在停止…','正在结束播放会话。','停止中',MUTED),
            'reconnecting':('正在重新连接…',status.get('error','音箱暂时没有回应，正在重试。'),'重新连接',BLUE),
            'error':('转发未能继续',status.get('error','转发进程已退出，请重新启动。'),'连接异常',RED),
            'unresponsive':('转发状态未更新','程序长时间没有响应，请停止后重新启动。','状态异常',RED),
        }
        headline,description,tag,color=texts.get(current,texts['stopped'])
        if not state['busy']:
            if current=='connecting' and status.get('phase')=='audio_setup':
                description='正在等待 HomePod 时钟同步与音频通道确认。'
            big.config(text=headline);detail.config(text=state['notice'] or description,fg=RED if current=='error' else MUTED)
        badge.config(text='●  '+tag,fg=color)
        by_id={d['id']:d for d in devices}
        try:chosen=common.choose_leader(devices)['id']
        except RuntimeError:chosen=None
        chosen=status.get('target_id') if active else chosen
        for identity,parts in cards.items():
            dot,role,connection,address,note=parts;d=by_id.get(identity,{})
            online=d.get('reachable');leader=d.get('leader')
            address.config(text=d.get('address','地址待发现'))
            role.config(text='本次转发主机' if identity==chosen else ('立体声配对成员' if d.get('pair_id') else '配对信息待检测'))
            if online is None:
                text='待检测';info='正在读取设备状态';color2=MUTED
            elif not online:
                text='暂时无法连接';info='上次检测未收到设备回应';color2=RED
            elif active and identity==status.get('target_id'):
                text='已连接 · 正在转发';info='电脑声音从这里送入立体声对';color2=GREEN
            elif active and d.get('pair_id') and d.get('pair_id')==by_id.get(status.get('target_id'),{}).get('pair_id'):
                text='在线 · 配对成员';info='由组主机统一播放';color2=GREEN
            else:
                text='可连接';info='设备在线，等待转发' if not running else '设备在线，正在建立会话';color2=BLUE
            dot.config(fg=color2);connection.config(text=text,fg=color2);note.config(text=info)
        same=len(devices)==2 and devices[0].get('pair_id') and devices[0].get('pair_id')==devices[1].get('pair_id')
        pair.config(text='两台组成一个立体声对，启动一次即可一起播放。' if same else '正在核对两台音箱的立体声配对关系。')
        peak=status.get('peak',0) if active else 0
        level=min(1,max(0,(20*math.log10(max(1,peak)/32768)+60)/60)) if peak>2 else 0
        meter.coords(fill,0,0,meter.winfo_width()*level,7)
        activity.config(text='检测到电脑声音' if peak>15 else ('等待电脑播放声音' if active else '等待启动'),fg=GREEN if peak>15 else MUTED)
        capture.config(text='当前输出：'+status.get('capture_device','默认输出设备将在启动时读取'))
        pending=volume_state['pending']
        acknowledged=bool(pending and status.get('volume_request')==pending)
        if acknowledged:
            volume_state['error']=status.get('volume_error','')
            volume_state['pending']=None
        elif pending and pending!='editing' and time.time()-volume_state['sent_at']>8 and active:
            volume_state.update(pending=None,error='音箱尚未确认音量变化，请重试。')
        if active and not volume_state['pending'] and not scale.dragging and percent_entry.focus_get()!=percent_entry and status.get('remote_volume') is not None:
            actual=common.volume_value(status['remote_volume'])
            volume_state['sync']=True
            try:volume_var.set(actual)
            finally:volume_state['sync']=False
            remember_volume(actual)
        value=int(round(volume_var.get()))
        if percent_entry.focus_get()!=percent_entry:percent_var.set(str(value))
        suffix=' · 等待连接' if running and not active else (' · 应用中' if active and volume_state['pending'] else '')
        volume_text.config(text=f'{value}%'+suffix)
        mute_btn.config(text='取消静音' if value==0 else '静音')
        volume_error=volume_state['error']
        note_text=('音箱已静音。点击取消静音即可恢复。' if value==0 else '点击轨道或拖动调节，也可按 ±5，或输入百分比后回车。') if active else '此音量将在下次启动时应用。'
        if running and not active:note_text='音量已保存，连接成功后发送；当前尚未生效。'
        volume_note.config(text=volume_error or note_text,fg=RED if volume_error else MUTED)
        ready=chosen is not None
        start_btn.config(state='normal' if not running and ready and not state['busy'] and not state['repairing'] else 'disabled')
        repair_btn.config(state='disabled' if state['repairing'] or state['busy'] else 'normal',text='等待管理员确认…' if state['repairing'] else '修复网络许可')
        stop_btn.config(state='normal' if running and not state['busy'] else 'disabled')
        test_btn.config(state='normal' if active and not state['test'] and not state['busy'] else 'disabled')

    def poll():
        nonlocal devices
        try:
            while True:
                kind,result,error=events.get_nowait()
                if kind in {'start','stop','mode'}:
                    state['busy']=False
                    if kind=='mode':state['notice']=''
                    if error:
                        common.write_json(folder/'status.json',{'state':'error','time':time.time(),'error':error})
                    if state['closing']:
                        if kind in {'start','mode'}:
                            state['busy']=True
                            background('stop',lambda:stop(folder))
                        else:
                            root.destroy();return
                elif kind=='scan':
                    state['scanning']=False;scan_btn.config(text='刷新设备',state='normal')
                    if result is not None:devices=result
                    elif error:detail.config(text='刷新设备失败：'+error)
                elif kind=='test':state['test']=False
                elif kind=='repair':
                    state['repairing']=False
                    state['notice']='网络许可已更新，请点击启动转发。' if not error else error
                    if not error:rescan(True)
        except queue.Empty:pass
        paint();root.after(400,poll)

    def repeat_scan():
        if not state['closing']:
            rescan(False);root.after(15000,repeat_scan)

    def close():
        if state['closing']:return
        if volume_state['timer']:
            root.after_cancel(volume_state['timer']);send_volume()
        winsound.PlaySound(None,0)
        if state['worker'] or state['busy']:
            state['closing']=True
            (folder/'stop.request').write_text('closing',encoding='utf8')
            if not state['busy']:halt()
            big.config(text='正在停止并退出…')
        else:root.destroy()
    root.protocol('WM_DELETE_WINDOW',close)
    root.after(100,poll);root.after(200,repeat_scan)
    root.mainloop()
    ctypes.windll.kernel32.CloseHandle(mutex)

if __name__=='__main__':
    try:main()
    except Exception:
        import traceback
        error_folder=common.data_dir()
        (error_folder/'startup-error.log').write_text(traceback.format_exc(),encoding='utf8')
        raise
