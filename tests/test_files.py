import hashlib,json,pathlib,tempfile,unittest
from unittest.mock import patch
from pomerado_inbox.store import capture,status,connect
from pomerado_inbox.files import capture_files,validate,recover_files
J='job_'+'b'*32;F='file_'+'c'*32
class Files(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=self.tmp.name;self.data=b'hello file';self.meta={'id':F,'size':len(self.data),'sha256':hashlib.sha256(self.data).hexdigest(),'download_url':'https://files.example.com/download/opaque','name':'../../escape'}
 def tearDown(self):self.tmp.cleanup()
 def hold(self):return capture(self.root,J,lambda j:json.dumps({'id':J,'status':'succeeded','result':{'receipt':{'$file':self.meta}}}).encode())
 def test_recover_after_file_fsync(self):
    self.hold()
    with self.assertRaises(RuntimeError):capture_files(self.root,J,set(),lambda u,n:self.data,False,'after_spool')
    self.assertEqual(recover_files(self.root,J)[0]['state'],'captured')
 def test_recover_missing_stays_uncertain(self):
    self.hold()
    with self.assertRaises(RuntimeError):capture_files(self.root,J,set(),lambda u,n:self.data,False,'after_response')
    self.assertEqual(recover_files(self.root,J)[0]['state'],'uncertain')
 def test_hash_and_size_verified(self):
    self.hold();r=capture_files(self.root,J,set(),lambda u,n:self.data,False);self.assertEqual(r[0]['state'],'captured');self.assertEqual(pathlib.Path(r[0]['path']).read_bytes(),self.data);self.assertNotIn('escape',r[0]['path'])
 def test_no_duplicate_download(self):
    self.hold();calls=[]
    def fetch(u,n):calls.append(1);return self.data
    capture_files(self.root,J,set(),fetch,False);capture_files(self.root,J,set(),fetch,False);self.assertEqual(len(calls),1)
 def test_bad_hash_uncertain_no_retry(self):
    self.hold()
    with self.assertRaises(ValueError):capture_files(self.root,J,set(),lambda u,n:b'bad',False)
    self.assertEqual(capture_files(self.root,J,set(),lambda u,n:self.fail(),False)[0]['state'],'uncertain')
 def test_crash_after_response_not_retried(self):
    self.hold()
    with self.assertRaises(RuntimeError):capture_files(self.root,J,set(),lambda u,n:self.data,False,'after_response')
    self.assertEqual(capture_files(self.root,J,set(),lambda u,n:self.fail(),False)[0]['state'],'uncertain')
 def test_no_capability_url_in_db(self):
    self.hold();capture_files(self.root,J,set(),lambda u,n:self.data,False)
    with connect(self.root) as db:serialized=str([tuple(r) for r in db.execute('SELECT * FROM files')])
    self.assertNotIn('/download/opaque',serialized)
 def test_private_address_block(self):
    with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
     with self.assertRaises(ValueError):validate(self.meta,{'files.example.com'})
 def test_public_address_allowed(self):
    with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('1.1.1.1',443))]):self.assertEqual(validate(self.meta,{'files.example.com'})[0],F)
 def test_unlisted_host_blocked(self):
    with self.assertRaises(ValueError):validate(self.meta,set())
 def test_http_credentials_and_fragments_rejected(self):
    for u in ['http://files.example.com/x','https://x:y@files.example.com/x','https://files.example.com:8080/x','https://files.example.com/x#token']:
     with self.assertRaises(ValueError):validate(dict(self.meta,download_url=u),{'files.example.com'})
 def test_invalid_hash_size_and_id_rejected(self):
    for k,v in [('size',True),('size',-1),('size',100000000),('sha256','bad'),('id','../../x')]:
     with self.assertRaises(ValueError):validate(dict(self.meta,**{k:v}),{'files.example.com'})
 def test_validate_all_before_download(self):
    self.hold()
    with self.assertRaises(ValueError):capture_files(self.root,J,set(),lambda u,n:self.fail())
if __name__=='__main__':unittest.main()
