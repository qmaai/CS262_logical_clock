"""
CS 262 Distributed System. Assignment 2. Logical Clocks
Author: 
"""
import sys
import time
import datetime
import socket
import random
import logging
import os
import queue
import threading
from multiprocessing import Process

VM_PORTS = [4096, 4097, 4098]
LOCAL_HOST = '127.0.0.1'


def setup_logger(logger_name, log_file, level=logging.INFO):
    l = logging.getLogger(logger_name)
    formatter = logging.Formatter('%(asctime)s : %(message)s')
    fileHandler = logging.FileHandler(log_file, mode='w')
    fileHandler.setFormatter(formatter)

    streamHandler = logging.StreamHandler()
    streamHandler.setFormatter(formatter)

    l.setLevel(level)
    l.addHandler(fileHandler)
    l.addHandler(streamHandler)
    return l

# VMs are assumed to exist in a same machine
# Each VMs maintain two bidirectional sockets, one for each other machine.
# Each socket is used by two threads. One for sending and one for receiving.
# Opening up one socket for each message is a bad practice.
class VM():
    
    def __init__(self, host, ports, folder, index, tick, total_time=60):
        """
        Params:
            host: the IP address of socket for virtual machine comunication
            ports: a list of ports for all vms
            folder: base folder for log file
            index: the position of self in all |ports| VMs. ports[index] is own port
            tick: number of clock ticks per (real world) second for the VM
            total_time: the total time the process run for in seconds
        Initialization automatically connects the VM to two other VMs
        """
        self.host = host
        self.index = index
        assert len(ports) > index, "index larger than number of VMs"
        self.port = ports[index]
        self.all_ports = ports

        # clock rate ticks, clock is the variable for the logical clock
        assert tick > 0
        self.tick = tick
        self.total_time = total_time
        self.clock = 0 # initialization starting from 1
        self.name = "VM"+str(index)+"_cr"+str(self.tick) # a presentable VM name

        # generate a log file and maintain a log handle
        log_file = folder + "/" +self.name+".log"
        self.logger = setup_logger(self.name,log_file)
        self.logger.debug("{} successfully instantiated".format(self.name))

        # Internal Queue. Messages received from sockets will be pulled into this internal
        # Queue. This queue models the internal system queue
        self.q = queue.Queue()
        self.q_lock = threading.Lock() # two process listen and dumping simultaneously so use lock
        
        # during initialization, build connection to two other processes
        # self.connect()

    # The three VMs uses sockets to form communication
    # P1 --> P2 --> P3 --> P1
    # P1 initiates a connection to P2, P2 initiates a connection to P3, 
    # P3 initiates a connection to P1
    def initiate_socket(self):
        """
        This function establish a connection to the next process, and retain a socket handle
        self.out_s for future communication
        """
        # find the index of the process to connect
        to_connect = int( (self.index+1) % len(self.all_ports))
        self.out_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.out_s.settimeout(300)
        try:
            self.out_s.connect((LOCAL_HOST, self.all_ports[to_connect]))        
            self.logger.info("{} connected to VM{} on {} port on {}.".format(self.name, to_connect, LOCAL_HOST, self.all_ports[to_connect]))
        except:
            self.logger.error("{} failed to connect to VM{} on {} port {}. Error".format(self.name, to_connect, LOCAL_HOST, self.all_ports[to_connect]))
            sys.exit()
    
    # P1 listens for P3, P2 listens for P1, P3 listens for P2
    def receive_socket(self):
        """
        This function listens for a connection to the previous process, and retain a socket handle        self.in_s for future communication
        """
        to_connect = int( (self.index-1) % len(self.all_ports)) # the index of incoming connection vm
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind((LOCAL_HOST, self.port)) 
            s.listen(5)
            self.in_s, _ = s.accept() # listen for one incoming connection, acquire handle
            self.logger.info("{} has incoming connection from VM{} on {} port on {}.".format(self.name, to_connect, LOCAL_HOST, self.port))
        except:
            self.logger.error("{} failed to receive incoming connection from VM{} on {} port {}. Error".format(self.name, to_connect, LOCAL_HOST, self.all_ports[to_connect]))
            sys.exit()
    
    # a wrapper function to operate receive_socket in a thread, and then having
    # VM initate connections
    # the two functions initiate_socket and receive_socket cannot run sequentially, otherwise P1 try to connect to P2 and wait,
    # P2 try to connect to P3 and wait, P3 try to connect to P1 and wait. Locks.
    # So use threads
    def connect(self):
        """
        Threads can access and modify the instance simultaneously. Take care.
        But since initate_socket and receive_socket is alterning different things.
        """
        # VMs first start to listen
        receive_thread = threading.Thread(target=self.receive_socket)
        receive_thread.start()
        # indicate I am listening
        self.logger.info("{} listening on port {}".format(self.name, self.port))

        # wait a little bit for other VMs to ready for listen
        time.sleep(3)

        # initiate a connection to other's listening port
        self.initiate_socket()

        # make sure the handle self.in_s is in place
        receive_thread.join()
    
    def listen(self, socket):
        """
        Given a socket that connects to an external VM, always listen for messages that come 
        in using recv and dump it in the internal queue
        """
        while self.need_to_listen:
            try:
                # blocking call to listen for bytes on sockets
                # being lenient here, not fully defining the protocol for sockets
                msg = socket.recv(1024).decode()
                # as soon as hear a msg from socket, put it into the local queue
                if msg != "":
                    with self.q_lock:
                        self.q.put(msg)
                    # log info
                    self.logger.debug("{} pulled a message {} at system time {}".format(self.name, msg, datetime.datetime.now().strftime("%m_%d_%y_%H:%M:%S")))

            except Exception as err:
                self.logger.error("Failed to receive message!")
                socket.close()

    def send(self, msg, socket):
        """
        A wrapper send function through socket
        """
        try:
            socket.sendall(msg.encode())
        except Exception as err:
            self.logger.error(" Failed to send message!")
            socket.close()
            sys.exit()
    
    def close_down(self):
        try:
            self.in_s.shutdown(socket.SHUT_RDWR)
            self.in_s.close()
        except:
            pass
        
        try:
            self.out_s.shutdown(socket.SHUT_RDWR)
            self.out_s.close()
        except:
            pass


    def work(self):
        start_time = time.time() # for recording the start time of system time

        # two threads always listening in the background and putting msgs in que
        self.need_to_listen = True # an indicator for stopping the listening thread
        threading.Thread(target=self.listen,args=(self.out_s,)).start()
        threading.Thread(target=self.listen, args=(self.in_s,)).start()
        
        # now main process work according to clock rates
        # always running for total_time seconds
        for ti in range(self.total_time):
            # for tick times every second, wakes up, read and send messages
            for i in range(self.tick):
                wake_up_this_round_time = time.time()
                # if there is message in internal que, pull one off
                if not self.q.empty():
                    with self.q_lock:
                        msg = self.q.get() # msg in form "vm_name:clock_val"
                        msg_logic_clock_val = msg.split(":")[-1]
                        self.logger.info(self.name +' Received Message '+ msg + ' with queue size ' + str(self.q.qsize())+ ' and internal logic clock ' + str(self.clock)+" at system time "+ str(time.time()-start_time)[0:5])
                        self.clock = max(self.clock, int(msg_logic_clock_val))

                # otherwise try to send a message
                r_num = random.randint(1, 10)

                # send to out vm machine the clock value
                if r_num == 1:
                    out_vm = "VM"+str( (self.index+1) % 3) # a presentable VM name
                    msg = self.name +":"+str(self.clock)
                    self.logger.info(self.name +' Send Message '+ msg + " to " + out_vm +" at system time "+ str(time.time()-start_time)[0:5])
                    self.send(msg, self.out_s)

                # send to in vm machine the clock value
                elif r_num == 2:
                    out_vm = "VM"+str( (self.index-1) % 3) # a presentable VM name
                    msg = self.name +":"+str(self.clock)
                    self.logger.info(self.name +' send message '+ msg + " to " + out_vm +" at system time "+ str(time.time()-start_time)[0:5])
                    self.send(msg, self.in_s)

                # send to both vms machines the clock value
                elif r_num == 3:
                    msg = self.name +":"+str(self.clock)
                    self.logger.info(self.name +' send message '+ msg + " to both other VMs at system time "+ str(time.time()-start_time)[0:5])
                    t_out_send = threading.Thread(target=self.send, args=(str(self.clock),self.out_s))
                    t_in_send = threading.Thread(target=self.send, args=(str(self.clock),self.in_s))
                    t_out_send.start()
                    t_in_send.start()
                    t_out_send.join()
                    t_in_send.join()

                # otherwise no communication and simply just internal event
                else:
                    self.logger.info(self.name +' Internal Event with logical clock '+ str(self.clock) + " at system time "+ str(time.time()-start_time)[0:5])

                self.clock += 1
                # sleep for 1/rate before waking up again
                # adjust for the operation in this round
                round_time = time.time() - wake_up_this_round_time
                time.sleep(1/self.tick - round_time)

        self.need_to_listen = False # indicate the listening thread can stop working now
        
        
# running a virtual machine
# a wrapper function to call the object instance' method
def run_vm(host, ports, exp_folder, index, tick):
    # instantiate an object in the 
    vm = VM(host=host, ports=ports, folder=exp_folder, index=index, tick=tick)
    # 
    vm.connect()
    vm.work()
    vm.close_down()


if __name__ == "__main__":
    
    # base of the log file
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # each experiment has a unique folder for three log file
    exp_folder = "logs/"+datetime.datetime.now().strftime("%m_%d_%y_%H:%M:%S")
    os.makedirs(exp_folder)
    
    try: 
        ps = []
        for i in range(len(VM_PORTS)):
            tick = random.randint(1,6)
            proc = Process(target=run_vm, args=(LOCAL_HOST, VM_PORTS, exp_folder, i, tick))
            proc.start()
            ps.append(proc)

        
        # make sure the main threads wait, and the childs processes don't become ofans
        time.sleep(70)
        for proc in ps:
            proc.terminate()
        print("All processes stopped naturally.")

    except KeyboardInterrupt: # if user decides to stop the processes in the middle
        for proc in ps:
            proc.terminate()
        print("Stopped by user. All processes stop.")
        sys.exit(0)
