"""Portable project snapshot. Standard library only; Python 3.12+ for restore."""
import argparse, hashlib, json, os, shutil, tarfile, tempfile
from pathlib import Path

SKIP = {'.git', '.venv', 'node_modules', '__pycache__', '.pytest_cache', '.DS_Store'}

def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()

class Parts:
    def __init__(self, folder):
        self.folder, self.f, self.n, self.size = folder, None, 0, 0
    def write(self, data):
        total = len(data)
        while data:
            if self.f is None or self.size == 1024**3:
                if self.f: self.f.close()
                self.n += 1; self.size = 0
                self.f = open(self.folder / f'babel-snapshot.tar.part{self.n:03}', 'xb')
            b = data[:1024**3-self.size]
            self.f.write(b); self.size += len(b); data = data[len(b):]
        return total
    def close(self):
        if self.f: self.f.close()

def pack(root, folder):
    root, folder = root.resolve(), folder.resolve()
    if folder.is_relative_to(root): raise ValueError('Archive destination must be outside source')
    folder.mkdir(parents=True, exist_ok=False)
    entries, excluded = [], []
    for base, dirs, files in os.walk(root, followlinks=False):
        dirs.sort(); files.sort()
        for name in list(dirs):
            p = Path(base)/name
            if name in SKIP or name.endswith('.egg-info'):
                excluded.append(str(p.relative_to(root))); dirs.remove(name)
            elif p.is_symlink(): files.append(name); dirs.remove(name)
        for name in files:
            p = Path(base)/name; rel = p.relative_to(root).as_posix()
            if name in SKIP or name.startswith('.env') or name.endswith(('.pem','.key')):
                excluded.append(rel); continue
            if p.is_symlink():
                target = p.resolve()
                if not target.is_relative_to(root):
                    raise ValueError(f'External link needs explicit handling: {rel}')
                link = os.path.relpath(target, p.parent)
                entries.append({'path':rel,'link':link})
            elif p.is_file():
                entries.append({'path':rel,'size':p.stat().st_size,'sha256':digest(p)})
    writer = Parts(folder)
    try:
        with tarfile.open(fileobj=writer, mode='w|') as tar:
            for item in entries:
                p = root/item['path']; info = tar.gettarinfo(str(p), arcname=item['path'])
                info.uid=info.gid=0; info.uname=info.gname=''
                if 'link' in item:
                    info.linkname=item['link']; tar.addfile(info)
                else:
                    with p.open('rb') as f: tar.addfile(info,f)
    finally: writer.close()
    parts=[{'name':p.name,'size':p.stat().st_size,'sha256':digest(p)} for p in sorted(folder.glob('*.part*'))]
    manifest={'format':1,'entries':entries,'parts':parts,'excluded':excluded}
    (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (folder/'SHA256SUMS').write_text(''.join(f"{x['sha256']}  {x['name']}\n" for x in parts)+f"{digest(folder/'manifest.json')}  manifest.json\n")
    print(json.dumps({'files_and_links':len(entries),'parts':len(parts),'bytes':sum(x['size'] for x in parts),'excluded':len(excluded)}))

def restore(folder, dest, verify_only):
    folder=folder.resolve(); m=json.loads((folder/'manifest.json').read_text())
    for x in m['parts']:
        if Path(x['name']).name != x['name']: raise ValueError('Unsafe part name')
        p=folder/x['name']
        if p.stat().st_size!=x['size'] or digest(p)!=x['sha256']: raise ValueError(f'Bad part: {p.name}')
    if not verify_only and (dest.exists() and any(dest.iterdir())): raise ValueError('Destination must be empty')
    expected={e['path']:e for e in m['entries']}; seen=set()
    # The temporary joined tar needs approximately the size of all parts in free space.
    with tempfile.TemporaryFile(dir=folder) as joined:
        for x in m['parts']:
            with open(folder/x['name'],'rb') as src: shutil.copyfileobj(src,joined)
        joined.seek(0)
        with tarfile.open(fileobj=joined,mode='r:') as tar:
            for info in tar:
                e=expected.get(info.name)
                if e is None or info.name in seen: raise ValueError('Unexpected/duplicate archive member')
                seen.add(info.name)
                if 'link' in e:
                    if not info.issym() or info.linkname!=e['link']: raise ValueError('Link mismatch')
                else:
                    if not info.isfile() or info.size!=e['size']: raise ValueError('File mismatch')
                    h=hashlib.sha256()
                    with tar.extractfile(info) as f:
                        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
                    if h.hexdigest()!=e['sha256']: raise ValueError(f'Bad file: {info.name}')
            if seen!=set(expected): raise ValueError('Missing files')
            if not verify_only:
                dest.mkdir(parents=True,exist_ok=True)
                tar.extractall(dest,filter='data')
    print(f"Verified {len(seen)} files/links; " + ('no extraction requested' if verify_only else f'restored to {dest}'))

if __name__=='__main__':
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='action',required=True)
    p=sub.add_parser('pack');p.add_argument('root',type=Path);p.add_argument('folder',type=Path)
    p=sub.add_parser('restore');p.add_argument('folder',type=Path);p.add_argument('destination',type=Path);p.add_argument('--verify-only',action='store_true')
    a=ap.parse_args()
    if a.action=='pack': pack(a.root,a.folder)
    else: restore(a.folder,a.destination,a.verify_only)
