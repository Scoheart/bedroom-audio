"""First-run receiver selection, also available in the frozen application."""
from __future__ import annotations
import asyncio
from datetime import datetime
import queue
import shutil
import threading
import common


def selection_config(first, second, preferred=''):
    """Persist only explicit selection; discovery metadata stays on this PC."""
    import re
    selected = []
    for record in (first, second):
        identity = common.normalize(record.get('id', ''))
        if not re.fullmatch(r'[0-9A-F]{12}', identity):
            raise ValueError('请选择有效的 HomePod。')
        selected.append({'id': identity, 'name': str(record.get('name', '')).strip() or 'HomePod'})
    if selected[0]['id'] == selected[1]['id']:
        raise ValueError('请分别选择两台不同的音箱。')
    a, b = first.get('pair_id'), second.get('pair_id')
    if a and b and a != b:
        raise ValueError('这两台音箱属于不同立体声组，请先在「家庭」App 中确认配对。')
    preferred = common.normalize(preferred)
    if preferred and preferred not in {d['id'] for d in selected}:
        preferred = ''
    return {'devices': selected, 'preferred_receiver': preferred}


def save_selection(folder, first, second, preferred=''):
    config = selection_config(first, second, preferred)
    path = folder/'config.json'
    if path.exists():
        backup = folder/('config.backup.' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.json')
        shutil.copy2(path, backup)
    common.write_json(path, config)
    return config


def run_setup(folder, notice=''):
    import tkinter as tk
    from tkinter import ttk
    root = tk.Tk()
    root.title('Bedroom Audio · 选择 HomePod')
    root.geometry('680x410'); root.minsize(640, 390)
    root.option_add('*Font', ('Microsoft YaHei UI', 10))
    try: root.iconbitmap(str(common.RESOURCE/'bedroom.ico'))
    except tk.TclError: pass
    frame = ttk.Frame(root, padding=24); frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='选择你的 HomePod 立体声对', font=('Microsoft YaHei UI', 16, 'bold')).pack(anchor='w')
    ttk.Label(frame, text='先在 Apple「家庭」App 中把两台 HomePod 配成一对，\n再从下面分别选择。保存后进入主界面，点击「启动转发」才会播放。',
              wraplength=610, justify='left').pack(anchor='w', pady=(10, 18))
    first = tk.StringVar(); second = tk.StringVar()
    boxes = []
    for label, value in (('第一台音箱', first), ('第二台音箱', second)):
        ttk.Label(frame, text=label).pack(anchor='w')
        box = ttk.Combobox(frame, textvariable=value, state='disabled', width=72)
        box.pack(fill='x', pady=(4, 12)); boxes.append(box)
    status = tk.StringVar(value=notice or '正在发现局域网音箱…')
    ttk.Label(frame, textvariable=status, wraplength=610, justify='left').pack(anchor='w', pady=(0, 10))
    controls = ttk.Frame(frame); controls.pack(fill='x', side='bottom')
    state = {'records': {}, 'saved': False, 'closed': False, 'busy': False}
    events = queue.Queue()
    old = common.read_json(folder/'config.json', {})
    if not isinstance(old, dict): old = {}
    old_ids = [common.normalize(d.get('id', '')) for d in old.get('devices', []) if isinstance(d, dict)] if isinstance(old.get('devices', []), list) else []

    def refresh():
        if state['busy']: return
        state['busy'] = True; status.set('正在扫描局域网，约需 5 秒…')
        scan.config(state='disabled'); save.config(state='disabled')
        for box in boxes: box.config(state='disabled')
        def work():
            try: events.put((asyncio.run(common.list_receivers()), None))
            except Exception as error: events.put(([], str(error)))
        threading.Thread(target=work, daemon=True).start()

    def confirm():
        a = state['records'].get(first.get()); b = state['records'].get(second.get())
        if not a or not b:
            status.set('请分别选择两台音箱。'); return
        try:
            save_selection(folder, a, b, old.get('preferred_receiver', ''))
        except (ValueError, OSError) as error:
            status.set(str(error)); return
        state['saved'] = True; close()

    def close():
        state['closed'] = True; root.destroy()

    def poll():
        if state['closed']: return
        try:
            records, error = events.get_nowait()
        except queue.Empty:
            root.after(100, poll); return
        state['busy'] = False; scan.config(state='normal')
        state['records'] = {f"{d['name']}  ·  {d['id']}": d for d in records}
        choices = list(state['records'])
        for position, (value, box) in enumerate(zip((first, second), boxes)):
            box.config(values=choices, state='readonly')
            selected = next((label for label, d in state['records'].items()
                             if position < len(old_ids) and d['id'] == old_ids[position]), '')
            value.set(selected)
        save.config(state='normal' if len(choices) >= 2 else 'disabled')
        status.set('发现失败：' + error if error else (
            '请选择两台已配对的音箱。设备选择仅保存在本机。' if len(choices) >= 2
            else '暂未发现两台音箱。请检查同一局域网、接收器权限和立体声配对后重新扫描。'))
        root.after(100, poll)

    scan = ttk.Button(controls, text='重新扫描', command=refresh); scan.pack(side='left')
    ttk.Button(controls, text='取消', command=close).pack(side='right')
    save = ttk.Button(controls, text='保存并继续', command=confirm, state='disabled')
    save.pack(side='right', padx=12)
    root.protocol('WM_DELETE_WINDOW', close)
    root.after(100, refresh); root.after(100, poll); root.mainloop()
    return state['saved']
