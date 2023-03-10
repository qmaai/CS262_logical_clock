# CS262_logical_clock
Logical Clock Implementation for Harvard CS262 Distributed Computation

## Installation and Running
First, download or clone this github repository to the local machine.  To clone, cd into a folder where you want to put this repository and enter command: 
```console
$ git clone https://github.com/qmaai/CS262_logical_clock.git
```
Then, cd into the repository: 
```console
$ cd CS262_logical_clock
```
Now you can run by 
```console
$ python3 clock.py
```
This will automatically create a __log__ folder, where experiment has its own timestamped folder and each virtual machine 
has a log file of the form __VM0_CR1__, where __VM__ means virtual machine and __CR__ being the clock rate.

Run the entire test by 
```console
$ python3 -m unittest test
```
and for individual test suites by  
```console
$ python3 -m unittest test.VMTestIndividual
```
The resulting experiment log folders is 
```
+-- logs
|   +-- 03_08_23_11:50:06
|   +-- 03_08_23_12:00:17
|   +-- tests
|   |    +-- VM0_CR1
|   |    +-- VM1_CR2
|   |    +-- VM2_CR6
``` 

## High Level Modeling Choices
To keep codes concentrated and concise, we gather all code into a single file __clock.py__. To model three virtual machines, each interacting with each other, it is natural to use three instances of a Virtual Machine Class, where each instance is instantiated in a separate process.
To model the independent machines with their own memory more closely, the three processes deployed should not share memory through operating system process queues nor pipes, and the most natural way for them to communicate is through sockets. For each machine, two sockets are required, one for each other virtual machine.
Finally each virtual machine must both send and listen on two sockets, multi-threading will be used.

## Low Level Implementation Choices
Spawn one process to represent each virtual machine, on each process instantiate a VM (virtual machine) object. Upon instantiation the VM object knows its own port, both of other virtual machines' ports, its own clock rate, and a logger handle. 
It holds two sockets to communicate to the other two virtual machines. To establish all six sockets connections, one symmetric way is to have VM1 acting as host to listen for VM3, while reaching out as client for VM2; VM2 acting as host to listen for VM1 and reach out as client to VM3; and the same logic for VM3. They then form a cycle.
```
VM1 <--> VM2 <--> VM3
```
To implement this logic, for each VM upon instantiation, a connect method is called. It first spawns a thread that acts like a server and starts to listen for incoming connections. It then waits for one second for the other two virtual machines to set up for listening as well, and only then does it reach out to connect. The one second wait is crutial because otherwise the next virtual machine might not have prepared for listening when the current vm reaches out. This will result in a connection refused error.
In practice, this is resolved by each virtual machine trying to repeatedly send a request of connect until granted. But for this implementation, we make sure one connect request is sufficient.
For ease of implementation, we did not define a full-fledged wire-protocol like that in project one. A simple `socket.sendall()` and `socket.recv()` command surfices.

After the initial connection is established, each VM holds two sockets. For each socket, the VM spawns out a listening thread to continuously listen for messages that come from that socket. Whenever a non-empty message is received, it immediately pulls the message to an internal queue for storage. The listen thread operates at a rate of the operating system, not at the tick rate of the virtual machine. This is allowed in the spec.
Besides the two threads for listening, the main thread of the virtual machine is mimicking the sleep - wake up behavior : it wakes up every '1/tick' seconds, and roll a ten-faced die to determine sending messages through the two socket handles to either one, or both, or none of the two other virtual machines. The logic clock is implemented as requested by the spec.
Two things to note is one: wake up time is adjusted by the time amount of operating each round, so as to keep sync with the operating system.

## Observations

When the rate of internal event is fixed to `7/10`, we make the following observations
### drift in the values of the local logical clocks
Clock drift are defined as differences in time between two clocks. In our context, a virtual machine running at clock rate one for one real minute can have
a value of 59, while that running at clock rate two can have a value of 115. If using the real operating system time as a benchmark standard, the clock rate one 
machine has a drift of `59/1-60=-1` and the clock rate 2 virtual machine has a drift of `115/2-60=-2.5`. Hence, it only makes sense to read the drift of logical 
clock values when the three virtual machines in a set of experiments are running at the same clock rate. We here examine the differences in values should the
clock rate be 1, 3, 6, 9, 12 respectively. Drifts are measured by `(Logical Clock Value / Clock Rate - System Time) / System Time`

