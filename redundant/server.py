# from subprocess import Popen, PIPE
#!/usr/bin/env python3


# pipe = Popen('ifconfig', stdout=PIPE, shell=True)
# text = pipe.communicate()[0].decode()
# l = text.split('\n')
# network_interface_list = []
# for x in l:
#     if r"flags" in x and 'lo' not in x:
#         print(x[:x.find(':')])
#         network_interface_list.append(x[:x.find(':')])
# network_interface_list = sorted(network_interface_list)
# print(network_interface_list)
# print()


import socket
import time
import threading
import os
import datetime as dt
import argparse
import subprocess
import re
import signal
import numpy as np

parser = argparse.ArgumentParser()

TCP_CONGESTION = 13

num_ports = 1
UL_ports = np.arange(3270, 3270+2*num_ports, 2)
DL_ports = np.arange(3271, 3271+2*num_ports, 2)

print("UL_ports", UL_ports)
print("DL_ports", DL_ports)

HOST = '192.168.1.248'
HOST = '0.0.0.0'

thread_stop = False
exit_program = False
length_packet = 362
bandwidth = 289.6*100
total_time = 3600
cong_algorithm = 'cubic'
expected_packet_per_sec = bandwidth / (length_packet << 3)
sleeptime = 1.0 / expected_packet_per_sec
prev_sleeptime = sleeptime
pcap_path = "/home/wmnlab/D/pcap_data"
ss_dir = "/home/wmnlab/D/ss"


cong = 'cubic'.encode()

def connection(host, port, result):
    print("host", host, "port", port, "result", result)
    s_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s_tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # s_tcp.setsockopt(socket.SOL_IP, IP_MTU_DISCOVER, IP_PMTUDISC_DO)
    s_tcp.setsockopt(socket.IPPROTO_TCP, TCP_CONGESTION, cong)
    s_tcp.bind((host, port))
    print((host, port), "wait for connection...")
    s_tcp.listen(1)
    conn, tcp_addr = s_tcp.accept()
    print((host, port), "connection setup complete")
    result[0] = s_tcp, conn, tcp_addr

def get_ss(port):
    now = dt.datetime.today()
    n = '-'.join([str(x) for x in[ now.year, now.month, now.day, now.hour, now.minute, now.second]])
    f = open(os.path.join(ss_dir, str(port) + '_' + n)+'.csv', 'a+')
    while not thread_stop:
        proc = subprocess.Popen(["ss -ai dst :%d"%(port)], stdout=subprocess.PIPE, shell=True)
        line = proc.stdout.readline()
        line = proc.stdout.readline()
        line = proc.stdout.readline().decode().strip()
        f.write(",".join([str(dt.datetime.now())]+ re.split("[: \n\t]", line))+'\n')
        time.sleep(1)
    f.close()

def transmision(conn_list):
    print("start transmision")
    i = 0
    prev_transmit = 0
    ok = (1).to_bytes(1, 'big')
    start_time = time.time()
    count = 1
    sleeptime = 1.0 / expected_packet_per_sec
    prev_sleeptime = sleeptime
    global thread_stop
    while time.time() - start_time < total_time and not thread_stop:
        try:
            t = time.time()
            t = int(t*1000).to_bytes(8, 'big')
            z = i.to_bytes(4, 'big')
            redundent = os.urandom(length_packet-12-1)
            outdata = t + z + ok +redundent
            for j in range(len(conn_list)):
                conn_list[j].sendall(outdata)
            i += 1
            time.sleep(sleeptime)
            if time.time()-start_time > count:
                print("[%d-%d]"%(count-1, count), "transmit", i-prev_transmit)
                count += 1
                sleeptime = prev_sleeptime / expected_packet_per_sec * (i-prev_transmit) # adjust sleep time dynamically
                prev_transmit = i
                prev_sleeptime = sleeptime
        except:
            thread_stop = True
            break    
    print("---transmision timeout---")
    # ok = (0).to_bytes(1, 'big')
    # redundent = os.urandom(length_packet-12-1)
    # outdata = t + z + ok +redundent
    # for i in range(len(conn_list)):
    #     conn_list[i].sendall(outdata)
    print("transmit", i, "packets")


def receive(conn):
    conn.settimeout(10)
    print("wait for indata...")
    i = 0
    start_time = time.time()
    count = 1
    seq = 0
    prev_capture = 0
    capture = 0
    prev_loss = 0
    global thread_stop
    global buffer
    while not thread_stop:
        try:
            indata = conn.recv(65535)
            capture += len(indata) / 362
            if time.time()-start_time > count:
                print("[%d-%d]"%(count-1, count), "capture", capture)
                count += 1
                capture = 0
        except Exception as inst:
            print("Error: ", inst)
            thread_stop = True
    thread_stop = True
    print("[%d-%d]"%(count-1, count), "capture", capture, sep='\t')
    print("---Experiment Complete---")
    print("STOP receiving")



