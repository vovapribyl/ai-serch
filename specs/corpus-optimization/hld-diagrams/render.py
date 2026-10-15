"""Documentation renderer; SVG is local layout, not PlantUML compilation."""
from pathlib import Path
import json
from html import escape
ROOT=Path(__file__).resolve().parent
# Reuse the existing document sequence layout, without its generation entrypoint.
layout=(ROOT.parent/'diagrams/render.py').read_text().split('diagrams=json.loads')[0]
exec(layout)
ROOT=Path(__file__).resolve().parent

def architecture(d):
    slug=d['slug'];width=d.get('width',800);height=d.get('height',805)
    out=svg_start(slug,d['title'],d['desc'],width,height)+header(d['title'],d['subtitle'],width)
    if d.get('zone','default') is not None:
        out+='<rect x="30" y="170" width="740" height="590" rx="10" fill="#FAFBFD" stroke="#C9D3DF"/>'
    for edge in d['edges']:
        a,b,path,x,y,label=edge[:6]
        kind=edge[6] if len(edge)>6 else 'uses'
        dash=' stroke-dasharray="6 4"' if kind=='implements' else ''
        out+=f'<path d="{path}" fill="none" stroke="{MUTED}"{dash} marker-end="url(#{slug}-arrow)"/>'
        w=len(label)*7+18
        out+=f'<rect x="{x-w/2}" y="{y-15}" width="{w}" height="20" fill="white"/>'+text(x,y,label,13)
    for alias,x,y,w,h,lines in d['nodes']:
        focal=alias in ('supervisor','core')
        out+=f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{("#EEF3FB" if focal else "white")}" stroke="{ACCENT if focal else RULE}"/>'
        for i,line in enumerate(lines):out+=text(x+w/2,y+24+i*19,line,15)
    out+=text(width/2,height-20,d['footer'],11,color=MUTED)+'</svg>'
    pu=['@startuml',f'title {d["title"]}','skinparam backgroundColor white','skinparam shadowing false']
    for alias,x,y,w,h,lines in d['nodes']:pu.append('component "'+r'\n'.join(lines)+'" as '+alias)
    for edge in d['edges']:
        a,b,path,x,y,label=edge[:6]
        kind=edge[6] if len(edge)>6 else 'uses'
        pu.append(a+(' ..> ' if kind=='implements' else ' --> ')+b+' : '+label)
    pu+=['@enduml']
    return out,'\n'.join(pu)+'\n'

ds=json.loads((ROOT/'descriptions.json').read_text())
for d in ds:
    svg,pu=architecture(d) if d['type']=='architecture' else sequence(d)
    (ROOT/(d['slug']+'.svg')).write_text(svg)
    (ROOT/(d['slug']+'.puml')).write_text(pu)
sections=''.join('<section id="'+d['slug']+'"><h2>'+escape(d['title'])+'</h2>'+(ROOT/(d['slug']+'.svg')).read_text()+'</section>' for d in ds)
(ROOT/'preview.html').write_text('<!doctype html><html lang="ru"><meta charset="utf-8"><title>HLD пополнения</title><style>body{font:16px Arial;color:#243247;margin:24px;background:white}svg{max-width:100%;height:auto}section{margin:24px 0;border-top:1px solid #C9D3DF}</style><h1>HLD пополнения · APPROVED_BY_OWNER</h1><p>Локальный SVG layout; PlantUML не компилировался.</p>'+sections+'</html>')
print(f'Generated {len(ds)} HLD SVG / PlantUML sources')
