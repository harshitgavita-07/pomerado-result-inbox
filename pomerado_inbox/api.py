import json,urllib.error,urllib.request
from .store import valid_id
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None
class Pomerado:
    """Read existing jobs only. No tool runs, writes, sign-ins, answers or retries."""
    def __init__(self,key=None):self.key=key;self.opener=urllib.request.build_opener(NoRedirect())
    def get(self,ident,include_result=True):
        valid_id(ident)
        headers={'Accept':'application/json'}
        if self.key:headers['Authorization']='Bearer '+self.key
        request=urllib.request.Request('https://api.pomerado.ai/v1/jobs/'+ident+'?include_result='+str(include_result).lower(),headers=headers)
        with self.opener.open(request,timeout=30) as response:
            # Exact bytes are persisted by the caller before parsing. Bound memory use.
            data=response.read(4*1024*1024+1)
            if len(data)>4*1024*1024:raise ValueError('response over4MiB; result delivery may be uncertain')
            if response.status!=200:raise ValueError('unexpected HTTP response')
            return data
