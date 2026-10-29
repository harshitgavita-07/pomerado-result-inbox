import io,unittest,urllib.error
from unittest.mock import patch
from pomerado_inbox.api import Pomerado,NoRedirect
from pomerado_inbox.files import download
J='job_'+'f'*32
class Response(io.BytesIO):
 status=200
class APIs(unittest.TestCase):
 def test_status_only_exact_endpoint(self):
    api=Pomerado('fixture-not-secret');seen=[]
    def open(req,timeout):seen.append(req);return Response(b'{}')
    with patch.object(api.opener,'open',side_effect=open):api.get(J,False)
    self.assertEqual(seen[0].full_url,'https://api.pomerado.ai/v1/jobs/'+J+'?include_result=false');self.assertEqual(seen[0].get_method(),'GET');self.assertEqual(seen[0].get_header('Authorization'),'Bearer fixture-not-secret')
 def test_keyless_no_auth(self):
    api=Pomerado();seen=[]
    def open(req,timeout):seen.append(req);return Response(b'{}')
    with patch.object(api.opener,'open',side_effect=open):api.get(J)
    self.assertIsNone(seen[0].get_header('Authorization'))
 def test_oversized_job_response(self):
    api=Pomerado()
    with patch.object(api.opener,'open',return_value=Response(b'x'*(4*1024*1024+1))):
     with self.assertRaises(ValueError):api.get(J)
 def test_redirect_not_followed(self):self.assertIsNone(NoRedirect().redirect_request(None,None,None,None,None,None))
 def test_file_has_no_authorization(self):
    class Opener:
     def open(s,req,timeout):
      self.assertIsNone(req.get_header('Authorization'));self.assertEqual(req.get_method(),'GET');return Response(b'hello')
    with patch('urllib.request.build_opener',return_value=Opener()):self.assertEqual(download('https://files.example.com/f',5),b'hello')
 def test_file_too_large(self):
    class Opener:
     def open(s,req,timeout):return Response(b'123456')
    with patch('urllib.request.build_opener',return_value=Opener()):
     with self.assertRaises(ValueError):download('https://files.example.com/f',5)
if __name__=='__main__':unittest.main()
