"""Real browser acceptance. All proposals are explicitly human-authored; no AI calls."""
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'evidence'
SHOTS=ROOT/'docs'/'screenshots'
EVIDENCE.mkdir(exist_ok=True);SHOTS.mkdir(parents=True,exist_ok=True)


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0));return s.getsockname()[1]


def chromium_options():
    options={'headless':True,'args':['--no-sandbox','--disable-dev-shm-usage','--disable-background-networking']}
    executable=os.environ.get('COURSE_CHROMIUM')
    if not executable and Path('/usr/bin/chromium').is_file():
        executable='/usr/bin/chromium'
    if executable:
        options['executable_path']=executable
    return options


def wait_server(base,process):
    for _ in range(80):
        if process.poll() is not None: raise RuntimeError('Server stopped before readiness')
        try:
            if httpx.get(base+'/api/status',timeout=.3,trust_env=False).status_code==200:return
        except httpx.HTTPError:pass
        time.sleep(.1)
    raise RuntimeError('Server readiness timeout')


def run():
    checks=[]
    with tempfile.TemporaryDirectory(prefix='course-browser-',dir=EVIDENCE) as work:
        work=Path(work);port=free_port();base=f'http://127.0.0.1:{port}'
        command=[sys.executable,'-c',"import sys,uvicorn;from app.main import create_app;uvicorn.run(create_app(sys.argv[1],live_allowed=False),host='127.0.0.1',port=int(sys.argv[2]),log_level='warning')",str(work/'data'),str(port)]
        process=subprocess.Popen(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            wait_server(base,process)
            with sync_playwright() as pw:
                browser=pw.chromium.launch(**chromium_options())
                context=browser.new_context(viewport={'width':1440,'height':1080},device_scale_factor=1)
                page=context.new_page();errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base,wait_until='networkidle')
                page.get_by_role('heading',name='每一次更新，都有据可查。').wait_for()
                page.screenshot(path=str(SHOTS/'01-import-own-course.png'),full_page=True)
                page.get_by_role('button',name='打开合成示例').click()
                page.get_by_role('button',name='载入人工演示建议').wait_for()
                run_id=page.url.split('#')[1]
                page.get_by_role('button',name='载入人工演示建议').click()
                page.locator('[data-chapter="ch-export"]').click()
                page.locator('[data-target="b-limit"]').wait_for()
                page.screenshot(path=str(SHOTS/'02-source-review.png'),full_page=True)
                for target in ('b-limit','q-limit','b-retention','b-button'):
                    card=page.locator('[data-target="'+target+'"]')
                    if target=='b-retention':card.get_by_role('textbox',name='处理理由').fill('课程负责人选择14天；21天备忘待修正，这不是来源共识。')
                    if target=='b-button':card.get_by_role('textbox',name='处理理由').fill('本次培训保留旧按钮名称，另行安排迁移。')
                    card.get_by_role('button',name='拒绝' if target=='b-button' else '批准',exact=True).click()
                    expected='已拒绝' if target=='b-button' else '已批准'
                    page.wait_for_function("([target, expected]) => document.querySelector('[data-target=\"'+target+'\"] .badge').textContent.includes(expected)",arg=[target,expected])
                page.locator('[data-chapter="ch-handout"]').click()
                for target in ('h-limit','h-retention','h-button'):
                    card=page.locator('[data-target="'+target+'"]')
                    if target=='h-retention':card.get_by_role('textbox',name='处理理由').fill('讲义采用14天，负责人已处理14/21天冲突。')
                    card.get_by_role('button',name='拒绝' if target=='h-button' else '批准',exact=True).click()
                    page.wait_for_function("([target, expected]) => document.querySelector('[data-target=\"'+target+'\"] .badge').textContent.includes(expected)",arg=[target,'已拒绝' if target=='h-button' else '已批准'])
                checks.append('Trainer approved capacity and quiz, resolved 14/21-day conflict with reasons, rejected both button renames through actual UI')
                # A fresh author context proves waiting decisions are server-persistent.
                context.close();context=browser.new_context(viewport={'width':1440,'height':1080});page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/#'+run_id,wait_until='networkidle')
                assert page.locator('.mini-summary').inner_text().find('5')>=0
                page.get_by_role('button',name='应用已批准项',exact=True).click()
                page.wait_for_function("() => document.querySelector('#apply').disabled && document.querySelector('.mini-summary').textContent.includes('已应用')")
                page.locator('[data-chapter="ch-export"]').click()
                page.locator('[data-target="q-limit"] .badge').filter(has_text='已应用').wait_for()
                page.screenshot(path=str(SHOTS/'03-applied-course.png'),full_page=True)
                with page.expect_download() as download:
                    page.get_by_role('button',name='下载课程与讲义').click()
                artifact=EVIDENCE/'beacon-maintained.course.zip';download.value.save_as(artifact)
                assert artifact.stat().st_size>1000
                checks.append('Fresh browser restored decisions, applied five real target updates and downloaded course/handout/change package')
                with zipfile.ZipFile(artifact) as z:
                    destination=work/'learner'
                    z.extractall(destination)
                    data=json.loads(z.read('course.json'))
                    report=json.loads(z.read('changes.json'))
                assert data['chapters'][1]['quizzes'][0]['answer_id']=='C'
                assert data['chapters'][1]['quizzes'][0]['choices'][1]['text']=='20MB'
                assert '2 项建议已拒绝' in report['notice']
                # Stop the author application entirely; use a separate browser process/profile.
                context.close();browser.close();process.terminate();process.wait(timeout=10)
                # Managed Chromium denies file:// navigation. Do not override that policy.
                # Verify a separate supported delivery mode: the export's own static origin.
                learner_port=free_port();learner_base=f'http://127.0.0.1:{learner_port}'
                static_server=subprocess.Popen([sys.executable,'-m','http.server',str(learner_port),'--bind','127.0.0.1','--directory',str(destination)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                for _ in range(50):
                    try:
                        if httpx.get(learner_base+'/course.html',trust_env=False,timeout=.3).status_code==200:break
                    except httpx.HTTPError:time.sleep(.1)
                learner=pw.chromium.launch_persistent_context(str(work/'learner-profile'),viewport={'width':1280,'height':960},**chromium_options())
                lp=learner.new_page();requests=[];lp.on('request',lambda req:requests.append(req.url));lp.on('pageerror',lambda e:errors.append(str(e)))
                lp.goto(learner_base+'/course.html',wait_until='load')
                learner.set_offline(True)
                assert lp.locator('img').evaluate_all('(images)=>images.every(i=>i.complete && i.naturalWidth>0)')
                assert lp.locator('img').count()==1
                lp.locator('#q-limit input[value="B"]').check();lp.locator('#q-limit button').click()
                assert '不正确' in lp.locator('#q-limit .feedback').inner_text()
                lp.locator('#q-limit input[value="C"]').check();lp.locator('#q-limit button').click()
                assert '回答正确' in lp.locator('#q-limit .feedback').inner_text()
                assert '50MB' in lp.locator('#q-limit .feedback').inner_text()
                lp.screenshot(path=str(SHOTS/'04-independent-offline-course.png'),full_page=True)
                for anchor in lp.locator('a[href^="#"]').evaluate_all('(links)=>links.map(a=>a.getAttribute("href").slice(1))'):
                    assert lp.locator('[id="'+anchor+'"]').count()==1
                learner.set_offline(False)
                lp.goto(learner_base+'/handout.html',wait_until='load')
                learner.set_offline(True)
                assert '50MB' in lp.locator('body').inner_text()
                assert '14 天' in lp.locator('body').inner_text()
                assert 'Export data' in lp.locator('body').inner_text()
                lp.screenshot(path=str(SHOTS/'05-offline-handout.png'),full_page=True)
                assert not [u for u in requests if u.startswith(('http://','https://')) and not u.startswith(learner_base+'/')],requests
                checks.append('Author server stopped; separate browser process/profile loaded the export from an independent local static origin, then went offline; embedded image and every internal link worked; B scored wrong and C scored correct')
                checks.append('Standalone handout contains approved 50MB/14-day text and explicitly retained Export data; change report records rejected suggestions and human conflict reasons')
                learner.close()
                static_server.terminate();static_server.wait(timeout=10)
                # Restart for an arbitrary user-authored course, independent of sample IDs.
                process=subprocess.Popen(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE);wait_server(base,process)
                browser=pw.chromium.launch(**chromium_options())
                page=browser.new_page(viewport={'width':1280,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base,wait_until='networkidle');page.locator('#course-title').fill('自有课程 · 客户支持')
                page.locator('#course-text').fill('## 服务介绍\n\n客户支持时间为每天8小时。\n\n如需联系团队，请使用帮助中心。\n\n## 咨询入口\n\n请通过帮助中心联系团队。')
                page.locator('#new-source').fill('# 新版支持规则\n客户支持时间为每天12小时。\n\n## 其他规则\n请通过帮助中心联系团队。')
                page.get_by_text('添加选择题与图片（可选）',exact=True).click()
                page.locator('#add-quiz').click()
                page.locator('.quiz-prompt').fill('联系团队请使用哪个入口？');page.locator('.quiz-choices').fill('帮助中心\n电话');page.locator('.quiz-answer').select_option('0');page.locator('.quiz-explanation').fill('培训材料应指明帮助中心入口。');page.locator('.quiz-chapter').select_option('0')
                page.locator('#course-images').set_input_files(destination/'assets'/'export-guide.png')
                page.locator('.image-alt').fill('自有课程的支持流程配图')
                page.locator('.image-chapter').select_option('1')
                page.get_by_role('button',name='建立维护任务 →').click()
                page.wait_for_function('() => location.hash.length > 1')
                run_id=page.url.split('#')[1]
                page.get_by_role('button',name='＋ 人工添加修改').wait_for()
                page.get_by_role('button',name='＋ 人工添加修改').click()
                support_option=page.locator('#edit-target option').filter(has_text='客户支持时间为每天8小时。').first
                page.locator('#edit-target').select_option(support_option.get_attribute('value'))
                page.locator('#replacement-text').fill('客户支持时间为每天12小时。');page.locator('#edit-rationale').fill('培训负责人核对新版支持规则后更新。');page.locator('#edit-start').fill('2');page.locator('#edit-end').fill('2');page.get_by_role('button',name='保存为待审建议',exact=True).click()
                page.locator('.proposal').wait_for()
                # Saving an unchanged revision must not accidentally reject the same proposal.
                page.locator('.proposal').filter(has_text='内容更新建议').get_by_role('button',name='修订',exact=True).click()
                page.get_by_role('button',name='保存修订并撤回原建议',exact=True).click()
                page.locator('#toast').filter(has_text='内容没有变化').wait_for()
                page.locator('[data-close="editor"]').click()
                support_card=page.locator('.proposal').filter(has_text='内容更新建议')
                assert support_card.locator('.badge').inner_text()=='待审核'

                page.get_by_role('button',name='＋ 人工添加修改').click()
                quiz_option=page.locator('#edit-target option').filter(has_text='题目：联系团队请使用哪个入口？').first
                page.locator('#edit-target').select_option(quiz_option.get_attribute('value'))
                page.locator('#replacement-prompt').fill('新版资料指明联系团队的入口是？')
                page.locator('#replacement-answer').select_option('A')
                page.locator('#replacement-explanation').fill('培训资料应明确使用帮助中心联系团队。')
                page.locator('#edit-rationale').fill('培训负责人核对帮助中心原文后统一题目措辞。')
                page.locator('#edit-start').fill('5');page.locator('#edit-end').fill('5')
                page.get_by_role('button',name='保存为待审建议',exact=True).click()
                quiz_card=page.locator('.proposal').filter(has_text='新版资料指明联系团队的入口是？')
                quiz_card.wait_for()
                assert page.locator('.proposal').count()==2
                support_card.get_by_role('button',name='批准',exact=True).click()
                page.locator('.proposal').filter(has_text='内容更新建议').locator('.badge').filter(has_text='已批准').wait_for()
                quiz_card.get_by_role('button',name='批准',exact=True).click()
                page.locator('.proposal').filter(has_text='新版资料指明联系团队的入口是？').locator('.badge').filter(has_text='已批准').wait_for()

                # Change only the first cited fact. The second unique citation and its
                # adjacent heading stay fixed, so its proposal remains eligible for
                # explicit confirmation while the changed citation requires full review.
                page.locator('.source-panel details summary').click()
                old_reference=page.locator('#replacement-source').input_value()
                assert '每天12小时' in old_reference and '请通过帮助中心联系团队。' in old_reference
                page.locator('#replacement-source').fill(old_reference.replace('每天12小时','每天14小时'))
                page.get_by_role('button',name='保存新版资料并重新审阅',exact=True).click()
                page.locator('.proposal .badge').filter(has_text='来源已变 · 需重审').first.wait_for()
                support_card=page.locator('.proposal').filter(has_text='内容更新建议')
                quiz_card=page.locator('.proposal').filter(has_text='新版资料指明联系团队的入口是？')
                support_review=support_card.locator('.revalidation-card')
                quiz_review=quiz_card.locator('.revalidation-card')
                assert support_card.locator('.badge').inner_text()=='来源已变 · 需重审'
                assert '必须完整复核' in support_review.inner_text()
                assert '引用已变更或消失' in support_review.inner_text()
                assert support_review.locator('[data-reconfirm-ack]').count()==0
                assert quiz_card.locator('.badge').inner_text()=='来源已变 · 需重审'
                assert '唯一定位，行号未变' in quiz_review.inner_text()
                ack=quiz_card.locator('[data-reconfirm-ack]')
                confirm=quiz_card.locator('[data-reconfirm]')
                assert not ack.is_checked()
                assert confirm.is_disabled()
                with page.expect_response(lambda response:response.url.endswith('/export')) as blocked_export:
                    page.get_by_role('button',name='下载课程与讲义').click()
                assert blocked_export.value.status==409

                # A full refresh must reconstruct the diff and both per-proposal decisions.
                page.reload(wait_until='networkidle')
                source_panel=page.locator('#source-revision')
                source_panel.wait_for()
                diff_text=source_panel.locator('.source-diff').inner_text()
                assert '每天12小时' in diff_text and '每天14小时' in diff_text
                support_card=page.locator('.proposal').filter(has_text='内容更新建议')
                quiz_card=page.locator('.proposal').filter(has_text='新版资料指明联系团队的入口是？')
                support_review=support_card.locator('.revalidation-card')
                quiz_review=quiz_card.locator('.revalidation-card')
                assert '引用已变更或消失' in support_review.inner_text()
                assert support_review.locator('[data-reconfirm-ack]').count()==0
                ack=quiz_card.locator('[data-reconfirm-ack]')
                confirm=quiz_card.locator('[data-reconfirm]')
                assert not ack.is_checked() and confirm.is_disabled()
                page.screenshot(path=str(SHOTS/'06-source-revalidation.png'),full_page=True)
                checks.append('A trainer created a separate Markdown course with a quiz and uploaded image through forms, without manual IDs or JSON')
                checks.append('Changed citation was blocked from quick re-confirmation; unchanged unique citation retained a disabled explicit-confirm action; the diff and both locator states survived a full page refresh; export returned HTTP 409 while proposals were stale')

                support_card.locator('.reason').fill('新版资料改为14小时，旧建议需重写。')
                support_card.get_by_role('button',name='拒绝',exact=True).click()
                page.locator('.proposal').filter(has_text='内容更新建议').locator('.badge').filter(has_text='已拒绝').wait_for()
                ack.check()
                assert not confirm.is_disabled()
                confirm.click()
                page.locator('.proposal').filter(has_text='新版资料指明联系团队的入口是？').locator('.badge').filter(has_text='已批准').wait_for()
                assert '客户支持时间为每天8小时。' in page.locator('.original-block').first.evaluate('(el)=>el.textContent')
                course_path=work/'data'/'runs'/run_id/'course.json'
                before_apply=json.loads(course_path.read_text())
                assert before_apply['chapters'][0]['quizzes'][0]['prompt']=='联系团队请使用哪个入口？'
                assert '每天8小时' in before_apply['chapters'][0]['blocks'][0]['text']

                # Rejection and explicit approval both survive another refresh. The
                # approved quiz still needs the separate Apply action.
                page.reload(wait_until='networkidle')
                support_card=page.locator('.proposal').filter(has_text='内容更新建议')
                quiz_card=page.locator('.proposal').filter(has_text='新版资料指明联系团队的入口是？')
                assert support_card.locator('.badge').inner_text()=='已拒绝'
                assert quiz_card.locator('.badge').inner_text()=='已批准 · 待应用'
                assert '已在当前资料版本上由用户显式重新确认' in quiz_card.locator('.revalidation-card').inner_text()
                assert not page.locator('#apply').is_disabled()
                before_apply=json.loads(course_path.read_text())
                assert before_apply['chapters'][0]['quizzes'][0]['prompt']=='联系团队请使用哪个入口？'
                assert '每天8小时' in before_apply['chapters'][0]['blocks'][0]['text']

                page.get_by_role('button',name='应用已批准项',exact=True).click()
                quiz_card=page.locator('.proposal').filter(has_text='新版资料指明联系团队的入口是？')
                quiz_card.locator('.badge').filter(has_text='已应用').wait_for()
                assert support_card.locator('.badge').inner_text()=='已拒绝'
                persisted=json.loads(course_path.read_text())
                assert persisted['chapters'][0]['quizzes'][0]['prompt']=='新版资料指明联系团队的入口是？'
                assert '每天8小时' in persisted['chapters'][0]['blocks'][0]['text']
                with page.expect_download() as support_download:
                    page.get_by_role('button',name='下载课程与讲义').click()
                support_artifact=EVIDENCE/'customer-support-maintained.course.zip'
                support_download.value.save_as(support_artifact)
                assert support_artifact.stat().st_size>1000
                with zipfile.ZipFile(support_artifact) as z:
                    exported=json.loads(z.read('course.json'))
                    exported_report=json.loads(z.read('changes.json'))
                    course_html=z.read('course.html').decode()
                    handout_html=z.read('handout.html').decode()
                assert exported['chapters'][0]['quizzes'][0]['prompt']=='新版资料指明联系团队的入口是？'
                assert '每天8小时' in exported['chapters'][0]['blocks'][0]['text']
                assert '已拒绝' in exported_report['notice']
                assert '新版资料指明联系团队的入口是？' in course_html
                assert '客户支持时间为每天8小时。' in handout_html
                assert 'data-quiz' not in handout_html
                assert 'data-quiz' in course_html and 'data-quiz' not in handout_html
                assert '<img ' in course_html and '<img ' in handout_html
                assert len([name for name in z.namelist() if name.startswith('assets/')])==1
                assert any(event['type']=='source_changed' for event in exported_report['events'])
                assert any(event['type']=='proposal_reconfirmed' for event in exported_report['events'])
                checks.append('The full review rejection remained visible; explicit reconfirmation preserved approval after reload but did not edit the course until Apply; course.json, source, image, quiz, course HTML, print handout and change report were exported and checked')
                browser.close()
                assert not errors,errors
                report={'status':'passed','scope':'Real browser offline workflow; human-authored proposals; no AI calls','browser_environment':'macOS; Playwright-managed Chromium in isolated headless profiles','checks':checks,'browser_errors':errors,'external_learner_requests':0,'delivery_limitation':'Managed browser blocks file://. Direct double-click opening was not verified. Independent static-origin delivery was verified; no browser policy was overridden.','artifact':'evidence/beacon-maintained.course.zip','artifacts':['evidence/beacon-maintained.course.zip','evidence/customer-support-maintained.course.zip'],'screenshots':[str(x.relative_to(ROOT)) for x in sorted(SHOTS.glob('*.png'))],'live_ai_verified':False}
                (EVIDENCE/'browser-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
                print(json.dumps(report,ensure_ascii=False,indent=2))
        finally:
            if process.poll() is None:process.terminate();process.wait(timeout=10)


if __name__=='__main__':run()
