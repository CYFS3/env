"""Format changed C/C++ files with clang-format 22.1.8."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from env_paths import get_env_root


CLANG_FORMAT_VERSION = '22.1.8'
EXTENSIONS = {'.c', '.h', '.cc', '.hh', '.cpp', '.hpp', '.cxx', '.hxx', '.c++', '.h++', '.inl', '.ipp', '.tpp'}
DIFF_OPTIONS = ['--name-only', '-z', '--diff-filter=ACMR', '--no-ext-diff', '--ignore-submodules=all']


class CommandError(Exception):
    pass


def git(*args, cwd=None):
    result = subprocess.run(['git', *args], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise CommandError(result.stderr.decode('utf-8', errors='replace').strip())
    return result.stdout


def filenames(data):
    return {os.fsdecode(name) for name in data.split(b'\0') if name}


def changed_files(root, base):
    symlinks = set()
    for entry in git('ls-files', '--stage', '-z', cwd=root).split(b'\0'):
        if not entry:
            continue
        metadata, _, name = entry.partition(b'\t')
        mode, _, stage = metadata.split()
        if stage != b'0':
            raise CommandError('Resolve merge conflicts before running format-changed.')
        if mode == b'120000':
            symlinks.add(os.fsdecode(name))

    names = filenames(git('diff', *DIFF_OPTIONS, '--', cwd=root))
    names.update(filenames(git('diff', '--cached', *DIFF_OPTIONS, '--', cwd=root)))
    names.update(filenames(git('ls-files', '--others', '--exclude-standard', '-z', cwd=root)))

    if base:
        revision = git('rev-parse', '--verify', '--end-of-options', base + '^{commit}', cwd=root).strip().decode('ascii')
        ancestor = git('merge-base', 'HEAD', revision, cwd=root).strip().decode('ascii')
        names.update(filenames(git('diff', *DIFF_OPTIONS, ancestor, 'HEAD', '--', cwd=root)))

    selected = []
    for name in sorted(names - symlinks):
        path = root / name
        if path.suffix.lower() not in EXTENSIONS or not path.is_file() or path.is_symlink():
            continue
        try:
            path.resolve().relative_to(root)
        except ValueError:
            continue
        selected.append(path)
    return selected


def has_project_style(path, root):
    directory = path.parent
    while True:
        if any((directory / name).is_file() for name in ('.clang-format', '_clang-format')):
            return True
        if directory == root:
            return False
        directory = directory.parent


def find_clang_format():
    executable = 'clang-format.exe' if os.name == 'nt' else 'clang-format'
    bundled = Path(get_env_root()) / 'tools' / 'bin' / executable
    command = str(bundled) if bundled.is_file() else shutil.which('clang-format')
    if not command:
        raise CommandError('clang-format 22.1.8 was not found. Install it and add it to PATH, or use Env for Windows with it bundled.')
    result = subprocess.run([command, '--version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    version = result.stdout.decode('utf-8', errors='replace').strip()
    match = re.search(r'\bversion\s+(\d+\.\d+\.\d+)\b', version)
    if result.returncode or not match or match.group(1) != CLANG_FORMAT_VERSION:
        raise CommandError('clang-format 22.1.8 is required; %s reported: %s' % (command, version or 'unknown version'))
    return command


def cmd(args):
    try:
        root = Path(os.fsdecode(git('rev-parse', '--show-toplevel').rstrip(b'\r\n'))).resolve()
        files = changed_files(root, args.base)
        if not files:
            print('No changed C/C++ files to process.')
            return 0

        missing = [path.relative_to(root).as_posix() for path in files if not has_project_style(path, root)]
        if missing:
            raise CommandError(
                'No .clang-format or _clang-format found inside the repository for:\n  '
                + '\n  '.join(missing)
                + "\nAdd the project's formatting configuration and run again. No files were formatted."
            )

        clang_format = find_clang_format()
        options = ['--style=file', '--fallback-style=none', '--Werror']
        options += ['--dry-run'] if args.check else ['-i']
        action = 'Checking' if args.check else 'Formatting'
        print('Selected %d changed C/C++ file(s).' % len(files), flush=True)
        failed = False
        for path in files:
            print('%s: %s' % (action, path.relative_to(root).as_posix()), flush=True)
            result = subprocess.run([clang_format, *options, str(path)], cwd=root)
            if result.returncode:
                failed = True
                if not args.check:
                    return result.returncode if result.returncode > 0 else 1
        if failed:
            return 1
        if args.check:
            print('Formatting check passed.')
        else:
            print('Done. Review git diff and git add the files you want to commit.')
        return 0
    except (CommandError, OSError) as error:
        print('Error: %s' % error, file=sys.stderr)
        return 1


def add_parser(sub):
    parser = sub.add_parser(
        'format-changed',
        help=__doc__,
        description=(
            'Format whole changed C/C++ files with clang-format 22.1.8. '
            'Includes unstaged, staged and untracked files; leaves the Git index unchanged.'
        ),
    )
    parser.add_argument('--base', metavar='REF', help='also include committed changes since the merge base of HEAD and REF')
    parser.add_argument('--check', action='store_true', help='check formatting without modifying files (nonzero exit on violations)')
    parser.set_defaults(func=cmd)
