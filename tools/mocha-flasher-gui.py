#!/usr/bin/env python3
"""Native Windows front end for flash-distribution.py."""
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
import importlib
import os
import shutil
import sys
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

installer = importlib.import_module('flash-distribution')
MIB = 1024 ** 2
STAGES = {
    'verify': (1, '校验镜像', '正在检查安装包内的文件和 SHA-256。'),
    'ram': (2, '启动维护环境', '保持 USB 连接。若 Windows 将新设备识别为 Android ADB Interface，请在设备管理器改为 Android Bootloader Interface。'),
    'backup': (3, '备份设备数据', '正在备份引导、分区表和 Wi-Fi 校准数据。'),
    'prepare': (4, '准备分区', '正在清除 APP、UDA 和 cache，并将 APP 设置为 3 GiB。'),
    'app': (5, '写入并校验系统', '正在向平板传输系统镜像。'),
    'data': (6, '恢复桌面数据', '正在恢复桌面资源并同步到存储。'),
    'lnx': (7, '写入并校验引导', '正在恢复 Wi-Fi 校准数据并校验引导分区。'),
    'cuda': (8, '设置 CUDA 自检权限', '正在检查自检程序的执行权限。'),
    'poweroff': (9, '发出关机指令', '写入及校验通过，安装器正在请求平板完全关机。'),
}


class Output:
    def __init__(self, events):
        self.events = events
        self.local = threading.local()

    def write(self, value):
        pending = getattr(self.local, 'pending', '') + value
        lines = pending.split('\n')
        self.local.pending = lines.pop()
        for line in lines:
            self.events.put(('line', line.rstrip('\r')))
        return len(value)

    def flush(self):
        pending = getattr(self.local, 'pending', '')
        if pending:
            self.events.put(('line', pending))
            self.local.pending = ''


