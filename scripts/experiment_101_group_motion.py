from pathlib import Path
import json
from bom2kit.mesh_motion import check_vertical_sequence
root=Path('packaging-results/so-arm-101/regrouped-without-camera');p=json.loads((root/'problem.json').read_text());l=json.loads((root/'layout.json').read_text());g=json.loads((root/'motion-blocking-diagnostics.json').read_text())['proposed_groups'];r=check_vertical_sequence(p,l,groups=g,time_limit=120);(root/'motion-grouped-validation.json').write_text(json.dumps(r,indent=2));print(r['valid'],r['unresolved_groups'],r['elapsed_seconds'],flush=True)
