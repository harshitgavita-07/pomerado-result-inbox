import contextlib,hashlib,json,os,pathlib,re,sqlite3,time,uuid

@contextlib.contextmanager
def connect(root):
    root=pathlib.Path(root);root.mkdir(parents=True,exist_ok=True,mode=0o700)
    db=sqlite3.connect(root/'inbox.db',timeout=15,isolation_level=None);db.row_factory=sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA synchronous=FULL')
    db.executescript('''CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,state TEXT NOT NULL,token TEXT,path TEXT,sha256 TEXT,reason TEXT);
    CREATE TABLE IF NOT EXISTS deliveries(consumer TEXT NOT NULL,job TEXT NOT NULL,state TEXT NOT NULL,token TEXT,PRIMARY KEY(consumer,job));
    CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY,at REAL NOT NULL,job TEXT NOT NULL,kind TEXT NOT NULL);
    ''')
    os.chmod(root/'inbox.db',0o600)
    try:yield db
    finally:db.close()

def event(db,ident,kind):db.execute('INSERT INTO events(at,job,kind) VALUES(?,?,?)',(time.time(),ident,kind))
def valid_id(ident):
    if not re.fullmatch(r'job_[0-9a-f]{32}',ident):raise ValueError('invalid Pomerado job id')
def register(root,ident):
    valid_id(ident)
    with connect(root) as db:db.execute("INSERT OR IGNORE INTO jobs(id,state) VALUES(?,'pending')",(ident,))
def status(root):
    with connect(root) as db:return [dict(r) for r in db.execute('SELECT * FROM jobs ORDER BY rowid')]
def atomic(root,name,data):
    root=pathlib.Path(root);folder=root/'responses';folder.mkdir(exist_ok=True,mode=0o700)
    target=folder/name;temp=folder/(name+'.part-'+uuid.uuid4().hex)
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(temp,target)
        fd=os.open(folder,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:temp.unlink(missing_ok=True)
    return target

def has_files(value):
    if isinstance(value,dict):return '$file' in value or any(has_files(v) for v in value.values())
    if isinstance(value,list):return any(has_files(v) for v in value)
    return False

def classify(job):
    if job.get('status') in {'queued','running'}:return 'pending',''
    if job.get('status') in {'needs_input','paused'}:return 'needs_attention','job needs owner input; no answer sent'
    if job.get('result_status') in {'delivered','expired'} and job.get('result') is None:return 'unavailable','remote result already delivered or expired'
    if job.get('result_file') or (isinstance(job.get('build'),dict) and job['build'].get('example_result_file')) or has_files(job.get('result')):return 'needs_attention','file result preserved as metadata; single-use file bytes not downloaded'
    if job.get('status')=='succeeded' and job.get('result_status') not in {'delivered','expired'}:
        # null can be a real JSON output. Presence of the field plus available status matters.
        if 'result' in job and (job['result'] is not None or job.get('result_status') in {'available','ready'}):return 'captured',''
        return 'needs_attention','succeeded without usable result evidence'
    if job.get('status') in {'failed','cancelled'}:return 'failed','remote job failed or cancelled; no rerun'
    return 'needs_attention','unrecognized job state; raw response retained'

def capture(root,ident,transport,fault=None):
    """At most one destructive read per registered job; unresolved reads never auto-repeat."""
    register(root,ident);token=uuid.uuid4().hex
    with connect(root) as db:
        db.execute('BEGIN IMMEDIATE');r=db.execute('SELECT * FROM jobs WHERE id=?',(ident,)).fetchone()
        if r['state']!='pending':db.rollback();return r['state']
        db.execute("UPDATE jobs SET state='receiving',token=? WHERE id=?",(token,ident));event(db,ident,'receive_started');db.commit()
    try:
        raw=transport(ident)
        if fault=='after_response':raise RuntimeError('injected crash after remote response before local save')
        path=atomic(root,ident+'-'+token+'.json',raw)
        if fault=='after_spool':raise RuntimeError('injected interruption after durable spool')
        return settle(root,ident,token,path,raw)
    except Exception:
        with connect(root) as db:
            db.execute("UPDATE jobs SET state='uncertain',reason='read may have consumed remote result; inspect durable spool before any retry' WHERE id=? AND token=? AND state='receiving'",(ident,token));event(db,ident,'receive_uncertain')
        raise

def settle(root,ident,token,path,raw):
    parsed=json.loads(raw)
    if not isinstance(parsed,dict) or parsed.get('id')!=ident:raise ValueError('response job identity mismatch')
    state,reason=classify(parsed);digest=hashlib.sha256(raw).hexdigest()
    with connect(root) as db:
        db.execute('BEGIN IMMEDIATE')
        r=db.execute('SELECT * FROM jobs WHERE id=?',(ident,)).fetchone()
        if not r or r['token']!=token or r['state'] not in {'receiving','uncertain'}:db.rollback();raise ValueError('stale capture')
        db.execute('UPDATE jobs SET state=?,path=?,sha256=?,reason=? WHERE id=?',(state,str(path.resolve()),digest,reason,ident));event(db,ident,state);db.commit()
    return state

def recover(root,ident):
    """Recover only already-fsynced exact-attempt bytes; never contact the API."""
    with connect(root) as db:r=db.execute('SELECT * FROM jobs WHERE id=?',(ident,)).fetchone()
    if not r or r['state'] not in {'receiving','uncertain'}:return r['state'] if r else None
    path=pathlib.Path(root)/'responses'/(ident+'-'+r['token']+'.json')
    if not path.exists():
        with connect(root) as db:db.execute("UPDATE jobs SET state='uncertain',reason='no durable response; reconcile remotely, never auto-rerun' WHERE id=?",(ident,))
        return 'uncertain'
    return settle(root,ident,r['token'],path,path.read_bytes())

def read(root,ident):
    with connect(root) as db:r=db.execute('SELECT * FROM jobs WHERE id=?',(ident,)).fetchone()
    if not r or r['state']!='captured':raise ValueError('no captured JSON result')
    expected=pathlib.Path(root).resolve()/'responses'/(ident+'-'+r['token']+'.json')
    if pathlib.Path(r['path'])!=expected or expected.is_symlink():raise ValueError('invalid spool path')
    raw=expected.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=r['sha256']:raise ValueError('local response changed')
    return json.loads(raw)['result']

def deliver(root,ident,consumer):
    """Durable local outbox offer. Caller must dedupe/commit effects before acknowledge."""
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',consumer):raise ValueError('invalid consumer')
    result=read(root,ident)
    with connect(root) as db:
        db.execute('BEGIN IMMEDIATE');r=db.execute('SELECT * FROM deliveries WHERE consumer=? AND job=?',(consumer,ident)).fetchone()
        if r and r['state']=='acked':db.rollback();return None
        token=r['token'] if r else uuid.uuid4().hex
        db.execute("INSERT OR IGNORE INTO deliveries VALUES(?,?,'offered',?)",(consumer,ident,token));db.commit()
    return {'job_id':ident,'consumer':consumer,'delivery_token':token,'result':result}

def acknowledge(root,ident,consumer,token):
    with connect(root) as db:
        n=db.execute("UPDATE deliveries SET state='acked' WHERE consumer=? AND job=? AND token=? AND state='offered'",(consumer,ident,token)).rowcount
        if not n:raise ValueError('unknown/already-acked delivery token')
