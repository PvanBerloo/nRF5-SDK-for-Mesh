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
 
class Interface:
    composition_data_event = threading.Event()
    provision_complete_event = threading.Event()

    address_queue = queue.Queue(1)
    devkey_queue = queue.Queue(1)

    def __init__(self, port):
        self.db = MeshDB("database/example_database.json")

        self.device = Interactive(Uart(port))
        self.device.acidev.add_packet_recipient(self._event_handler)
 
        self.provisioner = Provisioner(self.device, self.db)
 
        self.cc = ConfigurationClient(self.db)
        self.device.model_add(self.cc)

    def start_scan(self):
        self.provisioner.scan_start()

    def stop_scan(self):
        self.provisioner.scan_stop()

    def get_unprovisioned_devices(self):
        uuids = []
        for i in range(len(self.provisioner.unprov_list)):
            uuids.append(self.provisioner.unprov_list[i])
        return uuids

    def get_nodes(self):
        return self.db.nodes

    def provision(self, _uuid):
        # remove old nodes with same UUID as new node
        self.db.nodes = [n for n in self.db.nodes if n.UUID.hex() != _uuid.hex()]

        self.provisioner.provision(uuid = _uuid)
        self.provisioner.unprov_list.remove(_uuid)

        self.provision_complete_event.wait()
        self.provision_complete_event.clear()

    def unprovision(self, unicast):
        node = self._find_node(unicast)

        devkey_handle, address_handle = self._get_handles(node)

        self.cc.publish_set(devkey_handle, address_handle)
        self.cc.node_reset()

        self._free_handles(devkey_handle, address_handle)
            
        self.db.nodes.remove(node)
        self.db.store()

    def client_set_publish(self, client_address, element, modelid, publish_address):
        node = self._find_node_int(client_address)

        devkey_handle, address_handle = self._get_handles(node)
 
        self.cc.publish_set(devkey_handle, address_handle)
        self.cc.model_publication_set(node.unicast_address + element, mt.ModelId(modelid), mt.Publish(publish_address, index = 0, ttl = 1))

        self._free_handles(devkey_handle, address_handle)

    def server_set_subscribe(self, server_address, element, modelid, subscribe_address):
        node = self._find_node_int(server_address)

        devkey_handle, address_handle = self._get_handles(node)
 
        self.cc.publish_set(devkey_handle, address_handle)
        self.cc.model_subscription_delete_all(node.unicast_address + element, mt.ModelId(modelid))
        self.cc.model_subscription_add(node.unicast_address + element, subscribe_address, mt.ModelId(modelid))

        self._free_handles(devkey_handle, address_handle)
 
    def _find_node(self, src):
        for node in self.db.nodes:
            if node.unicast_address == src:
                return node
        return None

    def _find_node_int(self, src):
        for node in self.db.nodes:
            if int(node.unicast_address) == src:
                return node
        return None

    def _get_handles(self, node):
        self.device.send(cmd.DevkeyAdd(node.unicast_address, 0, node.device_key))
        self.device.send(cmd.AddrPublicationAdd(node.unicast_address))
 
        address_handle = self.address_queue.get()
        devkey_handle = self.devkey_queue.get()
 
        print('Got handle for node:', node.unicast_address, 'devkey_handle:', devkey_handle, 'address_handle:', address_handle)

        return (devkey_handle, address_handle)

    def _free_handles(self, devkey_handle, address_handle):
        self.device.send(cmd.DevkeyDelete(devkey_handle))
        self.device.send(cmd.AddrPublicationRemove(address_handle))
 
    def _event_handler(self, event):
        thread = threading.Thread(target = self._event_handler_thread, args=(event, ))
        thread.start()  
 
    def _event_handler_thread(self, event):
        if event._opcode == evt.Event.PROV_COMPLETE:
            print('Node provisioned with address:', hex(event._data["address"]))

            address_handle = self.address_queue.get()
            devkey_handle = self.devkey_queue.get()
 
            unicast_address = event._data["address"]

            print('Got handle for node:', unicast_address, 'devkey_handle:', devkey_handle, 'address_handle:', address_handle)
 
            self.cc.publish_set(devkey_handle, address_handle)
            self.cc.appkey_add(0)

            time.sleep(1)
 
            self.cc.composition_data_get()
       
            # wait for composition data
            self.composition_data_event.wait()
            self.composition_data_event.clear()
            print("Received composition data.")

            # bind appkey 0 to all models
            node = self._find_node(unicast_address)
            for element in node.elements:
                for model in element.models:
                    if model.model_id.model_id >= 0x1000:
                        time.sleep(0.1)
                        self.cc.model_app_bind(unicast_address + element.index, 0, model.model_id)

            time.sleep(0.5)

            self.db.store()

            self._free_handles(devkey_handle, address_handle)

            self.provision_complete_event.set()

        if event._opcode == evt.Event.CMD_RSP:
            result = cmd.response_deserialize(event)
            if type(result) is cmd.AddrPublicationAddRsp:
                self.address_queue.put(result._data["address_handle"])
            if type(result) is cmd.DevkeyAddRsp:
                self.devkey_queue.put(result._data["devkey_handle"])

        if event._opcode == evt.Event.MESH_MESSAGE_RECEIVED_UNICAST:
            opcode = access.opcode_from_message_get(event._data["data"])          

            if (self.cc._COMPOSITION_DATA_STATUS.serialize() == opcode):
                self.composition_data_event.set()

                