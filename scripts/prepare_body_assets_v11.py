"""Prepare phase B native assets read-only from game PAKs, writing only project data."""
import argparse,json
from pathlib import Path
from scripts.generate_mod import ROOT,DIVINE,run_tool
from scripts.body_template_audit_v11 import nodes_for,attrs

def main(game_data):
    destination=ROOT/'.tools/v11-body'
    for pattern in ('*Equipment*.lsx','*ActionResource*','*LevelMapValues.lsx','*Armor*/*','Public/Shared/Content/Assets/Equipment/*','Public/*/Content/Assets/Loot/*','Public/Shared/Content/Assets/Weapons/*'):
        run_tool(DIVINE,'-a','extract-package','-s',str(game_data/'Shared.pak'),'-d',str(destination),'-x',pattern)
    for package in ('Shared','Gustav','GustavX'):
        if (game_data/(package+'.pak')).exists():
            run_tool(DIVINE,'-a','extract-package','-s',str(game_data/(package+'.pak')),'-d',str(ROOT/'.tools/v11-tags'),'-x','Public/*/Tags/*')
    import subprocess
    result=subprocess.run([str(DIVINE),'-g','bg3','-a','list-package','-s',str(game_data/'Models.pak')],capture_output=True,check=True)
    (ROOT/'build/v1.1/all-models.log').write_bytes(result.stdout)
    resources=json.loads((ROOT/'build/v1.1/resource-catalog.json').read_text(encoding='utf-8'))
    tags={a.get('value') for n in nodes_for(resources).values() for a in n.findall('./children/node[@id="Tags"]//attribute[@id="Object"]')}
    paths=list(destination.rglob('*.lsf'))+[p for p in (ROOT/'.tools/v11-tags').rglob('*.lsf') if p.stem in tags]
    for path in paths:
        run_tool(DIVINE,'-a','convert-resource','-s',str(path),'-d',str(path.with_suffix('.lsx')),'-i','lsf','-o','lsx')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--game-data',type=Path,required=True)
    main(parser.parse_args().game_data)
