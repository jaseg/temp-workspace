#!/usr/bin/env python3
import re
import hashlib
import tomllib
import shutil
import subprocess
import json
from pathlib import Path

import click

def tree_size(path):
    return sum(entry.stat().st_size for entry in path.glob('**/*') if entry.is_file())

@click.command()
@click.option('--dry-run', is_flag=True)
def do_release(dry_run):
    with open('pyproject.toml', 'rb') as f:
        project_file = tomllib.load(f)
        version = project_file['project']['version']
    
    if not dry_run:
        res = subprocess.run('git status --porcelain --untracked-files=no'.split(),
                       check=True, capture_output=True, text=True)
        if res.stdout.strip():
            raise click.ClickException('There are uncommitted changes in this repository.')

    project_root = Path(__file__).parent

    res = subprocess.run('git ls-files'.split(), check=True, capture_output=True, text=True)
    for path in res.stdout.splitlines():
        if re.fullmatch(r'de\.jaseg\.kicoil\.[^/]*-v[.0-9]*\.zip', path.strip()):
            print(f'Removing old release zip {path} from git index.')
            subprocess.run(['git', 'rm', path], check=True, capture_output=True)

    plugin_sources = project_root / 'kicad-plugin'
    pkg_dir = project_root / 'de.jaseg.kicoil'
    plugin_dir = pkg_dir / 'plugins'

    if pkg_dir.is_dir():
        shutil.rmtree(pkg_dir)
    pkg_dir.mkdir()

    shutil.copytree(plugin_sources, plugin_dir)
    shutil.copy(project_root / 'LICENSE', plugin_dir)

    meta_path = project_root / 'metadata.json'
    print(f'Updating metadata file {meta_path}')
    ver_dict = {
        'version': version,
        'status': 'stable',
        'kicad_version': '9.00',
    }

    meta_file = json.loads(meta_path.read_text())
    meta_file['versions'] = [ver_dict]
    (pkg_dir / 'metadata.json').write_text(json.dumps(meta_file, indent=4))

    res = subprocess.run(['uv', 'export', '--no-hashes', '--no-emit-project', '--format', 'requirements.txt', '--group', 'gui'],
                   check=True, capture_output=True, text=True)
    (plugin_dir / 'requirements.txt').write_text(res.stdout)

    (pkg_dir / 'resources').mkdir()
    shutil.copy(plugin_sources / 'icon-light.png', pkg_dir / 'resources' / 'icon.png')

    module_sources = project_root / 'src'
    for root, dirs, files in module_sources.walk(top_down=True):
        if root.name == '__pycache__':
            continue

        for path in dirs:
            if path == '__pycache__':
                continue

            path = root / path
            subdir = plugin_dir / path.relative_to(module_sources)
            subdir.mkdir()

        for path in files:
            path = root / path
            out_path = plugin_dir / path.relative_to(module_sources)
            if path.name == '__init__.py':
                content = path.read_text()
                lines = content.splitlines()
                lines_out = []
                for line in lines:
                    if line.startswith('__version__ = version('):
                        line = f'__version__ = {version!r}'
                    lines_out.append(line)
                content = '\n'.join(lines_out).encode('utf-8')
            else:
                content = path.read_bytes()
            out_path.write_bytes(content)

    zip_fn = Path(shutil.make_archive(f'{pkg_dir.name}-v{version}', 'zip', pkg_dir, '.'))
    if not dry_run:
        print(f'Adding new release zip {zip_fn} to git index.')
        subprocess.run(['git', 'add', str(zip_fn)], check=True, capture_output=True)

    # Add the zip's metadata to the metadata for the repository
    ver_dict['download_sha256'] = hashlib.sha256(zip_fn.read_bytes()).hexdigest()
    ver_dict['download_size'] = zip_fn.stat().st_size
    ver_dict['download_url'] = f'https://git.jaseg.de/kimesh.git/plain/{zip_fn.name}?h=v{version}'
    ver_dict['install_size'] = tree_size(pkg_dir)

    if not dry_run:
        meta_file = json.loads(meta_path.read_text())
        meta_file['versions'].append(ver_dict)
        meta_path.write_text(json.dumps(meta_file, indent=4))

        print(f'Adding updated metadata file {meta_path} to git index')
        subprocess.run(['git', 'add', str(meta_path)], check=True, capture_output=True)

    if not dry_run:
        print('Create git commit')
        subprocess.run(['git', 'commit', '-m', f'KiCad package version {version}', '--no-edit'], check=True, capture_output=True)
        res = subprocess.run('git rev-parse --short HEAD'.split(), check=True, capture_output=True, text=True)
        print(f'Created commit {res.stdout.strip()}')
        print(f'Creating and signing version tag v{version}')
        subprocess.run(['git',
                        '-c', 'user.signingkey=E36F75307F0A0EC2D145FF5CED7A208EEEC76F2D',
                        '-c', 'user.email=python-mpv@jaseg.de',
                        'tag', '-s', f'v{version}', '-m', f'Version v{version}'],
                       check=True)

if __name__ == '__main__':
    do_release()
