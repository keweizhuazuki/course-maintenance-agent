"""Explicit Markdown/text conversion, not AI analysis or semantic matching."""
import base64
import io
import json
import re
import uuid
import zipfile

from .models import Course
from .package import read_markdown, validate_image


def uid(prefix): return prefix+"-"+uuid.uuid4().hex[:12]


def create_course(payload):
    title=str(payload.get("title","")).strip()
    text=read_markdown(str(payload.get("text","")).encode())
    if not title or len(title)>200:
        raise ValueError("Give the course a title (up to 200 characters)")
    chapters=[]
    current=None
    for chunk in re.split(r"(?m)^(##\s+[^\n]+)\n?",text):
        if not chunk.strip(): continue
        if chunk.startswith("## "):
            current={"id":uid("chapter"),"title":chunk[3:].strip(),"blocks":[],"quizzes":[]}
            chapters.append(current)
        else:
            if current is None:
                current={"id":uid("chapter"),"title":"课程内容","blocks":[],"quizzes":[]}
                chapters.append(current)
            for paragraph in re.split(r"\n\s*\n",chunk.strip()):
                if paragraph.strip(): current["blocks"].append({"id":uid("block"),"text":paragraph.strip(),"image":None,"image_alt":None})
    for ch in chapters:
        if not ch["blocks"]: raise ValueError("Each chapter needs some text: "+ch["title"])
    for q in payload.get("quizzes",[]):
        ci=int(q.get("chapter_index",0))
        if ci<0 or ci>=len(chapters): raise ValueError("Choose an existing chapter for each question")
        choices=[str(x).strip() for x in q.get("choices",[]) if str(x).strip()]
        answer=int(q.get("answer_index",-1))
        if not 2<=len(choices)<=6 or not 0<=answer<len(choices): raise ValueError("Each question needs 2–6 choices and one correct answer")
        chapters[ci]["quizzes"].append({"id":uid("quiz"),"prompt":q.get("prompt",""),"choices":[{"id":chr(65+i),"text":v} for i,v in enumerate(choices)],"answer_id":chr(65+answer),"explanation":q.get("explanation","")})
    assets={}
    for image in payload.get("images",[]):
        ext=str(image.get("extension","")).lower()
        if ext not in {"png","jpg","jpeg","webp"}: raise ValueError("Choose a PNG, JPEG or WebP image")
        ci=int(image.get("chapter_index",0))
        if ci<0 or ci>=len(chapters): raise ValueError("Choose an existing image chapter")
        blob=base64.b64decode(image.get("data_base64",""),validate=True)
        name="assets/"+uid("image")+"."+ext
        validate_image(name,blob)
        alt=str(image.get("alt","")).strip()
        if not alt: raise ValueError("Describe the image for accessible offline viewing")
        assets[name]=blob
        chapters[ci]["blocks"].append({"id":uid("block"),"text":alt,"image":name,"image_alt":alt})
    course=Course.model_validate({"schema_version":1,"id":uid("course"),"title":title,"language":"zh-CN","chapters":chapters}).model_dump()
    old_source=read_markdown(str(payload.get("old_source") or text).encode())
    result=io.BytesIO()
    with zipfile.ZipFile(result,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("course.json",json.dumps(course,ensure_ascii=False,indent=2))
        z.writestr("source.md",old_source)
        for name,data in assets.items(): z.writestr(name,data)
    return result.getvalue(),course
