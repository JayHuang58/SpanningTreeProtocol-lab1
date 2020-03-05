from switchyard.lib.userlib import *
from SpanningTreeMessage import SpanningTreeMessage
import time


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


def main(net):
    my_interfaces = net.interfaces() # get itself interfaces/ports
    non_block_interfaces = my_interfaces # a copy of all physical interfaces
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
    # records the time at which the last spanning tree message was received

    # at the beginning, rootid == switchid
    stp_pkt = mk_stp_pkt(switchid, hops, switchid)
    # flood the packet to all ports
    for intf in my_interfaces:
        net.send_packet(intf.name, stp_pkt)  # send packet by one of its ports

    # continuing receiving packets, and records timestamp, input_port and packet info
    # need to distinguish packets, whether it is a normal packet or a spm packet
    while True:
        try:
            timestamp, incoming_interface, packet = net.recv_packet(timeout=2)  # receive packets
        except NoPackets:
            # if it is the root switch, it needs to send out stp packet to all non_block interfaces
            if switchid == root_switch_id:
                for intf in non_block_interfaces:
                    new_stp_pkt = mk_stp_pkt(root_switch_id, 0, switchid, intf.ethaddr)
                    log_debug("Flooding packet {} ".format(new_stp_pkt))
                    net.send_packet(intf.name, new_stp_pkt)
                # if it is the root switch, record the making time
                last_stp_time = time.time()
            continue
        except Shutdown:
            return
        # also the net has its own name
        log_debug("In {} received packet {} on {}".format(net.name, packet, incoming_interface))
        # if it is the root switch and time period before last stp time is larger than 2 seconds
        if switchid == root_switch_id and time.time() - last_stp_time >= 2:
            for intf in non_block_interfaces:
                new_stp_pkt = mk_stp_pkt(root_switch_id, 0, switchid, intf.ethaddr)
                log_debug("Flooding packet {} ".format(new_stp_pkt))
                net.send_packet(intf.name, new_stp_pkt)
            # if it is the root switch, record the making time
            last_stp_time = time.time()

        # more than 10 seconds, it needs to reset all values
        if time.time() - last_stp_time >= 10:
            reset = True

        packet_type = packet[Ethernet].ethertype
        if packet_type == EtherType.SLOW:
            log_debug("check point 1")
            # it receives spm, don't need to reset
            reset = False
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
                    non_block_interfaces = my_interfaces # reset all ports to unblock state

                for intf in non_block_interfaces:
                    log_debug("all interfaces are {} ".format(intf.name))
                root_interface = incoming_interface

                for intf in non_block_interfaces:
                    # send out new spm packet except incoming interface
                    if intf.name == incoming_interface:
                        continue
                    new_stp_pkt = mk_stp_pkt(root_switch_id, hops, switchid, intf.ethaddr)
                    log_debug("Flooding packet {} on {}".format(new_stp_pkt, intf.name))
                    net.send_packet(intf.name, new_stp_pkt)
                # if it is the root switch, record the making time
                last_stp_time = time.time()

            if spm.root == root_switch_id:
                log_debug("check point 3")
                if spm.hops_to_root + 1 < hops or (spm.hops_to_root + 1 == hops and root_switch_id > spm.switch_id):
                    # TODO if incoming_interface not in non_block_interfaces.name:

                    root_interface = incoming_interface

                    for intf in non_block_interfaces:
                        if intf.name == root_interface:
                            continue
                        new_stp_pkt = mk_stp_pkt(root_switch_id, spm.hops_to_root + 1, switchid, intf.ethaddr)
                        log_debug("Flooding packet {} on {}".format(new_stp_pkt, intf.name))
                        net.send_packet(intf.name, new_stp_pkt)
                    # if it is the root switch, record the making time
                    last_stp_time = time.time()
                else:
                    log_debug("need to remove incoming interface")
        else:
            # more than 10 sec it didn't receive any stp packet
            if reset:
                root_switch_id = switchid
                hops = 0
                non_block_interfaces = my_interfaces
            log_debug("check point 4")
            # the first part of packets records the destination info
            # the destination address is also an ethernet address
            if packet[0].dst in mymacs:
                # the packet is for this switch
                log_debug("Packet intended for me")
            else:
                # flood the packet to all ports except the input port
                for intf in non_block_interfaces:
                    if incoming_interface != intf.name:
                        log_debug("Flooding packet {} to {}".format(packet, intf.name))
                        net.send_packet(intf.name, packet)  # send packet by one of its ports
    # shutdown net, but it is out of the while loop
    net.shutdown()