if not os.path.exists(pcap_path):
    os.system("mkdir %s"%(pcap_path))

if not os.path.exists(ss_dir):
    os.system("mkdir %s"%(ss_dir))


while not exit_program:

    now = dt.datetime.today()
    n = [str(x) for x in[ now.year, now.month, now.day, now.hour, now.minute, now.second]]
    for i in range(len(n)-3, len(n)):
        if len(n[i]) < 2:
            n[i] = '0' + n[i]
    n = '-'.join(n)
    UL_pcapfiles = []
    DL_pcapfiles = []
    tcp_UL_proc = []
    tcp_DL_proc = []
    for p in UL_ports:
        UL_pcapfiles.append("%s/server_UL_%s_%s.pcap"%(pcap_path, p, n))
    for p in DL_ports:
        DL_pcapfiles.append("%s/server_DL_%s_%s.pcap"%(pcap_path, p, n))

    for p, pcapfile in zip(UL_ports, UL_pcapfiles):
        tcp_UL_proc.append(subprocess.Popen(["tcpdump -i any port %s -w %s &"%(p,  pcapfile)], shell=True, preexec_fn=os.setsid))

    for p, pcapfile in zip(DL_ports, DL_pcapfiles):
        tcp_UL_proc.append(subprocess.Popen(["tcpdump -i any port %s -w %s &"%(p,  pcapfile)], shell=True, preexec_fn=os.setsid))

    time.sleep(1)
    try:

    
        thread_list = []
        UL_result_list = []
        DL_result_list = []
        for i in range(num_ports):
            UL_result_list.append([None])
            DL_result_list.append([None])
        UL_tcp_list = [None] * num_ports
        UL_conn_list = [None] * num_ports
        DL_tcp_list = [None] * num_ports
        DL_conn_list = [None] * num_ports
        for i in range(len(UL_ports)):
            thread_list.append(threading.Thread(target = connection, args = (HOST, UL_ports[i], UL_result_list[i])))

        for i in range(len(DL_ports)):
            thread_list.append(threading.Thread(target = connection, args = (HOST, DL_ports[i], DL_result_list[i])))

        for i in range(len(thread_list)):
            thread_list[i].start()

        for i in range(len(thread_list)):
            thread_list[i].join()

        for i in range(num_ports):
            UL_tcp_list[i] = UL_result_list[i][0][0]
            UL_conn_list[i] = UL_result_list[i][0][1]
            DL_tcp_list[i] = DL_result_list[i][0][0]
            DL_conn_list[i] = DL_result_list[i][0][1]


    except KeyboardInterrupt:
        print("KeyboardInterrupt -> kill tcpdump")
        os.system("killall -9 tcpdump")
        for pcapfile in UL_pcapfiles:
            subprocess.Popen(["rm %s"%(pcapfile)], shell=True)
        for pcapfile in DL_pcapfiles:
            subprocess.Popen(["rm %s"%(pcapfile)], shell=True)
        exit_program = True
        thread_stop = True
        exit()

    except Exception as inst:
        print("Connection Error:", inst)
        print("KeyboardInterrupt -> kill tcpdump")
        os.system("killall -9 tcpdump")
        for pcapfile in UL_pcapfiles:
            subprocess.Popen(["rm %s"%(pcapfile)], shell=True)
        for pcapfile in DL_pcapfiles:
            subprocess.Popen(["rm %s"%(pcapfile)], shell=True)
        exit()
        continue


    for i in range(num_ports):
        UL_conn_list[i].sendall(b"START")
        DL_conn_list[i].sendall(b"START")
    time.sleep(0.5)
    thread_stop = False
    transmision_thread = threading.Thread(target = transmision, args = (DL_conn_list, ))
    recive_thread_list = []
    for i in range(num_ports):
        recive_thread_list.append(threading.Thread(target = receive, args = (UL_conn_list[i], )))


    try:
        transmision_thread.start()
        for i in range(len(recive_thread_list)):
            recive_thread_list[i].start()
        transmision_thread.join()
        for i in range(len(recive_thread_list)):
            recive_thread_list[i].join()
    except KeyboardInterrupt:
        print("finish")
    except Exception as inst:
        print("Error:", inst)
        print("finish")
    finally:
        thread_stop = True
        for i in range(num_ports):
            UL_conn_list[i].close()
            DL_conn_list[i].close()
            UL_tcp_list[i].close()
            DL_tcp_list[i].close()
        os.system("killall -9 tcpdump")
