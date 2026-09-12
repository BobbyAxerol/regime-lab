#!/usr/bin/env python3
"""Restore audit evidence embedded in one Markdown. No imports from restored code."""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zlib

MAX_DOCUMENT = 64 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024
MAX_MEMBERS = 64
START = re.compile(r'^<!-- AUDIT_MEMBER_V1 (\{[^\n]+\}) -->$', re.MULTILINE)
END = '<!-- AUDIT_MEMBER_END_V1 -->'

def decode_document(document: Path) -> list[tuple[PurePosixPath, bytes]]:
    if document.stat().st_size > MAX_DOCUMENT:
        raise ValueError('Markdown exceeds the allowed input size')
    text = document.read_text(encoding='utf-8')
    matches = list(START.finditer(text))
    if not 1 <= len(matches) <= MAX_MEMBERS:
        raise ValueError('Unexpected embedded member count')
    result = []
    seen: set[str] = set()
    total = 0
    for match in matches:
        meta = json.loads(match.group(1))
        name = meta['path']
        if not isinstance(name, str) or '\\' in name or '\x00' in name:
            raise ValueError('Invalid member path')
        path = PurePosixPath(name)
        if (path.is_absolute() or not path.parts or
                any(part in ('', '.', '..') for part in name.split('/')) or
                name in seen or path.parts[0] != 'regime_lab_audit'):
            raise ValueError('Unsafe or duplicate member path')
        seen.add(name)
        expected = meta['bytes']
        if type(expected) is not int or not 0 <= expected <= MAX_TOTAL:
            raise ValueError('Invalid member size')
        total += expected
        if total > MAX_TOTAL:
            raise ValueError('Archive exceeds allowed total size')
        pos = match.end()
        if text[pos:pos + 1] != '\n':
            raise ValueError('Malformed member separator')
        pos += 1
        fence_end = text.find('\n', pos)
        if fence_end < 0:
            raise ValueError('Missing opening fence')
        opening = text[pos:fence_end]
        fence_match = re.fullmatch(r'(`{4,})(?:[a-zA-Z0-9_+.-]+)?', opening)
        if fence_match is None:
            raise ValueError('Invalid payload fence')
        fence = fence_match.group(1)
        payload_start = fence_end + 1
        closing = '\n' + fence + '\n' + END
        payload_end = text.find(closing, payload_start)
        if payload_end < 0:
            raise ValueError('Missing payload terminator')
        payload = text[payload_start:payload_end]
        encoding = meta['encoding']
        if encoding == 'utf8':
            data = payload.encode('utf-8')
        elif encoding == 'zlib+base64':
            compressed = base64.b64decode(''.join(payload.split()), validate=True)
            decoder = zlib.decompressobj()
            data = decoder.decompress(compressed, expected + 1)
            if (len(data) > expected or decoder.unconsumed_tail or
                    decoder.unused_data or not decoder.eof):
                raise ValueError('Invalid or excessive compressed payload')
        else:
            raise ValueError('Unsupported payload encoding')
        if len(data) != expected:
            raise ValueError(f'Size mismatch: {name}')
        if hashlib.sha256(data).hexdigest() != meta['sha256']:
            raise ValueError(f'SHA-256 mismatch: {name}')
        result.append((path, data))
    return result

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('markdown', type=Path)
    parser.add_argument('--out', required=True, type=Path,
                        help='A NEW output directory; existing paths are refused')
    args = parser.parse_args()
    source = args.markdown.resolve(strict=True)
    records = decode_document(source)  # All hashes checked BEFORE any output.
    output = args.out.absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f'Refusing existing output: {output}')
    output.parent.resolve(strict=True)
    output.mkdir(mode=0o700, exist_ok=False)
    root = output.resolve(strict=True)
    for relative, data in records:
        destination = root.joinpath(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.parent.resolve().is_relative_to(root):
            raise ValueError('Resolved output path escaped extraction root')
        with destination.open('xb') as handle:
            handle.write(data)
    print(json.dumps({'status': 'RESTORED_VERIFIED', 'members': len(records),
                      'bytes': sum(len(data) for _, data in records),
                      'output': str(root), 'executed_restored_code': False},
                     ensure_ascii=False))

if __name__ == '__main__':
    main()
