import os
import logging
import unittest
import socket
import time
from clock import setup_logger
from clock import VM
import threading
from multiprocessing import Process


class VMTestIndividual(unittest.TestCase):
    """
    Testing individual functions from VM class that does not need process collaboration
    These incldue __init__, initiate_socket, receive_socket
    Besides Setup, test cases do not affect each other

    """
    def setUp(self):

        if not os.path.exists('logs/test/'):
            os.makedirs('logs/test/')

        self.vm0 = VM('127.0.0.1',[4096,4097, 4098],'logs/test/',0, 1)
        self.vm1 = VM('127.0.0.1',[4096,4097, 4098],'logs/test/',1, 2)
        self.vm2 = VM('127.0.0.1',[4096,4097, 4098],'logs/test/',2, 6)
        
    
    def test_instantiation(self):
        """
        Testing VM object instantiation
        """
        self.assertEqual(self.vm0.port, 4096)
        self.assertEqual(self.vm1.port, 4097)
        self.assertEqual(self.vm2.port, 4098)
        
        self.assertIsNotNone(self.vm0.logger)

        self.assertEqual(self.vm0.q.qsize(),0)
        self.assertEqual(self.vm1.q.qsize(),0)
        self.assertEqual(self.vm2.q.qsize(),0)
    
    def test_receive_socket(self):
        """
        test if the socket listening and successfully acquire a handle
        """

        #print("Wait for the ports from last test to clear")
        #time.sleep(15)
        #print("Finished waiting for the ports from last test to clear")

        # when vm2 not listening, cannot connect
        out_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # when vm2 has not started to listen, vm1 cannot make connection
        self.assertRaises(ConnectionRefusedError, out_s.connect,('127.0.0.1', 4098))    
        #out_s.shutdown(socket.SHUT_RDWR)
        out_s.close()
        

        # starting vm2 listening, and make sure it is ready
        thread = threading.Thread(target=self.vm2.receive_socket)
        thread.start()
        time.sleep(1)
        # when vm2 listening, can connect now
        out_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        out_s.connect(('127.0.0.1', 4098))
        thread.join()
        
        # vm2 should now possess a socket handle
        self.assertIsInstance(self.vm2.in_s, type(out_s))

        # clean up after testing
        out_s.shutdown(socket.SHUT_RDWR)
        out_s.close()
        self.vm2.close_down()


    def test_initiate_socket(self):
        
        #print("Wait for the ports from last test to clear")
        #time.sleep(15)
        #print("Finished waiting for the ports from last test to clear")
        # before any server starts listening
        # initate_socket will catch ConnectionRefusedError
        # and raise SystemExit instead
        # this will also generate an error log
        self.assertRaises(SystemExit, self.vm0.initiate_socket)
        
        # now start a listening socket
        thread = threading.Thread(target=self.vm1.receive_socket)
        thread.start()
        time.sleep(1)
       
        # connect and test again
        self.vm0.initiate_socket()
        thread.join()
        self.assertIsInstance(self.vm0.out_s, type(self.vm1.in_s))

        # clean up after testing
        self.vm0.close_down()
        self.vm1.close_down()
        

