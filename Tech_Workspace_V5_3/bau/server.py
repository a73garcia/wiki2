from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
from pathlib import Path
from datetime import datetime
import os, json, html, re, uuid, mimetypes

BASE=Path(__file__).resolve().parent
DATA=BASE/'data'; DB=DATA/'requests.json'; STATIC=BASE/'static'; UPLOADS=DATA/'uploads'
DATA.mkdir(exist_ok=True); UPLOADS.mkdir(parents=True,exist_ok=True)
PORTAL_URL=os.environ.get('PORTAL_URL','http://127.0.0.1:8079')
WIKI_URL=os.environ.get('WIKI_URL','http://127.0.0.1:8080')
GESTOR_URL=os.environ.get('GESTOR_URL','http://127.0.0.1:8081')
STATUSES=['Nueva','En curso','Pendiente','Resuelta','Cerrada']
PRIORITIES=['Baja','Media','Alta','Crítica']
TYPES=['Petición','Incidencia','Consulta','Cambio','Problema']
SYSTEMS=['Cisco ESA','Proofpoint','Splunk','CrowdStrike','Microsoft','Windows','Linux','Redes','Otro']

def esc(v): return html.escape(str(v or ''),quote=True)
def load():
    try:return json.loads(DB.read_text(encoding='utf-8')) if DB.exists() else []
    except Exception:return []
def save(rows): DB.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
def now(): return datetime.now().isoformat(timespec='seconds')
def getone(rid): return next((x for x in load() if x.get('id')==rid),None)
def badge(v,kind=''): return f'<span class="badge {kind} {esc(v).lower().replace("í","i").replace("á","a").replace(" ","-")}">{esc(v)}</span>'
def options(values,current=''): return ''.join(f'<option {"selected" if x==current else ""}>{esc(x)}</option>' for x in values)

def render(text):
    s=esc(text)
    s=re.sub(r'\[azul\](.*?)\[/azul\]',r'<span class="text-blue">\1</span>',s,flags=re.S|re.I)
    s=re.sub(r'\[rojo\](.*?)\[/rojo\]',r'<span class="text-red">\1</span>',s,flags=re.S|re.I)
    s=re.sub(r'\[amarillo\](.*?)\[/amarillo\]',r'<mark>\1</mark>',s,flags=re.S|re.I)
    s=re.sub(r'\[\[imagen:([^|\]]+)(?:\|([^\]]*))?\]\]',lambda m:f'<img class="embedded-image" src="/uploads/{quote(m.group(1))}" alt="{esc(m.group(2) or m.group(1))}">',s)
    s=re.sub(r'```([^\n]*)\n(.*?)```',lambda m:f'<pre><code class="language-{esc(m.group(1).strip() or "text")}">{m.group(2)}</code></pre>',s,flags=re.S)
    s=re.sub(r'^(={2,6})\s*(.*?)\s*\1$',lambda m:f'<h{min(len(m.group(1)),6)}>{m.group(2)}</h{min(len(m.group(1)),6)}>',s,flags=re.M)
    s=re.sub(r'^!!!\s+nota\s*(.*)$',r'<div class="admonition note"><strong>Nota</strong> \1</div>',s,flags=re.M|re.I)
    s=re.sub(r'^!!!\s+advertencia\s*(.*)$',r'<div class="admonition warning"><strong>Advertencia</strong> \1</div>',s,flags=re.M|re.I)
    s=re.sub(r'\*\*(.+?)\*\*',r'<strong>\1</strong>',s,flags=re.S)
    s=re.sub(r"''(.+?)''",r'<em>\1</em>',s,flags=re.S)
    s=re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)',r'<a href="\2" target="_blank">\1</a>',s)
    lines=s.splitlines(); out=[]; para=[]; in_ul=False
    def flush():
        nonlocal para
        if para: out.append('<p>'+'<br>'.join(para)+'</p>'); para=[]
    for line in lines:
        if line.startswith(('<h','<pre','<div class="admonition','<img')):
            flush()
            if in_ul: out.append('</ul>'); in_ul=False
            out.append(line); continue
        if re.match(r'^\s*[-*]\s+',line):
            flush()
            if not in_ul: out.append('<ul>'); in_ul=True
            out.append('<li>'+re.sub(r'^\s*[-*]\s+','',line)+'</li>'); continue
        if in_ul: out.append('</ul>'); in_ul=False
        if line.strip(): para.append(line)
        else: flush()
    flush()
    if in_ul: out.append('</ul>')
    return ''.join(out)

