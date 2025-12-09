#!/usr/bin/env python3
import re
import hashlib
import shutil
import subprocess
import json
from pathlib import Path

import click

def tree_size(path):
    return sum(entry.stat().st_size for entry in path.glob('**/*') if entry.is_file())

@click.command()
@click.option('--major', 'increment', flag_value='major')
@click.option('--minor', 'increment', flag_value='minor', default=True)
@click.option('--patch', 'increment', flag_value='patch', default=True)
@click.option('--dry-run', is_flag=True)
@click.argument('version', required=False)
def do_release(version, increment, dry_run):
    if not version:
        tag = subprocess.run('git describe --tags --abbrev=0 --match v*'.split(),
                             check=True, capture_output=True, text=True)
        major, minor, patch = map(int, re.fullmatch(r'v([0-9]+)\.([0-9]+)\.([0-9]+)', tag.stdout.strip()).groups())
        match increment:
            case 'major':
                major, minor, patch = (major+1, 0, 0)
            case 'minor':
                major, minor, patch = (major, minor+1, 0)
            case 'patch':
                major, minor, patch = (major, minor, patch+1)
        version = f'{major}.{minor}.{patch}'
    
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

    if pkg_dir.is_dir():
        shutil.rmtree(pkg_dir)

    shutil.copytree(plugin_sources, pkg_dir)
    shutil.copy(project_root / 'LICENSE', pkg_dir)

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

    res = subprocess.run(['uv', 'export', '--no-hashes', '--format', 'requirements-txt'],
                   check=True, capture_output=True, text=True)
    (pkg_dir / 'requirements.txt').write_text(res.stdout)

    shutil.copytree(project_root / 'src' / 'kicoil', pkg_dir / 'kicoil')

    zip_fn = Path(shutil.make_archive(f'{pkg_dir.name}-v{version}', 'zip', pkg_dir, '.'))
    if not dry_run:
        print(f'Adding new release zip {zip_fn} to git index.')
        subprocess.run(['git', 'add', str(zip_fn)], check=True, capture_output=True)

    # Add the zip's metadata to the metadata for the repository
    ver_dict['download_sha256'] = hashlib.sha256(zip_fn.read_bytes()).hexdigest()
    ver_dict['download_size'] = zip_fn.stat().st_size
    ver_dict['download_url'] = f'https://git.jaseg.de/kimesh.git/plain/{zip_fn.name}?h=v{version}'
    ver_dict['install_size'] = tree_size(pkg_dir)

    meta_file = json.loads(meta_path.read_text())
    meta_file['versions'].append(ver_dict)
    meta_path.write_text(json.dumps(meta_file, indent=4))

    if not dry_run:
        print(f'Adding updated metadata file {meta_path} to git index')
        subprocess.run(['git', 'add', str(meta_path)], check=True, capture_output=True)

    if not dry_run:
        print('Create git commit')
        subprocess.run(['git', 'commit', '-m', f'Version {version}', '--no-edit'], check=True, capture_output=True)
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
