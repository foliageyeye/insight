import requests
import sys
import json
import base64
if len(sys.argv) < 4:
    exit("usage:\n  python client.py location_id event_type event_factor snapshot.png")
name1 = sys.argv[4]

try:
    f1 = open(name1)
    data1 = base64.b64encode(f1.read())
except:
    data1 = None
payload1 = {"location_id": sys.argv[1], "event_type": sys.argv[2],
            "event_factor": sys.argv[3], "snapshot": data1}

try:
    requests.post("http://127.0.0.1:8888/api", data=json.dumps(payload1))

except:
    print "Post request error!"
