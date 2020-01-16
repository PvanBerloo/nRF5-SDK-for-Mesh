import json
import socket
import struct
import sys
import time

import traceback

from interface import Interface

if len(sys.argv) < 2:
    print("ERROR: no comport specified.")
    sys.exit(1)

ERROR_OK = 0
ERROR_FORMAT = 1
ERROR_NO_METHOD_FOUND = 2
ERROR_INVALID_ARGUMENTS = 3
ERROR_INTERNAL = 4

ERROR_DEVICE_NOT_FOUND = 100
ERROR_ELEMENT_NOT_FOUND = 101
ERROR_MODEL_NOT_FOUND = 102

def execute_method(request):
    method = request["method"]
    id = request["id"]

    if method == "start_scan":
        print("Scanning for unprovisioned devices...")
        _interface.start_scan()
        send_response(None, ERROR_OK, id)

    if method == "stop_scan":
        _interface.stop_scan()
        print("Scan stopped.")
        send_response(None, ERROR_OK, id)

    if method == "list_unprovisioned_devices":
        unprov_list = _interface.get_unprovisioned_devices()

        uuids = []
        for i in range(len(unprov_list)):
            uuids.append(unprov_list[i].hex())

        send_response(uuids, ERROR_OK, id)

    if method == "provision":
        if "params" in request:
            if "uuid" in request["params"]:
                unprov_list = _interface.get_unprovisioned_devices()

                for i in range(len(unprov_list)):
                    if unprov_list[i].hex() == request["params"]["uuid"]:
                        _interface.provision(unprov_list[i])
                        send_response(None, ERROR_OK, id)
                        break
                else:
                    send_response(None, ERROR_DEVICE_NOT_FOUND, id)
            else:
                send_response(None, ERROR_INVALID_ARGUMENTS, id)
        else:
            send_response(None, ERROR_INVALID_ARGUMENTS, id)

    if method == "unprovision":
        if "params" in request:
            if "unicast_address" in request["params"]:
                n = _interface.get_nodes()
                for i in range(len(n)):
                    if int(n[i].unicast_address) == request["params"]["unicast_address"]:
                        _interface.unprovision(n[i].unicast_address)
                        send_response(None, ERROR_OK, id)
                        break
                    else:
                        send_response(None, ERROR_DEVICE_NOT_FOUND, id)
            else:
                send_response(None, ERROR_INVALID_ARGUMENTS, id)
        else:
            send_response(None, ERROR_INVALID_ARGUMENTS, id)

    if method == "list_nodes":
        nodes = []
        n = _interface.get_nodes()
        for i in range(len(n)):
            node = {"unicast_address": int(n[i].unicast_address), "elements": []}

            index = 0
            for element in n[i].elements:
                e = {"index": index, "models": []}
                index += 1

                for model in element.models:
                    e["models"].append(int(model.model_id.model_id))
                node["elements"].append(e)
            nodes.append(node)

        send_response(nodes, ERROR_OK, id)

    if method == "client_set_publish":
        if "params" in request:
            params = request["params"]
            if "unicast_address" in params and "element" in params and "model_id" in params and "address" in params:
                _interface.client_set_publish(params["unicast_address"], params["element"], params["model_id"], params["address"])
                send_response(None, ERROR_OK, id)
            else:
                send_response(None, ERROR_INVALID_ARGUMENTS, id)
        else:
            send_response(None, ERROR_INVALID_ARGUMENTS, id)

    if method == "server_set_subscribe":
        if "params" in request:
            params = request["params"]
            if "unicast_address" in params and "element" in params and "model_id" in params and "address" in params:
                _interface.server_set_subscribe(params["unicast_address"], params["element"], params["model_id"], params["address"])
                send_response(None, ERROR_OK, id)
            else:
                send_response(None, ERROR_INVALID_ARGUMENTS, id)
        else:
            send_response(None, ERROR_INVALID_ARGUMENTS, id)
 
def send_response(result, error, id):
    obj = {"jsonrpc": "2.0"}
    if result is not None:
        obj["result"] = result
    obj["error"] = error
    obj["id"] = id

    string = json.dumps(obj)
    buffer = string.encode('ascii')
    message_size = struct.pack("H",len(buffer))
    #conn.sendall(message_size)
    conn.sendall(buffer)

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind(('127.0.0.1', 1234))
s.listen(1)

_interface = Interface(sys.argv[1])

while 1:
    conn, addr = s.accept()

    while 1:
        try:
            message_size = struct.unpack("H", conn.recv(2))[0]
            string = conn.recv(message_size)
        except Exception as e: 
            print(e)
            break
        
        try:
            request = json.loads(string)

            if "method" in request and "id" in request:
                execute_method(request)
            else:
                send_response(None, ERROR_FORMAT, -1)
        except Exception as e: 
            traceback.print_exc()
            send_response(None, ERROR_INTERNAL, -1)

        