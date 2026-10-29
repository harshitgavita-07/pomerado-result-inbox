"""Standard Webhooks verification + transactional inbox. Never performs a result read."""
import base64,hashlib,hmac,json,re,time
from .store import connect,valid_id

def receive(root,body,headers,secret,now=None,tolerance=300):
    if len(body)>64*1024:raise ValueError('oversized webhook')
    headers={k.lower():v for k,v in headers.items()}
    ident=headers.get('webhook-id','');timestamp=headers.get('webhook-timestamp','');signatures=headers.get('webhook-signature','')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',ident):raise ValueError('invalid webhook id')
    if not timestamp.isdigit() or abs((time.time() if now is None else now)-int(timestamp))>tolerance:raise ValueError('expired webhook')
    if not secret.startswith('whsec_'):raise ValueError('invalid webhook secret')
    try:key=base64.b64decode(secret[6:],validate=True)
    except Exception:raise ValueError('invalid signing secret')
    if len(key)<16:raise ValueError('short signing secret')
    expected=base64.b64encode(hmac.new(key,ident.encode()+b'.'+timestamp.encode()+b'.'+body,hashlib.sha256).digest()).decode()
    if not any(v.startswith('v1,') and hmac.compare_digest(v[3:],expected) for v in signatures.split()):raise ValueError('invalid webhook signature')
    item=json.loads(body)
    if not isinstance(item,dict):raise ValueError('invalid webhook body')
    event_id=item.get('id','');kind=item.get('type','');job=item.get('data',{}).get('job_id')
    if not re.fullmatch(r'evt_[0-9a-f]{32}',event_id):raise ValueError('invalid event id')
    # Unknown event types are still durably acknowledged but never trigger capture.
    actionable=kind=='job.succeeded'
    if actionable:valid_id(job)
    digest=hashlib.sha256(body).hexdigest()
    with connect(root) as db:
        db.execute('CREATE TABLE IF NOT EXISTS webhooks(id TEXT PRIMARY KEY,sha256 TEXT NOT NULL,kind TEXT NOT NULL,job TEXT,state TEXT NOT NULL)')
        db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT * FROM webhooks WHERE id=?',(event_id,)).fetchone()
        if old:
            db.rollback()
            if old['sha256']!=digest:raise ValueError('same event id with different content')
            return {'accepted':True,'duplicate':True}
        db.execute('INSERT INTO webhooks VALUES(?,?,?,?,?)',(event_id,digest,kind,job if actionable else None,'queued' if actionable else 'ignored'));db.commit()
    # A handler may send204 only after this commit. Worker runs separately.
    return {'accepted':True,'duplicate':False}

def drain(root,transport):
    from .store import capture
    with connect(root) as db:
        db.execute('CREATE TABLE IF NOT EXISTS webhooks(id TEXT PRIMARY KEY,sha256 TEXT NOT NULL,kind TEXT NOT NULL,job TEXT,state TEXT NOT NULL)')
        items=[dict(r) for r in db.execute("SELECT * FROM webhooks WHERE state='queued' ORDER BY rowid")]
    results=[]
    for item in items:
        # Capture has its own exclusive claim. Duplicate events never create new runs.
        state=capture(root,item['job'],transport)
        if state not in {'pending','receiving'}:
            with connect(root) as db:db.execute("UPDATE webhooks SET state='handled' WHERE id=?",(item['id'],))
        results.append({'event_id':item['id'],'state':state})
    return results
