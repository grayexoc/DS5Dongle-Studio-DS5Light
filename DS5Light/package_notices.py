"""Collect actual frozen-package notices; native linkage still needs review."""
import argparse,hashlib,json,shutil,ssl,sys
from importlib.metadata import distribution,packages_distributions
from pathlib import Path
from PyInstaller.archive.readers import CArchiveReader

def collect(exe,target):
    target.mkdir(parents=True,exist_ok=True)
    shutil.copy2('vendor/LICENSE-Studio.txt',target/'DS5Dongle-Studio-LICENSE.txt')
    archive=CArchiveReader(str(exe)).open_embedded_archive('PYZ.pyz')
    mapping=packages_distributions()
    names={'numpy','scipy','PyAudioWPatch','hidapi','pyinstaller','pyinstaller-hooks-contrib'}
    for module in archive.toc: names.update(mapping.get(module.split('.')[0],[]))
    if (exe.parent/'_internal/win32').exists(): names.add('pywin32')
    base=Path(sys.base_prefix)
    runtime={}
    for name,supplier in (
        ('python312.dll',base/'python312.dll'),
        ('libssl-3-x64.dll',base/'DLLs'/'libssl-3-x64.dll'),
        ('libcrypto-3-x64.dll',base/'DLLs'/'libcrypto-3-x64.dll'),
    ):
        packaged=exe.parent/'_internal'/name
        if not supplier.is_file():
            supplier=base/name
        digest=hashlib.sha256(packaged.read_bytes()).hexdigest()
        if digest!=hashlib.sha256(supplier.read_bytes()).hexdigest():
            raise RuntimeError(f'Packaged runtime DLL differs from build Python: {name}')
        runtime[name]=digest
    (target/'runtime.json').write_text(json.dumps(
        dict(python=sys.version.split()[0],openssl=ssl.OPENSSL_VERSION,dll_sha256=runtime),
        indent=2),encoding='utf-8')
    manifest=[]
    for name in sorted(names):
        d=distribution(name); found=[]
        for f in d.files or []:
            if not Path(str(f)).name.lower().startswith(('license','copying','copyright','notice','authors')): continue
            p=Path(d.locate_file(f))
            if p.is_file():
                relative=Path(name)/str(f).replace('..','_');dst=target/relative
                dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst);found.append(relative.as_posix())
        if not found: raise RuntimeError('License not found: '+name)
        manifest.append(dict(package=name,version=d.version,notice_files=found))
    svg_notices=[]
    svg_target=target/'tksvg-0.16';svg_target.mkdir(exist_ok=True)
    for name in ('license.terms','nanosvg-LICENSE.txt','nanosvgrast-LICENSE.txt','SOURCE.json'):
        shutil.copy2(Path('vendor/tksvg0.16')/name,svg_target/name)
        if name!='SOURCE.json':svg_notices.append('tksvg-0.16/'+name)
    manifest.append(dict(package='tksvg',version='0.16',notice_files=svg_notices))
    shutil.copy2(Path(sys.base_prefix)/'LICENSE.txt',target/'Python-LICENSE.txt')
    for p in (Path(sys.base_prefix)/'tcl').rglob('license*'):
        if p.is_file():
            dst=target/'TclTk'/p.relative_to(Path(sys.base_prefix)/'tcl')
            dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst)
    for name in ('Apache-2.0.txt','PortAudio-LICENSE.txt','Tcl-8.6.15-license.terms','OpenSSL-3-LICENSE.txt','zlib-LICENSE.txt','Python-3.12.16-CRT-LICENSE.txt','manifest.json'):
        dst=target/'upstream'/name;dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(Path('licenses/upstream')/name,dst)
    shutil.copytree('licenses/PyAudioWPatch-0.2.12.8',target/'PyAudioWPatch-source-notices',dirs_exist_ok=True)
    binaries=[]
    for p in sorted(exe.parent.rglob('*')):
        if p.is_file() and p.suffix.lower() in ('.dll','.pyd','.exe'):
            binaries.append(dict(file=p.relative_to(exe.parent).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    (target/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (target/'binary_inventory.json').write_text(json.dumps(binaries,indent=2),encoding='utf-8')
    print(f'{len(manifest)} package notice groups; {len(binaries)} native binaries inventoried')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--exe',type=Path,default=Path('dist/DS5Light/DS5Light.exe'))
    parser.add_argument('--target',type=Path,default=Path('dist/DS5Light/THIRD_PARTY'))
    args=parser.parse_args();collect(args.exe,args.target)