class App:
    def __init__(self, root):
        self.root = root
        self.events = Queue()
        self.busy = False
        self.log_file = None
        self.report_dir = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'Mocha Flasher'
        self.report_dir.mkdir(parents=True, exist_ok=True)
        here = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent
        image = next((p for p in (here/'image', here.parent/'image') if (p/'bundle.json').is_file()), None)
        self.image = tk.StringVar(value=str(image) if image else '')
        self.status = tk.StringVar(value='等待选择镜像和检查设备')
        self.hint = tk.StringVar(value='备份个人文件。平板关机后按电源＋音量减进入原厂 Fastboot，再用数据线连接电脑。')
        self.detail = tk.StringVar()

        root.title('Mocha 刷机工具')
        root.geometry('800x590')
        root.minsize(650, 500)
        root.protocol('WM_DELETE_WINDOW', self.close)
        frame = ttk.Frame(root, padding=16)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Mocha 刷机工具', font=('Microsoft YaHei UI', 16, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='Xiaomi Mocha · Debian · Windows').pack(anchor='w', pady=(2, 12))

        file_row = ttk.Frame(frame)
        file_row.pack(fill='x')
        ttk.Label(file_row, text='镜像目录').pack(side='left', padx=(0, 8))
        self.entry = ttk.Entry(file_row, textvariable=self.image)
        self.entry.pack(side='left', expand=True, fill='x')
        self.browse = ttk.Button(file_row, text='浏览…', command=self.select)
        self.browse.pack(side='left', padx=(8, 0))

        actions = ttk.Frame(frame)
        actions.pack(fill='x', pady=(12, 0))
        self.check = ttk.Button(actions, text='检查连接和镜像', command=lambda: self.start(False))
        self.check.pack(side='left')
        self.install = ttk.Button(actions, text='开始刷写', command=lambda: self.start(True))
        self.install.pack(side='left', padx=8)
        ttk.Button(actions, text='打开日志目录', command=self.open_logs).pack(side='right')
        ttk.Label(frame, text='刷写会清除 APP、UDA 和 cache 中的所有数据。', foreground='#a12a20').pack(anchor='w', pady=(8, 10))

        progress = ttk.LabelFrame(frame, text='安装进度', padding=10)
        progress.pack(fill='x')
        ttk.Label(progress, textvariable=self.status, font=('Microsoft YaHei UI', 10, 'bold')).pack(anchor='w')
        hint = ttk.Label(progress, textvariable=self.hint, wraplength=700)
        hint.pack(fill='x', pady=(3, 6))
        progress.bind('<Configure>', lambda event: hint.configure(wraplength=max(100, event.width-24)))
        self.bar = ttk.Progressbar(progress, maximum=100)
        self.bar.pack(fill='x')
        ttk.Label(progress, textvariable=self.detail).pack(anchor='w', pady=(4, 0))

        log = ttk.LabelFrame(frame, text='日志', padding=6)
        log.pack(fill='both', expand=True, pady=(12, 0))
        scroll = ttk.Scrollbar(log)
        scroll.pack(side='right', fill='y')
        self.log = tk.Text(log, wrap='word', height=8, font=('Consolas', 10),
                           state='disabled', yscrollcommand=scroll.set)
        self.log.pack(fill='both', expand=True)
        scroll.configure(command=self.log.yview)
        root.after(100, self.drain)

    def select(self):
        folder = filedialog.askdirectory(title='选择解压后包含 bundle.json 的 image 目录')
        if folder:
            self.image.set(folder)

    def open_logs(self):
        os.startfile(self.report_dir)

    def close(self):
        if self.busy:
            messagebox.showinfo('操作进行中', '请等待当前操作结束。刷写期间请保持 USB 连接。')
        else:
            self.root.destroy()

    def start(self, write):
        image = Path(self.image.get().strip())
        if (image/'image'/'bundle.json').is_file():
            image /= 'image'
        if not (image/'bundle.json').is_file():
            messagebox.showerror('找不到镜像', '请先完整解压镜像包，然后选择包含 bundle.json 的 image 目录。')
            return
        if write and not messagebox.askokcancel('确认清除数据', '这会清除平板 APP、UDA 和 cache。确认已备份个人文件，并准备开始刷写。', default='cancel'):
            return
        self.image.set(str(image))
        self.busy = True
        self.bar.configure(value=0)
        self.detail.set('')
        for control in (self.entry, self.browse, self.check, self.install):
            control.state(['disabled'])
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        self.log_file = self.report_dir / f'{timestamp}.log'
        backup = self.report_dir / 'backups' / timestamp
        self.append(f'日志文件：{self.log_file}')
        threading.Thread(target=self.run, args=(image, write, backup), daemon=True).start()

    def run(self, image, write, backup):
        output = Output(self.events)
        with redirect_stdout(output), redirect_stderr(output):
            try:
                embedded = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))/'platform-tools'/'fastboot.exe'
                fastboot = str(embedded) if embedded.is_file() else shutil.which('fastboot')
                for name in ('ssh', 'ssh-keygen'):
                    if not shutil.which(name):
                        raise RuntimeError('未找到 Windows OpenSSH 客户端工具 ' + name)
                if not fastboot:
                    raise RuntimeError('未找到 fastboot')
                if not write:
                    from windows_usb import repair_usb
                    rows = installer.output([fastboot, 'devices'], timeout=8).strip().splitlines()
                    if not rows:
                        repair_usb('fastboot')
                        rows = installer.output([fastboot, 'devices'], timeout=8).strip().splitlines()
                    if len(rows) != 1:
                        raise RuntimeError('请只连接一台处于原厂或 RAM Fastboot 的小米平板 1。')
                    product = installer.output([fastboot, '-s', rows[0].split()[0], 'getvar', 'product'], timeout=10)
                    if 'mocha' not in product.lower():
                        raise RuntimeError('当前设备型号无法确认为 Mocha。')
                    print('已通过 Fastboot 识别 Mocha。')
                args = [str(image), '--allow-candidate', '--fastboot', fastboot]
                if write:
                    print('备份目录：'+str(backup))
                    args += ['--install', '--erase', 'APP_UDA', '--backup', str(backup)]
                installer.main(args)
            except (Exception, SystemExit):
                traceback.print_exc()
                self.events.put(('done', (False, write)))
            else:
                self.events.put(('done', (True, write)))

    def append(self, line):
        if self.log_file:
            with self.log_file.open('a', encoding='utf-8') as log:
                print(line, file=log)
        self.log.configure(state='normal')
        self.log.insert('end', line+'\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def drain(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'line':
                    if value.startswith('MOCHA_STAGE '):
                        number, title, hint = STAGES[value.split()[1]]
                        self.status.set(f'{number} / 9  {title}')
                        self.hint.set(hint)
                        self.detail.set('')
                        self.bar.configure(value=(number-1)*100/9)
                        self.append(title)
                    elif value.startswith('MOCHA_PROGRESS '):
                        _, phase, count = value.split()
                        count = min(int(count), 3072*MIB)
                        fraction = count/(3072*MIB)
                        label = '回读校验' if phase == 'readback' else '写入系统'
                        self.detail.set(f'{label}  {count/MIB:.0f} / 3072 MiB  ({fraction:.0%})')
                        self.bar.configure(value=(4+((phase == 'readback')+fraction)/2)*100/9)
                    elif value:
                        self.append(value)
                else:
                    self.finish(*value)
        except Empty:
            pass
        self.root.after(150, self.drain)

    def finish(self, success, write):
        self.busy = False
        for control in (self.entry, self.browse, self.check, self.install):
            control.state(['!disabled'])
        if success:
            self.bar.configure(value=100)
            self.status.set('刷写和回读校验完成' if write else '连接和镜像检查通过')
            self.hint.set('已发出关机指令。等平板关机后，拔掉 USB，再按电源键正常开机。默认账户和密码均为 mocha。' if write else '备份个人文件后，点击「开始刷写」。')
        else:
            self.status.set('操作未完成')
            self.hint.set('请看下方最后几行日志。若已开始写入，保持 USB 连接，以便从当前阶段恢复。' if write else '检查 Fastboot 驱动、数据线和镜像目录，再试一次。')


if __name__ == '__main__':
    window = tk.Tk()
    App(window)
    window.mainloop()
