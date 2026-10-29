import base64,hashlib,hmac,json,tempfile,unittest
from pomerado_inbox.webhooks import receive,drain
from pomerado_inbox.store import status
J='job_'+'d'*32;E='evt_'+'e'*32;SECRET='whsec_'+base64.b64encode(b'x'*32).decode()
class Hooks(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=self.tmp.name;self.body=json.dumps({'id':E,'type':'job.succeeded','data':{'job_id':J}}).encode()
 def tearDown(self):self.tmp.cleanup()
 def headers(self,body=None,t=1000):
    body=self.body if body is None else body;stamp=str(t);ident='delivery-id';sig=base64.b64encode(hmac.new(b'x'*32,ident.encode()+b'.'+stamp.encode()+b'.'+body,hashlib.sha256).digest()).decode();return {'webhook-id':ident,'webhook-timestamp':stamp,'webhook-signature':'v1,'+sig}
 def accept(self):return receive(self.root,self.body,self.headers(),SECRET,now=1000)
 def test_durable_duplicate(self):self.assertFalse(self.accept()['duplicate']);self.assertTrue(self.accept()['duplicate'])
 def test_signature_rejected(self):
    h=self.headers();h['webhook-signature']='v1,wrong'
    with self.assertRaises(ValueError):receive(self.root,self.body,h,SECRET,now=1000)
 def test_replay_old(self):
    with self.assertRaises(ValueError):receive(self.root,self.body,self.headers(t=1),SECRET,now=1000)
 def test_future(self):
    with self.assertRaises(ValueError):receive(self.root,self.body,self.headers(t=9999),SECRET,now=1000)
 def test_tamper(self):
    with self.assertRaises(ValueError):receive(self.root,self.body+b' ',self.headers(),SECRET,now=1000)
 def test_no_remote_read_before_ack(self):self.accept();self.assertEqual(status(self.root),[])
 def test_drain_and_repeat(self):
    self.accept();calls=[]
    def remote(j):calls.append(j);return json.dumps({'id':J,'status':'succeeded','result_status':'available','result':42}).encode()
    self.assertEqual(drain(self.root,remote)[0]['state'],'captured');self.assertEqual(drain(self.root,remote),[]);self.assertEqual(len(calls),1)
 def test_same_id_conflict(self):
    self.accept();body=self.body+b' '
    with self.assertRaises(ValueError):receive(self.root,body,self.headers(body),SECRET,now=1000)
 def test_unknown_event_ignored(self):
    body=json.dumps({'id':E,'type':'job.future','data':{}}).encode();receive(self.root,body,self.headers(body),SECRET,now=1000);self.assertEqual(drain(self.root,lambda j:self.fail()),[])
 def test_rotation_signature(self):
    h=self.headers();h['webhook-signature']='v1,oldwrong '+h['webhook-signature'];self.assertTrue(receive(self.root,self.body,h,SECRET,now=1000)['accepted'])
 def test_oversized(self):
    with self.assertRaises(ValueError):receive(self.root,b'x'*65537,self.headers(),SECRET,now=1000)
 def test_invalid_job_id(self):
    body=json.dumps({'id':E,'type':'job.succeeded','data':{'job_id':'../../secret'}}).encode()
    with self.assertRaises(ValueError):receive(self.root,body,self.headers(body),SECRET,now=1000)
if __name__=='__main__':unittest.main()
