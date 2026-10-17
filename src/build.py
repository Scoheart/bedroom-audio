"""Build a portable Windows folder from a regular virtual environment."""
from pathlib import Path
import shutil
import hashlib
import importlib.metadata as metadata
import json
import sys
import PyInstaller.__main__
from version import VERSION


def collect_licenses(root, output):
    destination = output/'LICENSES'
    destination.mkdir(exist_ok=True)
    packages = []
    for line in (root/'requirements-lock.txt').read_text(encoding='utf8').splitlines():
        if not line or line.startswith('#'):continue
        name, expected = line.split('==')
        dist = metadata.distribution(name)
        if dist.version != expected:raise RuntimeError(f'{name}: expected {expected}, got {dist.version}')
        package = destination/f'{name}-{dist.version}'
        package.mkdir(exist_ok=True)
        # Include original notices from every pinned wheel, including build tools.
        for file in dist.files or []:
            parts = file.parts
            basename = file.name.lower()
            if (('licenses' in parts and file.suffix not in ('.pyc', '.py')) or
                    basename.startswith(('license', 'copying', 'notice', 'copyright'))):
                source = Path(dist.locate_file(file))
                if source.is_file():
                    relative = Path(*parts[parts.index('licenses')+1:]) if 'licenses' in parts else Path(file.name)
                    target = package/relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
        info = {field: dist.metadata.get_all(field, []) for field in
                ('Name', 'Version', 'License', 'License-Expression', 'Home-page', 'Project-URL', 'Author', 'Author-email')}
        (package/'METADATA.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf8')
        packages.append({'name': name, 'version': dist.version})
    shutil.copy2(Path(sys.base_prefix)/'LICENSE.txt', destination/'Python-LICENSE.txt')
    shutil.copy2(Path(sys.base_prefix)/'tcl/tk8.6/license.terms', destination/'Tk-license.terms')
    shutil.copytree(root/'third_party', destination/'native', dirs_exist_ok=True)
    return packages

def main():
    source = Path(__file__).resolve().parent
    root = source.parent
    PyInstaller.__main__.run([
        str(source/'BedroomAudio.spec'), '--noconfirm',
        '--distpath', str(root/'dist'), '--workpath', str(root/'build')])
    output = root/'dist/BedroomAudio'
    for name in ('README.md', 'THIRD_PARTY_NOTICES.md', 'THIRD_PARTY_SOURCES.md', 'requirements-lock.txt'):
        shutil.copy2(root/name, output/name)
    shutil.copytree(root/'docs', output/'docs', dirs_exist_ok=True)
    shutil.copy2(root/'examples/config.example.json', output/'config.example.json')
    shutil.copy2(root/'docs/portable-quickstart.txt', output/'START-HERE.txt')
    (output/'Configure-HomePods.cmd').write_text('@echo off\r\nstart "" "%~dp0BedroomAudio.exe" --configure\r\n', encoding='ascii', newline='')
    packages=collect_licenses(root, output)
    (output/'release-info.json').write_text(json.dumps({
        'application':'Bedroom Audio','version':VERSION,'platform':'windows-x64',
        'python':sys.version.split()[0],'dependencies':packages},indent=2),encoding='utf8')
    archive = f'BedroomAudio-{VERSION}-windows-x64-portable'
    archive_path = Path(shutil.make_archive(str(root/'dist'/archive), 'zip',
                        root/'dist', 'BedroomAudio'))
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    (root/'dist'/f'{archive}.sha256').write_text(digest+'  '+archive_path.name+'\n', encoding='ascii')
    print(output)

if __name__ == '__main__':
    main()
