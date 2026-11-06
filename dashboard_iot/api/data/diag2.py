import urllib.request, json, urllib.parse
mac = '80:F3:DA:4B:2A:DC'
ALL_MQTT_METRICS = 'sysctrl_.+|event_cnt_.+|event_handling_.+|machine_time_.+|heatpress_.+'
q = f'count({{__name__=~"{ALL_MQTT_METRICS}",MAC=~"(?i){mac}"}})'
url = 'http://prometheus:9090/api/v1/query?query=' + urllib.parse.quote(q)
r = urllib.request.urlopen(url, timeout=5)
data = json.loads(r.read())['data']['result']
print(data)
