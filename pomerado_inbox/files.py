"""Single-use file capture. Never follows redirects or forwards the API credential."""
import hashlib,ipaddress,json,os,pathlib,re,socket,urllib.parse,urllib.request,uuid
from .store import atomic,connect,event

def descriptors(value):
    if isinstance(value,dict):
        if '$file' in value:yield value['$file']
        for k,v in value.items():
            if k!='$file':yield from descriptors(v)
    elif isinstance(value,list):
        for v in value:yield from descriptors(v)

def validate(meta,allowed_hosts,max_bytes=16*1024*1024):
    ident=meta.get('id','');size=meta.get('size');sha=meta.get('sha256','');u=urllib.parse.urlsplit(meta.get('download_url',''))
    if not re.fullmatch(r'file_[0-9a-f]{32}',ident):raise ValueError('invalid file id')
    if not isinstance(size,int) or isinstance(size,bool) or size<0 or size>max_bytes:raise ValueError('invalid or oversized file')
    if not re.fullmatch(r'[0-9a-f]{64}',sha):raise ValueError('invalid sha256')
    if u.scheme!='https' or u.hostname not in allowed_hosts or u.username or u.password or u.port not in (None,443) or u.fragment:raise ValueError('download URL must be HTTPS on an explicitly allowed host')
    # The allowlist is an owner configuration, not learned from result content.
    for item in socket.getaddrinfo(u.hostname,443,type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(item[4][0]).is_global:raise ValueError('nonpublic download address')
    return ident,size,sha

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def download(url,limit):
    # Separate no-auth opener. File URL contains a bearer capability; never log it.
    opener=urllib.request.build_opener(NoRedirect(),urllib.request.ProxyHandler({}))
    with opener.open(urllib.request.Request(url,headers={'Accept':'application/octet-stream'}),timeout=30) as response:
        data=response.read(limit+1)
        if response.status!=200 or len(data)>limit:raise ValueError('unexpected download response or too large')
        return data

def capture_files(root,job,allowed_hosts,fetch=download,resolve=True,fault=None):
    with connect(root) as db:
        db.execute('CREATE TABLE IF NOT EXISTS files(job TEXT NOT NULL,id TEXT NOT NULL,state TEXT NOT NULL,token TEXT,path TEXT,sha256 TEXT,PRIMARY KEY(job,id))')
        r=db.execute('SELECT * FROM jobs WHERE id=?',(job,)).fetchone()
    if not r or r['state']!='needs_attention' or not r['path']:raise ValueError('no held file response')
    raw=pathlib.Path(r['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=r['sha256']:raise ValueError('response hash mismatch')
    metas=list(descriptors(json.loads(raw).get('result')))
    if not metas:raise ValueError('no file descriptors')
    # Validate the full set before consuming any links. Supplying a custom fetch is test-only.
    entries=[]
    for meta in metas:
        if resolve:ident,size,sha=validate(meta,allowed_hosts)
        else:
            # Only reachable by Python test callers, never exposed on CLI.
            ident=meta['id'];size=meta['size'];sha=meta['sha256']
            if not re.fullmatch(r'file_[0-9a-f]{32}',ident):raise ValueError('invalid file id')
        entries.append((meta,ident,size,sha))
    for meta,ident,size,sha in entries:
        token=uuid.uuid4().hex
        with connect(root) as db:
            db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT * FROM files WHERE job=? AND id=?',(job,ident)).fetchone()
            if old:db.rollback();continue
            db.execute("INSERT INTO files VALUES(?,?,'receiving',?,NULL,?)",(job,ident,token,sha));db.commit()
        try:
            data=fetch(meta['download_url'],size)
            if fault=='after_response':raise RuntimeError('injected file loss before spool')
            path=atomic(root,ident+'-'+token+'.blob',data)
            if fault=='after_spool':raise RuntimeError('injected file crash after fsync')
            if len(data)!=size or hashlib.sha256(data).hexdigest()!=sha:raise ValueError('file integrity mismatch')
            with connect(root) as db:db.execute("UPDATE files SET state='captured',path=? WHERE job=? AND id=? AND token=?",(str(path.resolve()),job,ident,token))
        except Exception:
            with connect(root) as db:db.execute("UPDATE files SET state='uncertain' WHERE job=? AND id=? AND token=?",(job,ident,token))
            raise
    with connect(root) as db:return [dict(r) for r in db.execute('SELECT id,state,path,sha256 FROM files WHERE job=?',(job,))]

def recover_files(root,job):
    """Recover complete verified spool bytes only. Never fetch a capability again."""
    with connect(root) as db:
        db.execute('CREATE TABLE IF NOT EXISTS files(job TEXT NOT NULL,id TEXT NOT NULL,state TEXT NOT NULL,token TEXT,path TEXT,sha256 TEXT,PRIMARY KEY(job,id))')
        r=db.execute('SELECT * FROM jobs WHERE id=?',(job,)).fetchone()
        files=[dict(f) for f in db.execute("SELECT * FROM files WHERE job=? AND state IN ('receiving','uncertain')",(job,))]
    if not r:raise ValueError('unknown job')
    raw=pathlib.Path(r['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=r['sha256']:raise ValueError('response hash mismatch')
    metas={m['id']:m for m in descriptors(json.loads(raw).get('result'))}
    for f in files:
        path=pathlib.Path(root)/'responses'/(f['id']+'-'+f['token']+'.blob');meta=metas[f['id']]
        ok=False
        if path.exists() and not path.is_symlink():
            data=path.read_bytes();ok=len(data)==meta['size'] and hashlib.sha256(data).hexdigest()==meta['sha256']
        with connect(root) as db:db.execute('UPDATE files SET state=?,path=? WHERE job=? AND id=?',('captured' if ok else 'uncertain',str(path.resolve()) if ok else None,job,f['id']))
    with connect(root) as db:return [dict(f) for f in db.execute('SELECT id,state,path,sha256 FROM files WHERE job=?',(job,))]
