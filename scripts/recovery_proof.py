"""Produce inspectable evidence of real local writes and abrupt process recovery."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.models import digest,targets
from app.service import InjectedInterruption,Problem,Service

FIX=ROOT/'fixtures';OUT=ROOT/'evidence';OUT.mkdir(exist_ok=True)


def prepared(service):
    s=service.create((FIX/'beacon-old.course.zip').read_bytes(),(FIX/'new-product.md').read_bytes())
    plans=json.loads((FIX/'human-authored-proposals.json').read_text())['proposals']
    s=service.add_drafts(s['id'],{'expected_revision':s['revision'],'source_hash':s['source_hash'],'proposals':plans},'human_authored_demo')
    for p in s['proposals']:
        decision='rejected' if 'button' in p['target_id'] else 'approved'
        reason='保留旧按钮用于本次培训；不宣称与新资料完全一致' if decision=='rejected' else ('负责人选择14天；21天备忘待修正，保留冲突记录' if p['body']['requires_resolution'] else '人工核对新版容量依据')
        service.decide(s['id'],p['id'],decision,reason)
    return service.get(s['id'])


def run():
    with tempfile.TemporaryDirectory(prefix='recovery-proof-',dir=OUT) as directory:
        root=Path(directory);service=Service(root);s=prepared(service);rid=s['id'];initial=s['current']
        child_code="from app.service import Service,InjectedInterruption;import sys,os\ns=Service(sys.argv[1])\ntry:s.apply(sys.argv[2],fault='after_materialize')\nexcept InjectedInterruption:os._exit(77)"
        child=subprocess.run([sys.executable,'-c',child_code,str(root),rid],cwd=ROOT,capture_output=True)
        assert child.returncode==77,child.stderr.decode()
        service=Service(root);partial=service.get(rid)
        assert len([p for p in partial['proposals'] if p['status']=='applied'])==1
        partial_file=json.loads((root/'runs'/rid/'course.json').read_text())
        assert partial_file==partial['current']
        service.apply(rid);complete=service.get(rid)
        before_repeat=len(complete['events']);path=root/'runs'/rid/'course.json';mtime=path.stat().st_mtime_ns
        service.apply(rid);repeated=service.get(rid)
        assert len(repeated['events'])==before_repeat and path.stat().st_mtime_ns==mtime
        old=targets(initial);new=targets(complete['current'])
        preserved=['b-welcome','b-access','b-button','h-button']
        assert all(old[k]['value']==new[k]['value'] for k in preserved)
        assert new['q-limit']['value']['answer_id']=='C' and new['q-limit']['value']['choices'][1]['text']=='20MB'
        try:service.export(rid,fault='after_export_file')
        except InjectedInterruption:pass
        with service.store.connect() as db:exports_before=db.execute('SELECT count(*) FROM exports').fetchone()[0]
        assert exports_before==0
        unacknowledged=next((root/'runs'/rid).glob('*.course.zip')).read_bytes()
        service=Service(root);data,fingerprint=service.export(rid);assert data==unacknowledged
        (OUT/'beacon-recovered.course.zip').write_bytes(data)
        assert service.export(rid)==(data,fingerprint)
        with service.store.connect() as db:exports_after=db.execute('SELECT count(*) FROM exports').fetchone()[0]
        assert exports_after==1
        # Source changes invalidate approvals; no targets are rewritten.
        changed=prepared(service);changed_before=digest(changed['current'])
        changed=service.update_source(changed['id'],changed['source'].replace('50MB','40MB').encode())
        assert len([p for p in changed['proposals'] if p['status']=='stale'])==5
        assert digest(changed['current'])==changed_before
        # A genuine external write must survive the attempted application.
        external=prepared(service);outside=json.loads(json.dumps(external['current']));outside['chapters'][1]['blocks'][0]['text']='外部培训人员新增的内容，不得覆盖。'
        external_path=root/'runs'/external['id']/'course.json';external_path.write_text(json.dumps(outside,ensure_ascii=False))
        try:service.apply(external['id'])
        except Problem:pass
        else:raise AssertionError('External edit was not blocked')
        assert json.loads(external_path.read_text())==outside
        with service.store.connect() as db:external_status={p['target_id']:p['status'] for p in db.execute('SELECT target_id,status FROM proposals WHERE run_id=?',(external['id'],))}
        assert external_status['b-limit']=='stale' and external_status['q-limit']=='approved'
        # Recovery tests above leave the final completed task intact; rollback is separate.
        service.rollback(rid);rolled=service.get(rid);assert rolled['current']==initial
        result={
            'status':'passed','synthetic_data':True,'proposal_origin':'human_authored_demo','live_ai_verified':False,
            'task_id':rid,'source_hash':s['source_hash'],
            'saved_decisions':{'approved':5,'rejected':2,'conflicts_resolved_by_human':2},
            'abrupt_exit':{'child_exit_code':child.returncode,'injection':'after first materialized course update','applied_at_exit':1,'partial_file_matches_durable_state':True,'active_batch_recovered':partial['active_batch']},
            'resumed':{'applied_target_count':5,'course_hash':digest(complete['current']),'repeat_apply_added_events':len(repeated['events'])-before_repeat,'repeat_apply_rewrote_file':False,'preserved_targets':preserved,'unaffected_chapter_hashes':[digest(initial['chapters'][i]) for i in (0,3)]},
            'quiz':{'old_answer':'B','new_answer':new['q-limit']['value']['answer_id'],'B_distractor':new['q-limit']['value']['choices'][1]['text'],'new_explanation':new['q-limit']['value']['explanation']},
            'export_interruption':{'injection':'ZIP file written before completion receipt','completed_exports_before_resume':exports_before,'completed_exports_after_repeat':exports_after,'bytes_identical_after_resume':True,'artifact_path':'evidence/beacon-recovered.course.zip','artifact_sha256':hashlib.sha256(data).hexdigest(),'fingerprint':fingerprint},
            'source_change':{'change':'50MB to 40MB after approval','invalidated_unapplied_approvals':5,'course_unchanged':True,'policy':'conservative whole-reference invalidation'},
            'external_edit':{'write_blocked':True,'external_content_preserved':True,'related_approval':external_status['b-limit'],'unrelated_approval':external_status['q-limit']},
            'rollback':{'restored_course_hash':digest(rolled['current']),'matches_original':rolled['current']==initial},
            'semantic_limits':'No AI influence identification, factual entailment or model prompt-injection resistance was tested. Evidence covers the deterministic review/write/recovery layer.'
        }
        (OUT/'recovery-proof.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':run()
