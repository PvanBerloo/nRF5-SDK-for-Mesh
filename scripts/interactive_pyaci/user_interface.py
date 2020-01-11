import sys
import time

from interface import Interface
 
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

if len(sys.argv) < 2:
    print("ERROR: no comport specified.")
    sys.exit(1)
 
interface = Interface(sys.argv[1])
 
print_commands()
print()
 
while True:
    keycode = input('Enter command code: ')
 
    if keycode == '0':
        print_commands()
 
    if keycode == '1':
        print("Scanning for unprovisioned devices...")
        interface.start_scan()
 
    if keycode == '2':
        interface.stop_scan()
        print("Scan stopped.")
       
    if keycode == '3':
        print('Unprovisioned devices:')

        unprov_list = interface.get_unprovisioned_devices()
        for i in range(len(unprov_list)):
            print('[' + str(i) + '] - UUID:', unprov_list[i].hex())
 
    if keycode == '4':
        i = int(input('Enter the index of the unprovisioned device: '))
 
        unprov_list = interface.get_unprovisioned_devices()
        if (-1 < i < len(unprov_list)):
            interface.provision(unprov_list[i])
        else:
            print('Invalid index.')
 
    if keycode == '5':
        nodes = interface.get_nodes()
        print('Nodes:')
        for i in range(len(nodes)):
            print('[' + str(i) + '] - Unicast address:', hex(nodes[i].unicast_address))      
 
    if keycode == '6':
        client_id = int(input('Client ID: '))
        client_unicast_address = interface.get_nodes()[client_id].unicast_address

        interface.client_set_publish(int(client_unicast_address), 1, 0x1001, 50000)

    if keycode == '7':
        server_id = int(input('Server ID: '))
        server_unicast_address = interface.get_nodes()[server_id].unicast_address

        interface.server_set_subscribe(int(server_unicast_address), 0, 0x1000, 50000)
 
    if keycode == '8':
        i = int(input('Enter the index of the node: '))
 
        nodes = interface.get_nodes()
        if (-1 < i < len(nodes)):
            interface.unprovision(nodes[i].unicast_address)
        else:
            print('Invalid index.')
   
    print()