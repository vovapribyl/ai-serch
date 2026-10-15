"""Build portfolio SVG and PlantUML sources from the same semantic descriptions.

SVG layout is generated locally; this is not a PlantUML compiler.
"""
from pathlib import Path
import json
from html import escape
import textwrap

ROOT = Path(__file__).resolve().parent
INK = '#243247'
MUTED = '#65758B'
ACCENT = '#2E5AA8'
RULE = '#C9D3DF'
PAPER = '#FFFFFF'


def text(x, y, value, size=14, anchor='middle', color=INK):
    return f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}" fill="{color}" font-family="Arial, sans-serif">{escape(value)}</text>'


def svg_start(slug, title, desc, width, height):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="{slug}-title {slug}-desc">
<title id="{slug}-title">{escape(title)}</title><desc id="{slug}-desc">{escape(desc)}</desc>
<defs><marker id="{slug}-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="{MUTED}"/></marker></defs>
<rect width="{width}" height="{height}" fill="{PAPER}"/>
'''


def header(title, subtitle, width):
    return text(width/2, 32, title, 22) + text(width/2, 60, subtitle, 13, color=MUTED)


def flow(diagram):
    slug=diagram['slug'];steps=diagram['steps'];width=800;height=128+len(steps)*92
    s=svg_start(slug,diagram['title'],diagram['desc'],width,height)+header(diagram['title'],diagram['subtitle'],width)
    for i in range(len(steps)-1):
        s+=f'<line x1="400" y1="{144+i*92}" x2="400" y2="{172+i*92}" stroke="{MUTED}" marker-end="url(#{slug}-arrow)"/>'
    for i,step in enumerate(steps):
        y=88+i*92;focal=i==diagram['focal']
        s+=f'<rect x="160" y="{y}" width="480" height="56" rx="6" fill="{("#EEF3FB" if focal else PAPER)}" stroke="{ACCENT if focal else RULE}"/>'
        for k,line in enumerate(step):s+=text(400,y+24+k*20,line,15)
    s+=text(400,height-20,diagram['footer'],12,color=MUTED)+'</svg>'
    lines=['@startuml',f'title {diagram["title"]}','start']
    for step in steps:lines.append(':'+r'\n'.join(step)+';')
    lines+=['stop','@enduml']
    return s,'\n'.join(lines)+'\n'


def sequence(diagram):
    slug=diagram['slug'];actors=diagram['actors'];messages=diagram['messages'];width=200*len(actors);gap=64
    xs={a[0]:100+i*200 for i,a in enumerate(actors)}
    loop_starts={first for first,last,label in diagram.get('loops',[])}
    ys=[];cursor=184
    for i in range(len(messages)):
        if i in loop_starts:cursor+=32
        ys.append(cursor);cursor+=gap
    end=cursor; height=end+72
    s=svg_start(slug,diagram['title'],diagram['desc'],width,height)+header(diagram['title'],diagram['subtitle'],width)
    for alias,label in actors:
        x=xs[alias];s+=f'<line x1="{x}" y1="132" x2="{x}" y2="{end}" stroke="{RULE}" stroke-dasharray="5 5"/>'
    for first,last,label in diagram.get('loops',[]):
        y=ys[first]-80;h=ys[last]-ys[first]+104
        involved={actor for msg in messages[first:last+1] for actor in msg[:2]}
        left=min(xs[a] for a in involved)-12;frame_width=max(xs[a] for a in involved)+12-left
        s+=f'<rect x="{left}" y="{y}" width="{frame_width}" height="{h}" fill="none" stroke="{RULE}"/>'
        s+=f'<rect x="{left+8}" y="{y-10}" width="{frame_width-16}" height="22" fill="white"/>'+text(left+16,y+6,'Повтор: '+label,12,anchor='start',color=ACCENT)
    for i,(a,b,label,kind) in enumerate(messages):
        y=ys[i];x1=xs[a];x2=xs[b];dash=' stroke-dasharray="6 4"' if kind=='return' else ''
        if a==b:
            s+=f'<path d="M{x1},{y} h48 v20 h-48" fill="none" stroke="{MUTED}"{dash} marker-end="url(#{slug}-arrow)"/>'
        else:s+=f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{MUTED}"{dash} marker-end="url(#{slug}-arrow)"/>'
        cx=(x1+x2)/2
        label_lines=textwrap.wrap(label,width=max(24,int(abs(x2-x1)/8)))
        if a==b:cx=x1+100
        boxw=max(len(t) for t in label_lines)*7.2+20;boxh=18*len(label_lines)+8
        s+=f'<rect x="{cx-boxw/2}" y="{y-boxh-8}" width="{boxw}" height="{boxh}" fill="white"/>'
        for k,t in enumerate(label_lines):s+=text(cx,y-boxh+8+k*18,t,16)
    for alias,label in actors:
        x=xs[alias];s+=f'<rect x="{x-88}" y="88" width="176" height="44" rx="6" fill="white" stroke="{RULE}"/>'
        for k,t in enumerate(label):s+=text(x,108+k*16,t,16)
    s+=text(width/2,height-40,diagram['footer'],13,color=MUTED)+text(width/2,height-18,'Сплошная стрелка — вызов; пунктирная — ответ. Время идёт сверху вниз.',12,color=MUTED)+'</svg>'
    lines=['@startuml',f'title {diagram["title"]}','hide footbox','skinparam backgroundColor white','skinparam shadowing false','skinparam sequenceArrowColor #65758B','skinparam sequenceLifeLineBorderColor #C9D3DF','skinparam sequenceParticipantBorderColor #C9D3DF','skinparam sequenceParticipantBackgroundColor white']
    for alias,label in actors:lines.append('participant "'+r'\n'.join(label)+'" as '+alias)
    starts={first:label for first,last,label in diagram.get('loops',[])};ends={last for first,last,label in diagram.get('loops',[])}
    for i,(a,b,label,kind) in enumerate(messages):
        if i in starts:lines.append('loop '+starts[i])
        lines.append(a+(' --> ' if kind=='return' else ' -> ')+b+' : '+label)
        if i in ends:lines.append('end')
    lines+=['note over '+actors[0][0]+', '+actors[-1][0]+' : '+diagram['footer'],'@enduml']
    return s,'\n'.join(lines)+'\n'


diagrams=json.loads((ROOT/'descriptions.json').read_text())

for d in diagrams:
    svg,puml=(flow if d['type']=='flow' else sequence)(d)
    (ROOT/(d['slug']+'.svg')).write_text(svg)
    (ROOT/(d['slug']+'.puml')).write_text(puml)
sections=''.join(f'<section id="{d["slug"]}"><h2>{escape(d["title"])}</h2>'+ (ROOT/(d['slug']+'.svg')).read_text()+'</section>' for d in diagrams)
nav=''.join(f'<a href="#{d["slug"]}">{escape(d["title"])}</a>' for d in diagrams)
(ROOT/'preview.html').write_text('<!doctype html><html lang="ru"><meta charset="utf-8"><title>AS-IS / TO-BE — диаграммы</title><style>body{font:16px Arial;color:#243247;background:white;margin:24px}nav{display:flex;flex-wrap:wrap;gap:20px}section{padding:20px 0;border-top:1px solid #C9D3DF;margin-top:24px}svg{max-width:100%;height:auto}a{color:#2E5AA8}</style><h1>Подготовка корпуса · AS-IS / TO-BE</h1><p>SVG отрисованы локально. TO-BE — проект; компиляция PlantUML не выполнялась.</p><nav>'+nav+'</nav>'+sections+'</html>')
print(f'Generated {len(diagrams)} SVG and PlantUML sources and local preview.')
