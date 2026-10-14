import io
import json
import os
import time
import uuid
import zipfile
from copy import deepcopy

from .models import Block, Course, DraftRequest, Quiz, citation_errors, digest, targets
from .package import read_markdown, unpack
from .revalidation import create_source_review
from .store import Store, encoded


class Problem(Exception):
    def __init__(self, message, status=409):
        self.message, self.status = message, status
        super().__init__(message)


class InjectedInterruption(Exception):
    """Used only by direct local tests, never exposed as an HTTP parameter."""


class Service:
    def __init__(self, root):
        self.store = Store(root)

    def _row(self, db, run_id):
        row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise Problem("Task not found",404)
        return row

    def create(self, archive, new_source):
        course, old_source, assets = unpack(archive)
        source = read_markdown(new_source)
        run_id = uuid.uuid4().hex
        with self.store.transaction() as db:
            db.execute("INSERT INTO runs(id,title,original,current,old_source,source,source_hash,created) VALUES(?,?,?,?,?,?,?,?)", (run_id, course["title"],encoded(course),encoded(course),old_source,source,digest(source.encode()),time.time()))
            db.executemany("INSERT INTO assets VALUES(?,?,?)",[(run_id,k,v) for k,v in assets.items()])
            self.store.event(db,run_id,"imported",{"source_hash":digest(source.encode()),"course_hash":digest(course)})
        self.materialize(run_id)
        return self.get(run_id)

    def list(self):
        with self.store.connect() as db:
            return [dict(x) for x in db.execute("SELECT id,title,revision,created FROM runs ORDER BY created DESC")]

    def materialize(self, run_id):
        with self.store.transaction() as db:
            row=self._row(db,run_id)
            folder=self.store.root / "runs" / run_id
            folder.mkdir(parents=True,exist_ok=True)
            path=folder / "course.json"
            current=json.loads(row["current"])
            if path.exists():
                try:
                    existing=digest(json.loads(path.read_text()))
                except (ValueError,UnicodeError):
                    raise Problem("Course file was edited outside this task. Restore it or start a new task; no changes were overwritten.")
                if existing not in {digest(current),row["materialized_digest"]}:
                    external=json.loads(path.read_text())
                    try:
                        outside=targets(external)
                        changed=[key for key,value in targets(current).items() if key not in outside or outside[key]["digest"]!=value["digest"]]
                    except (KeyError,TypeError):
                        changed=list(targets(current))
                    for target_id in changed:
                        db.execute("UPDATE proposals SET status='stale' WHERE run_id=? AND target_id=? AND status IN ('pending','approved')",(run_id,target_id))
                    self.store.event(db,run_id,"external_edit_blocked",{"affected_targets":changed})
                    db.commit()
                    raise Problem("Course file changed outside this task. Approvals cannot overwrite external edits.")
                if existing==digest(current):
                    if row["materialized_digest"]!=existing:
                        db.execute("UPDATE runs SET materialized_digest=? WHERE id=?",(existing,run_id))
                    return
            temp=folder / "course.json.tmp"
            temp.write_text(encoded(current)+"\n")
            os.replace(temp,path)
            db.execute("UPDATE runs SET materialized_digest=? WHERE id=?",(digest(current),run_id))

    def get(self, run_id):
        self.materialize(run_id)
        with self.store.connect() as db:
            row=dict(self._row(db,run_id))
            proposals=[]
            for p in db.execute("SELECT * FROM proposals WHERE run_id=? ORDER BY created,id",(run_id,)):
                item=dict(p)
                for key in ("body","before_value","errors"):
                    item[key]=json.loads(item[key])
                proposals.append(item)
            row["original"]=json.loads(row["original"])
            row["current"]=json.loads(row["current"])
            row["proposals"]=proposals
            row["targets"]=targets(row["current"])
            row["events"]=[{**dict(e),"details":json.loads(e["details"])} for e in db.execute("SELECT * FROM events WHERE run_id=? ORDER BY seq",(run_id,))]
            row["batches"]=[{k:v for k,v in dict(b).items() if k not in {"before_value","after_value"}} for b in db.execute("SELECT * FROM batches WHERE run_id=? ORDER BY created",(run_id,))]
            row["needs_revalidation"]=self._stale_applied(proposals,row["source_hash"])
            return row

    def _stale_applied(self, proposals, source_hash):
        latest={}
        for p in proposals:
            if p["status"]=="applied":
                latest[p["target_id"]]=p
        return [key for key,p in latest.items() if p["source_hash"]!=source_hash]

    def add_drafts(self, run_id, payload, origin="manual"):
        self.materialize(run_id)
        draft=DraftRequest.model_validate(payload).model_dump()
        with self.store.transaction() as db:
            row=self._row(db,run_id)
            if row["revision"]!=draft["expected_revision"] or row["source_hash"]!=draft["source_hash"]:
                raise Problem("The course or source changed while proposals were being prepared. Review the new version first.")
            current_targets=targets(json.loads(row["current"]))
            added=False
            for body in draft["proposals"]:
                target=current_targets.get(body["target_id"])
                if not target:
                    raise Problem("Unknown target: "+body["target_id"],422)
                replacement=(Block if target["kind"]=="block" else Quiz).model_validate(body["replacement"]).model_dump()
                if replacement["id"]!=body["target_id"]:
                    raise Problem("A proposal cannot change the target ID",422)
                if target["kind"]=="block" and (replacement.get("image"),replacement.get("image_alt"))!=(target["value"].get("image"),target["value"].get("image_alt")):
                    raise Problem("First version changes text only; image references must stay unchanged",422)
                body["replacement"]=replacement
                errors=citation_errors(body["citations"],row["source"])
                if body["expected_digest"]!=target["digest"]:
                    errors.append("target_changed")
                proposal_id=digest({"run":run_id,"source":row["source_hash"],"body":body})[:32]
                if db.execute("SELECT 1 FROM proposals WHERE id=?",(proposal_id,)).fetchone():
                    continue
                db.execute("INSERT INTO proposals(id,run_id,target_id,body,before_value,source_hash,origin,status,errors,created) VALUES(?,?,?,?,?,?,?,?,?,?)",(proposal_id,run_id,body["target_id"],encoded(body),encoded(target["value"]),row["source_hash"],origin,"blocked" if errors else "pending",encoded(errors),time.time()))
                added=True
                self.store.event(db,run_id,"proposal_added",{"proposal_id":proposal_id,"origin":origin,"errors":errors})
            if added:
                db.execute("UPDATE runs SET revision=revision+1 WHERE id=?",(run_id,))
        return self.get(run_id)

    def decide(self, run_id, proposal_id, decision, reason=""):
        self.materialize(run_id)
        if decision not in {"approved","rejected"}:
            raise Problem("Choose approve or reject",422)
        with self.store.transaction() as db:
            row=self._row(db,run_id)
            p=db.execute("SELECT * FROM proposals WHERE id=? AND run_id=?",(proposal_id,run_id)).fetchone()
            if not p: raise Problem("Proposal not found",404)
            if p["status"]==decision: return self.get_without_write(db,run_id)
            if p["status"] in {"applied","rolled_back"}:
                raise Problem("Applied or rolled-back proposals are immutable; create a new proposal")
            body=json.loads(p["body"])
            if decision=="approved":
                if p["source_hash"]!=row["source_hash"] or p["status"]=="stale":
                    raise Problem("Source changed. Prepare and review a new proposal.")
                if json.loads(p["errors"]):
                    raise Problem("This proposal has missing/invalid evidence or a changed target. Replace it before approval.")
                target=targets(json.loads(row["current"]))[p["target_id"]]
                if target["digest"]!=body["expected_digest"]:
                    raise Problem("Target changed since the proposal was made")
                if body["requires_resolution"] and len(reason.strip())<4:
                    raise Problem("Conflicting sources require an explicit resolution reason",422)
                competing=db.execute("SELECT id FROM proposals WHERE run_id=? AND target_id=? AND status='approved' AND id!=?",(run_id,p["target_id"],proposal_id)).fetchone()
                if competing: raise Problem("Another proposal for this item is already approved. Reject it before choosing this one.")
            db.execute("UPDATE proposals SET status=?,resolution=? WHERE id=?",(decision,reason.strip(),proposal_id))
            db.execute("UPDATE runs SET revision=revision+1 WHERE id=?",(run_id,))
            self.store.event(db,run_id,"decision",{"proposal_id":proposal_id,"decision":decision,"reason":reason.strip(),"source_hash":row["source_hash"]})
        return self.get(run_id)

    def get_without_write(self, db, run_id):
        return {"id":run_id,"unchanged":True}

    def update_source(self, run_id, data):
        source=read_markdown(data)
        with self.store.transaction() as db:
            row=self._row(db,run_id)
            new_hash=digest(source.encode())
            if new_hash==row["source_hash"]: return {"id":run_id,"unchanged":True}
            if row["active_batch"]: raise Problem("Finish or roll back the current batch before changing source")
            proposals=[]
            for stored in db.execute("SELECT * FROM proposals WHERE run_id=? AND status IN ('approved','pending','blocked','stale')",(run_id,)):
                proposal=dict(stored)
                proposal["body"]=json.loads(proposal["body"])
                proposal["errors"]=json.loads(proposal["errors"])
                proposals.append(proposal)
            review=create_source_review(row["source"],source,proposals,targets(json.loads(row["current"])),row["source_hash"],new_hash)
            db.execute("UPDATE proposals SET status='stale' WHERE run_id=? AND status IN ('approved','pending','blocked')",(run_id,))
            db.execute("UPDATE runs SET source=?,source_hash=?,revision=revision+1 WHERE id=?",(source,new_hash,run_id))
            review["approval_policy"]="All unapplied proposals remain stale until explicitly reconfirmed or replaced; citations marked for full review cannot be quick-reconfirmed."
            self.store.event(db,run_id,"source_changed",review)
        return self.get(run_id)

    def reconfirm_proposal(self, run_id, proposal_id):
        self.materialize(run_id)
        with self.store.transaction() as db:
            row=self._row(db,run_id)
            proposal=db.execute("SELECT * FROM proposals WHERE id=? AND run_id=?",(proposal_id,run_id)).fetchone()
            if not proposal: raise Problem("Proposal not found",404)
            event=db.execute("SELECT details FROM events WHERE run_id=? AND type='source_changed' ORDER BY seq DESC LIMIT 1",(run_id,)).fetchone()
            if not event: raise Problem("No source revision is awaiting revalidation")
            review=json.loads(event["details"])
            if review.get("after_hash")!=row["source_hash"]:
                raise Problem("Source changed again. Review the latest source diff.")
            check=review.get("proposal_reviews",{}).get(proposal_id)
            if not check: raise Problem("This proposal has no revalidation record. Create a new proposal.")
            if proposal["source_hash"]==row["source_hash"] and proposal["status"]==check["from_status"]:
                return self.get_without_write(db,run_id)
            if proposal["status"]!="stale" or proposal["source_hash"]!=review.get("before_hash"):
                raise Problem("Proposal is no longer eligible for this source revision.")
            if not check.get("quick_reconfirm"):
                raise Problem("This proposal needs full review; create a new proposal or reject it.")
            body=json.loads(proposal["body"])
            current_targets=targets(json.loads(row["current"]))
            target=current_targets.get(proposal["target_id"])
            if not target or target["digest"]!=body["expected_digest"]:
                raise Problem("Target changed; prepare and review a new proposal.")
            locations=check["citations"]
            if len(locations)!=len(body["citations"]) or any(location.get("status") not in {"unchanged","moved"} or "new_range" not in location for location in locations):
                raise Problem("Citation location is not stable; complete a full review.")
            for citation,location in zip(body["citations"],locations):
                citation["start_line"]=location["new_range"]["start_line"]
                citation["end_line"]=location["new_range"]["end_line"]
            if citation_errors(body["citations"],row["source"]):
                raise Problem("Citation no longer matches the current source; complete a full review.")
            next_status=check["from_status"]
            if next_status=="approved":
                competing=db.execute("SELECT id FROM proposals WHERE run_id=? AND target_id=? AND status='approved' AND id!=?",(run_id,proposal["target_id"],proposal_id)).fetchone()
                if competing: raise Problem("Another proposal for this item is already approved. Resolve it before reconfirming.")
            db.execute("UPDATE proposals SET body=?,source_hash=?,status=? WHERE id=?",(encoded(body),row["source_hash"],next_status,proposal_id))
            db.execute("UPDATE runs SET revision=revision+1 WHERE id=?",(run_id,))
            self.store.event(db,run_id,"proposal_reconfirmed",{"proposal_id":proposal_id,"source_hash":row["source_hash"],"status":next_status,"human_action":"Explicit reconfirmation after the source diff was displayed; locator status is not semantic verification."})
        return self.get(run_id)

    def apply(self, run_id, fault=None):
        self.materialize(run_id)
        with self.store.transaction() as db:
            row=self._row(db,run_id)
            batch_id=row["active_batch"]
            if not batch_id:
                ids=[p["id"] for p in db.execute("SELECT id FROM proposals WHERE run_id=? AND status='approved' ORDER BY created,id",(run_id,))]
                if not ids: return {"id":run_id,"unchanged":True}
                batch_id=uuid.uuid4().hex
                db.execute("INSERT INTO batches VALUES(?,?,?,?,?,?,?)",(batch_id,run_id,row["current"],None,encoded(ids),"applying",time.time()))
                db.execute("UPDATE runs SET active_batch=? WHERE id=?",(batch_id,run_id))
                self.store.event(db,run_id,"batch_started",{"batch_id":batch_id,"proposal_ids":ids})
            else:
                ids=json.loads(db.execute("SELECT proposal_ids FROM batches WHERE id=?",(batch_id,)).fetchone()[0])
        for index,pid in enumerate(ids):
            if fault=="before_write" and index==0: raise InjectedInterruption("before_write")
            with self.store.transaction() as db:
                row=self._row(db,run_id)
                p=db.execute("SELECT * FROM proposals WHERE id=?",(pid,)).fetchone()
                if p["status"]=="applied": continue
                if p["status"]!="approved" or p["source_hash"]!=row["source_hash"]:
                    raise Problem("A batch decision/source changed; stop and roll back this batch")
                course=json.loads(row["current"])
                body=json.loads(p["body"])
                if targets(course)[p["target_id"]]["digest"]!=body["expected_digest"]:
                    raise Problem("Target changed; this batch will not overwrite it")
                for chapter in course["chapters"]:
                    for key in ("blocks","quizzes"):
                        for i,obj in enumerate(chapter[key]):
                            if obj["id"]==p["target_id"]: chapter[key][i]=body["replacement"]
                Course.model_validate(course)
                db.execute("UPDATE runs SET current=?,revision=revision+1 WHERE id=?",(encoded(course),run_id))
                db.execute("UPDATE proposals SET status='applied' WHERE id=?",(pid,))
                self.store.event(db,run_id,"applied",{"proposal_id":pid,"batch_id":batch_id,"before":json.loads(p["before_value"]),"after":body["replacement"],"source_hash":p["source_hash"],"citations":body["citations"],"resolution":p["resolution"]})
            if fault=="after_commit" and index==0: raise InjectedInterruption("after_commit_before_ack")
            self.materialize(run_id)
            if fault=="after_materialize" and index==0: raise InjectedInterruption("after_partial_files")
        with self.store.transaction() as db:
            row=self._row(db,run_id)
            if db.execute("SELECT status FROM batches WHERE id=?",(batch_id,)).fetchone()[0]=="applying":
                db.execute("UPDATE batches SET status='complete',after_value=? WHERE id=?",(row["current"],batch_id))
                db.execute("UPDATE runs SET active_batch=NULL WHERE id=?",(run_id,))
                self.store.event(db,run_id,"batch_complete",{"batch_id":batch_id})
        self.materialize(run_id)
        return self.get(run_id)

    def rollback(self, run_id):
        self.materialize(run_id)
        with self.store.transaction() as db:
            row=self._row(db,run_id)
            batch=db.execute("SELECT * FROM batches WHERE run_id=? ORDER BY created DESC LIMIT 1",(run_id,)).fetchone()
            if not batch or batch["status"]=="rolled_back": return {"id":run_id,"unchanged":True}
            if batch["status"]=="complete" and row["current"]!=batch["after_value"]:
                raise Problem("Course changed after this batch. Refusing to overwrite newer content.")
            ids=json.loads(batch["proposal_ids"])
            db.execute("UPDATE runs SET current=?,active_batch=NULL,revision=revision+1 WHERE id=?",(batch["before_value"],run_id))
            for pid in ids:
                db.execute("UPDATE proposals SET status='rolled_back' WHERE id=?",(pid,))
            db.execute("UPDATE batches SET status='rolled_back' WHERE id=?",(batch["id"],))
            self.store.event(db,run_id,"rolled_back",{"batch_id":batch["id"]})
        self.materialize(run_id)
        return self.get(run_id)

    def export(self, run_id, fault=None):
        from .exporter import build_package
        state=self.get(run_id)
        if state["active_batch"]: raise Problem("Finish or roll back the active batch before export")
        unresolved=[p for p in state["proposals"] if p["status"] in {"approved","pending","blocked","stale"}]
        if unresolved: raise Problem("Approve/apply or explicitly reject every unresolved proposal before export")
        if state["needs_revalidation"]: raise Problem("Some applied changes use an older source. Re-review those targets against the new source before export")
        fingerprint=digest({"course":state["current"],"source":state["source_hash"],"proposals":[(p["id"],p["status"],p["resolution"]) for p in state["proposals"]]})
        with self.store.connect() as db:
            saved=db.execute("SELECT data FROM exports WHERE fingerprint=?",(fingerprint,)).fetchone()
            if saved: return bytes(saved[0]),fingerprint
            assets={r["name"]:bytes(r["data"]) for r in db.execute("SELECT name,data FROM assets WHERE run_id=?",(run_id,))}
        data=build_package(state,assets,fingerprint)
        folder=self.store.root / "runs" / run_id
        path=folder / (fingerprint+".course.zip")
        temp=path.with_suffix(".tmp")
        temp.write_bytes(data)
        os.replace(temp,path)
        if fault=="after_export_file": raise InjectedInterruption("export_file_before_receipt")
        with self.store.transaction() as db:
            current=self._row(db,run_id)
            if current["revision"]!=state["revision"]:
                raise Problem("Task changed during export; no completed package was registered. Export again.")
            inserted=db.execute("INSERT OR IGNORE INTO exports VALUES(?,?,?,?)",(fingerprint,run_id,data,time.time()))
            if inserted.rowcount:
                self.store.event(db,run_id,"exported",{"fingerprint":fingerprint,"course_hash":digest(state["current"]),"source_hash":state["source_hash"]})
        return data,fingerprint