| Clock Rates of Experiments  | Drifts in logical clock per seconds|
| --- | --- |
| 1,1,1                       | -0.00305                           |
| 3,3,3                       | -0.01034                           |
| 6,6,6                       | -0.01961                           |
| 9,9,9                       | -0.03995                           |

It can be seen that logical drift increases when the clock rate increases. Again note when simulating the clock rate of virtual machines, we have adjusted for the operation time
each round using `time.sleep(1/clock_rate - operation_time_each_round)`.

For the above set of experiments, logical clocks do not jump at all, and there are no gaps in logical clock values at all, while the queue size is almost always zero. This is due to 
the symmetric nature of the experiments performed. 

### Other Interesting observations when the rate of internal event is fixed to `7/10`
We performed a sweeping sets of experiments of one minute when the internal event is at rate `7/10`. __CR__ means clock rate. Average jump size 
per operation is calculated using the final average logic clock value over the number of operations performed. Gaps in logic clock values measures 
the differences between virtual machines of different rates at a same real operating system time. We use the final time as that benchmark. 
For ease of comparison, length of message queues is compared towards the end of the one minute.
|Clock Rate| Average Jump Size per Operation | Gaps in Logic Clock Values | Length of Message Queues at the end|
| -----| -----| -----| -----|
|1,1,1|0 | 0 | 0 |
|1,1,6|CR1: 3.5; CR1:3; CR6:1| CR1: 224 at 59.2s; CR1: 187 at 59.2s; CR6: 354 at 60.21s | CR1: 44; CR1: 43; CR6: 0|
|1,2,6|CR1:4; CR2:3; CR6: 1| CR1: 257 at 59.19s; CR2: 344 at 59.95s; CR6: 358 at 60.27s| CR1: 28; CR2: 0; CR6: 0|
|1,3,6|CR1:3; CR3:2; CR6: 1| CR1: 173 at 59.20s; CR3: 353 at 60.34s; CR6: 354 at 60.27s| CR1: 46; CR3: 0; CR6: 0|
|1,6,6|CR1:3; CR6:1; CR6: 1| CR1: 182 at 59.22s; CR6: 355 at 60.39s; CR6: 357 at 60.82s| CR1: 73; CR6: 0; CR6:0|

There are many interesting observations to be drawn from this set of experiment, though admittedly there are indeed quite a lot of
random forces at effect here without plotting out all the data from average. 

For average jump size per operation, we have the following
+ For average jump rate per operation, higher clock rate virtual machines have a lower jump, and the highest rate virtual machine never jump
+ For average jump rate per operation, if the clock rate of the highest clock rate virtual machine stays the same, then however 
one changes the clock rate of another second highest clock rate virtual machine, one's own virtual machine's jump stays roughly the same. This
is because jumps are directly determined by the messages received from the highest rate virtual machine. 
+ For average jump rate per operation, if the clock rate of the highest clock rate virtual machine stays the same, then if one's 
own virtual machine clock rate incraeses, the average jump size decreases. This is because one's own VM can process more and faster, and hence
the gap between clock speed is lower.

For Gaps in logic clock values
+ The largest gap occurs between the highest clock rate and the lowest clock rate virtual machines
+ Holding the highest and lowest clock rate virtual machine the same, gradually increasing the middle clock rate virtual machine
first reduces the gap between itself and the highest logic clock values, but then stays the same. This is because when the clock rate
is fast enough to handle the highest clock rate machine messages, it ceases to jump that fast and remain still.

The most interesting of all is the length of the queue when increasing the clock rate.
+ The slowest clock rate virtual machine, it cannot handle the messages so the length keeps increasing steadily
+ The highest clock rate virtual machine can always process all messages received, so the length is always zero.
+ The middle clock rate increases from 1 to 2 to 3, though the graph shows its queue length is always zero at the end of the 
operation, during the operation the queue length sometimes is one. This indicates that a clock rate of 2 is already fast enough
to handle messages sent by the fasted virtual machine at clock rate 6 but who rarely sends messages (1/5 probability). 

Decreasing the probablity of internal events indeeds change the behavior of the queue, as middle clock rate no longer always see zero.
