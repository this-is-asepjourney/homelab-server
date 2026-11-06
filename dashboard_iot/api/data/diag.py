import urllib.request, urllib.parse, json

prom = 'http://prometheus:9090'

def prom_query(q):
    url = prom + '/api/v1/query?query=' + urllib.parse.quote(q)
    try:
        r = urllib.request.urlopen(url, timeout=5)
        return json.loads(r.read())['data']['result']
    except Exception as e:
        return str(e)

all_metrics = "sysctrl_.+|event_cnt_.+|event_handling_.+|machine_time_.+|heatpress_.+"
q = f'{{__name__=~"{all_metrics}"}}'
print("All metrics for device:")
for r in prom_query(q):
    print("Metric name:", r['metric']['__name__'])
    print("Labels:", r['metric'])
    print("---")
