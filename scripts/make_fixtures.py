"""Build clearly labeled synthetic course and human-authored review proposals."""
import io
import json
import sys
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.models import Course, targets

DEST=ROOT / "fixtures"
DEST.mkdir(exist_ok=True)
old="""# Beacon Desk 旧版产品资料

CSV 导出单个文件上限为 20MB。
导出文件保留 30 天。
导出按钮名称为 Export data。
员工只能导出自己有访问权限的记录。
"""
new="""# Beacon Desk 新版资料（合成案例）

## 产品说明 A · 已批准
CSV 导出单个文件上限调整为 50MB。
导出文件保留 14 天，之后自动删除。
导出按钮名称调整为 Download CSV。
员工只能导出自己有访问权限的记录，此项没有变化。

## 支持备忘 B · 同级来源
导出文件保留 21 天，之后自动删除。
此备忘与产品说明 A 的保留期不一致，需要课程负责人决定采用哪项并记录理由。
"""
course={"schema_version":1,"id":"beacon-desk-training","title":"Beacon Desk · 数据导出培训","language":"zh-CN","chapters":[
{"id":"ch-start","title":"01 · 开始之前","blocks":[{"id":"b-welcome","text":"这份课程帮助团队正确导出 Beacon Desk 中的记录。完成课程后，可在[数据导出](#ch-export)章节复习操作。","image":"assets/export-guide.png","image_alt":"Beacon Desk 合成界面：选择记录、导出 CSV、检查文件"}],"quizzes":[]},
{"id":"ch-export","title":"02 · 数据导出","blocks":[{"id":"b-limit","text":"CSV 导出单个文件上限为 20MB。"},{"id":"b-retention","text":"导出文件保留 30 天，请在期限内保存。"},{"id":"b-button","text":"在记录页面点击 Export data 按钮导出文件。"}],"quizzes":[{"id":"q-limit","prompt":"单个 CSV 导出文件的大小上限是多少？","choices":[{"id":"A","text":"10MB"},{"id":"B","text":"20MB"},{"id":"C","text":"50MB"}],"answer_id":"B","explanation":"旧版产品说明规定单个 CSV 文件上限为 20MB。"}]},
{"id":"ch-handout","title":"03 · 操作速查讲义","blocks":[{"id":"h-limit","text":"文件检查：确认单个 CSV 不超过 20MB。"},{"id":"h-retention","text":"保存提醒：导出文件保留 30 天。"},{"id":"h-button","text":"操作入口：Export data。"}],"quizzes":[]},
{"id":"ch-access","title":"04 · 访问权限","blocks":[{"id":"b-access","text":"员工只能导出自己有访问权限的记录。权限不足时联系管理员，不尝试绕过访问限制。"}],"quizzes":[]}
]}
course=Course.model_validate(course).model_dump()
image=Image.new('RGB',(900,220),'#edf3ee');draw=ImageDraw.Draw(image)
for i,(label,color) in enumerate([('1. Select records','#205f4a'),('2. Export CSV','#267459'),('3. Check file','#398b6d')]):
    x=30+i*290;draw.rounded_rectangle((x,35,x+255,185),radius=15,fill=color);draw.text((x+24,100),label,fill='white',font_size=24)
png=io.BytesIO();image.save(png,format='PNG')
with zipfile.ZipFile(DEST/'beacon-old.course.zip','w',zipfile.ZIP_DEFLATED) as z:
    z.writestr('course.json',json.dumps(course,ensure_ascii=False,indent=2));z.writestr('source.md',old);z.writestr('assets/export-guide.png',png.getvalue())
(DEST/'new-product.md').write_text(new)
(DEST/'old-product.md').write_text(old)
(DEST/'course.json').write_text(json.dumps(course,ensure_ascii=False,indent=2)+'\n')
ts=targets(course);lines=new.splitlines()
def citation(line): return {'start_line':line,'end_line':line,'quote':lines[line-1]}
def block(id,text,line,reason,conflict=False):
    replacement=dict(ts[id]['value']);replacement['text']=text
    return {'target_id':id,'expected_digest':ts[id]['digest'],'replacement':replacement,'rationale':reason,'citations':[citation(x) for x in line],'requires_resolution':conflict}
proposals=[
block('b-limit','CSV 导出单个文件上限为 50MB。',[4],'新版容量上限影响课程正文。'),
block('h-limit','文件检查：确认单个 CSV 不超过 50MB。',[4],'速查讲义需要与批准容量一致。'),
block('b-retention','导出文件保留 14 天，请在期限内保存。',[5,10],'两份同级资料分别写 14 天和 21 天。这里提出 14 天作为待人工决定的候选值，不能视为来源共识。',True),
block('h-retention','保存提醒：导出文件保留 14 天。',[5,10],'讲义保留期同样存在来源冲突，需要人工明确选择和理由。',True),
block('b-button','在记录页面点击 Download CSV 按钮导出文件。',[6],'产品说明建议修改按钮名称，审核者可因培训版本安排拒绝此项。'),
block('h-button','操作入口：Download CSV。',[6],'讲义按钮名称的候选修改。')]
q=dict(ts['q-limit']['value']);q['answer_id']='C';q['explanation']='新版产品说明规定单个 CSV 文件上限为 50MB；20MB 仍保留为干扰选项。'
proposals.insert(2,{'target_id':'q-limit','expected_digest':ts['q-limit']['digest'],'replacement':q,'rationale':'上限改变需要同步答案与解释，保留 10MB 和 20MB 干扰选项。','citations':[citation(4)],'requires_resolution':False})
(DEST/'human-authored-proposals.json').write_text(json.dumps({'notice':'HUMAN-AUTHORED SYNTHETIC DEMONSTRATION. Not AI output, not evidence of semantic impact detection.','proposals':proposals},ensure_ascii=False,indent=2)+'\n')
print('Wrote synthetic course, references, media and 7 explicitly human-authored proposals.')
