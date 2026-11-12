"""Bounded optional exact-cover proposals, with independent quantity replay."""
from collections import Counter
import json
from pathlib import Path
import subprocess
import tempfile
from time import perf_counter


def select_cartons(candidates,expected,cartons,*,python,time_limit=2.,objective='volume',max_nominal_types=None):
    started=perf_counter()
    worker=Path(__file__).with_name('practical_master_worker.py')
    with tempfile.TemporaryDirectory(prefix='bom2kit-cover-') as directory:
        source=Path(directory)/'input.json';target=Path(directory)/'output.json'
        data={'candidates':candidates,'expected':expected,'cartons':cartons,'time_limit':time_limit,
              'objective':objective,'max_nominal_types':max_nominal_types}
        source.write_text(json.dumps(data),encoding='utf8')
        try:
            run=subprocess.run([str(python),str(worker),str(source),str(target)],capture_output=True,text=True,
                               timeout=time_limit+10,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except subprocess.TimeoutExpired:return {'status':'timeout','selected':[],'seconds':perf_counter()-started}
        if run.returncode or not target.exists():return {'status':'backend_error','selected':[],'message':run.stderr[-1200:]}
        result=json.loads(target.read_bytes())
    if result['selected']:
        selected=result['selected']
        if len(selected)!=cartons or len(set(selected))!=len(selected) or any(type(i) is not int or i<0 or i>=len(candidates) for i in selected):
            raise ValueError('Malformed exact-cover certificate')
        actual=Counter()
        for i in selected:actual.update(candidates[i]['contents'])
        if dict(actual)!=expected:raise ValueError('Exact-cover certificate changed source quantities')
    result['seconds']=perf_counter()-started
    return result
