import sys
 
if sys.version_info < (3, 5):
    print(("ERROR: To use {} you need at least Python 3.5.\n" +
           "You are currently using Python {}.{}").format(sys.argv[0], *sys.version_info))
    sys.exit(1)
 

import os
import queue
import threading
import time
 
from aci.aci_uart import Uart
from aci.aci_utils import STATUS_CODE_LUT
from aci.aci_config import ApplicationConfig
import aci.aci_cmd as cmd
import aci.aci_evt as evt
 
from mesh import access
from mesh.provisioning import Provisioner, Provisionee  # NOQA: ignore unused import
from mesh import types as mt                            # NOQA: ignore unused import
from mesh.database import MeshDB                        # NOQA: ignore unused import
from models.config import ConfigurationClient           # NOQA: ignore unused import
from models.generic_on_off import GenericOnOffClient    # NOQA: ignore unused import
 
class Logger:
    def __init__(self):
        self.info = self.void
        self.error = print
 
    def void(*args):
        return
 
 
class Interactive(object):
    DEFAULT_APP_KEY = bytearray([0xAA] * 16)
    DEFAULT_SUBNET_KEY = bytearray([0xBB] * 16)
    DEFAULT_VIRTUAL_ADDRESS = bytearray([0xCC] * 16)
    DEFAULT_STATIC_AUTH_DATA = bytearray([0xDD] * 16)
    DEFAULT_LOCAL_UNICAST_ADDRESS_START = 0x0001
    CONFIG = ApplicationConfig(
        header_path=os.path.join(os.path.dirname(sys.argv[0]),
                                 ("../../examples/serial/include/"
                                  + "nrf_mesh_config_app.h")))
    PRINT_ALL_EVENTS = True
 
    def __init__(self, acidev):
        self.acidev = acidev
        self._event_filter = []
        self._event_filter_enabled = True
        self._other_events = []
 
        self.logger = Logger()
        self.send = self.acidev.write_aci_cmd
 
        # Increment the local unicast address range
        # for the next Interactive instance
        self.local_unicast_address_start = (
            self.DEFAULT_LOCAL_UNICAST_ADDRESS_START)
        Interactive.DEFAULT_LOCAL_UNICAST_ADDRESS_START += (
            self.CONFIG.ACCESS_ELEMENT_COUNT)
 
        self.access = access.Access(self, self.local_unicast_address_start,
                                    self.CONFIG.ACCESS_ELEMENT_COUNT)
        self.model_add = self.access.model_add
 
        # Adding the packet recipient will start dynamic behavior.
        # We add it after all the member variables has been defined
        self.acidev.add_packet_recipient(self.__event_handler)
 
    def close(self):
        self.acidev.stop()
 
    def events_get(self):
        return self._other_events
 
    def event_filter_add(self, event_filter):
        self._event_filter += event_filter
 
    def event_filter_disable(self):
        self._event_filter_enabled = False
 
    def event_filter_enable(self):
        self._event_filter_enabled = True
 
    def device_port_get(self):
        return self.acidev.serial.port
 
    def quick_setup(self):
        self.send(cmd.SubnetAdd(0, bytearray(self.DEFAULT_SUBNET_KEY)))
        self.send(cmd.AppkeyAdd(0, 0, bytearray(self.DEFAULT_APP_KEY)))
        self.send(cmd.AddrLocalUnicastSet(
            self.local_unicast_address_start,
            self.CONFIG.ACCESS_ELEMENT_COUNT))
 
    def __event_handler(self, event):
        if self._event_filter_enabled and event._opcode in self._event_filter:
            # Ignore event
            return
        if event._opcode == evt.Event.DEVICE_STARTED:
            self.logger.info("Device rebooted.")
 
        elif event._opcode == evt.Event.CMD_RSP:
            if event._data["status"] != 0:
                self.logger.error("{}: {}".format(
                    cmd.response_deserialize(event),
                    STATUS_CODE_LUT[event._data["status"]]["code"]))
            else:
                text = str(cmd.response_deserialize(event))
                if text == "None":
                    text = "Success"
                self.logger.info(text)
        else:
            if self.PRINT_ALL_EVENTS and event is not None:
                self.logger.info(str(event._event_name))
            else:
                self._other_events.append(event)
 
 
composition_data_event = threading.Event()

address_queue = queue.Queue(1)
devkey_queue = queue.Queue(1)
 
def find_node(src):
        for node in db.nodes:
            if node.unicast_address == src:
                return node

def get_handles(node):
    device.send(cmd.DevkeyAdd(node.unicast_address, 0, node.device_key))
    device.send(cmd.AddrPublicationAdd(node.unicast_address))
 
    address_handle = address_queue.get()
    devkey_handle = devkey_queue.get()
 
    print('Got handle for node:', node.unicast_address, 'devkey_handle:', devkey_handle, 'address_handle:', address_handle)

    return (devkey_handle, address_handle)

def free_handles(devkey_handle, address_handle):
    device.send(cmd.DevkeyDelete(devkey_handle))
    device.send(cmd.AddrPublicationRemove(address_handle))
 
