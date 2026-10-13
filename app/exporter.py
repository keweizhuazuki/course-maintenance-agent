import base64
import html
import io
import json
import re
import zipfile

from .models import Course


STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f4f6fa;color:#203044;font:16px/1.7 system-ui,sans-serif}main{max-width:900px;margin:36px auto;padding:28px;background:white;border-radius:20px}h1{font-size:32px}h2{margin-top:40px;color:#115e59}nav{display:flex;gap:16px;flex-wrap:wrap}a{color:#0f766e}section{scroll-margin-top:20px}.block{white-space:normal;margin:18px 0}img{display:block;max-width:100%;max-height:260px;border-radius:10px}.note{padding:14px;background:#fff7df;border-radius:10px;font-size:14px}.quiz{margin:24px 0;padding:22px;background:#f1f6f7;border-radius:14px}label{display:block;padding:8px;border:1px solid #d5e2e2;margin:7px 0;border-radius:8px;cursor:pointer}button{background:#0f766e;color:white;border:0;padding:10px 22px;border-radius:8px;cursor:pointer;font-size:15px}.feedback{margin:14px 0;font-weight:600}.wrong{color:#a33b25}.correct{color:#15714d}.muted{color:#607080;font-size:13px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #d5dde5;padding:10px;text-align:left;vertical-align:top}pre{white-space:pre-wrap;font:13px/1.5 system-ui;background:#f4f6fa;padding:12px;border-radius:8px}details{margin:12px 0}summary{cursor:pointer}@media print{body{background:white}main{margin:0;max-width:none;padding:0}.quiz{break-inside:avoid}button{display:none}}
"""


def links(text):
    return re.findall(r"\[([^\]]+)\]\(([^\s)]+)\)",text)


def validate(course, assets):
    Course.model_validate(course)
    ids={course["id"]}
    for ch in course["chapters"]:
        ids.add(ch["id"])
        ids.update(x["id"] for x in ch["blocks"]+ch["quizzes"])
    errors=[]
    external=[]
    for ch in course["chapters"]:
        for item in ch["blocks"]+ch["quizzes"]:
            texts=[item.get("text",""),item.get("prompt",""),item.get("explanation","")]
            texts += [x["text"] for x in item.get("choices",[])]
            if item.get("image") and item["image"] not in assets:
                errors.append({"target":item["id"],"problem":"missing_asset"})
            for text in texts:
                for _,url in links(text):
                    if url.startswith("#"):
                        if url[1:] not in ids: errors.append({"target":item["id"],"problem":"broken_internal_link","url":url})
                    elif url.startswith(("https://","http://")):
                        external.append({"target":item["id"],"url":url,"status":"not_checked_offline"})
                    else:
                        errors.append({"target":item["id"],"problem":"unsupported_link","url":url})
    return {"errors":errors,"external_links":external,"quiz_structure":"valid","semantics":"requires_human_review","media_scope":"PNG/JPEG/WebP only; no video support"}


def rich(text):
    escaped=html.escape(text)
    def replace(m):
        label,url=m.groups()
        if url.startswith(("#","https://","http://")):
            return '<a href="'+url+'" rel="noreferrer noopener">'+label+'</a>'
        return label+" (unsupported link)"
    return re.sub(r"\[([^\]]+)\]\(([^\s)]+)\)",replace,escaped).replace("\n","<br>")


def document(title,body,script="",lang="zh-CN"):
    return '<!doctype html><html lang="'+html.escape(lang)+'"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'; script-src \'unsafe-inline\'; connect-src \'none\'; base-uri \'none\'; form-action \'none\'"><title>'+html.escape(title)+'</title><style>'+STYLE+'</style></head><body><main>'+body+'</main>'+script+'</body></html>'


def course_html(course,assets,notice,handout=False):
    body='<p class="muted">课程维护 · 离线交付 / Offline course</p><h1 id="'+course["id"]+'">'+html.escape(course["title"])+(' · 讲义' if handout else '')+'</h1>'
    body+='<div class="note">'+html.escape(notice)+'</div><nav>'
    body+=''.join('<a href="#'+c["id"]+'">'+html.escape(c["title"])+'</a>' for c in course["chapters"])
    body+='</nav>'
    answers={}
    for ch in course["chapters"]:
        body+='<section id="'+ch["id"]+'"><h2>'+html.escape(ch["title"])+'</h2>'
        for block in ch["blocks"]:
            body+='<div class="block" id="'+block["id"]+'">'+rich(block["text"])
            if block.get("image"):
                name=block["image"]
                mime="image/jpeg" if name.endswith((".jpg",".jpeg")) else "image/"+name.rsplit(".",1)[-1]
                body+='<img src="data:'+mime+';base64,'+base64.b64encode(assets[name]).decode()+'" alt="'+html.escape(block["image_alt"])+'">'
            body+='</div>'
        if not handout:
            for q in ch["quizzes"]:
                body+='<div class="quiz" id="'+q["id"]+'"><h3>'+html.escape(q["prompt"])+'</h3>'
                for choice in q["choices"]:
                    body+='<label><input type="radio" name="'+q["id"]+'" value="'+choice["id"]+'"> '+html.escape(choice["text"])+'</label>'
                body+='<button data-quiz="'+q["id"]+'">检查答案 / Check answer</button><div class="feedback" role="status"></div></div>'
                answers[q["id"]]={"answer":q["answer_id"],"explanation":q["explanation"]}
        else:
            # Keep links to question anchors resolvable in the printable handout.
            for q in ch["quizzes"]: body+='<span id="'+q["id"]+'"></span>'
        body+='</section>'
    body+='<p class="muted">'+("讲义保留已批准的课程文字。" if handout else "测验是本地学习辅助，答案随文件交付，不适合作为保密考试；不采集或发送学员数据。")+'</p>'
    safe_json=json.dumps(answers,ensure_ascii=False).replace("<","\\u003c")
    script='' if handout else '<script>const answers='+safe_json+''';document.querySelectorAll('[data-quiz]').forEach(button=>button.addEventListener('click',()=>{const box=button.closest('.quiz'),selected=box.querySelector('input:checked'),out=box.querySelector('.feedback');if(!selected){out.textContent='请选择一个答案。';return;}const ok=selected.value===answers[button.dataset.quiz].answer;out.className='feedback '+(ok?'correct':'wrong');out.textContent=(ok?'回答正确。 ':'回答不正确，请再核对。 ')+answers[button.dataset.quiz].explanation;}));</script>'''
    return document(course["title"],body,script,course["language"])


def build_package(state,assets,fingerprint):
    course=state["current"]
    checks=validate(course,assets)
    if checks["errors"]:
        from .service import Problem
        raise Problem("Fix broken internal links or missing media before export: "+json.dumps(checks["errors"],ensure_ascii=False),422)
    rejected=[p for p in state["proposals"] if p["status"]=="rejected"]
    rolled=[p for p in state["proposals"] if p["status"]=="rolled_back"]
    notice=(f"部分维护：{len(rejected)} 项建议已拒绝，相关旧内容按审核决定保留。" if rejected else "已应用审核通过的维护建议。")
    if not any(p["status"]=="applied" for p in state["proposals"]): notice="原课程交付：当前没有已应用的维护建议。"
    if rolled: notice+=f" {len(rolled)} 项历史改动已回滚。"
    notice+=" 原文依据、人工冲突处理及未检查的外部链接见 changes.html；不表示全部内容已与新版资料一致。"
    report={"format_version":1,"task_id":state["id"],"fingerprint":fingerprint,"source_hash":state["source_hash"],"notice":notice,"validation":checks,"proposals":state["proposals"],"events":[e for e in state["events"] if e["type"]!="exported"],"ai_status":"No claim of live AI verification; see each proposal origin"}
    rows=''
    for p in state["proposals"]:
        rows+='<tr><td>'+html.escape(p["target_id"])+'</td><td>'+html.escape(p["status"]+' / '+p["origin"])+'</td><td>'+html.escape(p["resolution"] or p["body"]["rationale"])+'</td></tr>'
    detail=''.join('<details><summary>'+html.escape(p["target_id"]+' · '+p["status"])+'</summary><pre>'+html.escape(json.dumps({"before":p["before_value"],"proposed":p["body"]["replacement"],"citations":p["body"]["citations"],"source_hash":p["source_hash"],"resolution":p["resolution"]},ensure_ascii=False,indent=2))+'</pre></details>' for p in state["proposals"])
    report_html=document("课程变更说明",'<h1>课程变更说明</h1><div class="note">'+html.escape(notice)+'</div><p>任务 '+state["id"]+' · 来源 '+state["source_hash"][:16]+'</p><table><tr><th>内容</th><th>处理 / 建议来源</th><th>理由</th></tr>'+rows+'</table>'+detail+'<h2>校验范围</h2><pre>'+html.escape(json.dumps(checks,ensure_ascii=False,indent=2))+'</pre>')
    contents={"course.json":json.dumps(course,ensure_ascii=False,indent=2).encode(),"source.md":state["source"].encode(),"course.html":course_html(course,assets,notice).encode(),"handout.html":course_html(course,assets,notice,True).encode(),"changes.json":json.dumps(report,ensure_ascii=False,indent=2).encode(),"changes.html":report_html.encode(),**assets}
    output=io.BytesIO()
    with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for name,data in sorted(contents.items()):
            info=zipfile.ZipInfo(name,date_time=(2026,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,data)
    return output.getvalue()