class VMTestListenSend(unittest.TestCase):
    """
    Testing listening and sending
    Besides Setup, test cases do not affect each other

    """
    def setUp(self):

        if not os.path.exists('logs/test/'):
            os.makedirs('logs/test/')

        self.vm0 = VM('127.0.0.1',[4099,4100, 4101],'logs/test/',0, 1)
        self.vm1 = VM('127.0.0.1',[4099,4100, 4101],'logs/test/',1, 2)
        self.vm2 = VM('127.0.0.1',[4099,4100, 4101],'logs/test/',2, 6)


    def test_listen(self):
        """
        The listen function maintains a socket that keep pushing msgs received to queue
        """
        #print("Wait for the ports from last test to clear")
        #time.sleep(15)
        #print("Finished waiting for the ports from last test to clear")


        # starting vm2 receiving connection, and make sure it is ready
        thread = threading.Thread(target=self.vm2.receive_socket)
        thread.start()
        time.sleep(1)
        # when vm2 listening, can connect now
        send_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        send_s.connect(('127.0.0.1', 4101))
        thread.join()

        
        # vm2 starts listening, but has not opened the start_listening switch 
        self.vm2.need_to_listen = False
        threading.Thread(target=self.vm2.listen,args=(self.vm2.in_s,)).start()
        self.assertEqual(self.vm2.q.qsize(),0)
        send_s.send("Message before listening".encode()) # this message is not going to be received yet
        self.assertEqual(self.vm2.q.qsize(),0)

        # now open the start_listening switch and try again
        self.vm2.need_to_listen = True
        threading.Thread(target=self.vm2.listen,args=(self.vm2.in_s,)).start()
        time.sleep(0.2) # wait for the listen to happen
        # now the previous message should appear in the queue
        self.assertEqual(self.vm2.q.qsize(),1)
        before_msg = self.vm2.q.get()
        self.assertEqual(before_msg, "Message before listening")

        # send messages and test
        send_s.send("First message".encode())
        time.sleep(0.2)
        self.assertEqual(self.vm2.q.qsize(),1)
        send_s.send("Second message:10".encode())
        time.sleep(0.2)
        self.assertEqual(self.vm2.q.qsize(),2)
        
        # message sent, now check vm2's queue
        msg1 = self.vm2.q.get()
        self.assertEqual(msg1, "First message")
        msg2 = self.vm2.q.get()
        self.assertEqual(msg2, "Second message:10")
      
        # finally test how does the listening socket behave when the sending socket closes
        send_s.shutdown(socket.SHUT_RDWR)
        send_s.close()
        self.assertEqual(self.vm2.q.qsize(),0)
        # stop the listening thread
        self.vm2.need_to_listen = False
        
        self.vm2.close_down()

    def test_send(self):
        """
        the sending function keeps a socket and sends
        the primary puurose to test is robustness against failed listener
        """

        #print("Wait for the ports from last test to clear")
        #time.sleep(15)
        #print("Finished waiting for the ports from last test to clear")

        # first start a listening socket from vm1
        thread = threading.Thread(target=self.vm1.receive_socket)
        thread.start()
        time.sleep(1)
       
        # connect and test again
        self.vm0.initiate_socket()
        thread.join()
        self.assertIsInstance(self.vm0.out_s, type(self.vm1.in_s))

        # now vm1 starts to listen
        self.vm1.need_to_listen = True
        threading.Thread(target=self.vm1.listen,args=(self.vm1.in_s,)).start()
        
        # vm0 sending message now
        self.vm0.send("First Message:2", self.vm0.out_s)
        time.sleep(0.2)
        self.assertEqual(self.vm1.q.qsize(),1)

        # now test if vm1 breaks
        self.vm1.need_to_listen = False
        self.vm1.in_s.shutdown(socket.SHUT_RDWR)

        # immediate next send will not fail
        self.vm0.send("A message that will never reach, but with no error", self.vm0.out_s)
        # verify only old message is there
        old_msg = self.vm1.q.get()
        self.assertEqual(old_msg,"First Message:2")
        self.assertEqual(self.vm1.q.qsize(),0)
        
        time.sleep(0.2)
        # the second send attempt will fail
        self.assertRaises(SystemExit, self.vm0.send, "A message that will never reach, and with error", self.vm0.out_s)

        self.assertEqual(self.vm1.q.qsize(),0)
    
        # clean up after closing down
        self.vm0.close_down()
        self.vm1.close_down()

def test_vm_connect_helper(host, ports, exp_folder, index, tick):
    # instantiate an object in the 
    vm = VM(host=host, ports=ports, folder=exp_folder, index=index, tick=tick)
    # 
    vm.connect()
    time.sleep(5)
    vm.close_down()


class VMTestConnect(unittest.TestCase):
    """
    Testing functions from VM class that need process collaboration
    These incldue connect
    Besides Setup, test cases do not affect each other

    """
    def test_connect(self):

        if not os.path.exists('logs/test/'):
            os.makedirs('logs/test/')

        vm_ports = [4102, 4103, 4104]
        local_host = "127.0.0.1"
        ps = []
        for i in range(len(vm_ports)):
            tick = i + 1
            proc = Process(target=test_vm_connect_helper, args=(local_host, vm_ports, 'logs/test/', i, tick))
            proc.start()
            ps.append(proc)
        
        time.sleep(5)
        for proc in ps:
            proc.terminate()

if __name__ == "__main__":
    unittest.main()
