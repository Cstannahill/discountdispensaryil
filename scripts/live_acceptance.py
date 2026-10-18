"""Run actual discovery/import through the local API and retain measured outcomes."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--zip', default='61358')
    parser.add_argument('--radius', type=int, default=50)
    parser.add_argument('--output', default='data/live-acceptance.json')
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=60, trust_env=False) as client:
        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()
        origin = request('POST', '/api/v1/locations/resolve', json={'query': args.zip})
        payload = {key: origin.get(key) for key in ('latitude','longitude','label','precision','source_url')}
        region = request('POST', '/api/v1/regions', json=dict(payload, radius_miles=args.radius))
        job = request('POST', '/api/v1/sync/runs', json={'region_id':region['id'],'discover':True})
        print(json.dumps({'region':region,'run_id':job['id'],'status':job['status']}), flush=True)
        previous = -1
        while job['status'] in ('queued','running'):
            time.sleep(3)
            job = request('GET', job['status_url'])
            if len(job['results']) != previous:
                for result in job['results'][max(previous,0):]:
                    print(json.dumps({k:result.get(k) for k in ('stage','store_name','provider','status','source_count','error','errors') if result.get(k) is not None}),flush=True)
                previous = len(job['results'])
        coverage = request('GET','/api/v1/coverage',params={'region_id':region['id']})
        stores = request('GET','/api/v1/dispensaries',params={'region_id':region['id'],'page_size':200})
        report = {'checked_at_utc':datetime.now(timezone.utc).isoformat(),'region':region,'job':job,'coverage':coverage,'stores':stores}
        target = Path(args.output)
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'status':job['status'],'counts':coverage['counts'],'report':str(target.resolve())}),flush=True)


if __name__ == '__main__':
    main()
