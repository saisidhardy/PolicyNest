"""Trusted local CLI: account provisioning, assignment, and recovery. Never exposed as public registration."""
import argparse
import getpass
import secrets
import os
import auth
import workflows


def main():
    if not os.environ.get('JWT_SECRET') and not os.environ.get('APP_NAME'):
        from pathlib import Path
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
        from run_local import configure
        configure()
    p=argparse.ArgumentParser();p.add_argument('action',choices=['provision','assign','reset-password','cases']);p.add_argument('--email');p.add_argument('--role',choices=['reviewer','admin','ops'],default='reviewer');p.add_argument('--case');p.add_argument('--reviewer',type=int)
    a=p.parse_args()
    if a.action=='provision':
        password=getpass.getpass('New account password (12+ characters): ')
        user=auth.register(a.email,password,'PolicyNest '+a.role)
        with auth._db() as db:db.execute('UPDATE users SET role=? WHERE id=?',(a.role,user['id']))
        print('Account provisioned. ID:',user['id'],'role:',a.role)
    elif a.action=='assign':
        workflows.assign({'id':0,'role':'admin'},a.case,a.reviewer);print('Assignment recorded.')
    elif a.action=='cases':
        workflows.init()
        with auth._db() as db:
            for row in db.execute('SELECT id,status,reviewer_id FROM cases'):print(dict(row))
    else:
        password=getpass.getpass('Replacement password (12+ characters): ')
        token=auth.create_reset(a.email)
        if token:auth.reset_password(token,password)
        print('Recovery processed if the account exists.')


if __name__=='__main__':main()
