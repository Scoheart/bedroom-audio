"""Build a portable Windows folder from a regular virtual environment."""
from pathlib import Path
import shutil
import PyInstaller.__main__

def main():
    source = Path(__file__).resolve().parent
    root = source.parent
    PyInstaller.__main__.run([
        str(source/'BedroomAudio.spec'), '--noconfirm',
        '--distpath', str(root/'dist'), '--workpath', str(root/'build')])
    output = root/'dist/BedroomAudio'
    for name in ('README.md', 'THIRD_PARTY_NOTICES.md'):
        shutil.copy2(root/name, output/name)
    shutil.copy2(root/'examples/config.example.json', output/'config.example.json')
    shutil.make_archive(str(root/'dist/BedroomAudio-portable'), 'zip',
                        root/'dist', 'BedroomAudio')
    print(output)

if __name__ == '__main__':
    main()
