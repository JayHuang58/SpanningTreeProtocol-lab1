'''
Ethernet learning switch in Python.

Note that this file currently has the code to implement a "hub"
in it, not a learning switch.  (I.e., it's currently a switch
that doesn't learn.)
'''
from switchyard.lib.userlib import *
from collections import OrderedDict


class LRUCache:

    def __init__(self):
        self.capacity = 5
        self.cache = OrderedDict()
        self.port2addre = dict()

    def get(self, ethaddr):
        if ethaddr in self.cache:
            port_name = self.cache.pop(ethaddr)
            self.cache[ethaddr] = port_name
            return port_name
        else:
            return None

    def insert(self, ethaddr, port_name):

        if port_name in self.port2addre:
            old_addr = self.port2addre[port_name]
            self.port2addre.pop(port_name)
            self.cache.pop(old_addr)
        self.port2addre[port_name] = ethaddr

        if ethaddr in self.cache:
            self.cache[ethaddr] = port_name
        else:
            if len(self.cache) >= self.capacity:
                self.cache.popitem(last=False)
            self.cache[ethaddr] = port_name


def main(net):
    my_interfaces = net.interfaces()
    mymacs = [intf.ethaddr for intf in my_interfaces]
    my_LRUCache = LRUCache()

    while True:
        try:
            timestamp, input_port, packet = net.recv_packet()
        except NoPackets:
            continue
        except Shutdown:
            return

        my_LRUCache.insert(packet[0].src, input_port)
        log_debug("In {} received packet {} on {}".format(net.name, packet, input_port))
        if packet[0].dst in mymacs:
            log_debug("Packet intended for me")
        else:
            dest_port = my_LRUCache.get(packet[0].dst)
            if dest_port is not None:
                net.send_packet(dest_port, packet)
            else:
                for intf in my_interfaces:
                    if input_port != intf.name:
                        log_debug("Flooding packet {} to {}".format(packet, intf.name))
                        net.send_packet(intf.name, packet)

    net.shutdown()