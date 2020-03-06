from switchyard.lib.userlib import *
from SpanningTreeMessage import SpanningTreeMessage
from collections import OrderedDict
import time


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


class G:
    blocked_interfaces = set()
    my_LRUCache = LRUCache()


# it is the spanning tree message packet
# the source can be anything but the destination should be ff:ff:ff:ff:ff:ff to broadcast all ports
def mk_stp_pkt(root_id, hops, switch_id, source="20:00:00:00:00:01", destination="ff:ff:ff:ff:ff:ff"):
    spm = SpanningTreeMessage(root_id=root_id, hops_to_root=hops, switch_id=switch_id)
    Ethernet.add_next_header_class(EtherType.SLOW, SpanningTreeMessage)
    # spanning tree message packet construction, header and spm
    pkt = Ethernet(src=source, dst=destination, ethertype=EtherType.SLOW) + spm
    xbytes = pkt.to_bytes()
    p = Packet(raw=xbytes)
    return p


def send_stp(net, root_switch_id, hops, switchid, interfaces):
    """
    it will only send packets to non_block interfaces
    """
    # flood the packet to all non_block ports
    for intf in interfaces:
        if intf.name in G.blocked_interfaces:
            continue
        new_stp_pkt = mk_stp_pkt(root_switch_id, hops, switchid, intf.ethaddr)
        log_debug("Flooding packet {} on {}".format(new_stp_pkt, intf.name))
        net.send_packet(intf.name, new_stp_pkt)  # send packet by one of its ports


def main(net):
    my_interfaces = net.interfaces() # get itself interfaces/ports
    # Ethernet address associated with the interface
    mymacs = [intf.ethaddr for intf in my_interfaces]
    reset = False
    # the smallest MAC address is the switch id
    switchid = mymacs[0]
    root_interface = -1  # don't know root interface
    for mac in mymacs:
        if switchid > mac:
            switchid = mac
    # at the beginning, rootid is the switchid
    root_switch_id = switchid
    # default hops is 0
    hops = 0
    # default
    original_incoming_interface = -1

    # flood the packet to all ports
    send_stp(net, root_switch_id, hops, switchid, my_interfaces)

    # continuing receiving packets, and records timestamp, input_port and packet info
    # need to distinguish packets, whether it is a normal packet or a spm packet
    while True:
        try:
            timestamp, incoming_interface, packet = net.recv_packet(timeout=2)  # receive packets
            log_debug("every incoming interface is "+ incoming_interface)
        except NoPackets:
            # if it is the root switch, it needs to send out stp packet to all non_block interfaces
            if switchid == root_switch_id:
                G.blocked_interfaces = set()
                send_stp(net, root_switch_id, hops, switchid, my_interfaces)
                # if it is the root switch, record the making time
                last_stp_time = time.time()
            continue
        except Shutdown:
            return
        # also the net has its own name
        log_debug("In {} received packet {} on {}".format(net.name, packet, incoming_interface))
        # if it is the root switch and time period before last stp time is larger than 2 seconds
        if switchid == root_switch_id and time.time() - last_stp_time >= 2:
            G.blocked_interfaces = set()
            send_stp(net, root_switch_id, hops, switchid, my_interfaces)
            # if it is the root switch, record the making time
            last_stp_time = time.time()

        # more than 10 seconds, it needs to reset all values
        if time.time() - last_stp_time >= 10:
            log_debug("reset")
            # at the beginning, rootid is the switchid
            root_switch_id = switchid
            # default hops is 0
            hops = 0
            G.blocked_interfaces = set()

        packet_type = packet[Ethernet].ethertype
        if packet_type == EtherType.SLOW:
            log_debug("check point 1")
            # it receives spm, don't need to reset
            # it is the spm packet
            spm = packet[SpanningTreeMessage]
            # if the packet knows a smaller switch id, vote it as the root switch id
            # if incoming_interface is same as root_interface
            if spm.root < root_switch_id or incoming_interface == root_interface:
                log_debug("check point 2")
                # select root switch
                root_switch_id = spm.root

                hops = spm.hops_to_root+1
                log_debug("incoming interface is: " + incoming_interface)

                if spm.root < root_switch_id:
                    G.blocked_interfaces = set() # reset all ports to unblock state

                root_interface = incoming_interface
                #TODO REMOVE??
                G.blocked_interfaces.add(incoming_interface)
                original_incoming_interface = incoming_interface
                send_stp(net, root_switch_id, hops, switchid, my_interfaces)
                # point 8, also need to update time
                last_stp_time = time.time()

            if spm.root > root_switch_id:
                if incoming_interface in G.blocked_interfaces:
                    G.blocked_interfaces.remove(incoming_interface)

            if spm.root == root_switch_id:
                log_debug("check point 3")
                if spm.hops_to_root + 1 < hops or (spm.hops_to_root + 1 == hops and root_switch_id > spm.switch_id):

                    # removes the incoming_interface from the list of blocked interfaces( if present)
                    if original_incoming_interface in G.blocked_interfaces:
                        log_debug("the orginal incoming interface is " + original_incoming_interface)
                        G.blocked_interfaces.remove(original_incoming_interface)

                    for intf in G.blocked_interfaces:
                        log_debug("the blocked interfaces are {}".format(intf))

                    # G.blocked_interfaces.add(root_interface)
                    log_debug("the incoming interface " + incoming_interface)
                    original_root_interface = root_interface
                    root_interface = incoming_interface
                    # should not send packet back to incoming interface
                    G.blocked_interfaces.add(incoming_interface)

                    root_switch_id = spm.switch_id

                    hops = spm.hops_to_root+1
                    last_stp_time = time.time()
                    # if incoming_interface not in G.blocked_interfaces:
                    #     G.blocked_interfaces.add(incoming_interface)
                    send_stp(net, root_switch_id, hops, switchid, my_interfaces)
                    # if it is the root switch, record the making time
                    G.blocked_interfaces.add(original_incoming_interface)

                else:
                    log_debug("need to block incoming interface"+incoming_interface)
                    G.blocked_interfaces.add(incoming_interface)
                    original_incoming_interface = incoming_interface
        else:
            G.my_LRUCache.insert(packet[0].src, incoming_interface)
            # more than 10 sec it didn't receive any stp packet
            log_debug("check point 4")

            dest_port = G.my_LRUCache.get(packet[0].dst)
            # the first part of packets records the destination info
            # the destination address is also an ethernet address
            if packet[0].dst in mymacs:
                # the packet is for this switch
                log_debug("Packet intended for me")
            elif dest_port is not None:
                log_debug("I escape")
                # this destination has been found in table
                net.send_packet(dest_port, packet)
            else:
                for intf in G.blocked_interfaces:
                    log_debug("the blocked interfaces are {}".format(intf))
                # flood the packet to all ports except the input port
                for intf in my_interfaces:
                    if intf.name in G.blocked_interfaces:
                        continue
                    log_debug("incoming interface is " + incoming_interface)
                    if incoming_interface != intf.name:
                        log_debug("Flooding packet {} to {}".format(packet, intf.name))
                        net.send_packet(intf.name, packet)  # send packet by one of its ports
    # shutdown net, but it is out of the while loop
    net.shutdown()