def event_handler(event):
    thread = threading.Thread(target = event_handler_thread, args=(event, ))
    thread.start()  
 
def event_handler_thread(event):
    if event._opcode == evt.Event.PROV_COMPLETE:
        print('Node provisioned with address:', hex(event._data["address"]))

        address_handle = address_queue.get()
        devkey_handle = devkey_queue.get()
 
        unicast_address = event._data["address"]

        print('Got handle for node:', unicast_address, 'devkey_handle:', devkey_handle, 'address_handle:', address_handle)
 
        cc.publish_set(devkey_handle, address_handle)
        cc.appkey_add(0)

        time.sleep(1)
 
        cc.composition_data_get()
       
        # wait for composition data
        composition_data_event.wait()
        composition_data_event.clear()
        print("Received composition data.")

        # bind appkey 0 to all models
        node = find_node(unicast_address)
        for element in node.elements:
            for model in element.models:
                cc.model_app_bind(unicast_address + element.index, 0, model.model_id)

        #cc.model_publication_set(unicast_address, mt.ModelId(0x0002), mt.Publish(0x0001, index=0, ttl=1))

        time.sleep(1)

        db.store()

        free_handles(devkey_handle, address_handle)

    if event._opcode == evt.Event.CMD_RSP:
        result = cmd.response_deserialize(event)
        if type(result) is cmd.AddrPublicationAddRsp:
            address_queue.put(result._data["address_handle"])
        if type(result) is cmd.DevkeyAddRsp:
            devkey_queue.put(result._data["devkey_handle"])

    if event._opcode == evt.Event.MESH_MESSAGE_RECEIVED_UNICAST:
        opcode = access.opcode_from_message_get(event._data["data"])

        if (cc._COMPOSITION_DATA_STATUS.serialize() == opcode):
            composition_data_event.set()

        print(opcode)
 
def print_commands():
    print('0 - show this.')
    print('1 - scan for unprovisioned devices.')
    print('2 - stop scanning for unprovisioned devices.')
    print('3 - list unprovisioned devices.')
    print('4 - provision device.')
    print('5 - list nodes.')
    print('6 - set publish address of client.')
    print('7 - set subscribe address of server.')
    print('8 - unprovision node.')
   
db = MeshDB("database/example_database.json")

if len(sys.argv) < 2:
    print("ERROR: no comport specified.")
    sys.exit(1)
 
device = Interactive(Uart(sys.argv[1]))
device.acidev.add_packet_recipient(event_handler)
 
p = Provisioner(device, db)
 
cc = ConfigurationClient(db)
device.model_add(cc)
 
print_commands()
print()
 
while True:
    keycode = input('Enter command code: ')
 
    if keycode == '0':
        print_commands()
 
    if keycode == '1':
        print("Scanning for unprovisioned devices...")
        p.scan_start()
 
    if keycode == '2':
        p.scan_stop()
        print("Scan stopped.")
       
    if keycode == '3':
        print('Unprovisioned devices:')
        for i in range(len(p.unprov_list)):
            print('[' + str(i) + '] - UUID:', p.unprov_list[i].hex())
 
    if keycode == '4':
        i = int(input('Enter the index of the unprovisioned device: '))
 
        if (-1 < i < len(p.unprov_list)):
            # remove old nodes with same UUID as new node
            db.nodes = [n for n in db.nodes if n.UUID.hex() != p.unprov_list[i].hex()]

            p.provision(uuid = p.unprov_list[i])
            p.unprov_list.pop(i)
        else:
            print('Invalid index.')
 
    if keycode == '5':
        print('Nodes:')
        for i in range(len(db.nodes)):
            print('[' + str(i) + '] - Unicast address:', hex(db.nodes[i].unicast_address))      
 
    if keycode == '6':
        client_id = int(input('Client ID: '))
        client_unicast_address = db.nodes[client_id].unicast_address

        n = db.nodes[client_id]

        devkey_handle, address_handle = get_handles(n)
 
        cc.publish_set(devkey_handle, address_handle)
        cc.model_publication_set(client_unicast_address + 1, mt.ModelId(0x1001), mt.Publish(50000, index=0, ttl=1))

        free_handles(devkey_handle, address_handle)

    if keycode == '7':
        server_id = int(input('Server ID: '))
        server_unicast_address = db.nodes[server_id].unicast_address

        n = db.nodes[server_id]

        devkey_handle, address_handle = get_handles(n)
 
        cc.publish_set(devkey_handle, address_handle)
        cc.model_subscription_delete_all(server_unicast_address, mt.ModelId(0x1000))
        cc.model_subscription_add(server_unicast_address, 50000, mt.ModelId(0x1000))

        free_handles(devkey_handle, address_handle)
 
    if keycode == '8':
        i = int(input('Enter the index of the node: '))
 
        if (-1 < i < len(db.nodes)):
            n = db.nodes[i]

            devkey_handle, address_handle = get_handles(n)

            cc.publish_set(devkey_handle, address_handle)
            cc.node_reset()

            free_handles(devkey_handle, address_handle)
            
            db.nodes.pop(i)
        else:
            print('Invalid index.')
   
    print()