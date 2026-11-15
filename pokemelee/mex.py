"""Small checked adapter to the pinned MexCLI; no Nucleus application state."""
import json
from pathlib import Path
import subprocess


def parse_result(text):
    decoder = json.JSONDecoder()
    for offset, char in enumerate(text):
        if char != '{':
            continue
        try:
            value, end = decoder.raw_decode(text, offset)
        except ValueError:
            continue
        if isinstance(value, dict) and not text[end:].strip():
            return value
    raise ValueError('MexCLI returned no final JSON result')


def check_result(value):
    if isinstance(value, dict):
        if value.get('success') is False or value.get('totalFailed', 0) or value.get('error'):
            raise ValueError('MexCLI failed: ' + json.dumps(value)[:1000])
        for child in value.values():
            check_result(child)
    elif isinstance(value, list):
        for child in value:
            check_result(child)
    return value


class Mex:
    def __init__(self, runtime, project, logs=None):
        self.cli = Path(runtime).resolve() / 'mex/win-x64/MexCLI.exe'
        self.project = Path(project).resolve()
        self.root = self.project.parent
        self.logs = Path(logs or self.root / 'builder-logs')
        self.logs.mkdir(parents=True, exist_ok=True)
        self.sequence = 0

    def command(self, command, *args, stdin=None, timeout=900, project=True):
        self.sequence += 1
        result = subprocess.run([str(self.cli), command, *([str(self.project)] if project else []),
                                 *map(str, args)], input=stdin, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=timeout)
        log = self.logs / f'{self.sequence:03d}-{command}.log'
        log.write_text(result.stdout + '\n' + result.stderr, encoding='utf-8')
        if result.returncode:
            raise ValueError(f'MexCLI {command} exited {result.returncode}; see {log}')
        return check_result(parse_result(result.stdout))

    def batch(self, command, manifest):
        file = self.logs / f'{self.sequence + 1:03d}-{command}.json'
        file.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        return self.command(command, file)

    def fighters(self):
        record = json.loads(self.project.read_text(encoding='utf-8-sig'))
        return [(self.root / 'data/fighters' / name,
                 json.loads((self.root / 'data/fighters' / name).read_text(encoding='utf-8-sig')))
                for name in record['fighterSaveMap']['filePaths']]

    def get_css_layout(self):
        return self.command('get-css-layout')

    def set_css_layout(self, value):
        return self.command('set-css-layout', stdin=value)

    def get_sss_layout(self):
        return self.command('get-sss-layout')

    def set_sss_layout(self, value):
        return self.command('set-sss-layout', stdin=value)
