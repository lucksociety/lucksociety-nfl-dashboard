"""Daily permanent import of delivered records; result updates never rewrite forecasts."""
import io,json,os,zipfile
from datetime import datetime
from .data import ROOT
from .run import learn,build_model,publication_records,next_slate,ET
from cfb.github_artifacts import api

def main():
    folder=ROOT/'data';pub=folder/'publications.json';state_file=folder/'learning-state.json'
    rows=json.loads(pub.read_text())if pub.exists()else[];known={r['key']for r in rows};state=json.loads(state_file.read_text())if state_file.exists()else dict(imported=[])
    imported=set(state['imported'])
    for page in range(1,11):
        runs=api('/actions/workflows/discord-ufc.yml/runs?per_page=100&page='+str(page))['workflow_runs']
        batch=[]
        for run in runs:
            if run['status']=='completed':batch.extend(api('/actions/runs/'+str(run['id'])+'/artifacts')['artifacts'])
        for a in batch:
            if a['expired']or not a['name'].startswith('ufc-record-')or a['id']in imported:continue
            z=zipfile.ZipFile(io.BytesIO(api('/actions/artifacts/'+str(a['id'])+'/zip',True)))
            files={f.filename.split('/')[-1]:f for f in z.infolist()}
            if 'frozen.json'in files and 'delivery.json'in files:
                for name in ['frozen.json','delivery.json']:
                    if files[name].file_size>10_000_000:raise ValueError('Oversized publication archive')
                records=publication_records(json.loads(z.read(files['frozen.json'])),json.loads(z.read(files['delivery.json'])))
                for r in records:
                    if r['key']not in known:rows.append(r);known.add(r['key'])
            imported.add(a['id'])
        if len(runs)<100:break
    else:raise ValueError('Artifact pagination incomplete')
    pub.write_text(json.dumps(rows,indent=2)+'\n');learn()
    # Rebuild on current results, but never optimize based on yesterday's wins/losses.
    slate,_=next_slate(datetime.now(ET).date().isoformat())
    build_model(True,slate=slate or None)
    state['imported']=sorted(imported);state_file.write_text(json.dumps(state)+'\n')
if __name__=='__main__':main()
