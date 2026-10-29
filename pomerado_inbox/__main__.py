import argparse,json,os,sys
from .store import register,status,capture,recover,read,deliver,acknowledge
from .api import Pomerado
from .files import capture_files,recover_files
p=argparse.ArgumentParser(description='Local capture for existing Pomerado JSON jobs. No new runs or automatic retries.')
p.add_argument('--root',required=True);sub=p.add_subparsers(dest='command',required=True)
sub.add_parser('status')
for cmd in ['peek','capture','recover','read','recover-files']:
 c=sub.add_parser(cmd);c.add_argument('job')
c=sub.add_parser('deliver');c.add_argument('job');c.add_argument('consumer')
c=sub.add_parser('files');c.add_argument('job');c.add_argument('--allow-host',action='append',required=True)
c=sub.add_parser('ack');c.add_argument('job');c.add_argument('consumer');c.add_argument('token')
a=p.parse_args();api=Pomerado(os.environ.get('POMERADO_API_KEY'))
if a.command=='status':value=status(a.root)
elif a.command=='peek':value=json.loads(api.get(a.job,False))
elif a.command=='capture':value=capture(a.root,a.job,api.get)
elif a.command=='recover':value=recover(a.root,a.job)
elif a.command=='read':value=read(a.root,a.job)
elif a.command=='deliver':value=deliver(a.root,a.job,a.consumer)
elif a.command=='recover-files':value=recover_files(a.root,a.job)
elif a.command=='files':value=capture_files(a.root,a.job,set(a.allow_host))
else:value=acknowledge(a.root,a.job,a.consumer,a.token)
print(json.dumps(value,indent=2))
