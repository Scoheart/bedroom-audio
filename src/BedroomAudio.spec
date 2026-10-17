# Run with the pinned dependencies installed in the active virtual environment.
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_all

source=Path(SPECPATH)
datas=[(str(source/'bedroom.ico'),'.'),
       (str(source/'Repair-HomePod-Network.ps1'),'.')]
binaries=[]
hiddenimports=['_miniaudio','_cffi_backend']
for package in ('pyatv','av','pyaudiowpatch','miniaudio','pycaw','comtypes'):
    found_data,found_binaries,found_imports=collect_all(package,include_py_files=False,
        filter_submodules=lambda name: not any(part in {'test','tests','__main__'} for part in name.split('.')),
        exclude_datas=['**/test/**','**/tests/**','**/__pycache__/**'])
    datas+=found_data;binaries+=found_binaries;hiddenimports+=found_imports

a=Analysis([str(source/'app.py')],pathex=[str(source)],
    binaries=binaries,datas=datas,hiddenimports=hiddenimports,
    excludes=['numpy','pytest','IPython'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='BedroomAudio',
    debug=False,bootloader_ignore_signals=False,strip=False,upx=False,
    console=False,icon=str(source/'bedroom.ico'))
collection=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='BedroomAudio')
