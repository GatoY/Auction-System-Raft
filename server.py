"""Server for multithreaded (asynchronous) chat application."""
from socket import *
from threading import Thread
import sys
import json
import random
from threading import Timer
import numpy as np


#
#
#   msg: {'REQ_VOTE'}
#        {'REQ_VOTE_REPLY'}
#        {'LOG'}
#        {'HEART_BEAT'}
#   Log status:         # Uncommit Commited Applied
#
#   AppendEntries RPC: HeartBeat, InfoSyn
#   # CurrentTerm, LeaderId, PrevLogIndex, PrevLogTerm, Entries, LeaderCommit
#
#   RPC Reply: CurrentTerm, Success
#
#
#
#

class Server:
    def __init__(self, server_id, num_nodes=3):
        CONFIG = json.load(open("config.json"))
        self.server_port = CONFIG['server_port']

        self.num_nodes = num_nodes
        self.clients = {}
        self.clients_con = []
        self.addresses = {}
        self.HOST = ''
        self.BUFSIZ = 1024

        self.server = socket(AF_INET, SOCK_STREAM)

        self.server.bind((self.HOST, self.server_port[server_id]['port']))
        self.server.listen(5)
        self.log = []

        self.listener = socket(AF_INET, SOCK_DGRAM)
        self.listener.bind((self.HOST, self.server_port[server_id]['server_port']))

        self.CommitIndex = 0
        self.LastApplied = 0
        self.server_id = server_id
        self.current_term = 0
        self.timeout = 3
        self.heart_beat = 0.1
        self.role = 'follower'
        self.election_timeout = random.uniform(self.timeout, 2 * self.timeout)
        self.nextIndices = {}

        # become candidate after timeout

        self.election_log = {}
        self.vote_log = {}

        # if self.role != 'leader':
        print(self.election_timeout)

        self.election_timer = Timer(self.election_timeout, self.start_election)
        self.election_timer.daemon = True
        self.election_timer.start()
        # else:
        #      self.election_timer = None

        Thread(target=self.start())
        # self.sendMessage('2', {'1':1})
        Thread(target=self.rec_msg())

        print('server running at ip: %s, port: %s' % (self.HOST, self.PORT))

    def start(self):
        print("Waiting for connection...")
        self.new_thread = Thread(target=self.accept_incoming_connections)
        self.new_thread.start()
        # self.new_thread.join()
        # self.server.close()

    # new_add
    def start_election(self):
        """
                start the election process
        """
        print('start election')
        self.role = 'candidate'
        self.leader_id = None
        self.resetElectionTimeout()
        self.current_term += 1
        self.votes = [self.server_id]
        # self.voted_for = self.server_id
        self.election_log[self.current_term] = self.votes
        self.vote_log[self.current_term] = self.server_id

        # dictobj = {'current_term': self.current_term, 'voted_for': self.voted_for}
        print('become candidate for term {}'.format(self.current_term))

        # handle the case where only one server is left
        if not self.isLeader() and self.enoughForLeader():
            self.becomeLeader()
            return
        # send RequestVote to all other servers
        # (index & term of last log entry)
        self.requestVote()

    def rec_msg(self):
        print('rec msg')
        while True:
            msg, address = self.listener.recvfrom(4096)
            msg = json.loads(msg)
            self.handleIncommingMessage(msg)

    # new_add
    def handleIncommingMessage(self, msg):
        # handle incomming messages
        # Message types:
        # messages from servers
        # 1. requestVote RPC
        msg_type = msg['Command']
        if msg_type == 'REQ_VOTE':
            self.handleRequestVote(msg)
        # 2. requestVoteReply RPC
        elif msg_type == 'REQ_VOTE_REPLY':
            self.handleRequestVoteReply(msg)
        elif msg_type == 'ClientRequest':
            self.handelClientRequest(msg)

    def handelClientRequest(self, msg):
        term = msg['current_term']
        if term<self.current_term:
            pass
            # self.clientRequestReply(msg, False)
        serverId = msg['server_id']
        self.nextIndices[serverId] = msg['CommitIndex']
        self.log.append(msg['Entries'])

    def clientRequestReply(self, msg, answer):
        # answer_msg = {'Command':}
        # self.sendMessage(msg['server_id'], )
        pass

    # new_add
    def requestVote(self):
        # broadcast the request Vote message to all other datacenters
        message = {'Command': 'REQ_VOTE', 'ServerId': self.server_id, 'current_term': self.current_term}
        for server_id in self.server_port:
            if server_id != self.server_id:
                self.sendMessage(server_id, message)

        # delay
        # Timer(CONFIG['messageDelay'], sendMsg).start()

    # new_add
    def handleRequestVote(self, msg):
        """
        Handle incoming requestVote message
        :type candidate_id: str
        :type candidate_term: int
        :type candidate_log_term: int
        :type candidate_log_index: int
        """
        candidate_term = msg['current_term']
        candidate_id = msg['ServerId']

        if candidate_term < self.current_term:
            self.requestVoteReply(candidate_id, False)
            return

        self.current_term = max(candidate_term, self.current_term)
        grant_vote = False
        if candidate_id not in self.vote_log:
            # self.stepDown()
            self.role = 'follower'
            self.vote_log[self.current_term] = candidate_id
            print('voted for DC-{} in term {}'.format(candidate_id, self.current_term))
            grant_vote = True

        self.requestVoteReply(candidate_id, grant_vote)

    def handleRequestVoteReply(self, msg):
        """
        handle the reply from requestVote RPC
        :type follower_id: str
        :type follower_term: int
        :type vote_granted: bool
        """

        follower_id = msg['server_id']
        follower_term = msg['current_term']
        vote_granted = msg['Decision']

        if vote_granted:
            self.votes.append(follower_id)
            self.election_log[self.current_term] = self.votes
            print('get another vote in term {}, votes got: {}'.format(self.current_term, self.votes))

            if not self.isLeader() and self.enoughForLeader():
                self.becomeLeader()
        else:
            if follower_term > self.current_term:
                self.current_term = follower_term
                dictobj = {'current_term': self.current_term, 'voted_for': self.voted_for, 'log': self.log}
                filename = "./state" + self.datacenter_id + '.pkl'
                fileobj = open(filename, 'wb')
                pickle.dump(dictobj, fileobj)
                fileobj.close()
                self.stepDown()

    def becomeLeader(self):
        """
        do things to be done as a leader
        """
        print('become leader for term {}'.format(self.current_term))

        # no need to wait for heartbeat anymore
        self.election_timer.cancel()

        self.role = 'leader'
        self.leader_id = self.server_id
        # keep track of the entries known to be logged in each data center
        # note that when we are in the transition phase
        # we as the leader need to keep track of nodes in
        # the old and the new config
        # self.loggedIndices = dict([(center_id, 0)
        #                            for center_id in self.getAllCenterID()
        #                            if center_id != self.datacenter_id])
        # initialize a record of nextIdx
        # self.nextIndices = dict([(center_id, self.getLatest()[1]+1)
        #                          for center_id in self.getAllCenterID()
        #                          if center_id != self.datacenter_id])
        print('send heartbeat')

        self.sendHeartbeat()
        self.heartbeat_timer = Timer(self.heartbeat_timeout, self.sendHeartbeat)
        self.heartbeat_timer.daemon = True
        self.heartbeat_timer.start()

    def sendHeartbeat(self, ignore_last=False):
        """
        Send heartbeat message to all pears in the latest configuration
        if the latest is a new configuration that is not committed
        go to the join configuration instead
        :type ignore_last: bool
              - this is used for the broadcast immediately after a new
              config is committed. We need to send not only to sites
              in the newly committed config, but also to the old ones
        """

        for server_id in self.server_port:
            if server_id != self.server_id:
                self.sendAppendEntry(server_id)

        self.resetHeartbeatTimeout()

    def sendAppendEntry(self, server_id):
        """
        send an append entry message to the specified datacenter
        :type center_id: str
        """
        prevEntry = self.log[self.nextIndices[server_id] - 1]
        self.server.appendEntry(center_id, self.current_term,
                                prevEntry.index, prevEntry.term,
                                self.log[self.nextIndices[center_id]:],
                                self.commit_idx)

    def enoughForLeader(self):
        """
        Given a list of servers who voted, find out whether it
        is enough to get a majority based on the current config
        :rtype: bool
        """
        return np.unique(np.array(self.votes)).shape[0] > self.num_nodes / 2

    def isLeader(self):
        """
        determine if the current server is the leader
        """
        return self.server_id == self.leader_id

    # new_add
    def requestVoteReply(self, target_id, grant_vote):
        # send reply to requestVote message
        message = {'Command': 'REQ_VOTE_REPLY', 'server_id': self.server_id, 'current_term': self.current_term,
                   'Decision': grant_vote}
        self.sendMessage(target_id, message)

    # Timer(CONFIG['messageDelay'], sendMsg).start()

    # new_add
    def sendMessage(self, server_id, message):
        """
        send a message to the target server
        should be a UDP packet, without gauranteed delivery
        :type target_meta: e.g. { "port": 12348 }
        :type message: str
        """
        message = json.dumps(message)
        peer_socket = socket(AF_INET, SOCK_DGRAM)
        port = self.server_port[server_id]['server_port']
        addr = (self.HOST, port)
        peer_socket.sendto(message.encode(), addr)

        # peer_socket.connect(addr)
        # self.all_socket[port].send(message)

    # new_add
    def resetElectionTimeout(self):
        """
        reset election timeout
        """
        if self.election_timer:
            self.election_timer.cancel()
        # need to restart election if the election failed
        print('reset ElectionTimeout')
        return
        self.election_timer = Timer(self.election_timeout, self.start_election())
        self.election_timer.daemon = True
        self.election_timer.start()

    def accept_incoming_connections(self):
        """Sets up handling for incoming clients."""
        while True:
            client, client_address = self.server.accept()
            self.clients_con.append(client)
            print("%s:%s has connected." % client_address)
            client.send(bytes("Welcome! Type your username and press enter to continue.", "utf8"))
            self.addresses[client] = client_address
            Thread(target=self.handle_client, args=(client,)).start()


    def rec_client(self, client, msg):
        # CurrentTerm, LeaderId, PrevLogIndex, PrevLogTerm, Entries, LeaderCommit
        entry = {'Command': 'ClientRequest', 'current_term': self.current_term, 'LeaderId': self.leader_id,
                 'Entries': msg, 'CommitIndex': self.CommitIndex, 'LastApplied':self.LastApplied, 'server_id': self.server_id}
        self.log.append(entry)
        self.CommitIndex += 1
        if self.server_id != self.leader_id:
            self.sendMessage(self.leader_id, entry)
        else:
            self.AppendEntries(msg)



    def handle_client(self, client):  # Takes client socket as argument.
        """Handles a single client connection."""

        name = client.recv(self.BUFSIZ).decode("utf8")
        welcome = 'Welcome %s! If you want to quit, type {quit} to exit.' % name
        client.send(bytes(welcome, "utf8"))
        msg = "%s has joined the chat!" % name

        self.rec_client(client, msg)

        # TODO

        self.broadcast(msg, name)
        self.broadcast_client(msg)
        self.clients[client] = name

        while True:
            msg = client.recv(self.BUFSIZ)
            if msg != bytes("{quit}", "utf8"):
                msg = msg.decode('utf8')
                self.broadcast_client(msg)
                self.broadcast(msg, name + ": ")
            else:
                client.send(bytes("{quit}", "utf8"))
                client.close()
                del self.clients[client]
                del self.clients_con[client]
                self.broadcast("%s has left the chat." % name)
                break

    def broadcast(self, msg, name):  # prefix is for name identification.
        """Broadcasts a message to all the servers."""
        message = {'Command': 'Broadcast', 'msg': msg, 'name': name}
        for server_id in self.server_port:
            if server_id != self.server_id:
                print(message)
                self.sendMessage(server_id, message)

    def broadcast_client(self, msg, prefix=""):
        for sock in self.clients:
            sock.send(bytes(prefix, "utf8") + msg)


if __name__ == "__main__":
    server = Server(str(sys.argv[1]), int(sys.argv[2]))
    server.start()
