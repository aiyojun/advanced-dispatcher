#!/usr/bin/python3

import sys
import requests


if __name__ == "__main__":
    if len(sys.argv) == 3:
        req = {
            "uuid": sys.argv[len(sys.argv) - 2],
            "token": sys.argv[len(sys.argv) - 1],
        }
    elif len(sys.argv) == 2:
        req = {
            "uuid": sys.argv[len(sys.argv) - 1],
        }
    else:
        req = {
            "error": "args: {}".format(str(sys.argv))
        }
    response = requests.post("http://127.0.0.1:HTTP_PORT/cron/trigger", json=req)
    print("server response: {}".format(response.content.decode('utf-8')))