def layout(title,body,active='bau'):
    links=[('Inicio',PORTAL_URL),('Wiki',WIKI_URL),('Proyectos y tareas',GESTOR_URL),('BAU','/')]
    nav=''.join(f'<a class="{"active" if n.lower().startswith(active) else ""}" href="{esc(u)}">{esc(n)}</a>' for n,u in links)
    return f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} · BAU</title><link rel="stylesheet" href="/static/style.css"></head><body><header><div class="brand">Tech Workspace · BAU</div><div class="header-actions"><a class="btn" href="{esc(PORTAL_URL)}">Inicio común</a><a class="btn primary" href="/new">+ Nueva BAU</a></div></header><div class="shell"><aside><nav>{nav}</nav><div class="aside-note">Aplicación local<br>Sin usuarios<br>Datos en JSON</div></aside><main>{body}</main></div><script src="/static/editor.js"></script></body></html>'''

def dashboard(qs):
    rows=load()
    status=qs.get('status',[''])[0]
    term=qs.get('q',[''])[0].strip().casefold()
    period=qs.get('period',['all'])[0]
    if period not in ('all','today'):
        period='all'
    today=datetime.now().date().isoformat()
    filtered=[r for r in rows if (period!='today' or r.get('opened')==today) and (not status or r.get('status')==status) and (not term or term in ' '.join(str(r.get(k,'')) for k in ('number','title','request','investigation','resolution','system')).casefold())]
    filtered.sort(key=lambda x:x.get('opened',''),reverse=True)
    stats=''.join(f'<a class="stat" href="/?status={quote(s)}&period={quote(period)}"><strong>{sum(1 for r in rows if r.get("status")==s and (period!="today" or r.get("opened")==today))}</strong><span>{esc(s)}</span></a>' for s in STATUSES)
    trs=''.join(f'''<tr><td><a href="/view?id={esc(r['id'])}"><strong>{esc(r.get('number'))}</strong></a></td><td class="bau-title"><a href="/view?id={esc(r['id'])}">{esc(r.get('title'))}</a></td><td>{badge(r.get('type'))}</td><td>{badge(r.get('status'))}</td><td>{badge(r.get('priority'),'priority')}</td><td>{esc(r.get('system'))}</td><td>{esc(r.get('opened'))}</td></tr>''' for r in filtered) or '<tr><td colspan="7" class="empty">No hay registros.</td></tr>'
    period_options=f'<option value="all" {"selected" if period=="all" else ""}>Todas</option><option value="today" {"selected" if period=="today" else ""}>Solo hoy</option>'
    body=f'''<div class="page-head"><div><h1>Gestión BAU</h1><p>Control de peticiones, incidencias, consultas, cambios y problemas operativos.</p></div></div><div class="stats">{stats}</div><section class="card"><form class="filters bau-filters" method="get"><input name="q" value="{esc(qs.get('q',[''])[0])}" placeholder="Número, título, sistema, solicitud o resolución"><select name="period" aria-label="Periodo">{period_options}</select><select name="status"><option value="">Todos los estados</option>{options(STATUSES,status)}</select><button class="btn">Filtrar</button><a class="btn ghost" href="/">Limpiar</a></form></section><section class="card"><div class="section-head"><h2>Registros BAU</h2><a class="btn primary" href="/new">+ Nueva BAU</a></div><div class="table-wrap"><table class="bau-table"><colgroup><col class="col-number"><col class="col-title"><col class="col-type"><col class="col-status"><col class="col-priority"><col class="col-system"><col class="col-date"></colgroup><thead><tr><th>Número</th><th>Título</th><th>Tipo</th><th>Estado</th><th>Prioridad</th><th>Sistema</th><th>Fecha</th></tr></thead><tbody>{trs}</tbody></table></div></section>'''
    return layout('Gestión BAU',body)

def editor_field(label,name,value):
    return f"""<section class="editor-block"><div class="editor-head"><h2>{label}</h2></div><div class="toolbar" data-target="{name}"><button type="button" data-insert="== Título ==&#10;">Título</button><button type="button" data-wrap="**">Negrita</button><button type="button" data-wrap="''">Cursiva</button><button type="button" data-wrap-open="[azul]" data-wrap-close="[/azul]">Azul</button><button type="button" data-wrap-open="[rojo]" data-wrap-close="[/rojo]">Rojo</button><button type="button" data-wrap-open="[amarillo]" data-wrap-close="[/amarillo]">Resaltar</button><button type="button" data-insert="- ">Lista</button><button type="button" data-indent="1">→ Tab +4</button><button type="button" data-outdent="1">← Quitar tab</button><button type="button" data-insert="!!! nota Nota importante&#10;">Nota</button><button type="button" data-insert="!!! advertencia Precaución&#10;">Advertencia</button><button type="button" data-code="spl">Código SPL</button><button type="button" data-code="python">Código Python</button><button type="button" data-image="1">🖼 Imagen</button></div><textarea id="{name}" name="{name}" rows="12">{esc(value)}</textarea><input class="bau-image-input" data-editor="{name}" type="file" accept="image/*" hidden><span class="upload-status" data-status="{name}"></span></section>"""

def form_page(r=None):
    r=r or {}; editing=bool(r)
    body=f'''<div class="page-head"><div><h1>{'Editar' if editing else 'Nueva'} BAU</h1><p>La solicitud, investigación y resolución usan el mismo editor técnico de la Wiki.</p></div></div><form class="card form" method="post" action="/save"><input type="hidden" name="id" value="{esc(r.get('id'))}"><div class="grid"><label>Número de petición o incidencia<input name="number" value="{esc(r.get('number'))}" placeholder="Ej.: INC12345, RITM-00821 o SR-ABC-77" required maxlength="80"></label><label>Fecha apertura<input type="date" name="opened" value="{esc(r.get('opened') or datetime.now().date())}" required></label><label>Estado<select name="status">{options(STATUSES,r.get('status','Nueva'))}</select></label><label>Prioridad<select name="priority">{options(PRIORITIES,r.get('priority','Media'))}</select></label><label>Tipo<select name="type">{options(TYPES,r.get('type','Petición'))}</select></label><label>Sistema<select name="system">{options(SYSTEMS,r.get('system','Otro'))}</select></label></div><label>Título / breve descripción<input name="title" value="{esc(r.get('title'))}" required maxlength="180"></label>{editor_field('Solicitud','request',r.get('request',''))}{editor_field('Investigación','investigation',r.get('investigation',''))}{editor_field('Resolución','resolution',r.get('resolution',''))}<div class="actions"><button class="btn primary">Guardar BAU</button><a class="btn ghost" href="/">Cancelar</a></div></form>'''
    return layout('Editor BAU',body)

def section(title,text): return f'<section class="card content"><h2>{title}</h2>{render(text or "Sin información.")}</section>'
def view_page(r):
    comments=''.join(f'<li><strong>{esc(c.get("date"))}</strong><div>{render(c.get("text",""))}</div></li>' for c in reversed(r.get('comments',[]))) or '<li class="empty">Sin comentarios.</li>'
    body=f'''<div class="page-head"><div><div class="eyebrow">{esc(r.get('number'))}</div><h1>{esc(r.get('title'))}</h1><div class="badges">{badge(r.get('type'))}{badge(r.get('status'))}{badge(r.get('priority'),'priority')}{badge(r.get('system'))}</div></div><div><a class="btn" href="/edit?id={esc(r['id'])}">Editar</a> <form class="inline" method="post" action="/delete" onsubmit="return confirm('¿Eliminar esta BAU?')"><input type="hidden" name="id" value="{esc(r['id'])}"><button class="btn danger">Eliminar</button></form></div></div><div class="meta-grid"><div><strong>Fecha de apertura</strong><span>{esc(r.get('opened'))}</span></div><div><strong>Última actualización</strong><span>{esc(r.get('updated') or '—')}</span></div></div>{section('Solicitud',r.get('request'))}{section('Investigación',r.get('investigation'))}{section('Resolución',r.get('resolution'))}<section class="card"><h2>Seguimiento</h2><form method="post" action="/comment"><input type="hidden" name="id" value="{esc(r['id'])}"><textarea name="text" rows="4" required placeholder="Añadir avance, respuesta, incidencia o decisión..."></textarea><button class="btn primary">Añadir comentario</button></form><ul class="timeline">{comments}</ul></section>'''
    return layout(r.get('number','BAU'),body)

class Handler(BaseHTTPRequestHandler):
    def send_html(self,s,status=200):
        b=s.encode(); self.send_response(status); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def redirect(self,u): self.send_response(303); self.send_header('Location',u); self.end_headers()
    def read_form(self):
        n=int(self.headers.get('Content-Length','0') or 0); return {k:v[-1] for k,v in parse_qs(self.rfile.read(n).decode('utf-8','replace'),keep_blank_values=True).items()}
    def multipart(self,max_size=15*1024*1024):
        ct=self.headers.get('Content-Type',''); m=re.search(r'boundary="?([^";]+)',ct); n=int(self.headers.get('Content-Length','0') or 0)
        if not m or n<=0 or n>max_size:return {},[]
        raw=self.rfile.read(n); boundary=('--'+m.group(1)).encode(); fields={}; files=[]
        for part in raw.split(boundary):
            if b'\r\n\r\n' not in part: continue
            head,body=part.split(b'\r\n\r\n',1); body=body.rstrip(b'\r\n-'); nm=re.search(br'name="([^"]+)"',head)
            if not nm: continue
            name=nm.group(1).decode('utf-8','replace'); fm=re.search(br'filename="([^"]*)"',head)
            if fm:
                fn=Path(fm.group(1).decode('utf-8','replace')).name
                if fn: files.append((name,fn,body))
            else: fields[name]=body.decode('utf-8','replace')
        return fields,files
    def do_GET(self):
        u=urlparse(self.path); qs=parse_qs(u.query)
        if u.path=='/': return self.send_html(dashboard(qs))
        if u.path=='/new': return self.send_html(form_page())
        if u.path in ('/view','/edit'):
            r=getone(qs.get('id',[''])[0])
            if not r:return self.send_error(404)
            return self.send_html(form_page(r) if u.path=='/edit' else view_page(r))
        if u.path.startswith('/static/'):
            p=(STATIC/u.path.removeprefix('/static/')).resolve()
            if STATIC.resolve() not in p.parents or not p.is_file(): return self.send_error(404)
            b=p.read_bytes(); self.send_response(200); self.send_header('Content-Type',mimetypes.guess_type(p)[0] or 'application/octet-stream'); self.send_header('Content-Length',str(len(b))); self.end_headers(); return self.wfile.write(b)
        if u.path.startswith('/uploads/'):
            p=(UPLOADS/Path(u.path).name).resolve()
            if UPLOADS.resolve() not in p.parents or not p.is_file():return self.send_error(404)
            b=p.read_bytes(); self.send_response(200); self.send_header('Content-Type',mimetypes.guess_type(p)[0] or 'application/octet-stream'); self.send_header('Content-Length',str(len(b))); self.end_headers(); return self.wfile.write(b)
        self.send_error(404)
    def do_POST(self):
        u=urlparse(self.path)
        if u.path=='/upload-image':
            _,files=self.multipart()
            if not files:return self.send_html(json.dumps({'ok':False,'error':'No se recibió ninguna imagen.'}),400)
            _,fn,data=files[0]; ext=Path(fn).suffix.lower()
            if ext not in ('.png','.jpg','.jpeg','.gif','.webp'):return self.send_html(json.dumps({'ok':False,'error':'Formato no permitido.'}),400)
            stored=f'{uuid.uuid4().hex}{ext}'; (UPLOADS/stored).write_bytes(data)
            payload=json.dumps({'ok':True,'filename':stored},ensure_ascii=False).encode(); self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(payload))); self.end_headers(); return self.wfile.write(payload)
        if u.path=='/save':
            f=self.read_form(); rows=load(); rid=f.get('id') or uuid.uuid4().hex; old=next((x for x in rows if x.get('id')==rid),{})
            r={**old,**{k:f.get(k,'').strip() for k in ('number','opened','status','priority','type','system','title','request','investigation','resolution')}}
            if not r.get('number'): return self.send_html(layout('Número obligatorio','<section class="card"><h1>Falta el número</h1><p>Introduce manualmente el número de petición o incidencia.</p><a class="btn" href="javascript:history.back()">Volver</a></section>'),400)
            r['id']=rid; r['created']=old.get('created') or now(); r['updated']=now(); r.setdefault('comments',[])
            rows=[x for x in rows if x.get('id')!=rid]+[r]; save(rows); return self.redirect('/view?id='+rid)
        f=self.read_form(); rid=f.get('id',''); rows=load(); r=next((x for x in rows if x.get('id')==rid),None)
        if u.path=='/comment' and r:
            r.setdefault('comments',[]).append({'date':now(),'text':f.get('text','').strip()}); r['updated']=now(); save(rows); return self.redirect('/view?id='+rid)
        if u.path=='/delete':
            save([x for x in rows if x.get('id')!=rid]); return self.redirect('/')
        self.send_error(404)
    def log_message(self,*args): pass

if __name__=='__main__': ThreadingHTTPServer(('127.0.0.1',int(os.environ.get('BAU_PORT','8082'))),Handler).serve_forever()
