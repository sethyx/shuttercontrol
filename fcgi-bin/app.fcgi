#!/usr/bin/env python3

from flask import Flask, request, g
from flup.server.fcgi import WSGIServer
import rf

app = Flask(__name__)

def get_rfdevice():
    if 'rfdevice' not in g:
        g.rfdevice = rf.RFDevice()
    return g.rfdevice

@app.route('/shutter', methods = ['POST'])
def shutter_control():
    device = request.form.get('device')
    command = request.form.get('cmd')

    rfdevice = get_rfdevice()

    result = rfdevice.tx_shutter_cmd(device, command)
    return '', 200 if result else 500

if __name__ == '__main__':
    WSGIServer(app).run()
