'''
Ethernet learning switch in Python.
Note that this file currently has the code to implement a "hub"
in it, not a learning switch.  (I.e., it's currently a switch
that doesn't learn.)
'''
from switchyard.lib.userlib import *

def main(net):
    my_interfaces = net.interfaces() # get itself interfaces/ports
    # Ethernet address associated with the interface
    mymacs = [intf.ethaddr for intf in my_interfaces]
    send_packet
    # continuing receiving packets, and records timestamp, input_port and packet info
    while True:
        try:
            timestamp, input_port, packet = net.recv_packet() # receive packets
        except NoPackets:
            continue
        except Shutdown:
            return
        # also the net has its own name
        log_debug("In {} received packet {} on {}".format(net.name, packet, input_port))
        # the first part of packets records the destination info
        # the destination address is also an ethernet address
        if packet[0].dst in mymacs: # if .... in ....
            # the packet is for this switch
            log_debug("Packet intended for me")
        else:
            # flood the packet to all ports except the input port
            for intf in my_interfaces:
                if input_port != intf.name:
                    log_debug("Flooding packet {} to {}".format(packet, intf.name))
                    net.send_packet(intf.name, packet) # send packet by one of its ports

    # shutdown net, but it is out of the while loop
    net.shutdown()
