import concurrent.futures,hashlib,json,multiprocessing,os,pathlib,subprocess,sys,tempfile,unittest
from pomerado_inbox.store import *
J='job_'+'a'*32

def payload(**kw):return json.dumps(dict(id=J,status='succeeded',result_status='available',result={'value':42},**kw)).encode()
def compete(root,barrier,q):
    def remote(j):q.put('read');return payload()
    barrier.wait();q.put(capture(root,J,remote))
class Tests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=self.tmp.name
 def tearDown(self):self.tmp.cleanup()
 def test_capture_local_repeat(self):
    calls=[]
    def remote(j):calls.append(j);return payload()
    self.assertEqual(capture(self.root,J,remote),'captured');self.assertEqual(capture(self.root,J,remote),'captured');self.assertEqual(len(calls),1);self.assertEqual(read(self.root,J),{'value':42})
 def test_null_is_data(self):
    b=json.dumps({'id':J,'status':'succeeded','result_status':'available','result':None}).encode();capture(self.root,J,lambda j:b);self.assertIsNone(read(self.root,J))
 def test_empty_result_is_data(self):
    for value in (False,0,[],{},''):
     with tempfile.TemporaryDirectory() as root:
      b=json.dumps({'id':J,'status':'succeeded','result_status':'available','result':value}).encode();capture(root,J,lambda j:b);self.assertEqual(read(root,J),value)
 def test_crash_before_save_no_retry(self):
    with self.assertRaises(RuntimeError):capture(self.root,J,lambda j:payload(),fault='after_response')
    self.assertEqual(recover(self.root,J),'uncertain');self.assertEqual(capture(self.root,J,lambda j:self.fail()),'uncertain')
 def test_crash_after_spool_local_recovery(self):
    with self.assertRaises(RuntimeError):capture(self.root,J,lambda j:payload(),fault='after_spool')
    self.assertEqual(recover(self.root,J),'captured');self.assertEqual(read(self.root,J),{'value':42})
 def test_hard_exit_after_fsync(self):
    register(self.root,J)
    code="from pomerado_inbox.store import *;import os;root="+repr(self.root)+";j="+repr(J)+";raw="+repr(payload())+";\nwith connect(root) as db:db.execute(\"UPDATE jobs SET state='receiving',token='crash' WHERE id=?\",(j,))\natomic(root,j+'-crash.json',raw);os._exit(17)"
    p=subprocess.run([sys.executable,'-c',code]);self.assertEqual(p.returncode,17);self.assertEqual(recover(self.root,J),'captured')
 def test_hard_exit_without_bytes_uncertain(self):
    register(self.root,J)
    with connect(self.root) as db:db.execute("UPDATE jobs SET state='receiving',token='lost' WHERE id=?",(J,))
    self.assertEqual(recover(self.root,J),'uncertain')
 def test_process_contention_one_read(self):
    register(self.root,J);ctx=multiprocessing.get_context('fork');barrier=ctx.Barrier(5);q=ctx.Queue();ps=[ctx.Process(target=compete,args=(self.root,barrier,q)) for _ in range(5)]
    for p in ps:p.start()
    for p in ps:p.join(10);self.assertEqual(p.exitcode,0)
    values=[q.get(timeout=2) for _ in range(6)];self.assertEqual(values.count('read'),1);self.assertEqual(read(self.root,J),{'value':42})
 def test_corrupt_local_bytes(self):
    capture(self.root,J,lambda j:payload());path=pathlib.Path(status(self.root)[0]['path']);path.write_bytes(b'bad')
    with self.assertRaises(ValueError):read(self.root,J)
 def test_identity_mismatch(self):
    with self.assertRaises(ValueError):capture(self.root,J,lambda j:b'{"id":"other"}')
    self.assertEqual(status(self.root)[0]['state'],'uncertain')
 def test_invalid_json(self):
    with self.assertRaises(ValueError):capture(self.root,J,lambda j:b'{broken')
    self.assertEqual(status(self.root)[0]['state'],'uncertain')
 def test_remote_errors_uncertain(self):
    def remote(j):raise TimeoutError()
    with self.assertRaises(TimeoutError):capture(self.root,J,remote)
    self.assertEqual(status(self.root)[0]['state'],'uncertain')
 def test_pending_not_result(self):
    b=json.dumps({'id':J,'status':'running','result':None}).encode();self.assertEqual(capture(self.root,J,lambda j:b),'pending')
 def test_delivered_is_unavailable(self):
    b=json.dumps({'id':J,'status':'succeeded','result_status':'delivered','result':None}).encode();self.assertEqual(capture(self.root,J,lambda j:b),'unavailable')
 def test_failed_no_rerun(self):
    b=json.dumps({'id':J,'status':'failed','result':None}).encode();self.assertEqual(capture(self.root,J,lambda j:b),'failed');self.assertEqual(capture(self.root,J,lambda j:self.fail()),'failed')
 def test_needs_input_no_answer(self):
    b=json.dumps({'id':J,'status':'needs_input','result':None}).encode();self.assertEqual(capture(self.root,J,lambda j:b),'needs_attention')
 def test_unknown_state(self):
    b=json.dumps({'id':J,'status':'future-state','result':None}).encode();self.assertEqual(capture(self.root,J,lambda j:b),'needs_attention')
 def test_files_explicit_hold(self):
    b=json.dumps({'id':J,'status':'succeeded','result':{'doc':{'$file':{'download_url':'https://example.com'}}}}).encode();self.assertEqual(capture(self.root,J,lambda j:b),'needs_attention')
    with self.assertRaises(ValueError):deliver(self.root,J,'c')
 def test_no_ready_evidence(self):
    b=json.dumps({'id':J,'status':'succeeded','result':None}).encode();self.assertEqual(capture(self.root,J,lambda j:b),'needs_attention')
 def test_outbox_redelivery_same_token(self):
    capture(self.root,J,lambda j:payload());a=deliver(self.root,J,'etl');b=deliver(self.root,J,'etl');self.assertEqual(a,b);acknowledge(self.root,J,'etl',a['delivery_token']);self.assertIsNone(deliver(self.root,J,'etl'));self.assertEqual(read(self.root,J),{'value':42})
 def test_outbox_consumer_isolation(self):
    capture(self.root,J,lambda j:payload());a=deliver(self.root,J,'a');b=deliver(self.root,J,'b');acknowledge(self.root,J,'a',a['delivery_token']);self.assertIsNotNone(deliver(self.root,J,'b'));self.assertNotEqual(a['delivery_token'],b['delivery_token'])
 def test_bad_ack(self):
    capture(self.root,J,lambda j:payload());deliver(self.root,J,'c')
    with self.assertRaises(ValueError):acknowledge(self.root,J,'c','wrong')
 def test_id_path_traversal(self):
    for j in ('../secrets','job_../x',J+'/../x'):
     with self.assertRaises(ValueError):register(self.root,j)
 def test_file_modes(self):
    capture(self.root,J,lambda j:payload());self.assertEqual(os.stat(status(self.root)[0]['path']).st_mode &0o777,0o600)
 def test_symlink_rejected(self):
    capture(self.root,J,lambda j:payload());p=pathlib.Path(status(self.root)[0]['path']);other=pathlib.Path(self.root)/'other';other.write_bytes(p.read_bytes());p.unlink();p.symlink_to(other)
    with self.assertRaises(ValueError):read(self.root,J)
if __name__=='__main__':unittest.main()
